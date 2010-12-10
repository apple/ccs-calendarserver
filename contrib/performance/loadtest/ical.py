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

from operator import getitem

from xml.etree import ElementTree
ElementTree.QName.__repr__ = lambda self: '<QName %r>' % (self.text,)

from twisted.python.log import err
from twisted.python.filepath import FilePath
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
from twisted.web.http_headers import Headers
from twisted.web.client import Agent

from protocol.webdav.propfindparser import PropFindParser
from protocol.webdav.definitions import davxml
from protocol.caldav.definitions import caldavxml
from protocol.caldav.definitions import csxml

from httpclient import StringProducer, readBody
from httpauth import AuthHandlerAgent

def loadRequestBody(label):
    return FilePath(__file__).sibling(label + '.request').getContent()


SUPPORTED_REPORT_SET = '{DAV:}supported-report-set'


class SnowLeopard(object):
    """
    Implementation of the SnowLeopard iCal network behavior.
    """

    CALENDAR_HOME_POLL_INTERVAL = 15

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


    def _parsePROPFINDResponse(self, response):
        """
        Construct a principal from the body a response to a
        I{PROPFIND} request for the principal URL.

        @type response: C{str}
        @rtype: C{cls}
        """
        parser = PropFindParser()
        parser.parseData(response)
        return parser.getResults()

    
    _CALENDAR_TYPES = set([
            caldavxml.calendar,
            caldavxml.schedule_inbox,
            caldavxml.schedule_outbox,
            csxml.notification,
            csxml.dropbox_home,
            ])
    def _extractCalendars(self, response):
        """
        Parse 
        """
        calendars = []
        principals = self._parsePROPFINDResponse(response)

        # XXX Here, it would be really great to somehow use
        # CalDAVClientLibrary.client.principal.CalDAVPrincipal.listCalendars
        for principal in principals:
            nodes = principals[principal].getNodeProperties()
            for nodeType in nodes[davxml.resourcetype].getchildren():
                if nodeType.tag in self._CALENDAR_TYPES:
                    calendars.append((nodeType.tag, principals[principal]))
                    break
        return sorted(calendars)


    def _principalPropfind(self, user):
        """
        Issue a PROPFIND on the likely principal URL for the given
        user and return a L{Principal} instance constructed from the
        response.
        """
        principalURL = '/principals/__uids__/' + user + '/'
        d = self._request(
            'PROPFIND',
            self.root + principalURL[1:],
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPAL_PROPFIND))
        d.addCallback(readBody)
        d.addCallback(self._parsePROPFINDResponse)
        d.addCallback(getitem, principalURL)
        return d


    def _principalsReport(self, principalCollectionSet):
        if principalCollectionSet.startswith('/'):
            principalCollectionSet = principalCollectionSet[1:]
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
        if calendarHomeSet.startswith('/'):
            calendarHomeSet = calendarHomeSet[1:]
        if not calendarHomeSet.endswith('/'):
            calendarHomeSet = calendarHomeSet + '/'
        d = self._request(
            'PROPFIND',
            self.root + calendarHomeSet,
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['1']}),
            StringProducer(self._STARTUP_CALENDARHOME_PROPFIND))
        d.addCallback(readBody)
        d.addCallback(self._parsePROPFINDResponse)
        def report(result):
            print result
        d.addCallback(report)
        return d


    def _notificationPropfind(self, notificationURL):
        if notificationURL.startswith('/'):
            notificationURL = notificationURL[1:]
        d = self._request(
            'PROPFIND',
            self.root + notificationURL,
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['1']}),
            StringProducer(self._STARTUP_NOTIFICATION_PROPFIND))
        d.addCallback(readBody)
        d.addCallback(self._extractCalendars)
        return d

    
    def _principalReport(self, principalURL):
        if principalURL.startswith('/'):
            principalURL = principalURL[1:]
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
    def startup(self):
        # Orient ourselves, or something
        principal = yield self._principalPropfind(self.user)
        hrefs = principal.getHrefProperties()

        # Do another kind of thing I guess
        principalCollection = hrefs[davxml.principal_collection_set].toString()
        print (yield self._principalsReport(principalCollection))

        # Whatever
        calendarHome = hrefs[caldavxml.calendar_home_set].toString()
        print (yield self._calendarHomePropfind(calendarHome))

        # Learn stuff I guess
        notificationURL = hrefs[csxml.notification_URL].toString()
        print (yield self._notificationPropfind(notificationURL))

        # More too
        principalURL = hrefs[davxml.principal_URL].toString()
        print (yield self._principalReport(principalURL))

        returnValue(principal)


    @inlineCallbacks
    def run(self):
        """
        Emulate a CalDAV client.
        """
        principal = yield self.startup()
        hrefs = principal.getHrefProperties()

        # Poll Calendar Home (and notifications?) every 15 (or
        # whatever) minutes
        pollCalendarHome = LoopingCall(
            self._calendarHomePropfind, 
            hrefs[caldavxml.calendar_home_set].toString())
        pollCalendarHome.start(self.CALENDAR_HOME_POLL_INTERVAL)

        yield Deferred()


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
