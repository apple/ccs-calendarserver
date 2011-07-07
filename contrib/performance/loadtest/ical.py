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

from uuid import uuid4
from datetime import timedelta, datetime
from urlparse import urlparse, urlunparse

from xml.etree import ElementTree
ElementTree.QName.__repr__ = lambda self: '<QName %r>' % (self.text,)

from vobject import readComponents
from vobject.base import ContentLine
from vobject.icalendar import VEvent, dateTimeToString

from twisted.python.log import addObserver, err, msg
from twisted.python.filepath import FilePath
from twisted.python.failure import Failure
from twisted.python.util import FancyEqMixin
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
from twisted.web.http_headers import Headers
from twisted.web.http import OK, MULTI_STATUS, CREATED, NO_CONTENT
from twisted.web.client import Agent

from protocol.webdav.propfindparser import PropFindParser
from protocol.webdav.definitions import davxml
from protocol.caldav.definitions import caldavxml
from protocol.caldav.definitions import csxml

from httpclient import StringProducer, readBody
from httpauth import AuthHandlerAgent

from subscribe import Periodical

from calendarserver.tools.notifications import PubSubClientFactory

def loadRequestBody(label):
    return FilePath(__file__).sibling('request-data').child(label + '.request').getContent()


SUPPORTED_REPORT_SET = '{DAV:}supported-report-set'

class IncorrectResponseCode(Exception):
    """
    Raised when a response has a code other than the one expected.

    @ivar expected: The response code which was expected.
    @type expected: C{int}

    @ivar response: The response which was received
    @type response: L{twisted.web.client.Response}
    """
    def __init__(self, expected, response):
        self.expected = expected
        self.response = response



class XMPPPush(object, FancyEqMixin):
    """
    This represents an XMPP PubSub location where push notifications for
    particular calendar home might be received.
    """
    compareAttributes = ('server', 'uri', 'pushkey')

    def __init__(self, server, uri, pushkey):
        self.server = server
        self.uri = uri
        self.pushkey = pushkey



class Event(object):
    def __init__(self, url, etag, vevent=None):
        self.url = url
        self.etag = etag
        self.scheduleTag = None
        self.vevent = vevent


    def getUID(self):
        """
        Return the UID from the vevent, if there is one.
        """
        if self.vevent is not None:
            uid = self.vevent.contents['vevent'][0].contents['uid'][0]
            return uid.value
        return None



class Calendar(object):
    def __init__(self, resourceType, name, url, ctag):
        self.resourceType = resourceType
        self.name = name
        self.url = url
        self.ctag = ctag
        self.events = {}



class BaseClient(object):
    user = None
    _events = None
    _calendars = None

    def _setEvent(self, href, event):
        self._events[href] = event
        calendar, uid = href.rsplit('/', 1)
        self._calendars[calendar + '/'].events[uid] = event


    def addEvent(self, href, vcalendar):
        raise NotImplementedError("%r does not implement addEvent" % (self.__class__,))


    def deleteEvent(self, href):
        raise NotImplementedError("%r does not implement deleteEvent" % (self.__class__,))


    def addEventAttendee(self, href, attendee):
        raise NotImplementedError("%r does not implement addEventAttendee" % (self.__class__,))


    def changeEventAttendee(self, href, oldAttendee, newAttendee):
        raise NotImplementedError("%r does not implement changeEventAttendee" % (self.__class__,))


class _PubSubClientFactory(PubSubClientFactory):
    def __init__(self, client, *args, **kwargs):
        PubSubClientFactory.__init__(self, *args, **kwargs)
        self._client = client

    def initFailed(self, reason):
        print 'XMPP initialization failed', reason

    def authFailed(self, reason):
        print 'XMPP Authentication failed', reason

    def handleMessageEventItems(self, iq):
        item = iq.firstChildElement().firstChildElement()
        if item:
            node = item.getAttribute("node")
            if node:
                url, name, kind = self.nodes.get(node, (None, None, None))
                if url is not None:
                    self._client._checkCalendarsForEvents(url)



class SnowLeopard(BaseClient):
    """
    Implementation of the SnowLeopard iCal network behavior.

    Anything SnowLeopard iCal does on its own, or any particular
    network behaviors it takes in response to a user action, belong on
    this class.

    Usage-profile based behaviors ("the user modifies an event every
    3.2 minutes") belong elsewhere.
    """

    USER_AGENT = "DAVKit/4.0.3 (732); CalendarStore/4.0.3 (991); iCal/4.0.3 (1388); Mac OS X/10.6.4 (10F569)"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by Snow
    # Leopard iCal.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60

    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody('sl_startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody('sl_startup_principals_report')
    _STARTUP_CALENDARHOME_PROPFIND = loadRequestBody('sl_startup_calendarhome_propfind')
    _STARTUP_NOTIFICATION_PROPFIND = loadRequestBody('sl_startup_notification_propfind')
    _STARTUP_PRINCIPAL_REPORT = loadRequestBody('sl_startup_principal_report')

    _CALENDAR_PROPFIND = loadRequestBody('sl_calendar_propfind')
    _CALENDAR_REPORT = loadRequestBody('sl_calendar_report')

    _USER_LIST_PRINCIPAL_PROPERTY_SEARCH = loadRequestBody('sl_user_list_principal_property_search')
    _POST_AVAILABILITY = loadRequestBody('sl_post_availability')

    email = None

    def __init__(self, reactor, root, record, auth, calendarHomePollInterval=None, supportPush=True):
        self.reactor = reactor
        self.agent = AuthHandlerAgent(Agent(self.reactor), auth)
        self.root = root
        self.record = record

        if calendarHomePollInterval is None:
            calendarHomePollInterval = self.CALENDAR_HOME_POLL_INTERVAL
        self.calendarHomePollInterval = calendarHomePollInterval

        self.supportPush = supportPush

        # Keep track of the calendars on this account, keys are
        # Calendar URIs, values are Calendar instances.
        self._calendars = {}

        # Keep track of the events on this account, keys are event
        # URIs (which are unambiguous across different calendars
        # because they start with the uri of the calendar they are
        # part of), values are Event instances.
        self._events = {}

        # Keep track of which calendar homes are being polled
        self._checking = set()

        # Keep track of XMPP parameters for calendar homes we encounter.  This
        # dictionary has calendar home URLs as keys and XMPPPush instances as
        # values.
        self.xmpp = {}

        # Allow events to go out into the world.
        self.catalog = {
            "eventChanged": Periodical(),
            }


    def _request(self, expectedResponseCode, method, url, headers=None, body=None):
        if headers is None:
            headers = Headers({})
        headers.setRawHeaders('User-Agent', [self.USER_AGENT])
        msg(type="request", method=method, url=url, user=self.record.uid)
        d = self.agent.request(method, url, headers, body)
        before = self.reactor.seconds()
        def report(response):
            # XXX This is time to receive response headers, not time
            # to receive full response.  Should measure the latter, if
            # not both.
            after = self.reactor.seconds()

            success = response.code == expectedResponseCode

            # if not success:
            #     import pdb; pdb.set_trace()
            msg(
                type="response", success=success, method=method,
                headers=headers, body=body, code=response.code,
                user=self.record.uid, duration=(after - before), url=url)

            if success:
                return response
            raise IncorrectResponseCode(expectedResponseCode, response)
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
    def _extractCalendars(self, response, calendarHome=None):
        """
        Parse a calendar home PROPFIND response and create local state
        representing the calendars it contains.

        If XMPP push is enabled, also look for and record information about
        that from the response.
        """
        calendars = []
        principals = self._parseMultiStatus(response)

        # XXX Here, it would be really great to somehow use
        # CalDAVClientLibrary.client.principal.CalDAVPrincipal.listCalendars
        for principal in principals:

            if principal == calendarHome:
                text = principals[principal].getTextProperties()
                server = text[csxml.xmpp_server]
                uri = text[csxml.xmpp_uri]
                pushkey = text[csxml.pushkey]
                if server and uri:
                    self.xmpp[principal] = XMPPPush(server, uri, pushkey)

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
            self.root + principalURL[1:].encode('utf-8'),
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPAL_PROPFIND))
        d.addCallback(readBody)
        d.addCallback(self._parseMultiStatus)
        def get(result):
            return result[principalURL]
        d.addCallback(get)
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
        d.addCallback(self._extractCalendars, '/' + calendarHomeSet)
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

        body = yield readBody(response)

        result = self._parseMultiStatus(body)
        for responseHref in result:
            if responseHref == calendar.url:
                continue

            try:
                etag = result[responseHref].getTextProperties()[davxml.getetag]
            except KeyError:
                # XXX Ignore things with no etag?  Seems to be dropbox.
                continue

            if responseHref not in self._events:
                self._setEvent(responseHref, Event(responseHref, None))
                
            event = self._events[responseHref]
            if event.etag != etag:
                response = yield self._eventReport(url, responseHref)
                body = yield readBody(response)
                res = self._parseMultiStatus(body)[responseHref]
                if res.getStatus() is None or " 404 " not in res.getStatus():
                    text = res.getTextProperties()
                    etag = text[davxml.getetag]
                    try:
                        scheduleTag = text[caldavxml.schedule_tag]
                    except KeyError:
                        scheduleTag = None
                    body = text[caldavxml.calendar_data]
                    self.eventChanged(responseHref, etag, scheduleTag, body)


    def eventChanged(self, href, etag, scheduleTag, body):
        event = self._events[href]
        event.etag = etag
        if scheduleTag is not None:
            event.scheduleTag = scheduleTag
        event.vevent = list(readComponents(body))[0]
        self.catalog["eventChanged"].issue(href)

                
    def _eventReport(self, calendar, event):
        # Next do a REPORT on each event that might have information
        # we don't know about.
        return self._request(
            MULTI_STATUS,
            'REPORT',
            self.root + calendar,
            Headers({'content-type': ['text/xml']}),
            StringProducer(self._CALENDAR_REPORT % {'href': event}))


    def _checkCalendarsForEvents(self, calendarHomeSet):
        if calendarHomeSet in self._checking:
            return
        self._checking.add(calendarHomeSet)
        d = self._calendarHomePropfind(calendarHomeSet)
        @inlineCallbacks
        def cbCalendars(calendars):
            for cal in calendars:
                if self._calendars.setdefault(cal.url, cal).ctag != cal.ctag or True:
                    yield self._updateCalendar(cal)
        d.addCallback(cbCalendars)
        d = self._newOperation("poll", d)
        def ebCalendars(reason):
            reason.trap(IncorrectResponseCode)
        d.addErrback(ebCalendars)
        def cleanupChecking(passthrough):
            self._checking.remove(calendarHomeSet)
            return passthrough
        d.addBoth(cleanupChecking)
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
        principal = yield self._principalPropfind(self.record.uid)

        hrefs = principal.getHrefProperties()

        # Remember our own email-like principal address
        for principalURL in hrefs[caldavxml.calendar_user_address_set]:
            if principalURL.toString().startswith(u"mailto:"):
                self.email = principalURL.toString()
            elif principalURL.toString().startswith(u"urn:"):
                self.uuid = principalURL.toString()
        if self.email is None:
            raise ValueError("Cannot operate without a mail-style principal URL")

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


    def _calendarCheckLoop(self, calendarHome):
        """
        Periodically check the calendar home for changes to calendars.
        """
        pollCalendarHome = LoopingCall(
            self._checkCalendarsForEvents, calendarHome)
        return pollCalendarHome.start(self.calendarHomePollInterval, now=False)


    def _newOperation(self, label, deferred):
        before = self.reactor.seconds()
        msg(type="operation", phase="start", user=self.record.uid, label=label)
        def finished(passthrough):
            success = not isinstance(passthrough, Failure)
            after = self.reactor.seconds()
            msg(type="operation", phase="end", duration=after - before,
                user=self.record.uid, label=label, success=success)
            return passthrough
        deferred.addBoth(finished)
        return deferred


    def _monitorPubSub(self, home, params):
        """
        Start monitoring the
        """
        host, port = params.server.split(':')
        port = int(port)

        service, stuff = params.uri.split('?')
        service = service.split(':', 1)[1]

        # XXX What is the domain of the 2nd argument supposed to be?  The
        # hostname we use to connect, or the same as the email address in the
        # user record?
        factory = _PubSubClientFactory(
            self, "%s@%s" % (self.record.uid, host),
            self.record.password, service,
            {params.pushkey: (home, home, "Calendar home")}, False)
        self.reactor.connectTCP(host, port, factory)


    @inlineCallbacks
    def run(self):
        """
        Emulate a CalDAV client.
        """
        @inlineCallbacks
        def startup():
            principal = yield self.startup()
            hrefs = principal.getHrefProperties()
            calendarHome = hrefs[caldavxml.calendar_home_set].toString()
            yield self._checkCalendarsForEvents(calendarHome)
            returnValue(calendarHome)
        calendarHome = yield self._newOperation("startup", startup())

        # Start monitoring PubSub notifications, if possible.
        # _checkCalendarsForEvents populates self.xmpp if it finds
        # anything.
        if self.supportPush and calendarHome in self.xmpp:
            self._monitorPubSub(calendarHome, self.xmpp[calendarHome])
            # Run indefinitely.
            yield Deferred()
        else:
            # This completes when the calendar home poll loop completes, which
            # currently it never will except due to an unexpected error.
            yield self._calendarCheckLoop(calendarHome)


    def _makeSelfAttendee(self):
        attendee = ContentLine(
            name=u'ATTENDEE', params=[
                [u'CN', self.record.commonName],
                [u'CUTYPE', u'INDIVIDUAL'],
                [u'PARTSTAT', u'ACCEPTED'],
                ],
            value=self.uuid,
            encoded=True)
        attendee.parentBehavior = VEvent
        return attendee


    def _makeSelfOrganizer(self):
        organizer = ContentLine(
            name=u'ORGANIZER', params=[
                [u'CN', self.record.commonName],
                ],
            value=self.uuid,
            encoded=True)
        organizer.parentBehavior = VEvent
        return organizer


    def addEventAttendee(self, href, attendee):
        name = attendee.params[u'CN'][0].encode('utf-8')
        prefix = name[:4].lower()
        email = attendee.params[u'EMAIL'][0].encode('utf-8')

        event = self._events[href]
        vevent = event.vevent

        # First try to discover some names to supply to the
        # auto-completion
        d = self._request(
            MULTI_STATUS, 'REPORT', self.root + 'principals/',
            Headers({'content-type': ['text/xml']}),
            StringProducer(self._USER_LIST_PRINCIPAL_PROPERTY_SEARCH % {
                    'displayname': prefix,
                    'email': prefix,
                    'firstname': prefix,
                    'lastname': prefix,
                    }))
        d.addCallback(readBody)
        def narrowed(ignored):
            # Next just learn about the one name we selected.
            d = self._request(
                MULTI_STATUS, 'REPORT', self.root + 'principals/',
                Headers({'content-type': ['text/xml']}),
                StringProducer(self._USER_LIST_PRINCIPAL_PROPERTY_SEARCH % {
                        'displayname': name,
                        'email': name,
                        'firstname': name,
                        'lastname': name,
                        }))
            d.addCallback(readBody)
            return d
        d.addCallback(narrowed)
        def specific(ignored):
            # Now learn about the attendee's availability
            return self.requestAvailability(
                vevent.contents[u'vevent'][0].contents[u'dtstart'][0].value,
                vevent.contents[u'vevent'][0].contents[u'dtend'][0].value,
                [self.email, u'mailto:' + email],
                [vevent.contents[u'vevent'][0].contents[u'uid'][0].value])
            return d
        d.addCallback(specific)
        def availability(ignored):
            # If the event has no attendees, add ourselves as an attendee.
            attendees = vevent.contents[u'vevent'][0].contents.setdefault(u'attendee', [])
            if len(attendees) == 0:
                # First add ourselves as a participant and as the
                # organizer.  In the future for this event we should
                # already have those roles.
                attendees.append(self._makeSelfAttendee())
                vevent.contents[u'vevent'][0].contents[u'organizer'] = [self._makeSelfOrganizer()]
            attendees.append(attendee)

            # At last, upload the new event definition
            d = self._request(
                NO_CONTENT, 'PUT', self.root + href[1:].encode('utf-8'),
                Headers({
                        'content-type': ['text/calendar'],
                        'if-match': [event.etag]}),
                StringProducer(vevent.serialize()))
            return d
        d.addCallback(availability)
        # Finally, re-retrieve the event to update the etag
        d.addCallback(self._updateEvent, href)
        return d


    def changeEventAttendee(self, href, oldAttendee, newAttendee):
        event = self._events[href]
        vevent = event.vevent

        # Change the event to have the new attendee instead of the old attendee
        attendees = vevent.contents[u'vevent'][0].contents[u'attendee']
        attendees.remove(oldAttendee)
        attendees.append(newAttendee)
        headers = Headers({
                'content-type': ['text/calendar'],
                })
        if event.scheduleTag is not None:
            headers.addRawHeader('if-schedule-tag-match', event.scheduleTag)

        d = self._request(
            NO_CONTENT, 'PUT', self.root + href[1:].encode('utf-8'),
            headers, StringProducer(vevent.serialize()))
        d.addCallback(self._updateEvent, href)
        return d


    def deleteEvent(self, href):
        """
        Issue a DELETE for the given URL and remove local state
        associated with that event.
        """
        d = self._request(
            NO_CONTENT, 'DELETE', self.root + href[1:].encode('utf-8'))

        calendar, uid = href.rsplit('/', 1)
        del self._events[href]
        del self._calendars[calendar + u'/'].events[uid]

        return d


    def addEvent(self, href, vcalendar):
        headers = Headers({
                'content-type': ['text/calendar'],
                })
        d = self._request(
            CREATED, 'PUT', self.root + href[1:].encode('utf-8'),
            headers, StringProducer(vcalendar.serialize()))
        d.addCallback(self._localUpdateEvent, href, vcalendar)
        return d


    def _localUpdateEvent(self, response, href, vcalendar):
        headers = response.headers
        etag = headers.getRawHeaders("etag", [None])[0]
        scheduleTag = headers.getRawHeaders("schedule-tag", [None])[0]

        event = Event(href, etag, vcalendar)
        event.scheduleTag = scheduleTag
        self._setEvent(href, event)


    def updateEvent(self, href):
        return self._updateEvent(None, href)


    def _updateEvent(self, ignored, href):
        d = self._request(OK, 'GET', self.root + href[1:].encode('utf-8'))
        def getETag(response):
            headers = response.headers
            etag = headers.getRawHeaders('etag')[0]
            scheduleTag = headers.getRawHeaders('schedule-tag', [None])[0]
            return readBody(response).addCallback(
                lambda body: (etag, scheduleTag, body))
        d.addCallback(getETag)
        def record((etag, scheduleTag, body)):
            self.eventChanged(href, etag, scheduleTag, body)
        d.addCallback(record)
        return d


    def requestAvailability(self, start, end, users, mask=set()):
        """
        Issue a VFREEBUSY request for I{roughly} the given date range for the
        given users.  The date range is quantized to one day.  Because of this
        it is an error for the range to span more than 24 hours.

        @param start: A C{datetime} instance giving the beginning of the
            desired range.

        @param end: A C{datetime} instance giving the end of the desired range.

        @param users: An iterable of user UUIDs which will be included in the
            request.

        @param mask: An iterable of event UIDs which are to be ignored for the
            purposes of this availability lookup.

        @return: A C{Deferred} which fires with a C{dict}.  Keys in the dict
            are user UUIDs (those requested) and values are something else.
        """
        outbox = self.root + 'calendars/__uids__/%s/outbox/' % (
            self.record.uid.encode('utf-8'),)

        if mask:
            maskStr = u'\r\n'.join(['X-CALENDARSERVER-MASK-UID:' + uid
                                    for uid in mask]) + u'\r\n'
        else:
            maskStr = u''
        maskStr = maskStr.encode('utf-8')

        attendeeStr = '\r\n'.join(['ATTENDEE:' + uuid.encode('utf-8')
                                   for uuid in users]) + '\r\n'

        # iCal issues 24 hour wide vfreebusy requests, starting and ending at 4am.
        if start.date() != end.date():
            msg("Availability request spanning multiple days (%r to %r), "
                "dropping the end date." % (start, end))

        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=24)

        start = dateTimeToString(start, convertToUTC=True)
        end = dateTimeToString(end, convertToUTC=True)
        now = dateTimeToString(datetime.now(), convertToUTC=True)

        # XXX Why does it not end up UTC sometimes?
        if not start.endswith('Z'):
            start = start + 'Z'
        if not end.endswith('Z'):
            end = end + 'Z'
        if not now.endswith('Z'):
            now = now + 'Z'

        d = self._request(
            OK, 'POST', outbox,
            Headers({
                    'content-type': ['text/calendar'],
                    'originator': [self.email],
                    'recipient': [u', '.join(users).encode('utf-8')]}),
            StringProducer(self._POST_AVAILABILITY % {
                    'attendees': attendeeStr,
                    'summary': (u'Availability for %s' % (', '.join(users),)).encode('utf-8'),
                    'organizer': self.email.encode('utf-8'),
                    'vfreebusy-uid': str(uuid4()).upper(),
                    'event-mask': maskStr,
                    'start': start,
                    'end': end,
                    'now': now}))
        d.addCallback(readBody)
        return d



class RequestLogger(object):
    format = u"%(user)s request %(code)s%(success)s[%(duration)5.2f s] %(method)8s %(url)s"
    success = u"\N{CHECK MARK}"
    failure = u"\N{BALLOT X}"

    def observe(self, event):
        if event.get("type") == "response":
            formatArgs = dict(
                user=event['user'],
                method=event['method'],
                url=urlunparse(('', '') + urlparse(event['url'])[2:]),
                code=event['code'],
                duration=event['duration'],
                )
                
            if event['success']:
                formatArgs['success'] = self.success
            else:
                formatArgs['success'] = self.failure
            print (self.format % formatArgs).encode('utf-8')


    def report(self):
        pass


    
def main():
    from urllib2 import HTTPDigestAuthHandler
    from twisted.internet import reactor
    auth = HTTPDigestAuthHandler()
    auth.add_password(
        realm="Test Realm",
        uri="http://127.0.0.1:8008/",
        user="user01",
        passwd="user01")

    addObserver(RequestLogger().observe)

    from sim import _DirectoryRecord
    client = SnowLeopard(
        reactor, 'http://127.0.0.1:8008/', 
        _DirectoryRecord(
            u'user01', u'user01', u'User 01', u'user01@example.org'),
        auth)
    d = client.run()
    d.addErrback(err, "Snow Leopard client run() problem")
    d.addCallback(lambda ignored: reactor.stop())
    reactor.run()


if __name__ == '__main__':
    main()
