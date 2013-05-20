# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
Upgrade to deal with normalization of UUIDs in
CALENDAR_HOME/ADDRESSBOOK_HOME/NOTIFICATION/APN_SUBSCRIPTIONS tables, as well
as in calendar data and properties.
"""

from txdav.common.datastore.sql import fixUUIDNormalization
from twisted.internet.defer import inlineCallbacks
from txdav.common.datastore.upgrade.sql.upgrades.util import updateCalendarDataVersion

UPGRADE_TO_VERSION = 3

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    Do the UUID-normalization upgrade if necessary and then bump the data
    version to indicate that it's been done.
    """
    yield fixUUIDNormalization(sqlStore)

    # Always bump the DB value
    yield updateCalendarDataVersion(
        sqlStore, UPGRADE_TO_VERSION
    )
