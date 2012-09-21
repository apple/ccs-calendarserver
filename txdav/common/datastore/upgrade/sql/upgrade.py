# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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

import re

from twext.python.log import LoggingMixIn

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.modules import getModule
from twisted.python.reflect import namedObject

class UpgradeDatabaseCoreService(Service, LoggingMixIn, object):
    """
    Base class for either schema or data upgrades on the database.

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

        @type service: L{IService}

        @type store: L{txdav.idav.IDataStore}

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
        self.schemaLocation = getModule(__name__).filePath.parent().parent().sibling("sql_schema")
        self.pyLocation = getModule(__name__).filePath.parent()
        
        self.versionKey = None
        self.versionDescriptor = ""
        self.upgradeFileSuffix = ""
        self.defaultKeyValue = None
        
    def startService(self):
        """
        Start the service.
        """
        self.databaseUpgrade()

    @inlineCallbacks
    def databaseUpgrade(self):
        """
        Do a database schema upgrade.
        """
        self.log_warn("Beginning database %s check." % (self.versionDescriptor,))
        
        # Retrieve information from schema and database
        dialect, required_version, actual_version = yield self.getVersions()

        if required_version == actual_version:
            self.log_warn("%s version check complete: no upgrade needed." % (self.versionDescriptor.capitalize(),))
        elif required_version < actual_version:
            msg = "Actual %s version %s is more recent than the expected version %s. The service cannot be started" % (
                self.versionDescriptor, actual_version, required_version,
            )
            self.log_error(msg)
            raise RuntimeError(msg)
        else:
            self.sqlStore.setUpgrading(True)
            yield self.upgradeVersion(actual_version, required_version, dialect)
            self.sqlStore.setUpgrading(False)
            
        self.log_warn("Database %s check complete." % (self.versionDescriptor,))

        # see http://twistedmatrix.com/trac/ticket/4649
        if self.wrappedService is not None:
            reactor.callLater(0, self.wrappedService.setServiceParent, self.parent)
    
    @inlineCallbacks
    def getVersions(self):
        """
        Extract the expected version from the database schema and get the actual version in the current
        database, along with the DB dialect.
        """

        # Retrieve the version number from the schema file
        current_schema = self.schemaLocation.child("current.sql").getContent()
        found = re.search("insert into CALENDARSERVER values \('%s', '(\d+)'\);" % (self.versionKey,), current_schema)
        if found is None:
            msg = "Schema is missing required database key %s insert statement: %s" % (self.versionKey, current_schema,)
            self.log_error(msg)
            raise RuntimeError(msg)
        else:
            required_version = int(found.group(1))
            self.log_warn("Required database key %s: %s." % (self.versionKey, required_version,))
        
        # Get the schema version in the current database
        sqlTxn = self.sqlStore.newTransaction()
        dialect = sqlTxn.dialect
        try:
            actual_version = yield sqlTxn.calendarserverValue(self.versionKey)
            actual_version = int(actual_version)
            yield sqlTxn.commit()
        except (RuntimeError, ValueError):
            self.log_error("Database key %s cannot be determined." % (self.versionKey,))
            yield sqlTxn.abort()
            if self.defaultKeyValue is None:
                raise
            else:
                actual_version = self.defaultKeyValue

        self.log_warn("Actual database key %s: %s." % (self.versionKey, actual_version,))

        returnValue((dialect, required_version, actual_version,))

    @inlineCallbacks
    def upgradeVersion(self, fromVersion, toVersion, dialect):
        """
        Update the database from one version to another (the current one). Do this by
        looking for upgrade_from_X_to_Y.sql files that cover the full range of upgrades.
        """

        self.log_warn("Starting %s upgrade from version %d to %d." % (self.versionDescriptor, fromVersion, toVersion,))
        
        # Scan for all possible upgrade files - returned sorted
        files = self.scanForUpgradeFiles(dialect)
        
        # Determine upgrade sequence and run each upgrade
        upgrades = self.determineUpgradeSequence(fromVersion, toVersion, files, dialect)

        # Use one transaction for the entire set of upgrades
        try:
            for fp in upgrades:
                yield self.applyUpgrade(fp)
        except RuntimeError:
            self.log_error("Database %s upgrade failed using: %s" % (self.versionDescriptor, fp.basename(),))
            raise

        self.log_warn("%s upgraded from version %d to %d." % (self.versionDescriptor.capitalize(), fromVersion, toVersion,))

    def getPathToUpgrades(self, dialect):
        """
        Return the path where appropriate upgrade files can be found. 
        """
        raise NotImplementedError

    def scanForUpgradeFiles(self, dialect):
        """
        Scan for upgrade files with the require name.
        """
        
        fp = self.getPathToUpgrades(dialect)
        upgrades = []
        regex = re.compile("upgrade_from_(\d+)_to_(\d+)%s" % (self.upgradeFileSuffix,))
        for child in fp.globChildren("upgrade_*%s" % (self.upgradeFileSuffix,)):
            matched = regex.match(child.basename())
            if matched is not None:
                fromV = int(matched.group(1))
                toV = int(matched.group(2))
                upgrades.append((fromV, toV, child))
        
        upgrades.sort(key=lambda x:(x[0], x[1]))
        return upgrades

    def determineUpgradeSequence(self, fromVersion, toVersion, files, dialect):
        """
        Determine the upgrade_from_X_to_Y(.sql|.py) files that cover the full range of upgrades.
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

    def applyUpgrade(self, fp):
        """
        Apply the supplied upgrade to the database. Always return an L{Deferred"
        """
        raise NotImplementedError
        
class UpgradeDatabaseSchemaService(UpgradeDatabaseCoreService):
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

    def __init__(self, sqlStore, service, uid=None, gid=None):
        """
        Initialize the service.
        
        @param sqlStore: The store to operate on. Can be C{None} when doing unit tests.
        @param service:  Wrapped service. Can be C{None} when doing unit tests.
        """
        super(UpgradeDatabaseSchemaService, self).__init__(sqlStore, service, uid, gid)
        
        self.versionKey = "VERSION"
        self.versionDescriptor = "schema"
        self.upgradeFileSuffix = ".sql"

    def getPathToUpgrades(self, dialect):
        return self.schemaLocation.child("upgrades").child(dialect)

    @inlineCallbacks
    def applyUpgrade(self, fp):
        """
        Apply the schema upgrade .sql file to the database.
        """
        self.log_warn("Applying schema upgrade: %s" % (fp.basename(),))
        sqlTxn = self.sqlStore.newTransaction()
        try:
            sql = fp.getContent()
            yield sqlTxn.execSQLBlock(sql)
            yield sqlTxn.commit()
        except RuntimeError:
            yield sqlTxn.abort()
            raise

class UpgradeDatabaseDataService(UpgradeDatabaseCoreService):
    """
    Checks and upgrades the database data. This assumes there are a bunch of
    upgrade python modules that we can execute against the database to
    accomplish the upgrade.

    @ivar sqlStore: The store to operate on.

    @type sqlStore: L{txdav.idav.IDataStore}

    @ivar wrappedService: Wrapped L{IService} that will be started after this
        L{UpgradeDatabaseSchemaService}'s work is done and the database schema
        of C{sqlStore} is fully upgraded.  This may also be specified as
        C{None}, in which case no service will be started.

    @type wrappedService: L{IService} or C{NoneType}
    """

    def __init__(self, sqlStore, service, uid=None, gid=None):
        """
        Initialize the service.
        
        @param sqlStore: The store to operate on. Can be C{None} when doing unit tests.
        @param service:  Wrapped service. Can be C{None} when doing unit tests.
        """
        super(UpgradeDatabaseDataService, self).__init__(sqlStore, service, uid, gid)
        
        self.versionKey = "CALENDAR-DATAVERSION"
        self.versionDescriptor = "data"
        self.upgradeFileSuffix = ".py"

    def getPathToUpgrades(self, dialect):
        return self.pyLocation.child("upgrades")

    @inlineCallbacks
    def applyUpgrade(self, fp):
        """
        Apply the data upgrade .py files to the database.
        """
        
        # Find the module function we need to execute
        try:
            module = getModule(__name__)
            module = ".".join(module.name.split(".")[:-1]) + ".upgrades." + fp.basename()[:-3] + ".doUpgrade"
            doUpgrade = namedObject(module)
        except ImportError:
            msg = "Failed data upgrade: %s" % (fp.basename()[:-4],)
            self.log_error(msg)
            raise RuntimeError(msg)

        self.log_warn("Applying data upgrade: %s" % (module,))
        yield doUpgrade(self.sqlStore)
