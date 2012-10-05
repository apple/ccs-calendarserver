##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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

from caldavclientlibrary.protocol.caldav.definitions import caldavxml
from caldavclientlibrary.protocol.caldav.definitions import csxml
from caldavclientlibrary.protocol.webdav.definitions import davxml
from caldavclientlibrary.protocol.webdav.propfindparser import PropFindParser

from calendarserver.push.amppush import subscribeToIDs
from calendarserver.tools.notifications import PubSubClientFactory

from contrib.performance.httpauth import AuthHandlerAgent
from contrib.performance.httpclient import StringProducer, readBody
from contrib.performance.loadtest.subscribe import Periodical

from pycalendar.datetime import PyCalendarDateTime
from pycalendar.duration import PyCalendarDuration
from pycalendar.timezone import PyCalendarTimezone

from twext.internet.adaptendpoint import connect
from twext.internet.gaiendpoint import GAIEndpoint

from twisted.internet.defer import Deferred, inlineCallbacks, returnValue,\
    succeed
from twisted.internet.task import LoopingCall
from twisted.python.filepath import FilePath
from twisted.python.log import addObserver, err, msg
from twisted.python.util import FancyEqMixin
from twisted.web.client import Agent, ContentDecoderAgent, GzipDecoder
from twisted.web.http import OK, MULTI_STATUS, CREATED, NO_CONTENT, PRECONDITION_FAILED, MOVED_PERMANENTLY,\
    FORBIDDEN, FOUND
from twisted.web.http_headers import Headers

from twistedcaldav.ical import Component, Property

from urlparse import urlparse, urlunparse, urlsplit, urljoin
from uuid import uuid4
from xml.etree import ElementTree

import json
import os
import random

ElementTree.QName.__repr__ = lambda self: '<QName %r>' % (self.text,)

def loadRequestBody(clientType, label):
    return FilePath(__file__).sibling('request-data').child(clientType).child(label + '.request').getContent()


SUPPORTED_REPORT_SET = '{DAV:}supported-report-set'

class IncorrectResponseCode(Exception):
    """
    Raised when a response has a code other than the one expected.

    @ivar expected: The response codes which was expected.
    @type expected: C{tuple} of C{int}

    @ivar response: The response which was received
    @type response: L{twisted.web.client.Response}
    """
    def __init__(self, expected, response):
        self.expected = expected
        self.response = response


class MissingCalendarHome(Exception):
    """
    Raised when the calendar home for a user is 404
    """


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



def u2str(data):
    return data.encode("utf-8") if type(data) is unicode else data



class Event(object):
    def __init__(self, serializeBasePath, url, etag, component=None):
        self.serializeBasePath = serializeBasePath
        self.url = url
        self.etag = etag
        self.scheduleTag = None
        if component is not None:
            self.component = component
        self.uid = component.resourceUID() if component is not None else None


    def getUID(self):
        """
        Return the UID of the calendar resource.
        """
        return self.uid


    def serializePath(self):
        if self.serializeBasePath:
            calendar = os.path.join(self.serializeBasePath, self.url.split("/")[-2])
            if not os.path.exists(calendar):
                os.makedirs(calendar)
            return os.path.join(calendar, self.url.split("/")[-1])
        else:
            return None

    def serialize(self):
        """
        Create a dict of the data so we can serialize as JSON.
        """
        
        result = {}
        for attr in ("url", "etag", "scheduleTag", "uid",):
            result[attr] = getattr(self, attr)
        return result


    @staticmethod
    def deserialize(serializeLocation, data):
        """
        Convert dict (deserialized from JSON) into an L{Event}.
        """
        
        event = Event(serializeLocation, None, None)
        for attr in ("url", "etag", "scheduleTag", "uid",):
            setattr(event, attr, u2str(data[attr]))
        return event


    @property
    def component(self):
        """
        Data always read from disk - never cached in the object.
        """
        path = self.serializePath()
        if path and os.path.exists(path):
            f = open(path)
            comp = Component.fromString(f.read())
            f.close()
            return comp
        else:
            return None


    @component.setter
    def component(self, component):
        """
        Data always written to disk - never cached on the object.
        """
        path = self.serializePath()
        if path:
            if component is None:
                os.remove(path)
            else:
                f = open(path, "w")
                f.write(str(component))
                f.close()
        self.uid = component.resourceUID() if component is not None else None


    def removed(self):
        """
        Resource no longer exists on the server - remove associated data.
        """
        path = self.serializePath()
        if path and os.path.exists(path):
            os.remove(path)


class Calendar(object):
    def __init__(self, resourceType, componentTypes, name, url, changeToken):
        self.resourceType = resourceType
        self.componentTypes = componentTypes
        self.name = name
        self.url = url
        self.changeToken = changeToken
        self.events = {}


    def serialize(self):
        """
        Create a dict of the data so we can serialize as JSON.
        """
        
        result = {}
        for attr in ("resourceType", "name", "url", "changeToken"):
            result[attr] = getattr(self, attr)
        result["componentTypes"] = list(sorted(self.componentTypes))
        result["events"] = sorted(self.events.keys())
        return result


    @staticmethod
    def deserialize(data, events):
        """
        Convert dict (deserialized from JSON) into an L{Calendar}.
        """
        
        calendar = Calendar(None, None, None, None, None)
        for attr in ("resourceType", "name", "url", "changeToken"):
            setattr(calendar, attr, u2str(data[attr]))
        calendar.componentTypes = set(map(u2str, data["componentTypes"]))
        
        for event in data["events"]:
            url = urljoin(calendar.url, event)
            if url in events:
                calendar.events[event] = events[url]
            else:
                # Ughh - an event is missing - force changeToken to empty to trigger full resync
                calendar.changeToken = ""
        return calendar



class BaseClient(object):
    """
    Base interface for all simulated clients.
    """

    user = None         # User account details
    _events = None      # Cache of events keyed by href
    _calendars = None   # Cache of calendars keyed by href
    started = False     # Whether or not startup() has been executed
    _client_type = None # Type of this client used in logging 
    _client_id = None   # Unique id for the client itself


    def _setEvent(self, href, event):
        """
        Cache the provided event
        """
        self._events[href] = event
        calendar, basePath = href.rsplit('/', 1)
        self._calendars[calendar + '/'].events[basePath] = event


    def _removeEvent(self, href):
        """
        Remove event from local cache.
        """
        self._events[href].removed()
        del self._events[href]
        calendar, basePath = href.rsplit('/', 1)
        del self._calendars[calendar + '/'].events[basePath]


    def addEvent(self, href, calendar):
        """
        Called when a profile needs to add an event (no scheduling).
        """
        raise NotImplementedError("%r does not implement addEvent" % (self.__class__,))


    def addInvite(self, href, calendar):
        """
        Called when a profile needs to add a new invite. The iCalendar data will already
        contain ATTENDEEs.
        """
        raise NotImplementedError("%r does not implement addInvite" % (self.__class__,))


    def deleteEvent(self, href):
        """
        Called when a profile needs to delete an event.
        """
        raise NotImplementedError("%r does not implement deleteEvent" % (self.__class__,))


    def addEventAttendee(self, href, attendee):
        """
        Called when a profile needs to add an attendee to an existing event.
        """
        raise NotImplementedError("%r does not implement addEventAttendee" % (self.__class__,))


    def changeEventAttendee(self, href, oldAttendee, newAttendee):
        """
        Called when a profile needs to change an attendee on an existing event.
        Used when an attendee is accepting.
        """
        raise NotImplementedError("%r does not implement changeEventAttendee" % (self.__class__,))


class _PubSubClientFactory(PubSubClientFactory):
    """
    Factory for XMPP pubsub functionality.
    """
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
                url, _ignore_name, _ignore_kind = self.nodes.get(node, (None, None, None))
                if url is not None:
                    self._client._checkCalendarsForEvents(url, push=True)



class BaseAppleClient(BaseClient):
    """
    Implementation of common OS X/iOS client behavior.
    """

    _client_type = "Generic"

    USER_AGENT = None   # Override this for specific clients

    # The default interval, used if none is specified in external
    # configuration.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60
    
    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 200

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = False

    # Override and turn on if client syncs using time-range queries
    _SYNC_TIMERANGE = False

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = True

    # Request body data
    _LOAD_PATH = None

    _STARTUP_WELL_KNOWN = None
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = None
    _STARTUP_PRINCIPAL_PROPFIND = None
    _STARTUP_PRINCIPALS_REPORT = None
    _STARTUP_PRINCIPAL_EXPAND = None
    _STARTUP_PROPPATCH_CALENDAR_COLOR = None
    _STARTUP_PROPPATCH_CALENDAR_ORDER = None
    _STARTUP_PROPPATCH_CALENDAR_TIMEZONE = None

    _POLL_CALENDARHOME_PROPFIND = None
    _POLL_CALENDAR_PROPFIND = None
    _POLL_CALENDAR_PROPFIND_D1 = None
    _POLL_CALENDAR_MULTIGET_REPORT = None
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = None
    _POLL_CALENDAR_SYNC_REPORT = None
    _POLL_NOTIFICATION_PROPFIND = None
    _POLL_NOTIFICATION_PROPFIND_D1 = None

    _USER_LIST_PRINCIPAL_PROPERTY_SEARCH = None
    _POST_AVAILABILITY = None

    email = None

    def __init__(
        self,
        reactor,
        root,
        principalPathTemplate,
        serializePath,
        record,
        auth,
        title=None,
        calendarHomePollInterval=None,
        supportPush=True,
        supportAmpPush=True,
        ampPushHost=None,
        ampPushPort=62311,
    ):
        
        self._client_id = str(uuid4())

        self.reactor = reactor

        # The server might use gzip encoding
        agent = Agent(self.reactor)
        agent = ContentDecoderAgent(agent, [("gzip", GzipDecoder)])
        self.agent = AuthHandlerAgent(agent, auth)

        self.root = root
        self.principalPathTemplate = principalPathTemplate
        self.record = record

        self.title = title if title else self._client_type

        if calendarHomePollInterval is None:
            calendarHomePollInterval = self.CALENDAR_HOME_POLL_INTERVAL
        self.calendarHomePollInterval = calendarHomePollInterval

        self.supportPush = supportPush

        self.supportAmpPush = supportAmpPush
        if ampPushHost is None:
            ampPushHost = urlparse(self.root)[1].split(":")[0]
        self.ampPushHost = ampPushHost
        self.ampPushPort = ampPushPort

        self.serializePath = serializePath

        self.supportSync = self._SYNC_REPORT

        # Keep track of the calendars on this account, keys are
        # Calendar URIs, values are Calendar instances.
        self._calendars = {}

        # The principalURL found during discovery
        self.principalURL = None

        # The principal collection found during startup
        self.principalCollection = None

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

        self.ampPushKeys = {}

        # Keep track of push factories so we can unsubscribe at shutdown
        self._pushFactories = []

        # Allow events to go out into the world.
        self.catalog = {
            "eventChanged": Periodical(),
            }


    def _addDefaultHeaders(self, headers):
        """
        Add the clients default set of headers to ones being used in a request.
        Default is to add User-Agent, sub-classes should override to add other
        client specific things, Accept etc.
        """
        headers.setRawHeaders('User-Agent', [self.USER_AGENT])


    @inlineCallbacks
    def _request(self, expectedResponseCodes, method, url, headers=None, body=None, method_label=None):
        """
        Execute a request and check against the expected response codes.
        """
        if type(expectedResponseCodes) is int:
            expectedResponseCodes = (expectedResponseCodes,)
        if headers is None:
            headers = Headers({})
        self._addDefaultHeaders(headers)
        msg(
            type="request",
            method=method_label if method_label else method,
            url=url,
            user=self.record.uid,
            client_type=self.title,
            client_id=self._client_id,
        )

        before = self.reactor.seconds()
        response = yield self.agent.request(method, url, headers, body)

        # XXX This is time to receive response headers, not time
        # to receive full response.  Should measure the latter, if
        # not both.
        after = self.reactor.seconds()

        success = response.code in expectedResponseCodes

        msg(
            type="response",
            success=success,
            method=method_label if method_label else method,
            headers=headers,
            body=body,
            code=response.code,
            user=self.record.uid,
            client_type=self.title,
            client_id=self._client_id,
            duration=(after - before),
            url=url,
        )

        if success:
            returnValue(response)

        raise IncorrectResponseCode(expectedResponseCodes, response)


    def _parseMultiStatus(self, response, otherTokens=False):
        """
        Parse a <multistatus> - might need to return other top-level elements
        in the response - e.g. DAV:sync-token
        I{PROPFIND} request for the principal URL.

        @type response: C{str}
        @rtype: C{cls}
        """
        parser = PropFindParser()
        parser.parseData(response)
        if otherTokens:
            return (parser.getResults(), parser.getOthers(),)
        else:
            return parser.getResults()

    
    _CALENDAR_TYPES = set([
            caldavxml.calendar,
            caldavxml.schedule_inbox,
            ])

    @inlineCallbacks
    def _propfind(self, url, body, depth='0', allowedStatus=(MULTI_STATUS,), method_label=None):
        """
        Issue a PROPFIND on the chosen URL
        """
        hdrs = Headers({'content-type': ['text/xml']})
        if depth is not None:
            hdrs.addRawHeader('depth', depth)
        response = yield self._request(
            allowedStatus,
            'PROPFIND',
            self.root + url.encode('utf-8'),
            hdrs,
            StringProducer(body),
            method_label=method_label,
        )
        
        body = yield readBody(response)
        result = self._parseMultiStatus(body) if response.code == MULTI_STATUS else None

        returnValue((response, result,))


    @inlineCallbacks
    def _proppatch(self, url, body, method_label=None):
        """
        Issue a PROPPATCH on the chosen URL
        """
        hdrs = Headers({'content-type': ['text/xml']})
        response = yield self._request(
            (OK, MULTI_STATUS,),
            'PROPPATCH',
            self.root + url.encode('utf-8'),
            hdrs,
            StringProducer(body),
            method_label=method_label,
        )
        if response.code == MULTI_STATUS:
            body = yield readBody(response)
            result = self._parseMultiStatus(body)
            returnValue(result)
        else:
            returnValue(None)


    @inlineCallbacks
    def _report(self, url, body, depth='0', allowedStatus=(MULTI_STATUS,), otherTokens=False, method_label=None):
        """
        Issue a REPORT on the chosen URL
        """
        hdrs = Headers({'content-type': ['text/xml']})
        if depth is not None:
            hdrs.addRawHeader('depth', depth)
        response = yield self._request(
            allowedStatus,
            'REPORT',
            self.root + url.encode('utf-8'),
            hdrs,
            StringProducer(body),
            method_label=method_label,
        )

        body = yield readBody(response)
        result = self._parseMultiStatus(body, otherTokens) if response.code == MULTI_STATUS else None

        returnValue(result)


    @inlineCallbacks
    def _startupPropfindWellKnown(self):
        """
        Issue a PROPFIND on the /.well-known/caldav/ URL
        """
        
        location = "/.well-known/caldav/"
        response, result = yield self._propfind(
            location,
            self._STARTUP_WELL_KNOWN,
            allowedStatus=(MULTI_STATUS, MOVED_PERMANENTLY, FOUND, ),
            method_label="PROPFIND{well-known}",
        )
        
        # Follow any redirect
        if response.code in (MOVED_PERMANENTLY, FOUND, ):
            location = response.headers.getRawHeaders("location")[0]
            location = urlsplit(location)[2]
            response, result = yield self._propfind(
                location,
                self._STARTUP_WELL_KNOWN,
                allowedStatus=(MULTI_STATUS),
                method_label="PROPFIND{well-known}",
            )
        
        returnValue(result[location])
            

    @inlineCallbacks
    def _principalPropfindInitial(self, user):
        """
        Issue a PROPFIND on the /principals/users/<uid> URL to retrieve
        the /principals/__uids__/<guid> principal URL
        """
        principalPath = self.principalPathTemplate % (user,)
        _ignore_response, result = yield self._propfind(
            principalPath,
            self._STARTUP_PRINCIPAL_PROPFIND_INITIAL,
            method_label="PROPFIND{find-principal}",
        )
        returnValue(result[principalPath])


    @inlineCallbacks
    def _principalPropfind(self):
        """
        Issue a PROPFIND on the likely principal URL for the given
        user and return a L{Principal} instance constructed from the
        response.
        """
        _ignore_response, result = yield self._propfind(
            self.principalURL,
            self._STARTUP_PRINCIPAL_PROPFIND,
            method_label="PROPFIND{principal}",
        )
        returnValue(result[self.principalURL])


    def _principalSearchPropertySetReport(self, principalCollectionSet):
        """
        Issue a principal-search-property-set REPORT against the chosen URL
        """
        return self._report(
            principalCollectionSet,
            self._STARTUP_PRINCIPALS_REPORT,
            allowedStatus=(OK,),
            method_label="REPORT{pset}",
        )


    @inlineCallbacks
    def _calendarHomePropfind(self, calendarHomeSet):
        """
        Do the poll Depth:1 PROPFIND on the calendar home.
        """
        if not calendarHomeSet.endswith('/'):
            calendarHomeSet = calendarHomeSet + '/'
        _ignore_response, result = yield self._propfind(
            calendarHomeSet,
            self._POLL_CALENDARHOME_PROPFIND,
            depth='1',
            method_label="PROPFIND{home}",
        )
        calendars = self._extractCalendars(result, calendarHomeSet)
        returnValue((calendars, result,))


    @inlineCallbacks
    def _extractPrincipalDetails(self):
        # Using the actual principal URL, retrieve principal information
        principal = yield self._principalPropfind()

        hrefs = principal.getHrefProperties()

        # Remember our outbox and ignore notifications
        self.outbox = hrefs[caldavxml.schedule_outbox_URL].toString()
        self.notificationURL = None

        # Remember our own email-like principal address
        cuaddrs = hrefs[caldavxml.calendar_user_address_set]
        if isinstance(cuaddrs, basestring):
            cuaddrs = (cuaddrs,)
        for cuaddr in cuaddrs:
            if cuaddr.toString().startswith(u"mailto:"):
                self.email = cuaddr.toString()
            elif cuaddr.toString().startswith(u"urn:"):
                self.uuid = cuaddr.toString()
        if self.email is None:
            raise ValueError("Cannot operate without a mail-style principal URL")

        # Do another kind of thing I guess
        self.principalCollection = hrefs[davxml.principal_collection_set].toString()
        yield self._principalSearchPropertySetReport(self.principalCollection)

        returnValue(principal)


    def _extractCalendars(self, results, calendarHome=None):
        """
        Parse a calendar home PROPFIND response and create local state
        representing the calendars it contains.

        If XMPP push is enabled, also look for and record information about
        that from the response.
        """
        calendars = []
        for href in results:

            if href == calendarHome:
                text = results[href].getTextProperties()

                try:
                    pushkey = text[csxml.pushkey]
                except KeyError:
                    pass
                else:
                    if pushkey:
                        self.ampPushKeys[href] = pushkey

                try:
                    server = text[csxml.xmpp_server]
                    uri = text[csxml.xmpp_uri]
                    pushkey = text[csxml.pushkey]
                except KeyError:
                    pass
                else:
                    if server and uri:
                        self.xmpp[href] = XMPPPush(server, uri, pushkey)

            nodes = results[href].getNodeProperties()
            for nodeType in nodes[davxml.resourcetype].getchildren():
                if nodeType.tag in self._CALENDAR_TYPES:
                    textProps = results[href].getTextProperties()
                    componentTypes = set()
                    if nodeType.tag == caldavxml.calendar:
                        if caldavxml.supported_calendar_component_set in nodes:
                            for comp in nodes[caldavxml.supported_calendar_component_set].getchildren():
                                componentTypes.add(comp.get("name").upper())

                    if textProps.get(davxml.displayname, None) == "tasks":
                        # Until we can fix caldavxml.supported_calendar_component_set
                        break                    
                    changeTag = davxml.sync_token if self.supportSync else csxml.getctag
                    calendars.append(Calendar(
                            nodeType.tag,
                            componentTypes,
                            textProps.get(davxml.displayname, None),
                            href,
                            textProps.get(changeTag, None),
                            ))
                    break
        return calendars


    def _updateCalendar(self, calendar, newToken):
        """
        Update the local cached data for a calendar in an appropriate manner.
        """
        if self.supportSync:
            return self._updateCalendar_SYNC(calendar, newToken)
        else:
            return self._updateCalendar_PROPFIND(calendar, newToken)

    @inlineCallbacks
    def _updateCalendar_PROPFIND(self, calendar, newToken):
        """
        Sync a collection by doing a full PROPFIND Depth:1 on it and then sync
        the results with local cached data.
        """

        # Grab old hrefs prior to the PROPFIND so we sync with the old state. We need this because
        # the sim can fire a PUT between the PROPFIND and when process the removals.
        old_hrefs = set([calendar.url + child for child in calendar.events.keys()])

        _ignore_response, result = yield self._propfind(
            calendar.url,
            self._POLL_CALENDAR_PROPFIND_D1,
            depth='1',
            method_label="PROPFIND{calendar}"
        )

        yield self._updateApplyChanges(calendar, result, old_hrefs)

        # Now update calendar to the new token
        self._calendars[calendar.url].changeToken = newToken


    @inlineCallbacks
    def _updateCalendar_SYNC(self, calendar, newToken):
        """
        Execute a sync REPORT against a calendar and apply changes to the local cache.
        The new token from the changed collection is passed in and must be applied to
        the existing calendar once sync is done.
        """

        # Grab old hrefs prior to the REPORT so we sync with the old state. We need this because
        # the sim can fire a PUT between the REPORT and when process the removals.
        old_hrefs = set([calendar.url + child for child in calendar.events.keys()])

        # Get changes from sync REPORT (including the other nodes at the top-level
        # which will have the new sync token.
        fullSync = not calendar.changeToken
        result = yield self._report(
            calendar.url,
            self._POLL_CALENDAR_SYNC_REPORT % {'sync-token': calendar.changeToken},
            depth='1',
            allowedStatus=(MULTI_STATUS, FORBIDDEN,), 
            otherTokens = True,
            method_label="REPORT{sync}" if calendar.changeToken else "REPORT{sync-init}",
        )
        if result is None:
            if not fullSync:
                fullSync = True
                result = yield self._report(
                    calendar.url,
                    self._POLL_CALENDAR_SYNC_REPORT % {'sync-token': ''},
                    depth='1',
                    otherTokens = True,
                    method_label="REPORT{sync}" if calendar.changeToken else "REPORT{sync-init}",
                )
            else:
                raise IncorrectResponseCode((MULTI_STATUS,), None)
                
        result, others = result
                

        changed = []
        for responseHref in result:
            if responseHref == calendar.url:
                continue

            try:
                etag = result[responseHref].getTextProperties()[davxml.getetag]
            except KeyError:
                # XXX Ignore things with no etag?  Seems to be dropbox.
                continue

            # Differentiate a remove vs new/update result
            if result[responseHref].getStatus() / 100 == 2:
                if responseHref not in self._events:
                    self._setEvent(responseHref, Event(self.serializeLocation(), responseHref, None))
                    
                event = self._events[responseHref]
                if event.etag != etag:
                    changed.append(responseHref)
            elif result[responseHref].getStatus() == 404:
                self._removeEvent(responseHref)

        yield self._updateChangedEvents(calendar, changed)

        # Handle removals only when doing an initial sync
        if fullSync:
            # Detect removed items and purge them
            remove_hrefs = old_hrefs - set(changed)
            for href in remove_hrefs:
                self._removeEvent(href)
            
        # Now update calendar to the new token taken from the report
        for node in others:
            if node.tag == davxml.sync_token:
                newToken = node.text
                break
        self._calendars[calendar.url].changeToken = newToken


    @inlineCallbacks
    def _updateApplyChanges(self, calendar, multistatus, old_hrefs):
        """
        Given a multistatus for an entire collection, sync the reported items
        against the cached items.
        """
        
        # Detect changes and new items
        all_hrefs = []
        changed_hrefs = []
        for responseHref in multistatus:
            if responseHref == calendar.url:
                continue
            all_hrefs.append(responseHref)
            try:
                etag = multistatus[responseHref].getTextProperties()[davxml.getetag]
            except KeyError:
                # XXX Ignore things with no etag?  Seems to be dropbox.
                continue

            if responseHref not in self._events:
                self._setEvent(responseHref, Event(self.serializeLocation(), responseHref, None))
                
            event = self._events[responseHref]
            if event.etag != etag:
                changed_hrefs.append(responseHref)
        
        # Retrieve changes
        yield self._updateChangedEvents(calendar, changed_hrefs)
    
        # Detect removed items and purge them
        remove_hrefs = old_hrefs - set(all_hrefs)
        for href in remove_hrefs:
            self._removeEvent(href)

        
    @inlineCallbacks
    def _updateChangedEvents(self, calendar, changed):
        """
        Given a set of changed hrefs, batch multiget them all to update the
        local cache.
        """

        while changed:
            batchedHrefs = changed[:self.MULTIGET_BATCH_SIZE]
            changed = changed[self.MULTIGET_BATCH_SIZE:]
    
            multistatus = yield self._eventReport(calendar.url, batchedHrefs)
            for responseHref in batchedHrefs:
                try:
                    res = multistatus[responseHref]
                except KeyError:
                    # Resource might have been deleted
                    continue
                if res.getStatus() == 200:
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
        event.component = Component.fromString(body)
        self.catalog["eventChanged"].issue(href)

                
    def _eventReport(self, calendar, events):
        # Next do a REPORT on events that might have information
        # we don't know about.
        hrefs = "".join([self._POLL_CALENDAR_MULTIGET_REPORT_HREF % {'href': event} for event in events])

        label_suffix = "small"
        if len(events) > 5:
            label_suffix = "medium"
        if len(events) > 20:
            label_suffix = "large"
        if len(events) > 75:
            label_suffix = "huge"

        return self._report(
            calendar,
            self._POLL_CALENDAR_MULTIGET_REPORT % {'hrefs': hrefs},
            depth=None,
            method_label="REPORT{multiget-%s}" % (label_suffix,),
        )


    @inlineCallbacks
    def _checkCalendarsForEvents(self, calendarHomeSet, firstTime=False, push=False):
        """
        The actions a client does when polling for changes, or in response to a
        push notification of a change. There are some actions done on the first poll
        we should emulate.
        """

        result = True
        try:
            result = yield self._newOperation("push" if push else "poll", self._poll(calendarHomeSet, firstTime))
        finally:
            if result:
                try:
                    self._checking.remove(calendarHomeSet)
                except KeyError:
                    pass
        returnValue(result)

    @inlineCallbacks
    def _poll(self, calendarHomeSet, firstTime):
        if calendarHomeSet in self._checking:
            returnValue(False)
        self._checking.add(calendarHomeSet)

        calendars, results = yield self._calendarHomePropfind(calendarHomeSet)
        
        # First time operations
        if firstTime:
            yield self._pollFirstTime1(results[calendarHomeSet], calendars)

        # Normal poll
        for cal in calendars:
            newToken = cal.changeToken
            if cal.url not in self._calendars:
                # Calendar seen for the first time - reload it
                self._calendars[cal.url] = cal
                cal.changeToken = ""
                yield self._updateCalendar(self._calendars[cal.url], newToken)
            elif self._calendars[cal.url].changeToken != newToken:
                # Calendar changed - reload it
                yield self._updateCalendar(self._calendars[cal.url], newToken)

        # When there is no sync REPORT, clients have to do a full PROPFIND
        # on the notification collection because there is no ctag
        if self.notificationURL is not None and not self.supportSync:
            yield self._notificationPropfind(self.notificationURL)
            yield self._notificationChangesPropfind(self.notificationURL)

        # One time delegate expansion
        if firstTime:
            yield self._pollFirstTime2()
            
        returnValue(True)

    @inlineCallbacks
    def _pollFirstTime1(self, homeNode, calendars):
        # Detect sync report if needed
        if self.supportSync:
            nodes = homeNode.getNodeProperties()
            syncnodes = nodes[davxml.supported_report_set].findall(
                str(davxml.supported_report) + "/" +
                str(davxml.report) + "/" +
                str(davxml.sync_collection)
            )
            self.supportSync = len(syncnodes) != 0

        # Patch calendar properties
        for cal in calendars:
            if cal.name != "inbox":
                yield self._proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_COLOR,
                    method_label="PROPPATCH{calendar}",
                )
                yield self._proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_ORDER,
                    method_label="PROPPATCH{calendar}",
                )
                yield self._proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_TIMEZONE,
                    method_label="PROPPATCH{calendar}",
                )


    def _pollFirstTime2(self):
        return self._principalExpand(self.principalURL)


    @inlineCallbacks
    def _notificationPropfind(self, notificationURL):
        _ignore_response, result = yield self._propfind(
            notificationURL,
            self._POLL_NOTIFICATION_PROPFIND,
            method_label="PROPFIND{notification}",
        )
        returnValue(result)

    
    @inlineCallbacks
    def _notificationChangesPropfind(self, notificationURL):
        _ignore_response, result = yield self._propfind(
            notificationURL,
            self._POLL_NOTIFICATION_PROPFIND_D1,
            depth='1',
            method_label="PROPFIND{notification-items}",
        )
        returnValue(result)

    
    @inlineCallbacks
    def _principalExpand(self, principalURL):
        result = yield self._report(
            principalURL,
            self._STARTUP_PRINCIPAL_EXPAND,
            depth=None,
            method_label="REPORT{expand}",
        )
        returnValue(result)


    def startup(self):
        raise NotImplementedError


    def _calendarCheckLoop(self, calendarHome):
        """
        Periodically check the calendar home for changes to calendars.
        """
        pollCalendarHome = LoopingCall(
            self._checkCalendarsForEvents, calendarHome)
        return pollCalendarHome.start(self.calendarHomePollInterval, now=False)


    @inlineCallbacks
    def _newOperation(self, label, deferred):
        before = self.reactor.seconds()
        msg(
            type="operation",
            phase="start",
            user=self.record.uid, 
            client_type=self.title,
            client_id=self._client_id,
            label=label,
        )
        
        try:
            result = yield deferred
        except IncorrectResponseCode:
            # Let this through
            success = False
            result = None
        except:
            # Anything else is fatal
            raise
        else:
            success = True
        
        after = self.reactor.seconds()
        msg(
            type="operation",
            phase="end",
            duration=after - before,
            user=self.record.uid,
            client_type=self.title,
            client_id=self._client_id,
            label=label,
            success=success,
        )
        returnValue(result)


    def _monitorPubSub(self, home, params):
        """
        Start monitoring the
        """
        host, port = params.server.split(':')
        port = int(port)

        service, _ignore_stuff = params.uri.split('?')
        service = service.split(':', 1)[1]

        # XXX What is the domain of the 2nd argument supposed to be?  The
        # hostname we use to connect, or the same as the email address in the
        # user record?
        factory = _PubSubClientFactory(
            self, "%s@%s" % (self.record.uid, host),
            self.record.password, service,
            {params.pushkey: (home, home, "Calendar home")}, False,
            sigint=False)
        self._pushFactories.append(factory)
        connect(GAIEndpoint(self.reactor, host, port), factory)

    def _receivedPush(self, inboundID):
        for href, id in self.ampPushKeys.iteritems():
            if inboundID == id:
                self._checkCalendarsForEvents(href, push=True)
                break
        else:
            # somehow we are not subscribed to this id
            pass


    def _monitorAmpPush(self, home, pushKeys):
        """
        Start monitoring for AMP-based push notifications
        """
        subscribeToIDs(self.ampPushHost, self.ampPushPort, pushKeys,
            self._receivedPush, self.reactor)


    @inlineCallbacks
    def _unsubscribePubSub(self):
        for factory in self._pushFactories:
            yield factory.unsubscribeAll()


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
            if calendarHome is None:
                raise MissingCalendarHome
            yield self._checkCalendarsForEvents(calendarHome, firstTime=True)
            returnValue(calendarHome)
        calendarHome = yield self._newOperation("startup: %s" % (self.title,), startup())

        self.started = True

        # Start monitoring PubSub notifications, if possible.
        # _checkCalendarsForEvents populates self.xmpp if it finds
        # anything.
        if self.supportPush and calendarHome in self.xmpp:
            self._monitorPubSub(calendarHome, self.xmpp[calendarHome])
            # Run indefinitely.
            yield Deferred()
        elif self.supportAmpPush and calendarHome in self.ampPushKeys:
            pushKeys = self.ampPushKeys.values()
            self._monitorAmpPush(calendarHome, pushKeys)
            # Run indefinitely.
            yield Deferred()
        else:
            # This completes when the calendar home poll loop completes, which
            # currently it never will except due to an unexpected error.
            yield self._calendarCheckLoop(calendarHome)


    def stop(self):
        """
        Called before connections are closed, giving a chance to clean up
        """
        
        self.serialize()
        return self._unsubscribePubSub()


    def serializeLocation(self):
        """
        Return the path to the directory where data for this user is serialized.
        """
        if self.serializePath is None or not os.path.isdir(self.serializePath):
            return None
        
        key = "%s-%s" % (self.record.uid, self.title.replace(" ", "_"))
        path = os.path.join(self.serializePath, key)
        if not os.path.exists(path):
            os.mkdir(path)
        elif not os.path.isdir(path):
            return None
        
        return path
        
    def serialize(self):
        """
        Write current state to disk.
        """
        
        path = self.serializeLocation()
        if path is None:
            return

        # Create dict for all the data we need to store
        data = {
            "principalURL": self.principalURL,
            "calendars":    [calendar.serialize() for calendar in sorted(self._calendars.values(), key=lambda x:x.name)],
            "events":       [event.serialize() for event in sorted(self._events.values(), key=lambda x:x.url)],
        }

        # Write JSON data
        json.dump(data, open(os.path.join(path, "index.json"), "w"), indent=2)
        

    def deserialize(self):
        """
        Read state from disk.
        """
        
        self._calendars = {}
        self._events = {}

        path = self.serializeLocation()
        if path is None:
            return
        
        # Parse JSON data for calendars
        try:
            data = json.load(open(os.path.join(path, "index.json")))
        except IOError:
            return

        self.principalURL = data["principalURL"]

        # Extract all the events first, then do the calendars (which reference the events)
        for event in data["events"]:
            event = Event.deserialize(self.serializeLocation(), event)
            self._events[event.url] = event
        for calendar in data["calendars"]:
            calendar = Calendar.deserialize(calendar, self._events)
            self._calendars[calendar.url] = calendar
            

    def _makeSelfAttendee(self):
        attendee = Property(
            name=u'ATTENDEE',
            value=self.email,
            params={
                'CN': self.record.commonName,
                'CUTYPE': 'INDIVIDUAL',
                'PARTSTAT': 'ACCEPTED',
            },
        )
        return attendee


    def _makeSelfOrganizer(self):
        organizer = Property(
            name=u'ORGANIZER',
            value=self.email,
            params={
                'CN': self.record.commonName,
            },
        )
        return organizer


    @inlineCallbacks
    def addEventAttendee(self, href, attendee):

        event = self._events[href]
        component = event.component

        # Trigger auto-complete behavior
        yield self._attendeeAutoComplete(component, attendee)

        # If the event has no attendees, add ourselves as an attendee.
        attendees = list(component.mainComponent().properties('ATTENDEE'))
        if len(attendees) == 0:
            # First add ourselves as a participant and as the
            # organizer.  In the future for this event we should
            # already have those roles.
            component.mainComponent().addProperty(self._makeSelfOrganizer())
            component.mainComponent().addProperty(self._makeSelfAttendee())
        attendees.append(attendee)
        component.mainComponent().addProperty(attendee)

        label_suffix = "small"
        if len(attendees) > 5:
            label_suffix = "medium"
        if len(attendees) > 20:
            label_suffix = "large"
        if len(attendees) > 75:
            label_suffix = "huge"
        
        # At last, upload the new event definition
        response = yield self._request(
            (NO_CONTENT, PRECONDITION_FAILED,),
            'PUT',
            self.root + href.encode('utf-8'),
            Headers({
                    'content-type': ['text/calendar'],
                    'if-match': [event.etag]}),
            StringProducer(component.getTextWithTimezones(includeTimezones=True)),
            method_label="PUT{organizer-%s}" % (label_suffix,)
        )

        # Finally, re-retrieve the event to update the etag
        yield self._updateEvent(response, href)


    @inlineCallbacks
    def _attendeeAutoComplete(self, component, attendee):

        if self._ATTENDEE_LOOKUPS:
            # Temporarily use some non-test names (some which will return
            # many results, and others which will return fewer) because the
            # test account names are all too similar
            # name = attendee.parameterValue('CN').encode("utf-8")
            # prefix = name[:4].lower()
            prefix = random.choice(["chris", "cyru", "dre", "eric", "morg",
                "well", "wilfr", "witz"])

            email = attendee.value()
            if email.startswith("mailto:"):
                email = email[7:]
            elif attendee.hasParameter('EMAIL'):
                email = attendee.parameterValue('EMAIL').encode("utf-8")
    
            # First try to discover some names to supply to the
            # auto-completion
            yield self._report(
                self.principalCollection,
                self._USER_LIST_PRINCIPAL_PROPERTY_SEARCH % {
                'displayname': prefix,
                'email': prefix,
                'firstname': prefix,
                'lastname': prefix,
                },
                depth=None,
                method_label="REPORT{psearch}",
           )
    
            # Now learn about the attendee's availability
            yield self.requestAvailability(
                component.mainComponent().getStartDateUTC(),
                component.mainComponent().getEndDateUTC(),
                [self.email, u'mailto:' + email],
                [component.resourceUID()]
            )


    @inlineCallbacks
    def changeEventAttendee(self, href, oldAttendee, newAttendee):
        event = self._events[href]
        component = event.component

        # Change the event to have the new attendee instead of the old attendee
        component.mainComponent().removeProperty(oldAttendee)
        component.mainComponent().addProperty(newAttendee)
        okCodes = NO_CONTENT
        headers = Headers({
                'content-type': ['text/calendar'],
                })
        if event.scheduleTag is not None:
            headers.addRawHeader('if-schedule-tag-match', event.scheduleTag)
            okCodes = (NO_CONTENT, PRECONDITION_FAILED,)

        attendees = list(component.mainComponent().properties('ATTENDEE'))
        label_suffix = "small"
        if len(attendees) > 5:
            label_suffix = "medium"
        if len(attendees) > 20:
            label_suffix = "large"
        if len(attendees) > 75:
            label_suffix = "huge"
        
        response = yield self._request(
            okCodes,
            'PUT',
            self.root + href.encode('utf-8'),
            headers, StringProducer(component.getTextWithTimezones(includeTimezones=True)),
            method_label="PUT{attendee-%s}" % (label_suffix,),
        )

        # Finally, re-retrieve the event to update the etag
        self._updateEvent(response, href)


    @inlineCallbacks
    def deleteEvent(self, href):
        """
        Issue a DELETE for the given URL and remove local state
        associated with that event.
        """
        
        self._removeEvent(href)

        response = yield self._request(
            NO_CONTENT,
            'DELETE',
            self.root + href.encode('utf-8'),
            method_label="DELETE{event}",
        )
        returnValue(response)


    @inlineCallbacks
    def addEvent(self, href, component, invite=False):
        headers = Headers({
                'content-type': ['text/calendar'],
                })

        attendees = list(component.mainComponent().properties('ATTENDEE'))
        label_suffix = "small"
        if len(attendees) > 5:
            label_suffix = "medium"
        if len(attendees) > 20:
            label_suffix = "large"
        if len(attendees) > 75:
            label_suffix = "huge"

        response = yield self._request(
            CREATED,
            'PUT',
            self.root + href.encode('utf-8'),
            headers,
            StringProducer(component.getTextWithTimezones(includeTimezones=True)),
            method_label="PUT{organizer-%s}" % (label_suffix,) if invite else "PUT{event}",
        )
        self._localUpdateEvent(response, href, component)


    @inlineCallbacks
    def addInvite(self, href, component):
        """
        Add an event that is an invite - i.e., has attendees. We will do attendee lookups and freebusy
        checks on each attendee to simulate what happens when an organizer creates a new invite.
        """
        
        # Do lookup and free busy of each attendee (not self)
        attendees = list(component.mainComponent().properties('ATTENDEE'))
        for attendee in attendees:
            if attendee.value() in (self.uuid, self.email):
                continue
            yield self._attendeeAutoComplete(component, attendee)
        
        # Now do a normal PUT
        yield self.addEvent(href, component, invite=True)


    def _localUpdateEvent(self, response, href, component):
        headers = response.headers
        etag = headers.getRawHeaders("etag", [None])[0]
        scheduleTag = headers.getRawHeaders("schedule-tag", [None])[0]

        event = Event(self.serializeLocation(), href, etag, component)
        event.scheduleTag = scheduleTag
        self._setEvent(href, event)


    def updateEvent(self, href):
        return self._updateEvent(None, href)


    @inlineCallbacks
    def _updateEvent(self, ignored, href):
        response = yield self._request(
            OK,
            'GET',
            self.root + href.encode('utf-8'),
            method_label="GET{event}",
        )
        headers = response.headers
        etag = headers.getRawHeaders('etag')[0]
        scheduleTag = headers.getRawHeaders('schedule-tag', [None])[0]
        body = yield readBody(response)
        self.eventChanged(href, etag, scheduleTag, body)


    @inlineCallbacks
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
        outbox = self.root + self.outbox

        if mask:
            maskStr = u'\r\n'.join(['X-CALENDARSERVER-MASK-UID:' + uid
                                    for uid in mask]) + u'\r\n'
        else:
            maskStr = u''
        maskStr = maskStr.encode('utf-8')

        attendeeStr = '\r\n'.join(['ATTENDEE:' + uuid.encode('utf-8')
                                   for uuid in users]) + '\r\n'

        # iCal issues 24 hour wide vfreebusy requests, starting and ending at 4am.
        if start.compareDate(end):
            msg("Availability request spanning multiple days (%r to %r), "
                "dropping the end date." % (start, end))

        start.setTimezone(PyCalendarTimezone(utc=True))
        start.setHHMMSS(0, 0, 0)
        end = start + PyCalendarDuration(hours=24)

        start = start.getText()
        end = end.getText()
        now = PyCalendarDateTime.getNowUTC().getText()

        label_suffix = "small"
        if len(users) > 5:
            label_suffix = "medium"
        if len(users) > 20:
            label_suffix = "large"
        if len(users) > 75:
            label_suffix = "huge"

        response = yield self._request(
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
                    'now': now}),
            method_label="POST{fb-%s}" % (label_suffix,),
        )
        body = yield readBody(response)
        returnValue(body)



class OS_X_10_6(BaseAppleClient):
    """
    Implementation of the OS X 10.6 iCal network behavior.

    Anything OS X 10.6 iCal does on its own, or any particular
    network behaviors it takes in response to a user action, belong on
    this class.

    Usage-profile based behaviors ("the user modifies an event every
    3.2 minutes") belong elsewhere.
    """

    _client_type = "OS X 10.6"

    USER_AGENT = "DAVKit/4.0.3 (732); CalendarStore/4.0.3 (991); iCal/4.0.3 (1388); Mac OS X/10.6.4 (10F569)"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by Snow
    # Leopard iCal.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60
    
    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 200

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = False

    # Override and turn on if client syncs using time-range queries
    _SYNC_TIMERANGE = False

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = True

    # Request body data
    _LOAD_PATH = "OS_X_10_6"

    _STARTUP_WELL_KNOWN = loadRequestBody(_LOAD_PATH, 'startup_well_known')
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind_initial')
    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody(_LOAD_PATH, 'startup_principals_report')
    _STARTUP_PRINCIPAL_EXPAND = loadRequestBody(_LOAD_PATH, 'startup_principal_expand')
    _STARTUP_PROPPATCH_CALENDAR_COLOR = loadRequestBody(_LOAD_PATH, 'startup_calendar_color_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_ORDER = loadRequestBody(_LOAD_PATH, 'startup_calendar_order_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_TIMEZONE = loadRequestBody(_LOAD_PATH, 'startup_calendar_timezone_proppatch')

    _POLL_CALENDARHOME_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendarhome_propfind')
    _POLL_CALENDAR_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_CALENDAR_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind_d1')
    _POLL_CALENDAR_MULTIGET_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget')
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget_hrefs')
    _POLL_CALENDAR_SYNC_REPORT = None
    _POLL_NOTIFICATION_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_NOTIFICATION_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_notification_propfind_d1')

    _USER_LIST_PRINCIPAL_PROPERTY_SEARCH = loadRequestBody(_LOAD_PATH, 'user_list_principal_property_search')
    _POST_AVAILABILITY = loadRequestBody(_LOAD_PATH, 'post_availability')

    @inlineCallbacks
    def startup(self):

        # Try to read data from disk - if it succeeds self.principalURL will be set
        self.deserialize()
        
        if self.principalURL is None:
            # PROPFIND principal path to retrieve actual principal-URL
            response = yield self._principalPropfindInitial(self.record.uid)
            hrefs = response.getHrefProperties()
            self.principalURL = hrefs[davxml.principal_URL].toString()

        # Using the actual principal URL, retrieve principal information
        principal = (yield self._extractPrincipalDetails())
        returnValue(principal)


class OS_X_10_7(BaseAppleClient):
    """
    Implementation of the OS X 10.7 iCal network behavior.
    """

    _client_type = "OS X 10.7"

    USER_AGENT = "CalendarStore/5.0.2 (1166); iCal/5.0.2 (1571); Mac OS X/10.7.3 (11D50)"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by Snow
    # Leopard iCal.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60
    
    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 50

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = True

    # Override and turn on if client syncs using time-range queries
    _SYNC_TIMERANGE = False

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = True

    # Request body data
    _LOAD_PATH = "OS_X_10_7"

    _STARTUP_WELL_KNOWN = loadRequestBody(_LOAD_PATH, 'startup_well_known')
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind_initial')
    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody(_LOAD_PATH, 'startup_principals_report')
    _STARTUP_PRINCIPAL_EXPAND = loadRequestBody(_LOAD_PATH, 'startup_principal_expand')
    _STARTUP_PROPPATCH_CALENDAR_COLOR = loadRequestBody(_LOAD_PATH, 'startup_calendar_color_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_ORDER = loadRequestBody(_LOAD_PATH, 'startup_calendar_order_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_TIMEZONE = loadRequestBody(_LOAD_PATH, 'startup_calendar_timezone_proppatch')

    _POLL_CALENDARHOME_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendarhome_propfind')
    _POLL_CALENDAR_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_CALENDAR_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind_d1')
    _POLL_CALENDAR_MULTIGET_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget')
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget_hrefs')
    _POLL_CALENDAR_SYNC_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_sync')
    _POLL_NOTIFICATION_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_NOTIFICATION_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_notification_propfind_d1')

    _USER_LIST_PRINCIPAL_PROPERTY_SEARCH = loadRequestBody(_LOAD_PATH, 'user_list_principal_property_search')
    _POST_AVAILABILITY = loadRequestBody(_LOAD_PATH, 'post_availability')


    def _addDefaultHeaders(self, headers):
        """
        Add the clients default set of headers to ones being used in a request.
        Default is to add User-Agent, sub-classes should override to add other
        client specific things, Accept etc.
        """
        
        super(OS_X_10_7, self)._addDefaultHeaders(headers)
        headers.setRawHeaders('Accept', ['*/*'])
        headers.setRawHeaders('Accept-Language', ['en-us'])
        headers.setRawHeaders('Accept-Encoding', ['gzip,deflate'])
        headers.setRawHeaders('Connection', ['keep-alive'])


    @inlineCallbacks
    def startup(self):

        # Try to read data from disk - if it succeeds self.principalURL will be set
        self.deserialize()
        
        if self.principalURL is None:
            # PROPFIND well-known with redirect
            response = yield self._startupPropfindWellKnown()
            hrefs = response.getHrefProperties()
            if davxml.current_user_principal in hrefs:
                self.principalURL = hrefs[davxml.current_user_principal].toString()
            elif davxml.principal_URL in hrefs:
                self.principalURL = hrefs[davxml.principal_URL].toString()
            else:
                # PROPFIND principal path to retrieve actual principal-URL
                response = yield self._principalPropfindInitial(self.record.uid)
                hrefs = response.getHrefProperties()
                self.principalURL = hrefs[davxml.principal_URL].toString()

        # Using the actual principal URL, retrieve principal information
        principal = yield self._extractPrincipalDetails()
        returnValue(principal)



class iOS_5(BaseAppleClient):
    """
    Implementation of the iOS 5 network behavior.
    """

    _client_type = "iOS 5"

    USER_AGENT = "iOS/5.1 (9B179) dataaccessd/1.0"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by Snow
    # Leopard iCal.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60
    
    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 50

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = False

    # Override and turn on if client syncs using time-range queries
    _SYNC_TIMERANGE = True

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = False

    # Request body data
    _LOAD_PATH = "iOS_5"

    _STARTUP_WELL_KNOWN = loadRequestBody(_LOAD_PATH, 'startup_well_known')
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind_initial')
    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody(_LOAD_PATH, 'startup_principals_report')
    _STARTUP_PROPPATCH_CALENDAR_COLOR = loadRequestBody(_LOAD_PATH, 'startup_calendar_color_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_ORDER = loadRequestBody(_LOAD_PATH, 'startup_calendar_order_proppatch')

    _POLL_CALENDARHOME_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendarhome_propfind')
    _POLL_CALENDAR_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_CALENDAR_VEVENT_TR_QUERY = loadRequestBody(_LOAD_PATH, 'poll_calendar_vevent_tr_query')
    _POLL_CALENDAR_VTODO_QUERY = loadRequestBody(_LOAD_PATH, 'poll_calendar_vtodo_query')
    _POLL_CALENDAR_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind_d1')
    _POLL_CALENDAR_MULTIGET_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget')
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget_hrefs')


    def _addDefaultHeaders(self, headers):
        """
        Add the clients default set of headers to ones being used in a request.
        Default is to add User-Agent, sub-classes should override to add other
        client specific things, Accept etc.
        """
        
        super(iOS_5, self)._addDefaultHeaders(headers)
        headers.setRawHeaders('Accept', ['*/*'])
        headers.setRawHeaders('Accept-Language', ['en-us'])
        headers.setRawHeaders('Accept-Encoding', ['gzip,deflate'])
        headers.setRawHeaders('Connection', ['keep-alive'])


    @inlineCallbacks
    def _pollFirstTime1(self, homeNode, calendars):
        # Patch calendar properties
        for cal in calendars:
            if cal.name != "inbox":
                yield self._proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_COLOR,
                    method_label="PROPPATCH{calendar}",
                )
                yield self._proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_ORDER,
                    method_label="PROPPATCH{calendar}",
                )


    def _pollFirstTime2(self):
        # Nothing here
        return succeed(None)


    def _updateCalendar(self, calendar, newToken):
        """
        Update the local cached data for a calendar in an appropriate manner.
        """
        if calendar.name == "inbox":
            # Inbox is done as a PROPFIND Depth:1
            return self._updateCalendar_PROPFIND(calendar, newToken)
        elif "VEVENT" in calendar.componentTypes:
            # VEVENTs done as time-range VEVENT-only queries
            return self._updateCalendar_VEVENT(calendar, newToken)
        elif "VTODO" in calendar.componentTypes:
            # VTODOs done as VTODO-only queries
            return self._updateCalendar_VTODO(calendar, newToken)


    @inlineCallbacks
    def _updateCalendar_VEVENT(self, calendar, newToken):
        """
        Sync all locally cached VEVENTs using a VEVENT-only time-range query.
        """

        # Grab old hrefs prior to the PROPFIND so we sync with the old state. We need this because
        # the sim can fire a PUT between the PROPFIND and when process the removals.
        old_hrefs = set([calendar.url + child for child in calendar.events.keys()])

        now = PyCalendarDateTime.getNowUTC()
        now.setDateOnly(True)
        now.offsetMonth(-1) # 1 month back default
        result = yield self._report(
            calendar.url,
            self._POLL_CALENDAR_VEVENT_TR_QUERY % {"start-date":now.getText()},
            depth='1',
            method_label="REPORT{vevent}",
        )

        yield self._updateApplyChanges(calendar, result, old_hrefs)

        # Now update calendar to the new token
        self._calendars[calendar.url].changeToken = newToken


    @inlineCallbacks
    def _updateCalendar_VTODO(self, calendar, newToken):
        """
        Sync all locally cached VTODOs using a VTODO-only query.
        """

        # Grab old hrefs prior to the PROPFIND so we sync with the old state. We need this because
        # the sim can fire a PUT between the PROPFIND and when process the removals.
        old_hrefs = set([calendar.url + child for child in calendar.events.keys()])

        result = yield self._report(
            calendar.url,
            self._POLL_CALENDAR_VTODO_QUERY,
            depth='1',
            method_label="REPORT{vtodo}",
        )

        yield self._updateApplyChanges(calendar, result, old_hrefs)

        # Now update calendar to the new token
        self._calendars[calendar.url].changeToken = newToken


    @inlineCallbacks
    def startup(self):

        # Try to read data from disk - if it succeeds self.principalURL will be set
        self.deserialize()
        
        if self.principalURL is None:
            # PROPFIND well-known with redirect
            response = yield self._startupPropfindWellKnown()
            hrefs = response.getHrefProperties()
            if davxml.current_user_principal in hrefs:
                self.principalURL = hrefs[davxml.current_user_principal].toString()
            elif davxml.principal_URL in hrefs:
                self.principalURL = hrefs[davxml.principal_URL].toString()
            else:
                # PROPFIND principal path to retrieve actual principal-URL
                response = yield self._principalPropfindInitial(self.record.uid)
                hrefs = response.getHrefProperties()
                self.principalURL = hrefs[davxml.principal_URL].toString()

        # Using the actual principal URL, retrieve principal information
        principal = yield self._extractPrincipalDetails()
        returnValue(principal)


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


    def report(self, output):
        pass


    def failures(self):
        return []


    
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
    client = OS_X_10_6(
        reactor, 'http://127.0.0.1:8008/', 
        _DirectoryRecord(
            u'user01', u'user01', u'User 01', u'user01@example.org'),
        auth)
    d = client.run()
    d.addErrback(err, "10.6 client run() problem")
    d.addCallback(lambda ignored: reactor.stop())
    reactor.run()


if __name__ == '__main__':
    main()
