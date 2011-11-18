# -*- test-case-name: txdav.common.datastore.test -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Utilities, mostly related to upgrading, common to calendar and addresbook
data stores.
"""

import os
import re
import errno
import xattr

from twext.python.log import LoggingMixIn
from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python.modules import getModule
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
        self.sqlStore.setMigrating(True)

        self.log_warn("Beginning filesystem -> database upgrade.")
        for homeType, migrateFunc, eachFunc, destFunc, topPathName in [
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



class UpgradeDatabaseSchemaService(Service, LoggingMixIn, object):
    """
    Checks and upgrades the database schema. This assumes there are a bunch of
    upgrade files in sql syntax that we can execute against the database to
    accomplish the upgrade.

    @ivar sqlStore: The store to operate on.

    @type sqlStore: L{txdav.idav.IDataStore}

    @ivar wrappedService: Wrapped L{IService} that will be started after this
        L{UpgradeDatabaseSchemaService}'s work is done and the database schema
        of C{sqlStore} is fully upgraded.  This may also be specified as
        C{None}, in which case no service will be started.

    @type wrappedService: L{IService} or C{NoneType}
    """

    @classmethod
    def wrapService(cls, service, store, uid=None, gid=None):
        """
        Create an L{UpgradeDatabaseSchemaService} when starting the database
        so we can check the schema version and do any upgrades.

        @param service: the service to wrap.  This service should be started
            when the upgrade is complete.  (This is accomplished by returning
            it directly when no upgrade needs to be done, and by adding it to
            the service hierarchy when the upgrade completes; assuming that the
            service parent of the resulting service will be set to a
            L{MultiService} or similar.)

        @param store: the SQL storage service.

        @type store: L{txdav.idav.IDataStore}

        @type service: L{IService}

        @return: a service
        @rtype: L{IService}
        """
        return cls(store, service, uid=uid, gid=gid,)


    def __init__(self, sqlStore, service, uid=None, gid=None):
        """
        Initialize the service.
        """
        self.wrappedService = service
        self.sqlStore = sqlStore
        self.uid = uid
        self.gid = gid
        self.schemaLocation = getModule(__name__).filePath.sibling("sql_schema")


    @inlineCallbacks
    def doUpgrade(self):
        """
        Do the schema check and upgrade if needed.  Called by C{startService},
        but a different method because C{startService} should return C{None},
        not a L{Deferred}.

        @return: a Deferred which fires when the migration is complete.
        """
        self.log_warn("Beginning database schema check.")

        # Retrieve the version number from the schema file
        current_schema = self.schemaLocation.child("current.sql").getContent()
        found = re.search(
            "insert into CALENDARSERVER values \('VERSION', '(\d)+'\);",
            current_schema)
        if found is None:
            msg = (
                "Schema is missing required schema VERSION insert statement: %s"
                % (current_schema,)
            )
            self.log_error(msg)
            raise RuntimeError(msg)
        else:
            required_version = int(found.group(1))
            self.log_warn("Required schema version: %s." % (required_version,))

        # Get the schema version in the current database
        sqlTxn = self.sqlStore.newTransaction()
        dialect = sqlTxn.dialect
        try:
            actual_version = yield sqlTxn.schemaVersion()
            yield sqlTxn.commit()
        except RuntimeError:
            self.log_error("Database schema version cannot be determined.")
            yield sqlTxn.abort()
            raise

        self.log_warn("Actual schema version: %s." % (actual_version,))

        if required_version == actual_version:
            self.log_warn("Schema version check complete: no upgrade needed.")
        elif required_version < actual_version:
            msg = ("Actual schema version %s is more recent than the expected"
                   " version %s. The service cannot be started" %
                   (actual_version, required_version,))
            self.log_error(msg)
            raise RuntimeError(msg)
        else:
            yield self.upgradeVersion(actual_version, required_version, dialect)

        self.log_warn(
            "Database schema check complete, launching database service."
        )
        # see http://twistedmatrix.com/trac/ticket/4649
        if self.wrappedService is not None:
            reactor.callLater(0, self.wrappedService.setServiceParent,
                              self.parent)


    @inlineCallbacks
    def upgradeVersion(self, fromVersion, toVersion, dialect):
        """
        Update the database from one version to another (the current one). Do this by
        looking for upgrade_from_X_to_Y.sql files that cover the full range of upgrades.
        """

        self.log_warn("Starting schema upgrade from version %d to %d." % (fromVersion, toVersion,))
        
        # Scan for all possible upgrade files - returned sorted
        files = self.scanForUpgradeFiles(dialect)
        
        # Determine upgrade sequence and run each upgrade
        upgrades = self.determineUpgradeSequence(fromVersion, toVersion, files, dialect)

        # Use one transaction for the entire set of upgrades
        sqlTxn = self.sqlStore.newTransaction()
        try:
            for fp in upgrades:
                yield self.applyUpgrade(sqlTxn, fp)
            yield sqlTxn.commit()
        except RuntimeError:
            self.log_error("Database upgrade failed:" % (fp.basename(),))
            yield sqlTxn.abort()
            raise

        self.log_warn("Schema upgraded from version %d to %d." % (fromVersion, toVersion,))

    def scanForUpgradeFiles(self, dialect):
        """
        Scan the module path for upgrade files with the require name.
        """
        
        fp = self.schemaLocation.child("upgrades").child(dialect)
        upgrades = []
        regex = re.compile("upgrade_from_(\d)+_to_(\d)+.sql")
        for child in fp.globChildren("upgrade_*.sql"):
            matched = regex.match(child.basename())
            if matched is not None:
                fromV = int(matched.group(1))
                toV = int(matched.group(2))
                upgrades.append((fromV, toV, child))
        
        upgrades.sort(key=lambda x:(x[0], x[1]))
        return upgrades
    
    def determineUpgradeSequence(self, fromVersion, toVersion, files, dialect):
        """
        Determine the upgrade_from_X_to_Y.sql files that cover the full range of upgrades.
        Note that X and Y may not be consecutive, e.g., we might have an upgrade from 3 to 4,
        4 to 5, and 3 to 5 - the later because it is more efficient to jump over the intermediate
        step. As a result we will always try and pick the upgrade file that gives the biggest
        jump from one version to another at each step.
        """

        # Now find the path from the old version to the current one
        filesByFromVersion = {}
        for fromV, toV, fp in files:
            if fromV not in filesByFromVersion or filesByFromVersion[fromV][1] < toV:
                filesByFromVersion[fromV] = fromV, toV, fp
        
        upgrades = []
        nextVersion = fromVersion
        while nextVersion != toVersion:
            if nextVersion not in filesByFromVersion:
                msg = "Missing upgrade file from version %d with dialect %s" % (nextVersion, dialect,)
                self.log_error(msg)
                raise RuntimeError(msg)
            else:
                upgrades.append(filesByFromVersion[nextVersion][2])
                nextVersion = filesByFromVersion[nextVersion][1]
        
        return upgrades

    @inlineCallbacks
    def applyUpgrade(self, sqlTxn, fp):
        """
        Apply the schema upgrade .sql file to the database.
        """
        self.log_warn("Applying schema upgrade: %s" % (fp.basename(),))
        sql = fp.getContent()
        yield sqlTxn.execSQLBlock(sql)
        
    def startService(self):
        """
        Start the service.
        """
        self.doUpgrade()



