##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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

from twisted.web2.dav.fileop import rmdir
from twistedcaldav.config import config
from twistedcaldav.directory.calendaruserproxy import CalendarUserProxyDatabase
from twistedcaldav.log import Logger
import os

log = Logger()

class UpgradeTheServer(object):
    
    @staticmethod
    def doUpgrade():
        
        UpgradeTheServer._doPrincipalCollectionInMemoryUpgrade()
    
    @staticmethod
    def _doPrincipalCollectionInMemoryUpgrade():
        
        # Look for the /principals/ directory on disk
        old_principals = os.path.join(config.DocumentRoot, "principals")
        if os.path.exists(old_principals):
            # First move the proxy database and rename it
            UpgradeTheServer._doProxyDatabaseMoveUpgrade()
        
            # Now delete the on disk representation of principals
            rmdir(old_principals)
            log.info(
                "Removed the old principal directory at '%s'."
                % (old_principals,)
            )

    @staticmethod
    def _doProxyDatabaseMoveUpgrade():
        
        # See if the old DB is present
        old_db_path = os.path.join(config.DocumentRoot, "principals", CalendarUserProxyDatabase.dbOldFilename)
        if not os.path.exists(old_db_path):
            # Nothing to be done
            return
        
        # See if the new one is already present
        new_db_path = os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)
        if os.path.exists(new_db_path):
            # We have a problem - both the old and new ones exist. Stop the server from starting
            # up and alert the admin to this condition
            raise UpgradeError(
                "Upgrade Error: unable to move the old calendar user proxy database at '%s' to '%s' because the new database already exists."
                % (old_db_path, new_db_path,)
            )
        
        # Now move the old one to the new location
        try:
            os.rename(old_db_path, new_db_path)
        except Exception, e:
            raise UpgradeError(
                "Upgrade Error: unable to move the old calendar user proxy database at '%s' to '%s' due to %s."
                % (old_db_path, new_db_path, str(e))
            )
            
        log.info(
            "Moved the calendar user proxy database from '%s' to '%s'."
            % (old_db_path, new_db_path,)
        )

class UpgradeError(RuntimeError):
    """
    Generic upgrade error.
    """
    pass
