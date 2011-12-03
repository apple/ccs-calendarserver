# -*- test-case-name: txdav.common.datastore.upgrade.test.test_migrate -*-
##
# Copyright (c) 2011 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

"""
Migrating from file store to sql store.
"""

import os
import errno
import xattr

from twext.python.log import LoggingMixIn

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import maybeDeferred, DeferredList
from twisted.python.runtime import platform

from twext.python.filepath import CachingFilePath
from twext.internet.spawnsvc import SpawnerService

from twisted.protocols.amp import AMP, Command, String

from txdav.caldav.datastore.util import migrateHome as migrateCalendarHome
from txdav.carddav.datastore.util import migrateHome as migrateAddressbookHome
from txdav.common.datastore.file import CommonDataStore as FileStore, TOPPATHS
from txdav.base.propertystore.xattr import PropertyStore as XattrPropertyStore
from txdav.base.propertystore.appledouble_xattr import (PropertyStore
                                                        as AppleDoubleStore)


homeTypeLookup = {
    "calendar": (migrateCalendarHome,
                 lambda txn: txn.calendarHomeWithUID),
    "addressbook": (migrateAddressbookHome,
                    lambda txn: txn.addressbookHomeWithUID)
}


def swapAMP(oldAMP, newAMP):
    """
    Swap delivery of messages from an old L{AMP} instance to a new one.

    This is useful for implementors of L{StoreSpawnerService} since they will
    typically want to create one protocol for initializing the store, and
    another for processing application commands.

    @param oldAMP: An AMP instance currently hooked up to a transport, whose
        job is done and wants to stop receiving messages.

    @param newAMP: An AMP instance who wants to take over and start receiving
        messages previously destined for oldAMP.

    @return: C{newAMP}
    """
    oldAMP.boxReceiver = newAMP
    newAMP.startReceivingBoxes(oldAMP)
    return newAMP



class StoreSpawnerService(SpawnerService):
    """
    Abstract subclass of L{SpawnerService} that describes how to spawn a subclass.
    """

    def spawnWithStore(self, here, there):
        """
        Like L{SpawnerService.spawn}, but instead of instantiating C{there}
        with 0 arguments, it instantiates it with an L{ICalendarStore} /
        L{IAddressbookStore}.
        """
        raise NotImplementedError("subclasses must implement the specifics")



class Configure(Command):
    """
    Configure the upgrade helper process.
    """

    arguments = [("filename", String())]


    
class OneUpgrade(Command):
    """
    Upgrade a single calendar home.
    """

    arguments = [("uid", String()),
                 ("homeType", String())]



class LogIt(Command):
    """
    Log a message.
    """
    arguments = [("message", String())]



class UpgradeDriver(AMP):
    """
    Helper protocol which runs in the master process doing the upgrade.
    """

    def __init__(self, upgradeService):
        super(UpgradeDriver, self).__init__()
        self.service = upgradeService


    def configure(self, filename):
        """
        Configure the subprocess to examine the file store at the given path
        name.
        """
        return self.callRemote(Configure, filename=filename)


    def oneUpgrade(self, uid, homeType):
        """
        Upgrade one calendar or addressbook home, with the given uid of the
        given type, and return a L{Deferred} which will fire when the upgrade
        is complete.
        """
        return self.callRemote(OneUpgrade, uid=uid, homeType=homeType)



class UpgradeHelperProcess(AMP):
    """
    Helper protocol which runs in a subprocess to upgrade.
    """

    def __init__(self, store):
        """
        
        """
        super(UpgradeHelperProcess, self).__init__()
        self.store = store
        self.store.setMigrating(True)
        

    @Configure.responder
    def configure(self, filename):
        subsvc = None
        self.upgrader = UpgradeToDatabaseService.wrapService(
            CachingFilePath(filename), subsvc, self.store
        )
        return {}

        # This stuff needs to be done by somebody in caldavd.py
        from twistedcaldav.config import config
        from calendarserver.tap.util import getDBPool, storeFromConfig
        config.load(filename)
        pool, txnf = getDBPool(config)
        if pool is not None:
            pool.startService()
            reactor.addSystemEventTrigger("before", "shutdown",
                                          pool.stopService)
        # XXX: SharedConnectionPool needs to be relayed out of band, as
        # calendarserver.tap.caldav does with its own thing.
        dbstore = storeFromConfig(config, txnf)
        dbstore.setMigrating(True)
        return {}


    @OneUpgrade.responder
    def oneUpgrade(self, uid, homeType):
        """
        Upgrade one calendar home.
        """
        migrateFunc, destFunc = homeTypeLookup[homeType]
        fileTxn = self.upgrader.fileStore.newTransaction()
        return (
            maybeDeferred(destFunc(fileTxn), uid)
            .addCallback(
                lambda fileHome:
                self.upgrader.migrateOneHome(fileTxn, homeType, fileHome)
            )
            .addCallback(lambda ignored: {})
        )



class UpgradeToDatabaseService(Service, LoggingMixIn, object):
    """
    Upgrade resources from a filesystem store to a database store.
    """

    @classmethod
    def wrapService(cls, path, service, store, uid=None, gid=None,
                    parallel=0, spawner=None):
        """
        Create an L{UpgradeToDatabaseService} if there are still file-based
        calendar or addressbook homes remaining in the given path.

        @param path: a path pointing at the document root, where the file-based
            data-store is located.
        @type path: L{CachingFilePath}

        @param service: the service to wrap.  This service should be started
            when the upgrade is complete.  (This is accomplished by returning
            it directly when no upgrade needs to be done, and by adding it to
            the service hierarchy when the upgrade completes; assuming that the
            service parent of the resulting service will be set to a
            L{MultiService} or similar.)

        @param store: the SQL storage service.

        @type service: L{IService}

        @param parallel: The number of parallel subprocesses that should manage
            the upgrade.

        @param spawner: a concrete L{StoreSpawnerService} subclass that will be
            used to spawn helper processes.

        @return: a service
        @rtype: L{IService}
        """
        # TODO: TOPPATHS should be computed based on enabled flags in 'store',
        # not hard coded.
        for homeType in TOPPATHS:
            if path.child(homeType).exists():
                if platform.isMacOSX():
                    appropriateStoreClass = XattrPropertyStore
                else:
                    attrs = xattr.xattr(path.path)
                    try:
                        attrs.get('user.should-not-be-set')
                    except IOError, ioe:
                        if ioe.errno == errno.ENODATA:
                            # xattrs are supported and enabled on the filesystem
                            # where the calendar data lives.  this takes some
                            # doing (you have to edit fstab), so this means
                            # we're trying to migrate some 2.x data from a
                            # previous linux installation.
                            appropriateStoreClass = XattrPropertyStore
                        elif ioe.errno == errno.EOPNOTSUPP:
                            # The operation wasn't supported.  This is what will
                            # usually happen on a naively configured filesystem,
                            # so this means we're most likely trying to migrate
                            # some data from an untarred archive created on an
                            # OS X installation using xattrs.
                            appropriateStoreClass = AppleDoubleStore
                        else:
                            # No need to check for ENOENT and the like; we just
                            # checked above to make sure the parent exists.
                            # Other errors are not anticipated here, so fail
                            # fast.
                            raise

                    appropriateStoreClass = AppleDoubleStore

                self = cls(
                    FileStore(path, None, True, True,
                              propertyStoreClass=appropriateStoreClass),
                    store, service, uid=uid, gid=gid, spawner=spawner
                )
                return self
        return service


    def __init__(self, fileStore, sqlStore, service, uid=None, gid=None,
                 parallel=0, spawner=None):
        """
        Initialize the service.
        """
        self.wrappedService = service
        self.fileStore = fileStore
        self.sqlStore = sqlStore
        self.uid = uid
        self.gid = gid
        self.parallel = parallel
        self.spawner = spawner


    @inlineCallbacks
    def migrateOneHome(self, fileTxn, homeType, fileHome):
        """
        Migrate an individual calendar or addressbook home.
        """
        migrateFunc, destFunc = homeTypeLookup.get(homeType)
        uid = fileHome.uid()
        self.log_warn("Migrating %s UID %r" % (homeType, uid))
        sqlTxn = self.sqlStore.newTransaction()
        homeGetter = destFunc(sqlTxn)
        if (yield homeGetter(uid, create=False)) is not None:
            self.log_warn(
                "%s home %r already existed not migrating" % (
                    homeType, uid))
            yield sqlTxn.abort()
            yield fileTxn.commit()
            returnValue(None)
        sqlHome = yield homeGetter(uid, create=True)
        yield migrateFunc(fileHome, sqlHome)
        yield fileTxn.commit()
        yield sqlTxn.commit()
        # Remove file home after migration. FIXME: instead, this should be a
        # public remove...HomeWithUID() API for de-provisioning.  (If we had
        # this, this would simply be a store-to-store migrator rather than a
        # filesystem-to-database upgrade.)
        fileHome._path.remove()


    @inlineCallbacks
    def doMigration(self):
        """
        Do the migration.  Called by C{startService}, but a different method
        because C{startService} should return C{None}, not a L{Deferred}.

        @return: a Deferred which fires when the migration is complete.
        """
        self.sqlStore.setMigrating(True)
        parallel = self.parallel
        if parallel:
            self.log_warn("Starting upgrade helper processes.")
            spawner = self.spawner
            spawner.startService()
            drivers = []
            for value in xrange(parallel):
                driver = yield spawner.spawnWithStore(UpgradeDriver(self),
                                                      UpgradeHelperProcess)
                drivers.append(driver)

            # Wait for all subprocesses to be fully configured before
            # continuing, but let them configure in any order.
            self.log_warn("Configuring upgrade helper processes.")
            yield DeferredList([driver.configure(self.fileStore._path.path)
                                for driver in drivers])
            self.log_warn("Upgrade helpers ready.")

        self.log_warn("Beginning filesystem -> database upgrade.")
        inParallel = []
        for homeType, eachFunc in [
                ("calendar", self.fileStore.eachCalendarHome),
                ("addressbook", self.fileStore.eachAddressbookHome),
            ]:
            for fileTxn, fileHome in eachFunc():
                uid = fileHome.uid()
                self.log_warn("Migrating %s UID %r" % (homeType, uid))
                if parallel:
                    # No-op transaction here: make sure everything's unlocked
                    # before asking the subprocess to handle it.
                    yield fileTxn.commit()
                    if not drivers:
                        # All the subprocesses are currently busy processing an
                        # upgrade.  Wait for one to become available.
                        yield DeferredList(inParallel, fireOnOneCallback=True,
                                           fireOnOneErrback=True)
                    busy = drivers.pop(0)
                    d = busy.oneUpgrade(fileHome.uid(), homeType)
                    inParallel.append(d)
                    def freeUp(result, d=d, busy=busy):
                        inParallel.remove(d)
                        drivers.append(busy)
                        return result
                    d.addBoth(freeUp)
                else:
                    yield self.migrateOneHome(fileTxn, homeType, fileHome)

        if inParallel:
            yield DeferredList(inParallel)

        for homeType in TOPPATHS:
            homesPath = self.fileStore._path.child(homeType)
            if homesPath.isdir():
                homesPath.remove()

        # Set attachment directory ownership.  FIXME: is this still necessary
        # since attachments started living outside the database directory
        # created by initdb?  default permissions might be correct now.
        sqlAttachmentsPath = self.sqlStore.attachmentsPath
        if (sqlAttachmentsPath and sqlAttachmentsPath.exists() and
            (self.uid or self.gid)):
            uid = self.uid or -1
            gid = self.gid or -1
            for fp in sqlAttachmentsPath.walk():
                os.chown(fp.path, uid, gid)

        self.sqlStore.setMigrating(False)

        if parallel:
            self.log_warn("Stopping upgrade helper processes.")
            yield spawner.stopService()
            self.log_warn("Upgrade helpers all stopped.")
        self.log_warn(
            "Filesystem upgrade complete, launching database service."
        )
        wrapped = self.wrappedService
        if wrapped is not None:
            # see http://twistedmatrix.com/trac/ticket/4649
            reactor.callLater(0, wrapped.setServiceParent, self.parent)


    def startService(self):
        """
        Start the service.
        """
        self.doMigration()
