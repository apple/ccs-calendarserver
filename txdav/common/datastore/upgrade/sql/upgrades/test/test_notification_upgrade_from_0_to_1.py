##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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

from txdav.caldav.datastore.test.util import CommonStoreTests
from txdav.common.datastore.sql_tables import _BIND_STATUS_INVITED, \
    _BIND_MODE_WRITE, _BIND_STATUS_ACCEPTED, _BIND_MODE_READ
from txdav.common.datastore.upgrade.sql.upgrades.notification_upgrade_from_0_to_1 import doUpgrade

import json

"""
Tests for L{txdav.common.datastore.upgrade.sql.upgrade}.
"""

class Upgrade_from_0_to_1(CommonStoreTests):
    """
    Tests for notification upgrade.
    """

    @inlineCallbacks
    def test_upgrade_invite(self):

        data = (
            (
                "uid1",
                """<?xml version='1.0' encoding='UTF-8'?>
<CS:notification xmlns:CS='http://calendarserver.org/ns/'>
    <CS:invite-notification shared-type='calendar'/>
</CS:notification>
""",
                {
                    "notification-type": "invite-notification",
                    "shared-type": "calendar",
                },
                """<?xml version='1.0' encoding='UTF-8'?>
<notification xmlns='http://calendarserver.org/ns/'>
  <dtstamp>20131113T153109Z</dtstamp>
  <invite-notification shared-type='calendar'>
    <uid>uid1</uid>
    <href xmlns='DAV:'>urn:uuid:user02</href>
    <invite-noresponse/>
    <access>
      <read-write/>
    </access>
    <hosturl>
      <href xmlns='DAV:'>/calendars/__uids__/user01/calendar</href>
    </hosturl>
    <organizer>
      <href xmlns='DAV:'>urn:uuid:user01</href>
      <common-name>User 01</common-name>
    </organizer>
    <summary>Shared</summary>
    <supported-calendar-component-set xmlns='urn:ietf:params:xml:ns:caldav'>
      <comp name='VEVENT'/>
      <comp name='VTODO'/>
    </supported-calendar-component-set>
  </invite-notification>
</notification>
""",
                {
                    "notification-type": "invite-notification",
                    "shared-type": "calendar",
                    "dtstamp": "20131113T153109Z",
                    "owner": "user01",
                    "sharee": "user02",
                    "uid": "uid1",
                    "status": _BIND_STATUS_INVITED,
                    "access": _BIND_MODE_WRITE,
                    "name": "calendar",
                    "summary": "Shared",
                    "supported-components": "VEVENT,VTODO",
                },
            ),
            (
                "uid2",
                """<?xml version='1.0' encoding='UTF-8'?>
<CS:notification xmlns:CS='http://calendarserver.org/ns/'>
    <CS:invite-notification shared-type='addressbook'/>
</CS:notification>
""",
                {
                    "notification-type": "invite-notification",
                    "shared-type": "addressbook",
                },
                """<?xml version='1.0' encoding='UTF-8'?>
<notification xmlns='http://calendarserver.org/ns/'>
  <dtstamp>20131113T153110Z</dtstamp>
  <invite-notification shared-type='addressbook'>
    <uid>uid2</uid>
    <href xmlns='DAV:'>/principals/users/user02/</href>
    <invite-accepted/>
    <access>
      <read/>
    </access>
    <hosturl>
      <href xmlns='DAV:'>/addressbooks/__uids__/user01/addressbook/</href>
    </hosturl>
    <organizer>
      <href xmlns='DAV:'>/principals/users/user01/</href>
      <common-name>User 01</common-name>
    </organizer>
    <summary>Shared 2</summary>
  </invite-notification>
</notification>
""",
                {
                    "notification-type": "invite-notification",
                    "shared-type": "addressbook",
                    "dtstamp": "20131113T153110Z",
                    "owner": "user01",
                    "sharee": "user02",
                    "uid": "uid2",
                    "status": _BIND_STATUS_ACCEPTED,
                    "access": _BIND_MODE_READ,
                    "name": "addressbook",
                    "summary": "Shared 2",
                },
            ),
            (
                "uid3",
                """<?xml version='1.0' encoding='UTF-8'?>
<CS:notification xmlns:CS='http://calendarserver.org/ns/'>
    <CS:invite-reply/>
</CS:notification>
""",
                {
                    "notification-type": "invite-reply",
                },
                """<?xml version='1.0' encoding='UTF-8'?>
<notification xmlns='http://calendarserver.org/ns/'>
  <dtstamp>20131113T153111Z</dtstamp>
  <invite-reply shared-type='calendar'>
    <href xmlns='DAV:'>mailto:user02@example.com</href>
    <invite-accepted/>
    <hosturl>
      <href xmlns='DAV:'>/calendars/__uids__/user01/calendar</href>
    </hosturl>
    <in-reply-to>uid1</in-reply-to>
  </invite-reply>
</notification>
""",
                {
                    "notification-type": "invite-reply",
                    "shared-type": "calendar",
                    "dtstamp": "20131113T153111Z",
                    "owner": "user01",
                    "sharee": "user02",
                    "status": _BIND_STATUS_ACCEPTED,
                    "name": "calendar",
                    "in-reply-to": "uid1",
                    "summary": "",
                },
            ),
        )

        for uid, xmltype, _ignore_jtype, xmldata, _ignore_jdata in data:
            notifications = yield self.transactionUnderTest().notificationsWithUID("user01")
            yield notifications.writeNotificationObject(uid, xmltype, xmldata)

        # Force data version to previous
        nh = notifications._homeSchema
        yield Update(
            {nh.DATAVERSION: 0},
            Where=None,
        ).on(self.transactionUnderTest())

        yield self.commit()
        yield doUpgrade(self._sqlCalendarStore)

        notifications = yield self.transactionUnderTest().notificationsWithUID("user01")
        version = (yield notifications.dataVersion())
        self.assertEqual(version, 1)

        for uid, _ignore_xmltype, jtype, _ignore_xmldata, jdata in data:
            notification = (yield notifications.notificationObjectWithUID(uid))
            self.assertTrue(notification is not None, msg="Failed {uid}".format(uid=uid))
            self.assertEqual(json.loads(notification.xmlType()), jtype, msg="Failed {uid}".format(uid=uid))
            data = (yield notification.xmldata())
            self.assertEqual(json.loads(data), jdata, msg="Failed {uid}".format(uid=uid))
