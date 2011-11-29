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
from twisted.internet.defer import inlineCallbacks
from twisted.python.runtime import platform

from txdav.caldav.datastore.util import migrateHome as migrateCalendarHome
from txdav.carddav.datastore.util import migrateHome as migrateAddressbookHome
from txdav.common.datastore.file import CommonDataStore as FileStore, TOPPATHS
from txdav.base.propertystore.xattr import PropertyStore as XattrPropertyStore
from txdav.base.propertystore.appledouble_xattr import (
    PropertyStore as AppleDoubleStore)

class UpgradeToDatabaseService(Service, LoggingMixIn, object):
    """
    Upgrade resources from a filesystem store to a database store.
    """

    @classmethod
    def wrapService(cls, path, service, store, uid=None, gid=None):
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
                    store, service, uid=uid, gid=gid,
                )
                return self
        return service


    def __init__(self, fileStore, sqlStore, service, uid=None, gid=None):
        """
        Initialize the service.
        """
        self.wrappedService = service
        self.fileStore = fileStore
        self.sqlStore = sqlStore
        self.uid = uid
        self.gid = gid


    @inlineCallbacks
    def doMigration(self):
        """
        Do the migration.  Called by C{startService}, but a different method
        because C{startService} should return C{None}, not a L{Deferred}.

        @return: a Deferred which fires when the migration is complete.
        """
        self.log_warn("Beginning filesystem -> database upgrade.")

        self.sqlStore.setMigrating(True)

        for homeType, migrateFunc, eachFunc, destFunc, _ignore_topPathName in [
            ("calendar", migrateCalendarHome,
                self.fileStore.eachCalendarHome,
                lambda txn: txn.calendarHomeWithUID,
                "calendars"),
            ("addressbook", migrateAddressbookHome,
                self.fileStore.eachAddressbookHome,
                lambda txn: txn.addressbookHomeWithUID,
                "addressbooks")
            ]:
            for fileTxn, fileHome in eachFunc():
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
                    continue
                sqlHome = yield homeGetter(uid, create=True)
                if sqlHome is None:
                    raise RuntimeError("THIS SHOULD NOT BE POSSIBLE.")
                yield migrateFunc(fileHome, sqlHome)
                yield fileTxn.commit()
                yield sqlTxn.commit()
                # FIXME: need a public remove...HomeWithUID() for de-
                # provisioning

                # Remove file home after migration
                fileHome._path.remove()
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
        self.log_warn(
            "Filesystem upgrade complete, launching database service."
        )

        # see http://twistedmatrix.com/trac/ticket/4649
        reactor.callLater(0, self.wrappedService.setServiceParent, self.parent)


    def startService(self):
        """
        Start the service.
        """
        self.doMigration()
