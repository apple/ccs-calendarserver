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
#
##

from twisted.trial.unittest import TestCase

from ical import Principal

PROPFIND_RESPONSE = """\
<?xml version='1.0' encoding='UTF-8'?>
<multistatus xmlns='DAV:'>
  <response>
    <href>/principals/__uids__/user01/</href>
    <propstat>
      <prop>
        <principal-collection-set>
          <href>/principals/</href>
        </principal-collection-set>
        <calendar-home-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01</href>
        </calendar-home-set>
        <calendar-user-address-set xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/principals/__uids__/user01/</href>
          <href xmlns='DAV:'>/principals/users/user01/</href>
        </calendar-user-address-set>
        <schedule-inbox-URL xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/inbox/</href>
        </schedule-inbox-URL>
        <schedule-outbox-URL xmlns='urn:ietf:params:xml:ns:caldav'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/outbox/</href>
        </schedule-outbox-URL>
        <dropbox-home-URL xmlns='http://calendarserver.org/ns/'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/dropbox/</href>
        </dropbox-home-URL>
        <notification-URL xmlns='http://calendarserver.org/ns/'>
          <href xmlns='DAV:'>/calendars/__uids__/user01/notification/</href>
        </notification-URL>
        <displayname>User 01</displayname>
        <principal-URL>
          <href>/principals/__uids__/user01/</href>
        </principal-URL>
        <supported-report-set>
          <supported-report>
            <report>
              <acl-principal-prop-set/>
            </report>
          </supported-report>
          <supported-report>
            <report>
              <principal-match/>
            </report>
          </supported-report>
          <supported-report>
            <report>
              <principal-property-search/>
            </report>
          </supported-report>
          <supported-report>
            <report>
              <expand-property/>
            </report>
          </supported-report>
        </supported-report-set>
      </prop>
      <status>HTTP/1.1 200 OK</status>
    </propstat>
    <propstat>
      <prop>
        <xmpp-uri xmlns='http://calendarserver.org/ns/'/>
      </prop>
      <status>HTTP/1.1 404 Not Found</status>
    </propstat>
  </response>
</multistatus>
"""


class PrincipalTests(TestCase):
    """
    Tests for L{Principal}, a class for representing "a distinct human
    or computational actor that initiates access to network
    resources." (U{http://tools.ietf.org/html/rfc4918})
    """
    def test_fromPROPFINDResponse(self):
        """
        L{Principal.fromPROPFINDResponse} accepts an XML document like
        the one returned from a I{PROPFIND /principals/__uids__/<uid>}
        and extracts all of the properties from it.
        """
        principal = Principal.fromPROPFINDResponse(PROPFIND_RESPONSE)
        self.assertEquals(
            principal.properties,
            {Principal.PRINCIPAL_COLLECTION_SET: '/principals/',
             Principal.CALENDAR_HOME_SET: '/calendars/__uids__/user01',
             Principal.CALENDAR_USER_ADDRESS_SET: set([
                    '/principals/__uids__/user01/',
                    '/principals/users/user01/',
                    ]),
             Principal.SCHEDULE_INBOX_URL: '/calendars/__uids__/user01/inbox/',
             Principal.SCHEDULE_OUTBOX_URL: '/calendars/__uids__/user01/outbox/',
             Principal.DROPBOX_HOME_URL: '/calendars/__uids__/user01/dropbox/',
             Principal.NOTIFICATION_URL: '/calendars/__uids__/user01/notification/',
             Principal.DISPLAY_NAME: 'User 01',
             Principal.PRINCIPAL_URL: '/principals/__uids__/user01/',
             Principal.SUPPORTED_REPORT_SET: set([
                        '{DAV:}acl-principal-prop-set',
                        '{DAV:}principal-match',
                        '{DAV:}principal-property-search',
                        '{DAV:}expand-property',
                        ]),
             })


class SnowLeopardTests(TestCase):
    """
    Tests for L{SnowLeopard}.
    """
    def test_findCalendars(self):
        """
        L{SnowLeopard._findCalendars} accepts a calendar home PROPFIND
        response body and returns a list of calendar identifiers
        extracted from it.
        """
        client = SnowLeopard(None, None, None, None)
        client._findCalendars()

