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

from twext.python.log import LoggingMixIn
from twisted.application.service import Service
from txdav.common.datastore.file import CommonDataStore as FileStore, TOPPATHS
from txdav.common.datastore.sql import CommonDataStore as SqlStore
from txdav.caldav.datastore.util import migrateHome as migrateCalendarHome
from txdav.carddav.datastore.util import migrateHome as migrateAddressbookHome
from twisted.internet.defer import inlineCallbacks
from twisted.internet import reactor


class UpgradeToDatabaseService(Service, LoggingMixIn, object):
    """
    Upgrade resources from a filesystem store to a database store.
    """


    @classmethod
    def wrapService(cls, path, service, connectionFactory, sqlAttachmentsPath):
        """
        Create an L{UpgradeToDatabaseService} if there are still file-based
        calendar or addressbook homes remaining in the given path.

        Maintenance note: we may want to pass a SQL store in directly rather
        than the combination of connection factory and attachments path, since
        there always must be a SQL store, but the path should remain a path
        because there may not I{be} a file-backed store present and we should
        not create it as a result of checking for it.

        @param path: a path pointing at the document root.
        @type path: L{CachingFilePath}

        @param service: the service to wrap.  This service should be started
            when the upgrade is complete.  (This is accomplished by returning
            it directly when no upgrade needs to be done, and by adding it to
            the service hierarchy when the upgrade completes; assuming that the
            service parent of the resulting service will be set to a
            L{MultiService} or similar.)

        @type service: L{IService}

        @return: a service
        @rtype: L{IService}
        """
        for homeType in TOPPATHS:
            if path.child(homeType).exists():
                self = cls(
                    FileStore(path, None, True, True),
                    SqlStore(connectionFactory, None, sqlAttachmentsPath,
                             True, True),
                    service
                )
                return self
        return service


    def __init__(self, fileStore, sqlStore, service):
        """
        Initialize the service.
        """
        self.wrappedService = service
        self.fileStore = fileStore
        self.sqlStore = sqlStore


    @inlineCallbacks
    def doMigration(self):
        """
        Do the migration.  Called by C{startService}, but a different method
        because C{startService} should return C{None}, not a L{Deferred}.

        @return: a Deferred which fires when the migration is complete.
        """
        self.log_warn("Beginning filesystem -> database upgrade.")
        for homeType, migrateFunc, eachFunc, destFunc in [
            ("calendar", migrateCalendarHome,
                self.fileStore.eachCalendarHome,
                lambda uid, txn: txn.calendarHomeWithUID(uid, create=True)),
            ("addressbook", migrateAddressbookHome, self.fileStore.eachAddressbookHome,
                lambda uid, txn: txn.addressbookHomeWithUID(uid, create=True))
            ]:
            for fileTxn, fileHome in eachFunc():
                uid = fileHome.uid()
                self.log_warn("Migrating %s UID %r" % (homeType, uid))
                sqlTxn = self.sqlStore.newTransaction()
                sqlHome = destFunc(uid, sqlTxn)
                yield migrateFunc(fileHome, sqlHome)
                fileTxn.commit()
                sqlTxn.commit()
                # FIXME: need a public remove...HomeWithUID() for de-
                # provisioning
                storePath = self.fileStore._path
                fromParent = fileHome._path.segmentsFrom(storePath)
                fromParent[0] += "-migrated"
                backupPath = storePath
                for segment in fromParent:
                    try:
                        backupPath.createDirectory()
                    except OSError:
                        pass
                    backupPath = backupPath.child(segment)
                fileHome._path.moveTo(backupPath)
        for homeType in TOPPATHS:
            homesPath = self.fileStore._path.child(homeType)
            if homesPath.isdir():
                homesPath.remove()
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



