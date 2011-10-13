# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2010-2011 Apple Inc. All rights reserved.
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
from twisted.python.reflect import namedObject

"""
Utilities, mostly related to upgrading, common to calendar and addresbook
data stores.
"""

import re

from twext.python.log import LoggingMixIn
from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python.modules import getModule

class UpgradeDatabaseSchemaService(Service, LoggingMixIn, object):
    """
    Checks and upgrades the database schema. This assumes there are a bunch of
    upgrade files in sql syntax that we can execute against the database to accomplish
    the upgrade.
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

        @return: a service
        @rtype: L{IService}
        """
        return cls(store, service, uid=uid, gid=gid,)


    def __init__(self, sqlStore, service, uid=None, gid=None):
        """
        Initialize the service.
        
        @param sqlStore: The store to operate on. Can be C{None} when doing unit tests.
        @param service:  Wrapped service. Can be C{None} when doing unit tests.
        """
        self.wrappedService = service
        self.sqlStore = sqlStore
        self.uid = uid
        self.gid = gid
        self.schemaLocation = getModule(__name__).filePath.parent().parent().sibling("sql_schema")
        self.pyLocation = getModule(__name__).filePath.parent()

    @inlineCallbacks
    def doUpgrade(self):
        """
        Do the schema check and upgrade if needed.  Called by C{startService}, but a different method
        because C{startService} should return C{None}, not a L{Deferred}.

        @return: a Deferred which fires when the migration is complete.
        """
        self.log_warn("Beginning database schema check.")
        
        # Retrieve the version number from the schema file
        current_schema = self.schemaLocation.child("current.sql").getContent()
        found = re.search("insert into CALENDARSERVER values \('VERSION', '(\d)+'\);", current_schema)
        if found is None:
            msg = "Schema is missing required schema VERSION insert statement: %s" % (current_schema,)
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
            msg = "Actual schema version %s is more recent than the expected version %s. The service cannot be started" % (actual_version, required_version,)
            self.log_error(msg)
            raise RuntimeError(msg)
        else:
            yield self.upgradeVersion(actual_version, required_version, dialect)
            
        self.log_warn(
            "Database schema check complete, launching database service."
        )
        # see http://twistedmatrix.com/trac/ticket/4649
        if self.wrappedService is not None:
            reactor.callLater(0, self.wrappedService.setServiceParent, self.parent)

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
        
        doDataUpgrade = self.getDataUpgrade(fp)
        if doDataUpgrade is not None:
            yield doDataUpgrade(sqlTxn)

    def getDataUpgrade(self, fp):        
        # Also look for python module to execute
        check_name = self.pyLocation.child(fp.basename()[:-4] + ".py")
        if check_name.exists():
            try:
                module = getModule(__name__)
                module = ".".join(module.name.split(".")[:-1]) + "." + fp.basename()[:-4] + ".doUpgrade"
                doUpgrade = namedObject(module)
                self.log_warn("Applying data upgrade: %s" % (module,))
                return doUpgrade
            except ImportError:
                msg = "Failed data upgrade: %s" % (fp.basename()[:-4],)
                self.log_error(msg)
                raise RuntimeError(msg)
        else:
            self.log_warn("No data upgrade: %s" % (fp.basename()[:-4],))
            return None
        
    def startService(self):
        """
        Start the service.
        """
        self.doUpgrade()
