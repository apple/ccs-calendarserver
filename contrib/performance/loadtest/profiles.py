##
# Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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

"""
Implementation of specific end-user behaviors.
"""

from __future__ import division

import random
from uuid import uuid4
from numbers import Number

from caldavclientlibrary.protocol.caldav.definitions import caldavxml

from twisted.python import context
from twisted.python.log import msg
from twisted.python.failure import Failure
from twisted.internet.defer import Deferred, DeferredList, succeed, fail
from twisted.internet.task import LoopingCall
from twisted.web.http import PRECONDITION_FAILED

from twistedcaldav.ical import Property

from contrib.performance.loadtest.distributions import (
    NearFutureDistribution, NormalDistribution, UniformDiscreteDistribution, BernoulliDistribution,
    LogNormalDistribution, RecurrenceDistribution, FixedDistribution
)
from contrib.performance.loadtest.ical import IncorrectResponseCode
from contrib.performance.loadtest.resources import Calendar, Event
from contrib.performance.loadtest.templates import eventTemplate, alarmTemplate, taskTemplate

from pycalendar.datetime import DateTime
from pycalendar.duration import Duration
from pycalendar.value import Value

def _loopWithDistribution(reactor, distribution, function):
    result = Deferred()
    print(distribution)

    def repeat(ignored):
        reactor.callLater(distribution.sample(), iterate)

    def iterate():
        d = function()
        if d is not None:
            d.addCallbacks(repeat, result.errback)
        else:
            repeat(None)

    repeat(None)
    return result

class ProfileBase(object):
    """
    Base class which provides some conveniences for profile
    implementations.
    """
    random = random

    def __init__(self, enabled, interval, **params):
        self.enabled = enabled
        if isinstance(interval, Number):
            interval = FixedDistribution(interval)
        self._interval = interval
        self._params = params
        self.setDistributions(**params)
        self._initialized = False

    def duplicate(self):
        return type(self)(enabled=self.enabled, interval=self._interval, **self._params)

    def setUp(self, reactor, simulator, client, record):
        self._reactor = reactor
        self._sim = simulator
        self._client = client
        self._record = record
        self._initialized = True

    def setDistributions(self):
        pass

    def _wrapper(self):
        if not self.enabled:
            return succeed(None)
        if not self._client.started:
            return succeed(None)
        return self.action()

    def run(self):
        return _loopWithDistribution(self._reactor, self._interval, self._wrapper)

    def _calendarsOfType(self, calendarType, componentType):
        return [
            cal
            for cal
            in self._client._calendars.itervalues()
            if cal.resourceType == calendarType and componentType in cal.componentTypes]


    def _isSelfAttendee(self, attendee):
        """
        Try to match one of the attendee's identifiers against one of
        C{self._client}'s identifiers.  Return C{True} if something matches,
        C{False} otherwise.
        """
        return attendee.parameterValue('EMAIL') == self._client.email[len('mailto:'):]


    def _getRandomCalendarOfType(self, component_type):
        """
        Return a random L{Calendar} object from the current user
        or C{None} if there are no calendars to work with
        """
        calendars = self._calendarsOfType(caldavxml.calendar, component_type)
        if not calendars: # Oh no! There are no calendars to play with
            return None
        # Choose a random calendar
        calendar = self.random.choice(calendars)
        return calendar


    def _getRandomEventOfType(self, component_type):
        """
        Return a random L{Event} object from the current user
        or C{None} if there are no events to work with
        """
        calendars = self._calendarsOfType(caldavxml.calendar, component_type)
        while calendars:
            calendar = self.random.choice(calendars)
            calendars.remove(calendar)
            if not calendar.events:
                continue

            events = calendar.events.keys()
            while events:
                href = self.random.choice(events)
                events.remove(href)
                event = calendar.events[href]
                if not event.component:
                    continue
                return event
        return None


    def _getRandomLocation(self):
        pass


    def _newOperation(self, label, deferred):
        """
        Helper to emit a log event when a new operation is started and
        another one when it completes.
        """
        # If this is a scheduled request, record the lag in the
        # scheduling now so it can be reported when the response is
        # received.
        lag = context.get('lag', None)

        before = self._reactor.seconds()
        msg(
            type="operation",
            phase="start",
            user=self._client.record.uid,
            client_type=self._client.title,
            client_id=self._client._client_id,
            label=label,
            lag=lag,
        )

        def finished(passthrough):
            success = not isinstance(passthrough, Failure)
            if not success:
                passthrough.trap(IncorrectResponseCode)
                passthrough = passthrough.value.response
            after = self._reactor.seconds()
            msg(
                type="operation",
                phase="end",
                duration=after - before,
                user=self._client.record.uid,
                client_type=self._client.title,
                client_id=self._client._client_id,
                label=label,
                success=success,
            )
            return passthrough
        deferred.addBoth(finished)
        return deferred


    def _failedOperation(self, label, reason):
        """
        Helper to emit a log event when an operation fails.
        """
        msg(
            type="operation",
            phase="failed",
            user=self._client.record.uid,
            client_type=self._client.title,
            client_id=self._client._client_id,
            label=label,
            reason=reason,
        )
        self._sim._simFailure("%s: %s" % (label, reason,), self._reactor)



class CannotAddAttendee(Exception):
    """
    Indicates no new attendees can be invited to a particular event.
    """
    pass


#####################
# Eventer Hierarchy #
# ----------------- #
# EventBase         #
#   Eventer         #
#   EventUpdaterBase#
#     Titler        #
#     Noter         #
#     Linker        #
#     Relocater     #
#     Repeater      #
#     Rescheduler   #
#     ~Alerter~     #
#     Attacher      #
#     InviterBase   #
#       Inviter     #
#       Relocater   #
#   EventDeleter    #
#####################

class EventBase(ProfileBase):
    """
    Base profile for a calendar user who interacts with events
    """
    def _getRandomCalendar(self):
        return self._getRandomCalendarOfType('VEVENT')

    def _getRandomEvent(self):
        return self._getRandomEventOfType('VEVENT')


class Eventer(EventBase):
    """
    A Calendar user who creates new events.
    """
    def setDistributions(
        self,
        eventStartDistribution=NearFutureDistribution(),
        eventDurationDistribution=UniformDiscreteDistribution([
            15 * 60, 30 * 60,
            45 * 60, 60 * 60,
            120 * 60
        ])
    ):
        """
        @param eventStartDistribution: Generates datetimes at which an event starts
        @param eventDurationDistribution: Generates length of event (in seconds)
        """
        self._eventStart = eventStartDistribution
        self._eventDuration = eventDurationDistribution

    def _addEvent(self):
        # Choose a random calendar on which to add an event
        calendar = self._getRandomCalendar()
        if not calendar:
            return succeed(None)
        # print "Going to add an event"

        # Form a new event by modifying fields of the template event
        vcalendar = eventTemplate.duplicate()
        vevent = vcalendar.mainComponent()
        uid = str(uuid4())
        dtstart = self._eventStart.sample()
        dtend = dtstart + Duration(seconds=self._eventDuration.sample())

        vevent.replaceProperty(Property("UID", uid))
        vevent.replaceProperty(Property("CREATED", DateTime.getNowUTC()))
        vevent.replaceProperty(Property("DTSTAMP", DateTime.getNowUTC()))
        vevent.replaceProperty(Property("DTSTART", dtstart))
        vevent.replaceProperty(Property("DTEND", dtend))

        href = '%s%s.ics' % (calendar.url, uid)
        # print("Vcalendar is", vcalendar)
        event = Event(self._client.serializeLocation(), href, None, component=vcalendar)
        # print("ABout to add event", event.component)
        d = self._client.addEvent(href, event)
        return self._newOperation("create{event}", d)

    action = _addEvent

# Could have better handling for not changing events once they're modified
# esp re: repeating
class EventUpdaterBase(EventBase):
    """Superclass of all event mixins.
    Accepts two parameters
    enabled: bool on or off
    interval: distibution that generates integers representing delays
    """
    def action(self):
        event = self._getRandomEvent()
        if not event:
            return succeed(None)
        component = event.component
        vevent = component.mainComponent()

        label = self.modifyEvent(event.url, vevent)
        vevent.replaceProperty(Property("DTSTAMP", DateTime.getNowUTC()))

        event.component = component
        return self._client.updateEvent(event)
        # d.addCallback(finish)

        return self._newOperation(label, d)

    def modifyEvent(self, href, vevent):
        """Overriden by subclasses"""
        pass

class Titler(EventUpdaterBase):
    def setDistributions(
        self,
        titleLengthDistribution=NormalDistribution(10, 2)
    ):
        self._titleLength = titleLengthDistribution

    def modifyEvent(self, _ignore_href, vevent):
        length = max(5, int(self._titleLength.sample()))
        vevent.replaceProperty(Property("SUMMARY", "Event" + "." * (length - 5)))
        return "update{title}"

class Transparenter(EventUpdaterBase):
    def setDistributions(
        self,
        transparentLikelihoodDistribution=BernoulliDistribution(0.95)
    ):
        self._transparentLikelihood = transparentLikelihoodDistribution

    def modifyEvent(self, _ignore_href, vevent):
        if self._transparentLikelihood.sample():
            transparency = "TRANSPARENT"
        else:
            transparency = "OPAQUE"
        vevent.replaceProperty(Property("TRANSP", transparency))
        return "update{transp}"

class Hider(EventUpdaterBase):
    def setDistributions(
        self,
        publicLikelihoodDistribution=BernoulliDistribution(0.95)
    ):
        self._publicLikelihood = publicLikelihoodDistribution

    def modifyEvent(self, _ignore_href, vevent):
        if self._publicLikelihood.sample():
            privacy = "PUBLIC"
        else:
            privacy = "CONFIDENTIAL"
        vevent.replaceProperty(Property("X-CALENDARSERVER-ACCESS", privacy))
        return "update{privacy}"

class Noter(EventUpdaterBase):
    def setDistributions(
        self,
        noteLengthDistribution=NormalDistribution(10, 2)
    ):
        self._noteLength = noteLengthDistribution

    def modifyEvent(self, _ignore_href, vevent):
        length = max(5, int(self._noteLength.sample()))
        vevent.replaceProperty(Property("DESCRIPTION", "." * length))
        return "update{notes}"

class Linker(EventUpdaterBase):
    def setDistributions(
        self,
        urlLengthDistribution=NormalDistribution(10, 2)
    ):
        self._urlLength = urlLengthDistribution

    def modifyEvent(self, _ignore_href, vevent):
        length = max(5, int(self._urlLength.sample()))
        vevent.replaceProperty(Property("URL", 'https://bit.ly/' + '*' * length, valuetype=Value.VALUETYPE_URI))
        return "update{url}"

class Repeater(EventUpdaterBase):
    def setDistributions(
        self,
        recurrenceDistribution=RecurrenceDistribution(False)
    ):
        self._recurrence = recurrenceDistribution

    def modifyEvent(self, _ignore_href, vevent):
        rrule = self._recurrence.sample()
        if rrule is not None:
            vevent.replaceProperty(Property(None, None, None, pycalendar=rrule))
        return "update{rrule}"

class Rescheduler(EventUpdaterBase):
    def setDistributions(
        self,
        eventStartDistribution=NearFutureDistribution(),
        eventDurationDistribution=UniformDiscreteDistribution([
            15 * 60, 30 * 60,
            45 * 60, 60 * 60,
            120 * 60
        ])
    ):
        self._eventStart = eventStartDistribution
        self._eventDuration = eventDurationDistribution

    def modifyEvent(self, _ignore_href, vevent):
        dtstart = self._eventStart.sample()
        dtend = dtstart + Duration(seconds=self._eventDuration.sample())
        vevent.replaceProperty(Property("DTSTART", dtstart))
        vevent.replaceProperty(Property("DTEND", dtend))
        return "reschedule{event}"

# class Alerter(EventUpdaterBase):
# component.replaceProperty(Property("ACKNOWLEDGED", DateTime.getNowUTC()))
#     pass

class Attacher(EventUpdaterBase):
    def setDistributions(
        self,
        filesizeDistribution=NormalDistribution(24, 3),
        numAttachmentsDistribution=LogNormalDistribution(2, 1),
        attachLikelihoodDistribution=BernoulliDistribution(0.9),

    ):
        self._filesize = filesizeDistribution
        # self._numAttachments = numAttachmentsDistribution
        # self._attachLikelihood = attachLikelihoodDistribution
        # pass

    def modifyEvent(self, href, vevent):
        d = self._client.postAttachment(href, 'x' * 1024)
        return "attach{files}"

    def handleAttachments(self):
        pass

        # if True: # attachLikelihoodDistribution.sample():
        #     # size = max(0, int(self._filesize.sample()))
        #     numAttachments()
        #     self.attachFiles(event, filesizeDistribution.sample())
        # else:
        #     pass

    def attachFile(self, event):
        # PUT new event information (nothing has actually changed)
        # POST attachment (with Content-Disposition header, and response location)
        # GET updated event
        pass

    def unattachFile(self):
        pass

class InviterBase(EventUpdaterBase):
    def setDistributions(
        self,
        numInviteesDistribution=NormalDistribution(7, 2)
    ):
        self._numInvitees = numInviteesDistribution

    def _findUninvitedRecord(self, vevent):
        pass

    def _addAttendee(self, some_id):
        attendeeProp = self._buildAttendee()
        self._client.attendeeAutocomplete

    # def _didSelfOrganize(self, vevent):

    # TODO handle alternate roles
    def _buildAttendee(self, commonname, cuaddr, isIndividual=True, isRequired=False):
        return Property(
            name=u'ATTENDEE',
            value=cuaddr.encode("utf-8"),
            params={
                'CN': commonname,
                'CUTYPE': 'INDIVIDUAL' if isIndividual else 'ROOM',
                'PARTSTAT': 'NEEDS-ACTION',
                'ROLE': 'REQ-PARTICIPANT',
                'RSVP': 'TRUE',
            },
        )

    def _getAttendees(self, vevent):
        return vevent.properties('ATTENDEE')

    def _invite():
        raise NotImplementedError

    def _addAttendee():
        raise NotImplementedError

class Inviter(InviterBase):
    def modifyEvent(self, href, vevent):
        print("*" * 16)
        numToInvite = max(0, int(self._numInvitees.sample()))
        deferreds = []
        for _ignore_i in xrange(numToInvite):
            number = random.randint(1, 50)
            record = self._sim.getUserRecord(number)
            attendee = self._buildAttendee(record.commonName, record.email)
            deferreds.append(self._client.addEventAttendee(href, attendee))
            vevent.addProperty(attendee)
        # d = self._client.addInvite(event)
        # deferreds.append(d)
        return DeferredList(deferreds)


    def test(self):
        event = self._getRandomEvent()
        if not event:
            return succeed(None)
        href = event.url

        attendee = Property(
            name=u'ATTENDEE',
            value='urn:uuid:30000000-0000-0000-0000-000000000002',
            params={
                'CN': 'Location 02',
                'CUTYPE': 'ROOM',
                'PARTSTAT': 'NEEDS-ACTION',
                'ROLE': 'REQ-PARTICIPANT',
                'RSVP': 'TRUE',
            },
        )

        d = self._client.addEventAttendee(href, attendee)

        component = event.component
        component.mainComponent().addProperty(attendee)
        event.component = component

        d2 = self._client.addInvite(event)
        return self._newOperation("add attendee", DeferredList([d, d2]))


    def _addAttendee(self, event, attendees):
        """
        Create a new attendee to add to the list of attendees for the
        given event.
        """
        selfRecord = self._sim.getUserRecord(self._number)
        invitees = set([u'mailto:%s' % (selfRecord.email,)])
        for att in attendees:
            invitees.add(att.value())

        for _ignore_i in range(10):
            invitee = max(
                0, self._number + self._inviteeDistribution.sample())
            try:
                record = self._sim.getUserRecord(invitee)
            except IndexError:
                continue
            cuaddr = u'mailto:%s' % (record.email,)
            uuidx = u'urn:x-uid:%s' % (record.guid,)
            uuid = u'urn:uuid:%s' % (record.guid,)
            if cuaddr not in invitees and uuidx not in invitees and uuid not in invitees:
                break
        else:
            return fail(CannotAddAttendee("Can't find uninvited user to invite."))

        attendee = Property(
            name=u'ATTENDEE',
            value=cuaddr.encode("utf-8"),
            params={
                'CN': record.commonName,
                'CUTYPE': 'INDIVIDUAL',
                'PARTSTAT': 'NEEDS-ACTION',
                'ROLE': 'REQ-PARTICIPANT',
                'RSVP': 'TRUE',
            },
        )

        return succeed(attendee)


    def _invite(self):
        """
        Try to add a new attendee to an event, or perhaps remove an
        existing attendee from an event.

        @return: C{None} if there are no events to play with,
            otherwise a L{Deferred} which fires when the attendee
            change has been made.
        """

        if not self._client.started:
            return succeed(None)

        # Find calendars which are eligible for invites
        calendars = self._calendarsOfType(caldavxml.calendar, "VEVENT")

        while calendars:
            # Pick one at random from which to try to select an event
            # to modify.
            calendar = self.random.choice(calendars)
            calendars.remove(calendar)

            if not calendar.events:
                continue

            events = calendar.events.keys()
            while events:
                uuid = self.random.choice(events)
                events.remove(uuid)
                event = calendar.events[uuid].component
                if event is None:
                    continue

                component = event.mainComponent()
                organizer = component.getOrganizerProperty()
                if organizer is not None and not self._isSelfAttendee(organizer):
                    # This event was organized by someone else, don't try to invite someone to it.
                    continue

                href = calendar.url + uuid

                # Find out who might attend
                attendees = tuple(component.properties('ATTENDEE'))

                # d = self._addAttendee(event, attendees)
                d = self._addLocation(event, "Location 05", "urn:uuid:30000000-0000-0000-0000-000000000005")
                d.addCallbacks(
                    lambda attendee:
                        self._client.addEventAttendee(
                            href, attendee),
                    lambda reason: reason.trap(CannotAddAttendee))
                return self._newOperation("invite", d)

        # Oops, either no events or no calendars to play with.
        return succeed(None)

    # action = invite

class Relocater(InviterBase):
    def setDistributions(
        self,
    ):
        pass

class EventDeleter(EventBase):
    """
    A calendar user who deletes events at random
    """
    def _deleteEvent(self):
        event = self._getRandomEvent()
        if event is None:
            return succeed(None)
        d = self._client.deleteEvent(event.url)
        return self._newOperation("delete{event}", d)

    action = _deleteEvent




""" TEST """
# class Intern(object):
#     def __init__(self):
#         self.behaviors = [
#             Eventer(asdfjadsf),
#             Attacher(asjadsfjasdf),
#             Inviter(enabled=True, **params)
#         ]

#     def run(self):
#         deferreds = []
#         for behavior in self.behaviors:
#             deferreds.append(behavior.run())
#         return DeferredList(deferreds)



####################
# Tasker Hierarchy #
# ---------------- #
# TaskBase         #
#   Tasker         #
#   TaskDeleter    #
#   TaskUpdaterBase#
#     Titler       #
#     Noter        #
#     Prioritizer  #
#     Completer    #
#     Alerter      #
####################


class TaskBase(ProfileBase):
    """
    Base profile for a calendar user who interacts with tasks
    """
    def _getRandomCalendar(self):
        return self._getRandomCalendarOfType('VTODO')

    def _getRandomEvent(self):
        return self._getRandomEventOfType('VTODO')


class Tasker(TaskBase):
    """
    A Calendar user who creates new tasks.
    """
    def _addTask(self):
        calendar = self._getRandomCalendar()
        if not calendar:
            return succeed(None)

        # Form a new event by modifying fields of the template event
        vcalendar = taskTemplate.duplicate()
        vtodo = vcalendar.mainComponent()
        uid = str(uuid4())

        vtodo.replaceProperty(Property("UID", uid))
        vtodo.replaceProperty(Property("CREATED", DateTime.getNowUTC()))
        vtodo.replaceProperty(Property("DTSTAMP", DateTime.getNowUTC()))

        href = '%s%s.ics' % (calendar.url, uid)
        event = Event(self._client.serializeLocation(), href, None, component=vcalendar)
        d = self._client.addEvent(href, event)
        return self._newOperation("create{task}", d)

    action = _addTask

class TaskDeleter(TaskBase):
    def _deleteTask(self):
        event = self._getRandomEvent()
        if event is None:
            return succeed(None)

        d = self._client.deleteEvent(event.url)
        return self._newOperation("delete{task}", d)

    action = _deleteTask


class TaskUpdaterBase(TaskBase):
    def action(self):
        task = self._getRandomEvent()
        if not task:
            return succeed(None)
        component = task.component
        vtodo = component.mainComponent()

        label = self.modifyEvent(task.url, vtodo)
        vtodo.replaceProperty(Property("DTSTAMP", DateTime.getNowUTC()))

        task.component = component
        d = self._client.updateEvent(task, method_label="update{task}")
        return self._newOperation(label, d)

    def modifyEvent(self, href, vtodo):
        """Overriden by subclasses"""
        pass


class TaskTitler(TaskUpdaterBase, Titler):
    """
    Changes the SUMMARY of a random VTODO
    """
    def modifyEvent(self, _ignore_href, vtodo):
        vtodo.replaceProperty(Property("SUMMARY", "." * 5))
        return "update{title}"

class TaskNoter(TaskUpdaterBase, Noter):
    """
    Changes the NOTES of a random VTODO
    """
    def modifyEvent(self, _ignore_href, vtodo):
        vtodo.replaceProperty(Property("DESCRIPTION", "." * 5))
        return "update{notes}"


# class TaskAlerterMixin = AlerterMixin (alarm AND due)
# self._taskStartDistribution = taskDueDistribution
# vtodo.replaceProperty(Property("DUE", due))


class Prioritizer(TaskUpdaterBase):
    PRIORITY_NONE = 0
    PRIORITY_HIGH = 1
    PRIORITY_MEDIUM = 5
    PRIORITY_LOW = 9

    def setDistributions(
        self,
        priorityDistribution=UniformDiscreteDistribution([
            PRIORITY_NONE, PRIORITY_LOW, PRIORITY_MEDIUM, PRIORITY_HIGH
        ])
    ):
        self._priority = priorityDistribution

    def modifyEvent(self, _ignore_href, vtodo):
        self._setPriority(vtodo, self._priority.sample())


    def _setPriority(self, vtodo, priority):
        """ Set the PRIORITY of a VTODO """
        vtodo.replaceProperty(Property("PRIORITY", priority))

class Completer(TaskUpdaterBase):
    def setDistributions(
        self,
        completeLikelihood=BernoulliDistribution(0.9)
    ):
        self._complete = completeLikelihood

    def modifyEvent(self, _ignore_href, vtodo):
        if self._complete.sample():
            self._markTaskComplete(vtodo)
        else:
            self._markTaskIncomplete(vtodo)

    def _markTaskComplete(self, vtodo):
        """ Mark a VTODO as complete """
        vtodo.replaceProperty(Property("COMPLETED", DateTime.getNowUTC()))
        vtodo.replaceProperty(Property("PERCENT-COMPLETE", 100))
        vtodo.replaceProperty(Property("STATUS", "COMPLETED"))

    def _markTaskIncomplete(self, vtodo):
        """ Mark a VTODO as incomplete """
        vtodo.removeProperty("COMPLETED")
        vtodo.removeProperty("PERCENT-COMPLETE")
        vtodo.replaceProperty(Property("STATUS", "NEEDS-ACTION"))


##########################
# Notification Behaviors #
##########################
class Accepter(ProfileBase):
    """
    A Calendar user who accepts invitations to events. As well as accepting requests, this
    will also remove cancels and replies.
    """
    def setDistributions(
        self,
        enabled=True,
        acceptDelayDistribution=NormalDistribution(1200, 60)
    ):
        self.enabled = enabled
        self._accepting = set()
        self._acceptDelayDistribution = acceptDelayDistribution


    def run(self):
        self._subscription = self._client.catalog["eventChanged"].subscribe(self.eventChanged)
        # TODO: Propagate errors from eventChanged and _acceptInvitation to this Deferred
        return Deferred()


    def eventChanged(self, href):
        # Just respond to normal calendar events
        calendar = href.rsplit('/', 1)[0] + '/'
        try:
            calendar = self._client._calendars[calendar]
        except KeyError:
            return

        if calendar.resourceType == caldavxml.schedule_inbox:
            # Handle inbox differently
            self.inboxEventChanged(calendar, href)
        elif calendar.resourceType == caldavxml.calendar:
            self.calendarEventChanged(calendar, href)
        else:
            return


    def calendarEventChanged(self, calendar, href):
        if href in self._accepting:
            return

        component = self._client._events[href].component
        # Check to see if this user is in the attendee list in the
        # NEEDS-ACTION PARTSTAT.
        attendees = tuple(component.mainComponent().properties('ATTENDEE'))
        for attendee in attendees:
            if self._isSelfAttendee(attendee):
                if attendee.parameterValue('PARTSTAT') == 'NEEDS-ACTION':
                    delay = self._acceptDelayDistribution.sample()
                    self._accepting.add(href)
                    self._reactor.callLater(
                        delay, self._acceptInvitation, href, attendee)


    def inboxEventChanged(self, calendar, href):
        if href in self._accepting:
            return

        component = self._client._events[href].component
        method = component.propertyValue('METHOD')
        if method == "REPLY":
            # Replies are immediately deleted
            self._accepting.add(href)
            self._reactor.callLater(
                0, self._handleReply, href)

        elif method == "CANCEL":
            # Cancels are handled after a user delay
            delay = self._acceptDelayDistribution.sample()
            self._accepting.add(href)
            self._reactor.callLater(
                delay, self._handleCancel, href)


    def _acceptInvitation(self, href, attendee):
        def change():
            accepted = self._makeAcceptedAttendee(attendee)
            return self._client.changeEventAttendee(href, attendee, accepted)
        d = change()

        def scheduleError(reason):
            reason.trap(IncorrectResponseCode)
            if reason.value.response.code != PRECONDITION_FAILED:
                return reason.value.response.code

            # Download the event again and attempt to make the change
            # to the attendee list again.
            d = self._client._refreshEvent(href)
            def cbUpdated(ignored):
                d = change()
                d.addErrback(scheduleError)
                return d
            d.addCallback(cbUpdated)
            return d
        d.addErrback(scheduleError)

        def accepted(ignored):
            # Find the corresponding event in the inbox and delete it.
            uid = self._client._events[href].getUID()
            for cal in self._client._calendars.itervalues():
                if cal.resourceType == caldavxml.schedule_inbox:
                    for event in cal.events.itervalues():
                        if uid == event.getUID():
                            return self._client.deleteEvent(event.url)
        d.addCallback(accepted)
        def finished(passthrough):
            self._accepting.remove(href)
            return passthrough
        d.addBoth(finished)
        return self._newOperation("accept", d)


    def _handleReply(self, href):
        d = self._client.deleteEvent(href)
        d.addBoth(self._finishRemoveAccepting, href)
        return self._newOperation("reply done", d)


    def _finishRemoveAccepting(self, passthrough, href):
        self._accepting.remove(href)
        if isinstance(passthrough, Failure):
            passthrough.trap(IncorrectResponseCode)
            passthrough = passthrough.value.response
        return passthrough


    def _handleCancel(self, href):

        uid = self._client._events[href].getUID()
        d = self._client.deleteEvent(href)

        def removed(ignored):
            # Find the corresponding event in any calendar and delete it.
            for cal in self._client._calendars.itervalues():
                if cal.resourceType == caldavxml.calendar:
                    for event in cal.events.itervalues():
                        if uid == event.getUID():
                            return self._client.deleteEvent(event.url)
        d.addCallback(removed)
        d.addBoth(self._finishRemoveAccepting, href)
        return self._newOperation("cancelled", d)


    def _makeAcceptedAttendee(self, attendee):
        accepted = attendee.duplicate()
        accepted.setParameter('PARTSTAT', 'ACCEPTED')
        accepted.removeParameter('RSVP')
        return accepted



######################
# Calendar Behaviors #
######################
class CalendarBase(ProfileBase):
    """
    A calendar user who interacts with calendars
    """
    def initialize(self):
        self.action = lambda: None
        return succeed(None)


    def setDistributions(self, enabled=True, interval=25):
        self.enabled = enabled
        self._interval = interval



class CalendarMaker(CalendarBase):
    """ A Calendar user who adds new Calendars """

    def _addCalendar(self):
        print "Adding a calendar"
        # if not self._client.started:
        #     return None

        # uid = str(uuid4())

        # body = Calendar.buildCalendarXML(order=0, component_type="VEVENT", rgba_color='FB524FFF', name='Sample Calendar')
        # print("Making new calendar with uid: " + uid)
        # # XXX Just for testing! remove this soon
        # path = "/calendars/__uids__/" + self._client.record.guid + "/" + uid + "/"
        # d = self._client.addCalendar(path, body)
        d = succeed('calendar created')
        return self._newOperation("create", d)

    action = _addCalendar



class CalendarUpdater(CalendarBase):
    """
    A calendar user who updates random calendars
    """
    def initialize(self):
        from collections import defaultdict
        self.action = self._updateCalendar
        self._calendarModCount = defaultdict(int) # Map from calendar href to count of modifications
        return succeed(None)

    def _updateCalendar(self):
        if not self._client.started:
            return None

        calendar = self._getRandomCalendar()
        if not calendar:
            return None

        self._calendarModCount[calendar.url] += 1
        modcount = self._calendarModCount[calendar.url]

        colors = [
            "#800000FF", # maroon
            "#FF0000FF", # red
            "#008000FF", # green
            "#00FF00FF", # line
            "#000080FF", # navy
            "#0000FFFF", # blue
        ]
        color = colors[modcount % len(colors)]
        self._client.setCalendarDisplayName(calendar, "Calendar ({mods})".format(mods=modcount))
        self._client.setCalendarColor(calendar, color)
        # choice = self.random.randint(0, 4)
        # if choice == 0:
        #     self._client._
        # return succeed(None)

    def randomUpdate(self):
        pass

class CalendarSharer(CalendarBase, InviterBase):
    """
    A calendar user who shares random calendars.
    Even though the real client allows batch requests (e.g. 10 shares in one HTTP request),
    we simplify life (TODO: keep it real) by having each HTTP request only add or remove one sharee.
    """

    def initialize(self):
        self.action = self._shareCalendar
        return succeed(None)

    def _shareCalendar(self):
        if not self._client.started:
            return succeed(None)

        calendar = self._getRandomCalendar()
        if not calendar:
            return None

        # The decision of who to invite / uninvite should be made here
        inv = random.randint(0, 1)
        rem = random.randint(0, 1)

        invRecord = self._sim.getUserRecord(inv)
        remRecord = self._sim.getUserRecord(rem)

        print("Sharing " + calendar.url)
        self._inviteUser(calendar, invRecord)
        # self._removeUser(calendar, remRecord)

        return succeed(None)

    def _inviteUser(self, calendar, userRecord):
        mailto = "mailto:{}".format(userRecord.email)
        body = Calendar.addInviteeXML(mailto, calendar.name, readwrite=True)
        d = self._client.postXML(calendar.url, body)
        # print(body)

    def _removeUser(self, calendar, userRecord):
        mailto = "mailto:{}".format(userRecord.email)

        body = Calendar.removeInviteeXML(mailto)

        d = self._client.postXML(calendar.url, body)
        # print(body)



class CalendarDeleter(CalendarBase):
    """
    A calendar user who deletes entire calendars
    """
    def initialize(self):
        self.action = self._deleteCalendar
        return succeed(None)

    def _deleteCalendar(self):
        if not self._client.started:
            return succeed(None)

        calendar = self._getRandomCalendar()
        if not calendar:
            return None
        print("Deleting " + calendar.url)
        d = self._client.deleteCalendar(calendar.url)
        return self._newOperation("delete", d)

if __name__ == '__main__':
    class TestProfile(ProfileBase):
        def sayHello(self):
            print("Hello!")
        action = sayHello

    from twisted.internet import reactor

    profile = TestProfile(enabled=True, interval=1)
    profile.setUp(reactor, None, None, None)
    profile.run()
    reactor.run()
