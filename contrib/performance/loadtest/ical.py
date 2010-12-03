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

from xml.etree import ElementTree, ElementPath

from twisted.python.log import err
from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks
from twisted.web.http_headers import Headers
from twisted.web.client import Agent

from httpclient import StringProducer, readBody
from httpauth import AuthHandlerAgent

def loadRequestBody(label):
    return FilePath(__file__).sibling(label + '.request').getContent()


class Principal(object):

    PRINCIPAL_COLLECTION_SET = '{DAV:}principal-collection-set'
    CALENDAR_HOME_SET = '{urn:ietf:params:xml:ns:caldav}calendar-home-set'
    SCHEDULE_INBOX_URL = '{urn:ietf:params:xml:ns:caldav}schedule-inbox-URL'
    SCHEDULE_OUTBOX_URL = '{urn:ietf:params:xml:ns:caldav}schedule-outbox-URL'
    DROPBOX_HOME_URL = '{http://calendarserver.org/ns/}dropbox-home-URL'
    NOTIFICATION_URL = '{http://calendarserver.org/ns/}notification-URL'
    DISPLAY_NAME = '{DAV:}displayname'
    PRINCIPAL_URL = '{DAV:}principal-URL'
    
    _singlePropertyNames = [
        PRINCIPAL_COLLECTION_SET,
        CALENDAR_HOME_SET,
        SCHEDULE_INBOX_URL,
        SCHEDULE_OUTBOX_URL,
        DROPBOX_HOME_URL,
        NOTIFICATION_URL,
        PRINCIPAL_URL,
        ]

    CALENDAR_USER_ADDRESS_SET = '{urn:ietf:params:xml:ns:caldav}calendar-user-address-set'
    SUPPORTED_REPORT_SET = '{DAV:}supported-report-set'

    _multiPropertyNames = [
        CALENDAR_USER_ADDRESS_SET, SUPPORTED_REPORT_SET]


    def __init__(self):
        self.properties = {}


    @classmethod
    def fromPROPFINDResponse(cls, response):
        """
        Construct a principal from the body a response to a
        I{PROPFIND} request for the principal URL.

        @type response: C{str}
        @rtype: C{cls}
        """
        principal = cls()

        document = ElementTree.fromstring(response)
        pattern = '{DAV:}response/{DAV:}propstat/{DAV:}prop/'

        name = ElementPath.find(document, pattern + cls.DISPLAY_NAME)
        if name is not None:
            principal.properties[cls.DISPLAY_NAME] = name.text

        for prop in cls._singlePropertyNames:
            href = ElementPath.find(document, pattern + prop + '/{DAV:}href')
            principal.properties[prop] = href.text

        for prop in cls._multiPropertyNames:
            hrefs = ElementPath.findall(document, pattern + prop + '/{DAV:}href')
            principal.properties[prop] = set(href.text for href in hrefs)

        reports = ElementPath.findall(
            document,
            pattern + cls.SUPPORTED_REPORT_SET +
            '/{DAV:}supported-report/{DAV:}report')
        supported = principal.properties[cls.SUPPORTED_REPORT_SET] = set()
        for report in reports:
            for which in report:
                supported.add(which.tag)

        return principal



class SnowLeopard(object):
    """
    Implementation of the SnowLeopard iCal network behavior.
    """

    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody('sl_startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody('sl_startup_principals_report')
    _STARTUP_CALENDARHOME_PROPFIND = loadRequestBody('sl_startup_calendarhome_propfind')
    _STARTUP_NOTIFICATION_PROPFIND = loadRequestBody('sl_startup_notification_propfind')
    _STARTUP_PRINCIPAL_REPORT = loadRequestBody('sl_startup_principal_report')

    def __init__(self, reactor, host, port, user, auth):
        self.reactor = reactor
        self.agent = AuthHandlerAgent(Agent(self.reactor), auth)
        self.root = 'http://%s:%d/' % (host, port)
        self.user = user


    def _request(self, method, url, headers, body):
        # XXX Do return code checking here.
        return self.agent.request(method, url, headers, body)

    
    def _principalPropfind(self, user):
        d = self._request(
            'PROPFIND',
            self.root + 'principals/__uids__/' + user + '/',
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPAL_PROPFIND))
        d.addCallback(readBody)
        d.addCallback(Principal.fromPROPFINDResponse)
        return d


    def _principalsReport(self, principalCollectionSet):
        d = self._request(
            'REPORT',
            self.root + principalCollectionSet,
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPALS_REPORT))
        d.addCallback(readBody)
        return d


    def _calendarHomePropfind(self, calendarHomeSet):
        d = self._request(
            'PROPFIND',
            self.root + calendarHomeSet,
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['1']}),
            StringProducer(self._STARTUP_CALENDARHOME_PROPFIND))
        d.addCallback(readBody)
        return d


    def _notificationPropfind(self, notificationURL):
        d = self._request(
            'PROPFIND',
            self.root + notificationURL,
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['1']}),
            StringProducer(self._STARTUP_NOTIFICATION_PROPFIND))
        d.addCallback(readBody)
        return d

    
    def _principalReport(self, principalURL):
        d = self._request(
            'REPORT',
            self.root + principalURL,
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPAL_REPORT))
        d.addCallback(readBody)
        return d


    @inlineCallbacks
    def run(self):
        """
        Emulate a CalDAV client.
        """
        # Orient ourselves, or something
        principal = yield self._principalPropfind(self.user)

        # Do another kind of thing I guess
        principalCollectionSet = principal.properties[
            principal.PRINCIPAL_COLLECTION_SET]
        print (yield self._principalsReport(principalCollectionSet))

        # Whatever
        calendarHome = principal.properties[
            principal.CALENDAR_HOME_SET]
        print (yield self._calendarHomePropfind(calendarHome))

        # Learn stuff I guess
        notificationURL = principal.properties[
            principal.NOTIFICATION_URL]
        print (yield self._notificationPropfind(notificationURL))

        # More too
        principalURL = principal.properties[
            principal.PRINCIPAL_URL]
        print (yield self._principalReport(principalURL))


def main():
    from urllib2 import HTTPDigestAuthHandler
    from twisted.internet import reactor
    auth = HTTPDigestAuthHandler()
    auth.add_password(
        realm="Test Realm",
        uri="http://127.0.0.1:8008/",
        user="user01",
        passwd="user01")
    client = SnowLeopard(reactor, '127.0.0.1', 8008, 'user01', auth)
    d = client.run()
    d.addErrback(err, "Snow Leopard client run() problem")
    d.addCallback(lambda ignored: reactor.stop())
    reactor.run()


if __name__ == '__main__':
    main()
