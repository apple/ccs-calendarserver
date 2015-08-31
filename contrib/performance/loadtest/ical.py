##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
from __future__ import print_function

from caldavclientlibrary.protocol.caldav.definitions import caldavxml
from caldavclientlibrary.protocol.caldav.definitions import csxml
from caldavclientlibrary.protocol.webdav.definitions import davxml
from caldavclientlibrary.protocol.url import URL

from contrib.performance.httpclient import readBody
from contrib.performance.loadtest.pubsub import Publisher
from contrib.performance.loadtest.resources import Event, Calendar
from contrib.performance.loadtest.requester import Requester, IncorrectResponseCode
from contrib.performance.loadtest.push import PushMonitor

from pycalendar.datetime import DateTime
from pycalendar.duration import Duration
from pycalendar.timezone import Timezone

from twisted.internet.task import LoopingCall
from twisted.internet.defer import succeed, Deferred, inlineCallbacks, returnValue
from twisted.python.log import err, msg
from twisted.web.http import OK, MULTI_STATUS, CREATED, NO_CONTENT, FORBIDDEN, PRECONDITION_FAILED, MOVED_PERMANENTLY, FOUND
from twisted.web.http_headers import Headers

from twistedcaldav.ical import Component, Property

from urlparse import urlparse, urlsplit
from uuid import uuid4
from xml.etree import ElementTree

import json
import os
import random

"""
run
  startup
    deserialize
    _startupPropfindWellKnown
    _principalPropfindInitial
    _extractPrincipalDetails
    _checkCalendarsForEvents
"""


ElementTree.QName.__repr__ = lambda self: '<QName %r>' % (self.text,)

SUPPORTED_REPORT_SET = davxml.supported_report_set.text

class Attendee(Property):
    def __init__(self, ):
        pass


class MissingCalendarHome(Exception):
    """
    Raised when the calendar home for a user is 404
    """


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


    def _cacheEvent(self, href, event):
        """
        Cache the provided event
        """
        self._events[href] = event
        calendar, basePath = href.rsplit('/', 1)
        self._calendars[calendar + '/'].events[basePath] = event


    def _invalidateEvent(self, href):
        """
        Remove event from local cache.
        """
        self._events[href].removed()
        del self._events[href]
        calendar, basePath = href.rsplit('/', 1)
        del self._calendars[calendar + '/'].events[basePath]


    def _cacheCalendar(self, href, calendar):
        """
        Cache the provided L{Calendar}
        """
        self._calendars[href] = calendar


    def _invalidateCalendar(self, href):
        """
        Remove calendar from the local cache
        """
        if href in self._calendars:
            del self._calendars[href]


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


    def changeEvent(self, href, calendar):
        """
        Called when a profile needs to change an event (no scheduling).
        """
        raise NotImplementedError("%r does not implement changeEvent" % (self.__class__,))


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

    def addCalendar(self, href, calendar):
        """
        Called when a profile needs to add a new calendar.
        """
        raise NotImplementedError("%r does not implement addCalendar" % (self.__class__,))

    def changeCalendar(self, href, calendar):
        """
        Called when a profile needs to change a calendar.
        """
        raise NotImplementedError("%r does not implement changeCalendar" % (self.__class__,))


    def deleteCalendar(self, href):
        """
        Called when a profile needs to delete a calendar.
        """
        raise NotImplementedError("%r does not implement deleteCalendar" % (self.__class__,))





class BaseAppleClient(BaseClient):
    """
    Implementation of common OS X/iOS client behavior.
    """

    _client_type = "Generic"

    # Override this for specific clients
    USER_AGENT = None

    # The default interval, used if none is specified in external
    # configuration.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60

    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 200

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = False

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
        serializePath,
        record,
        auth,
        title=None,
        calendarHomePollInterval=None,
        supportAmpPush=True,
        ampPushHost=None,
        ampPushPort=62311,
    ):
        self._client_id = str(uuid4())
        self.reactor = reactor

        self.requester = Requester(
            root, self.getDefaultHeaders(), title,
            record.uid, self._client_id, auth, self.reactor
        )
        self.record = record

        self.title = title if title else self._client_type

        if calendarHomePollInterval is None:
            calendarHomePollInterval = self.CALENDAR_HOME_POLL_INTERVAL
        self.calendarHomePollInterval = calendarHomePollInterval

        if supportAmpPush:
            if ampPushHost is None:
                ampPushHost = urlparse(root)[1].split(":")[0]
            self.monitor = PushMonitor(self.reactor, ampPushHost, ampPushPort, self.updateCalendarHomeFromPush)
        else:
            self.monitor = None

        self.serializePath = serializePath

        self.supportSync = self._SYNC_REPORT

        # The principalURL found during discovery
        self.principalURL = None

        # The principal collection found during startup
        self.principalCollection = None

        # Keep track of the calendars on this account, keys are
        # Calendar URIs, values are Calendar instances.
        self._calendars = {}

        # Keep track of the events on this account, keys are event
        # URIs (which are unambiguous across different calendars
        # because they start with the uri of the calendar they are
        # part of), values are Event instances.
        self._events = {}

        # Allow events to go out into the world.
        self.catalog = {
            "eventChanged": Publisher(),
        }

        self._checking = set()

    _CALENDAR_TYPES = set([
        caldavxml.calendar,
        caldavxml.schedule_inbox,
    ])

    def getDefaultHeaders(self):
        return {
            'User-Agent': [self.USER_AGENT],
            'Accept': ['*/*'],
            'Accept-Language': ['en-us'],
            'Accept-Encoding': ['gzip,deflate'],
            'Connection': ['keep-alive']
        }

    @inlineCallbacks
    def _startupPropfindWellKnown(self):
        """
        Issue a PROPFIND on the /.well-known/caldav/ URL
        """

        location = "/.well-known/caldav/"
        response, result = yield self.requester.propfind(
            location,
            self._STARTUP_WELL_KNOWN,
            allowedStatus=(MULTI_STATUS, MOVED_PERMANENTLY, FOUND,),
            method_label="PROPFIND{well-known}",
        )

        # Follow any redirect
        if response.code in (MOVED_PERMANENTLY, FOUND,):
            location = response.headers.getRawHeaders("location")[0]
            location = urlsplit(location)[2]
            response, result = yield self.requester.propfind(
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
        principalPath = '/principals/users/%s' % (user,)
        _ignore_response, result = yield self.requester.propfind(
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
        _ignore_response, result = yield self.requester.propfind(
            self.principalURL,
            self._STARTUP_PRINCIPAL_PROPFIND,
            method_label="PROPFIND{principal}",
        )
        returnValue(result[self.principalURL])


    def _principalSearchPropertySetReport(self, principalCollectionSet):
        """
        Issue a principal-search-property-set REPORT against the chosen URL
        """
        return self.requester.report(
            principalCollectionSet,
            self._STARTUP_PRINCIPALS_REPORT,
            allowedStatus=(OK,),
            method_label="REPORT{pset}",
        )


    @inlineCallbacks
    def _extractPrincipalDetails(self):
        # Using the actual principal URL, retrieve principal information
        # XXX We could be recording more information here
        principal = yield self._principalPropfind()

        hrefs = principal.getHrefProperties()
        # from pprint import pprint
        # pprint(hrefs)

        # Remember our outbox and ignore notifications
        self.outbox = hrefs[caldavxml.schedule_outbox_URL].toString()
        self.notificationURL = None

        # Remember our own email-like principal address
        self.email = None
        self.uuid = None
        cuaddrs = hrefs[caldavxml.calendar_user_address_set]
        if isinstance(cuaddrs, URL):
            cuaddrs = (cuaddrs,)
        for cuaddr in cuaddrs:
            if cuaddr.toString().startswith(u"mailto:"):
                self.email = cuaddr.toString()
            elif cuaddr.toString().startswith(u"urn:x-uid"):
                self.uuid = cuaddr.toString()
            elif cuaddr.toString().startswith(u"urn:uuid") and self.uuid is None:
                self.uuid = cuaddr.toString()
        if self.email is None:
            raise ValueError("Cannot operate without a mail-style principal URL")

        # Do another kind of thing I guess
        self.principalCollection = hrefs[davxml.principal_collection_set].toString()
        yield self._principalSearchPropertySetReport(self.principalCollection)

        returnValue(principal)

    def startup(self):
        """
        Overridden by subclasses of BaseAppleClient.
        """
        raise NotImplementedError

    def calendarCheckLoop(self, calendarHome):
        """
        Periodically check the calendar home for changes to calendars.
        """
        pollCalendarHome = LoopingCall(
            self.checkCalendarsForEvents, calendarHome)
        return pollCalendarHome.start(self.calendarHomePollInterval, now=False)

    ### TODO this doesn't seem to always work
    @inlineCallbacks
    def updateCalendarHomeFromPush(self, calendarHomeSet):
        """
        Emulate the client behavior upon receiving a notification that the
        given calendar home has changed.
        """
        # Todo - ensure that the self._checking set is properly cleared even if there is an error
        self._checking.add(calendarHomeSet)
        result = yield self._poll(calendarHomeSet, firstTime=False)

        # Todo - should this be a returnValue?
        yield self._newOperation("push", result)

    @inlineCallbacks
    def checkCalendarsForEvents(self, calendarHomeSet, firstTime=False):
        """
        The actions a client does when polling for changes, or in response to a
        push notification of a change. There are some actions done on the first poll
        we should emulate.
        """

        result = True
        try:
            result = yield self._newOperation("poll", self._poll(calendarHomeSet, firstTime))
        finally:
            if result:
                try:
                    self._checking.remove(calendarHomeSet)
                except KeyError:
                    pass
        returnValue(result)

    """
    REFRESH UTILITIES
    """

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
            # yield self._pollFirstTime2()
            pass

        returnValue(True)

    @inlineCallbacks
    def _calendarHomePropfind(self, calendarHomeSet):
        """
        Do the poll Depth:1 PROPFIND on the calendar home.
        """
        if not calendarHomeSet.endswith('/'):
            calendarHomeSet = calendarHomeSet + '/'
        _ignore_response, result = yield self.requester.propfind(
            calendarHomeSet,
            self._POLL_CALENDARHOME_PROPFIND,
            depth='1',
            method_label="PROPFIND{home}",
        )
        calendars = self._extractCalendars(result, calendarHomeSet)
        returnValue((calendars, result,))


    def _extractCalendars(self, results, calendarHome=None):
        """
        Parse a calendar home PROPFIND response and create local state
        representing the calendars it contains.
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
                    if pushkey and self.monitor:
                        self.monitor.addPushkey(pushkey, href)

            nodes = results[href].getNodeProperties()
            for nodeType in nodes[davxml.resourcetype]:
                if nodeType.tag in self._CALENDAR_TYPES:
                    textProps = results[href].getTextProperties()
                    componentTypes = set()
                    if nodeType.tag == caldavxml.calendar:
                        if caldavxml.supported_calendar_component_set in nodes:
                            for comp in nodes[caldavxml.supported_calendar_component_set]:
                                componentTypes.add(comp.get("name").upper())

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
                # yield self.requester.proppatch(
                #     cal.url,
                #     self._STARTUP_PROPPATCH_CALENDAR_COLOR,
                #     method_label="PROPPATCH{calendar}",
                # )
                yield self.requester.proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_ORDER,
                    method_label="PROPPATCH{calendar}",
                )
                yield self.requester.proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_TIMEZONE,
                    method_label="PROPPATCH{calendar}",
                )


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

        _ignore_response, result = yield self.requester.propfind(
            calendar.url,
            self._POLL_CALENDAR_PROPFIND_D1,
            method_label="PROPFIND{calendar}",
            depth='1',
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
        result = yield self.requester.report(
            calendar.url,
            self._POLL_CALENDAR_SYNC_REPORT % {'sync-token': calendar.changeToken},
            depth='1',
            allowedStatus=(MULTI_STATUS, FORBIDDEN,),
            otherTokens=True,
            method_label="REPORT{sync}" if calendar.changeToken else "REPORT{sync-init}",
        )
        if result is None:
            if not fullSync:
                fullSync = True
                result = yield self.requester.report(
                    calendar.url,
                    self._POLL_CALENDAR_SYNC_REPORT % {'sync-token': ''},
                    depth='1',
                    otherTokens=True,
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
                    self._cacheEvent(responseHref, Event(self.serializeLocation(), responseHref, None))

                event = self._events[responseHref]
                if event.etag != etag:
                    changed.append(responseHref)
            elif result[responseHref].getStatus() == 404:
                self._invalidateEvent(responseHref)

        yield self._updateChangedEvents(calendar, changed)

        # Handle removals only when doing an initial sync
        if fullSync:
            # Detect removed items and purge them
            remove_hrefs = old_hrefs - set(changed)
            for href in remove_hrefs:
                self._invalidateEvent(href)

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
                self._cacheEvent(responseHref, Event(self.serializeLocation(), responseHref, None))

            event = self._events[responseHref]
            if event.etag != etag:
                changed_hrefs.append(responseHref)

        # Retrieve changes
        yield self._updateChangedEvents(calendar, changed_hrefs)

        # Detect removed items and purge them
        remove_hrefs = old_hrefs - set(all_hrefs)
        for href in remove_hrefs:
            self._invalidateEvent(href)


    @inlineCallbacks
    def _updateChangedEvents(self, calendar, changed):
        """
        Given a set of changed hrefs, batch multiget them all to update the
        local cache.
        """

        changed.sort()
        while changed:
            batchedHrefs = changed[:self.MULTIGET_BATCH_SIZE]
            changed = changed[self.MULTIGET_BATCH_SIZE:]

            multistatus = yield self._eventReport(calendar.url, batchedHrefs)
            for href in batchedHrefs:
                try:
                    res = multistatus[href]
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
                    component = Component.fromString(body)
                    self._updateEventCache(href, etag, scheduleTag, component)


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

        return self.requester.report(
            calendar,
            self._POLL_CALENDAR_MULTIGET_REPORT % {'hrefs': hrefs},
            depth=None,
            method_label="REPORT{multiget-%s}" % (label_suffix,),
        )


    @inlineCallbacks
    def _notificationPropfind(self, notificationURL):
        _ignore_response, result = yield self.requester.propfind(
            notificationURL,
            self._POLL_NOTIFICATION_PROPFIND,
            method_label="PROPFIND{notification}",
        )
        returnValue(result)


    @inlineCallbacks
    def _notificationChangesPropfind(self, notificationURL):
        _ignore_response, result = yield self.requester.propfind(
            notificationURL,
            self._POLL_NOTIFICATION_PROPFIND_D1,
            depth='1',
            method_label="PROPFIND{notification-items}",
        )
        returnValue(result)

    def _pollFirstTime2(self):
        return self._principalExpand(self.principalURL)

    @inlineCallbacks
    def _principalExpand(self, principalURL):
        result = yield self.requester.report(
            principalURL,
            self._STARTUP_PRINCIPAL_EXPAND,
            depth=None,
            method_label="REPORT{expand}",
        )
        returnValue(result)



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
            yield self.checkCalendarsForEvents(calendarHome, firstTime=True)
            returnValue(calendarHome)
        calendarHome = yield self._newOperation("startup: %s" % (self.title,), startup())
        self.started = True

        # Start monitoring AMP push notifications, if possible
        if self.monitor and self.monitor.isSubscribedTo(calendarHome):
            yield self.monitor.begin()
            # Run indefinitely.
            yield Deferred()
        else:
            # This completes when the calendar home poll loop completes, which
            # currently it never will except due to an unexpected error.
            yield self.calendarCheckLoop(calendarHome)


    def stop(self):
        """
        Called before connections are closed, giving a chance to clean up
        """
        self.serialize()
        if not self.monitor:
            return succeed(None)
        return self.monitor.end()


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
            "calendars": [calendar.serialize() for calendar in sorted(self._calendars.values(), key=lambda x:x.name)],
            "events": [event.serialize() for event in sorted(self._events.values(), key=lambda x:x.url)],
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

    def _getEventSizeDescription(self, numAttendees):
        if numAttendees > 75:
            return "huge"
        if numAttendees > 20:
            return "large"
        if numAttendees > 5:
            return "medium"
        return "small"

    """ literally wtf is this event stuff
submitEvent(event: Event, )

"""
    @inlineCallbacks
    def addEventAttendee(self, href, attendee):
        individual = attendee.parameterValue('CUTYPE') == 'INDIVIDUAL'

        event = self._events[href]
        component = event.component
        vevent = component.mainComponent()

        query = attendee.parameterValue('CN')

        from pprint import pprint
        # Trigger auto-complete behavior
        matchingPrincipals = yield self._principalSearchReport(query, isAttendeeSearch=individual)
        for k, v in matchingPrincipals.items():
            pprint(k)
            for prop, val in v.getNodeProperties().items():
                print("%s %s" % (prop, val.__dict__))
                for child in val._children:
                    print(child.text)

        uuids = []

        for principal_url, propfindresult in matchingPrincipals.items():
            props = propfindresult.getNodeProperties()
            for cuaddr in props.get(caldavxml.calendar_user_address_set):
                # print(cuaddr)
                uuids.append(cuaddr.text)
                break

        print(uuids)


        start = vevent.getStartDateUTC()
        end = vevent.getEndDateUTC()

        yield self.requestAvailability(start, end, uuids)

        # # Do free-busy lookups
        # if individual:
        #     # When adding individual attendees, we only look up the availability
        #     # of the specific attendee
        #     yield self.checkAvailability()
        # else:
        #     # When adding a location, we look up the availability of each location
        #     # returned by the principal search.
        #     yield self.checkAvailability()


    @inlineCallbacks
    def changeEventAttendee(self, href, oldAttendee, newAttendee):
        event = self._events[href]
        component = event.component

        # Change the event to have the new attendee instead of the old attendee
        component.mainComponent().removeProperty(oldAttendee)
        component.mainComponent().addProperty(newAttendee)

        headers = Headers()
        if event.scheduleTag is not None:
            headers.addRawHeader('if-schedule-tag-match', event.scheduleTag)
        event.component = component
        attendees = list(component.mainComponent().properties('ATTENDEE'))
        label_suffix = self._getEventSizeDescription(len(attendees))
        method_label = "PUT{attendee-%s}" % (label_suffix,)

        yield self.putEvent(href, event, headers=headers, method_label=method_label, new=False)


    @inlineCallbacks
    def addInvite(self, event):
        """
        Add an event that is an invite - i.e., has attendees. Presumably the appropriate principal searches and
        free-busy lookups have already been accounted for (in addEventAttendee)
        """
        vevent = event.component.mainComponent()
        # If the event has no attendees, add ourselves as an attendee.
        attendees = list(vevent.properties('ATTENDEE'))
        if len(attendees) == 0:
            # First add ourselves as a participant and as the
            # organizer.  In the future for this event we should
            # already have those roles.
            vevent.addProperty(self._makeSelfOrganizer())
            vevent.addProperty(self._makeSelfAttendee())

        label_suffix = self._getEventSizeDescription(len(attendees))
        method_label = "PUT{organizer-%s}" % (label_suffix,)

        yield self.updateEvent(event, method_label=method_label)


    @inlineCallbacks
    def addEvent(self, href, event):
        """
        client.addEvent(
            Event e
        """
        headers = Headers({
            'if-none-match': ['*']
        })
        yield self.putEvent(
            href,
            event,
            headers=headers,
            method_label="PUT{event}"
        )

    # attendees = list(component.mainComponent().properties('ATTENDEE'))
    # label_suffix = self._getEventSizeDescription(len(attendees))
    # method_label = "PUT{organizer-%s}" % (label_suffix,) if invite else "PUT{event}"

    @inlineCallbacks
    def updateEvent(self, event, method_label="PUT{event}"):
        headers = Headers({
            'if-match': [event.etag]
        })
        yield self.putEvent(event.url, event, headers=headers, method_label=method_label)


    @inlineCallbacks
    def putEvent(self, href, event, headers=None, method_label=None):
        """
        PUT an event to the server
        """
        if headers == None:
            headers = Headers()
        headers.addRawHeader('content-type', 'text/calendar')

        okCodes = (CREATED, NO_CONTENT, PRECONDITION_FAILED)

        # At last, upload the new event definition
        response = yield self.requester.put(
            okCodes,
            href,
            event.component,
            headers=headers,
            method_label=method_label
        )
        # If the server doesn't return an etag, it has changed the resource
        # and we need to refetch it
        if not response.headers.hasHeader('etag'):
            yield self._refreshEvent(href)
        else:
            etag, scheduleTag = self.extractTags(response)
            yield succeed(self._updateEventCache(href, etag=etag, scheduleTag=scheduleTag, component=event.component))


    @inlineCallbacks
    def _refreshEvent(self, href):
        """
        Issues a GET to the specified href (representing an event that already exists on the server)
        and uses the response to update local state associated with that event
        """
        response = yield self.requester.get(href, method_label="GET{event}")
        etag, scheduleTag = self.extractTags(response)
        body = yield readBody(response)
        component = Component.fromString(body)
        self._updateEventCache(href, etag=etag, scheduleTag=scheduleTag, component=component)

    def _updateEventCache(self, href, etag=None, scheduleTag=None, component=None):
        """
        Update local state associated with the event at href
        """

        if href in self._events:
            event = self._events[href]
        else: # This is a new resource
            event = Event(self.serializeLocation(), href, None, None)

        if etag:
            event.etag = etag
        if scheduleTag:
            event.scheduleTag = scheduleTag
        if component:
            event.component = component

        if True: # XXX some other test
            self.catalog["eventChanged"].issue(href)
        self._cacheEvent(href, event)

    @inlineCallbacks
    def deleteEvent(self, href):
        """
        Issue a DELETE for the given URL and remove local state
        associated with that event.
        """
        self._invalidateEvent(href)
        yield self.requester.delete(href, method_label="DELETE{event}")

    def extractTags(self, response):
        headers = response.headers
        etag = headers.getRawHeaders("etag", [None])[0]
        scheduleTag = headers.getRawHeaders("schedule-tag", [None])[0]
        return etag, scheduleTag

    # @inlineCallbacks
    # def _attendeeAutoComplete(self, component, attendee):

    #     if self._ATTENDEE_LOOKUPS:
    #         # Temporarily use some non-test names (some which will return
    #         # many results, and others which will return fewer) because the
    #         # test account names are all too similar
    #         # name = attendee.parameterValue('CN').encode("utf-8")
    #         # prefix = name[:4].lower()
    #         prefix = random.choice([
    #             "chris", "cyru", "dre", "eric", "morg",
    #             "well", "wilfr", "witz"
    #         ])

    #         email = attendee.value()
    #         if email.startswith("mailto:"):
    #             email = email[7:]
    #         elif attendee.hasParameter('EMAIL'):
    #             email = attendee.parameterValue('EMAIL').encode("utf-8")

    #         # First try to discover some names to supply to the
    #         # auto-completion
    #         yield self.requester.report(
    #             self.principalCollection,
    #             self._USER_LIST_PRINCIPAL_PROPERTY_SEARCH % {
    #                 'displayname': prefix,
    #                 'email': prefix,
    #                 'firstname': prefix,
    #                 'lastname': prefix,
    #             },
    #             depth=None,
    #             method_label="REPORT{psearch}",
    #         )

    #         # Now learn about the attendee's availability
    #         yield self.requestAvailability(
    #             component.mainComponent().getStartDateUTC(),
    #             component.mainComponent().getEndDateUTC(),
    #             [self.email, u'mailto:' + email],
    #             [component.resourceUID()]
    #         )

    @inlineCallbacks
    def _principalSearchReport(self, query, isAttendeeSearch):
        """ context = attendee if isAttendeeSearch else location """
        context = "attendee" if isAttendeeSearch else "location"
        tokens = query.split()
        search = '\n'.join(["<C:search-token>%s</C:search-token>" % (token, ) for token in tokens])
        body = self._CALENDARSERVER_PRINCIPAL_SEARCH_REPORT.format(context=context, searchTokens=search)
        principals = yield self.requester.report('/principals/', body, depth=None)
        print("Found some principals:")
        returnValue(principals)

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

        start.setTimezone(Timezone.UTCTimezone)
        start.setHHMMSS(0, 0, 0)
        end = start + Duration(hours=24)

        start = start.getText()
        end = end.getText()
        now = DateTime.getNowUTC().getText()

        label_suffix = self._getEventSizeDescription(len(users))

        headers = Headers({
            'content-type': ['text/calendar'],
            'originator': [self.email],
            'recipient': [u', '.join(users).encode('utf-8')]
        })
        response = yield self.requester.post(
            self.outbox,
            self._POST_AVAILABILITY % {
                'attendees': attendeeStr,
                'summary': (u'Availability for %s' % (', '.join(users),)).encode('utf-8'),
                'organizer': self.email.encode('utf-8'),
                'vfreebusy-uid': str(uuid4()).upper(),
                'event-mask': maskStr,
                'start': start,
                'end': end,
                'now': now,
            },
            headers=headers,
            method_label="POST{fb-%s}" % (label_suffix,),
        )

        body = yield readBody(response)
        returnValue(body)

    @inlineCallbacks
    def postAttachment(self, href, content):
        url = "{0}?{1}".format(href, "action=attachment-add")
        filename = 'file-{}.txt'.format(len(content))
        headers = Headers({
        #     'Transfer-Encoding': ['Chunked'],
            'Content-Disposition': ['attachment; filename="{}"'.format(filename)]
        })
        l = len(content)
        # lengthPrefix = hex(l)[2:].upper() # For some reason, this attachment is length-prefixed in hex
        label_suffix = self._getEventSizeDescription(l / 1024)
        # body = "{0}\n{1}\n0\n".format(lengthPrefix, content) # XXX There HAS to be a better way to do this
        yield self.requester.post(
            url,
            content,
            headers=headers,
            method_label="POST{attach-%s}" % (label_suffix,)
        )

    @inlineCallbacks
    def addCalendar(self, href, calendar_xml):
        """
        client.addCalendar(
            '/calendars/__uids__/10000000-0000-0000-0000-000000000001/1C1A8475-2671-4B97-AC58-DD9777B5CD93/',
            # <Component: 'BEGIN:VCALENDAR\r\n...END:VCALENDAR\r\n'>)
        )
        """
        response = yield self.requester.mkcalendar(
            href,
            calendar_xml,
            method_label="MK{calendar}",
        )
        # self._cacheCalendar(href, calendar)


    @inlineCallbacks
    def changeCalendar(self, href, body):

        calendar = self._calendars[href]
        headers = Headers({
            'content-type': ['text/xml']
        })

        # At last, upload the new event definition
        response = yield self.requester.proppatch(
            href,
            body,
            headers=headers,
            method_label="PATCH{calendar}"
        )

        # Finally, re-retrieve the event to update the etag
        # yield self._updateEvent(response, href)

    @inlineCallbacks
    def postXML(self, href, xml):
        headers = Headers({
            'content-type': ['text/xml']
        })
        response = yield self.requester.post(
            href,
            xml,
            headers=headers,
            method_label="SHARE{calendar}"
        )


    @inlineCallbacks
    def deleteCalendar(self, href):
        """
        Issue a DELETE for the given URL and remove local state
        associated with that calendar.

        Usage: client.deleteCalendar('/calendars/__uids__/<user-uid>/<calendar-uid>/')
        """

        self._invalidateCalendar(href)

        response = yield self.requester.delete(href, method_label="DELETE{calendar}")
        returnValue(response)



def main():
    from urllib2 import HTTPDigestAuthHandler
    from twisted.internet import reactor
    from twisted.python.log import addObserver
    from contrib.performance.loadtest.logger import RequestLogger
    from contrib.performance.loadtest.clients import OS_X_10_11
    auth = HTTPDigestAuthHandler()
    auth.add_password(
        realm="Test Realm",
        uri="http://127.0.0.1:8008/",
        user="user01",
        passwd="user01")

    addObserver(RequestLogger().observe)

    from contrib.performance.loadtest.records import DirectoryRecord
    client = OS_X_10_11(
        reactor,
        'http://127.0.0.1:8008/',   # root
        '/tmp/sim',                 # serializePath
        DirectoryRecord(u'user01', u'user01', u'User 01', u'user01@example.org', u'10000000-0000-0000-0000-000000000001'),
        auth,
        title='OS X 10.11 Client Simulator'
    )
    d = client.run()
    d.addErrback(err, "10.11 client run() problem")
    d.addCallback(lambda ignored: reactor.stop())
    reactor.run()


if __name__ == '__main__':
    main()
