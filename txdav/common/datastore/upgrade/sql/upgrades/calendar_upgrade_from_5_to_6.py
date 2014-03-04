# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Update

from twisted.internet.defer import inlineCallbacks

from txdav.common.datastore.sql_tables import schema, _BIND_MODE_OWN, \
    _TRANSP_TRANSPARENT
from txdav.common.datastore.upgrade.sql.upgrades.util import updateCalendarDataVersion, \
    updateAllCalendarHomeDataVersions

"""
Data upgrade from database version 5 to 6
"""

UPGRADE_TO_VERSION = 6

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    Do the required upgrade steps.
    """

    sqlTxn = sqlStore.newTransaction()
    cb = schema.CALENDAR_BIND

    # Fix shared calendar alarms which should default to "empty"
    yield Update(
        {
            cb.ALARM_VEVENT_TIMED: "empty",
            cb.ALARM_VEVENT_ALLDAY: "empty",
            cb.ALARM_VTODO_TIMED: "empty",
            cb.ALARM_VTODO_ALLDAY: "empty",
        },
        Where=(cb.BIND_MODE != _BIND_MODE_OWN)
    ).on(sqlTxn)

    # Fix inbox transparency which should always be True
    yield Update(
        {
            cb.TRANSP: _TRANSP_TRANSPARENT,
        },
        Where=(cb.CALENDAR_RESOURCE_NAME == "inbox")
    ).on(sqlTxn)
    yield sqlTxn.commit()

    # Always bump the DB value
    yield updateAllCalendarHomeDataVersions(sqlStore, UPGRADE_TO_VERSION)
    yield updateCalendarDataVersion(sqlStore, UPGRADE_TO_VERSION)
