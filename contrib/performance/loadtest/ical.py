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
from pprint import pprint

from xml.etree import ElementTree
ElementTree.QName.__repr__ = lambda self: '<QName %r>' % (self.text,)

from twisted.python.log import err, msg
from twisted.python.filepath import FilePath
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
from twisted.web.http_headers import Headers
from twisted.web.http import OK, MULTI_STATUS
from twisted.web.client import Agent

from protocol.webdav.propfindparser import PropFindParser
from protocol.webdav.definitions import davxml
from protocol.caldav.definitions import caldavxml
from protocol.caldav.definitions import csxml

from httpclient import StringProducer, readBody
from httpauth import AuthHandlerAgent

def loadRequestBody(label):
    return FilePath(__file__).sibling('request-data').child(label + '.request').getContent()


SUPPORTED_REPORT_SET = '{DAV:}supported-report-set'


class Event(object):
    def __init__(self, url, etag):
        self.url = url
        self.etag = etag


class Calendar(object):
    def __init__(self, resourceType, name, url, ctag):
        self.resourceType = resourceType
        self.name = name
        self.url = url
        self.ctag = ctag



class SnowLeopard(object):
    """
    Implementation of the SnowLeopard iCal network behavior.
    """

    USER_AGENT = "DAVKit/4.0.3 (732); CalendarStore/4.0.3 (991); iCal/4.0.3 (1388); Mac OS X/10.6.4 (10F569)"

    CALENDAR_HOME_POLL_INTERVAL = 15 * 60

    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody('sl_startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody('sl_startup_principals_report')
    _STARTUP_CALENDARHOME_PROPFIND = loadRequestBody('sl_startup_calendarhome_propfind')
    _STARTUP_NOTIFICATION_PROPFIND = loadRequestBody('sl_startup_notification_propfind')
    _STARTUP_PRINCIPAL_REPORT = loadRequestBody('sl_startup_principal_report')

    _CALENDAR_PROPFIND = loadRequestBody('sl_calendar_propfind')
    _CALENDAR_REPORT = loadRequestBody('sl_calendar_report')


    def __init__(self, reactor, host, port, user, auth):
        self.reactor = reactor
        self.agent = AuthHandlerAgent(Agent(self.reactor), auth)
        self.root = 'http://%s:%d/' % (host, port)
        self.user = user

        # Keep track of the calendars on this account, keys are
        # Calendar URIs, values are Calendar instances.
        self._calendars = {}

        # Keep track of the events on this account, keys are event
        # URIs (which are unambiguous across different calendars
        # because they start with the uri of the calendar they are
        # part of), values are Event instances.
        self._events = {}


    def _request(self, expectedResponseCode, method, url, headers, body):
        headers.setRawHeaders('User-Agent', [self.USER_AGENT])
        d = self.agent.request(method, url, headers, body)
        before = self.reactor.seconds()
        def report(response):
            success = response.code == expectedResponseCode
            after = self.reactor.seconds()
            # XXX This is time to receive response headers, not time
            # to receive full response.  Should measure the latter, if
            # not both.
            msg(
                type="request", success=success, method=method,
                duration=(after - before), url=url)
            return response
        d.addCallback(report)
        return d


    def _parseMultiStatus(self, response):
        """
        Parse a <multistatus>
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
        principals = self._parseMultiStatus(response)

        # XXX Here, it would be really great to somehow use
        # CalDAVClientLibrary.client.principal.CalDAVPrincipal.listCalendars
        for principal in principals:
            nodes = principals[principal].getNodeProperties()
            for nodeType in nodes[davxml.resourcetype].getchildren():
                if nodeType.tag in self._CALENDAR_TYPES:
                    textProps = principals[principal].getTextProperties()
                    calendars.append(Calendar(
                            nodeType.tag,
                            textProps.get(davxml.displayname, None),
                            principal,
                            textProps.get(csxml.getctag, None),
                            ))
                    break
        return calendars


    def _principalPropfind(self, user):
        """
        Issue a PROPFIND on the likely principal URL for the given
        user and return a L{Principal} instance constructed from the
        response.
        """
        principalURL = '/principals/__uids__/' + user + '/'
        d = self._request(
            MULTI_STATUS,
            'PROPFIND',
            self.root + principalURL[1:],
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPAL_PROPFIND))
        d.addCallback(readBody)
        d.addCallback(self._parseMultiStatus)
        d.addCallback(getitem, principalURL)
        return d


    def _principalsReport(self, principalCollectionSet):
        if principalCollectionSet.startswith('/'):
            principalCollectionSet = principalCollectionSet[1:]
        d = self._request(
            OK,
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
            MULTI_STATUS,
            'PROPFIND',
            self.root + calendarHomeSet,
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['1']}),
            StringProducer(self._STARTUP_CALENDARHOME_PROPFIND))
        d.addCallback(readBody)
        d.addCallback(self._extractCalendars)
        return d


    @inlineCallbacks
    def _updateCalendar(self, calendar):
        url = calendar.url
        if url.startswith('/'):
            url = url[1:]

        # First do a PROPFIND on the calendar to learn about events it
        # might have.
        response = yield self._request(
            MULTI_STATUS,
            'PROPFIND',
            self.root + url,
            Headers({'content-type': ['text/xml'], 'depth': ['1']}),
            StringProducer(self._CALENDAR_PROPFIND))

        # XXX Check the response status code

        body = yield readBody(response)

        result = self._parseMultiStatus(body)
        for responseHref in result:
            if responseHref == calendar.url:
                continue

            etag = result[responseHref].getTextProperties()[davxml.getetag]
            if responseHref not in self._events:
                self._events[responseHref] = Event(responseHref, None)

            if self._events[responseHref].etag != etag:
                response = yield self._updateEvent(url, responseHref)
                body = yield readBody(response)
                result = self._parseMultiStatus(body)[responseHref]
                etag = result.getTextProperties()[davxml.getetag]
                self._events[responseHref].etag = etag

                
    def _updateEvent(self, calendar, event):
        # Next do a REPORT on each event that might have information
        # we don't know about.
        return self._request(
            MULTI_STATUS,
            'REPORT',
            self.root + calendar,
            Headers({'content-type': ['text/xml']}),
            StringProducer(self._CALENDAR_REPORT % {'href': event}))


    def _checkCalendarsForEvents(self, calendarHomeSet):
        d = self._calendarHomePropfind(calendarHomeSet)
        def cbCalendars(calendars):
            for cal in calendars:
                if self._calendars.setdefault(cal.url, cal).ctag != cal.ctag or True:
                    self._updateCalendar(cal)
                    break
        d.addCallback(cbCalendars)
        return d


    def _notificationPropfind(self, notificationURL):
        if notificationURL.startswith('/'):
            notificationURL = notificationURL[1:]
        d = self._request(
            MULTI_STATUS,
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
            OK,
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
        (yield self._principalsReport(principalCollection))

        # Whatever

        # Learn stuff I guess
        # notificationURL = hrefs[csxml.notification_URL].toString()
        # (yield self._notificationPropfind(notificationURL))

        # More too
        # principalURL = hrefs[davxml.principal_URL].toString()
        # (yield self._principalReport(principalURL))

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
            self._checkCalendarsForEvents, 
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
