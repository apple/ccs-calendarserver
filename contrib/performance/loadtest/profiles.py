##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

import random

from vobject.base import ContentLine
from vobject.icalendar import VEvent

from protocol.caldav.definitions import caldavxml

from twisted.python.log import msg
from twisted.internet.defer import succeed
from twisted.internet.task import LoopingCall


class Inviter(object):
    """
    A Calendar user who invites and de-invites other users to events.
    """
    random = random

    def __init__(self, reactor, client, userNumber):
        self._reactor = reactor
        self._client = client
        self._number = userNumber


    def run(self):
        self._call = LoopingCall(self._invite)
        self._call.clock = self._reactor
        # XXX Base this on something real
        self._call.start(3)


    def _addAttendee(self, event, attendees):
        """
        Create a new attendee to add to the list of attendees for the
        given event.
        """
        invitees = set([self._client.email[len('mailto:'):]])
        for att in attendees:
            invitees.add(att.params[u'EMAIL'][0])

        while True:
            invitee = max(1, int(self.random.gauss(self._number, 30)))
            email = u'user%02d@example.com' % (invitee,)
            if email not in invitees:
                break

        user = u'User %02d' % (invitee,)
        uuid = u'urn:uuid:user%02d' % (invitee,)

        attendee = ContentLine(
            name=u'ATTENDEE', params=[
                [u'CN', user],
                [u'CUTYPE', u'INDIVIDUAL'],
                [u'EMAIL', email],
                [u'PARTSTAT', u'NEEDS-ACTION'],
                [u'ROLE', u'REQ-PARTICIPANT'],
                [u'RSVP', u'TRUE'],
                ],
            value=uuid,
            encoded=True)
        attendee.parentBehavior = VEvent

        return succeed(attendee)


    def _invite(self):
        """
        Try to add a new attendee to an event, or perhaps remove an
        existing attendee from an event.

        @return: C{None} if there are no events to play with,
            otherwise a L{Deferred} which fires when the attendee
            change has been made.
        """
        # Find calendars which are eligible for invites
        calendars = [
            cal 
            for cal 
            in self._client._calendars.itervalues() 
            if cal.resourceType == caldavxml.calendar]

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
                event = calendar.events[uuid].vevent
                if event is None:
                    continue

                href = calendar.url + uuid

                # Find out who might attend
                attendees = event.contents['vevent'][0].contents.get('attendee', [])

                d = self._addAttendee(event, attendees)
                d.addCallback(
                    lambda attendee:
                        self._client.addEventAttendee(
                            href, attendee))
                return d



class Accepter(object):
    """
    A Calendar user who accepts invitations to events.
    """
    random = random

    def __init__(self, reactor, client, userNumber):
        self._reactor = reactor
        self._client = client
        self._number = userNumber
        self._accepting = set()


    def run(self):
        self._subscription = self._client.catalog["eventChanged"].subscribe(self.eventChanged)


    def eventChanged(self, href):
        # Just respond to normal calendar events
        calendar = href.rsplit('/', 1)[0] + '/'
        try:
            calendar = self._client._calendars[calendar]
        except KeyError:
            return
        if calendar.resourceType != caldavxml.calendar:
            return
        if href in self._accepting:
            return

        vevent = self._client._events[href].vevent
        # Check to see if this user is in the attendee list in the
        # NEEDS-ACTION PARTSTAT.
        attendees = vevent.contents['vevent'][0].contents.get('attendee', [])
        for attendee in attendees:
            if attendee.params[u'EMAIL'][0] == self._client.email[len('mailto:'):]:
                if attendee.params[u'PARTSTAT'][0] == 'NEEDS-ACTION':
                    # XXX Base this on something real
                    delay = self.random.gauss(10, 2)
                    self._accepting.add(href)
                    self._reactor.callLater(
                        delay, self._acceptInvitation, href, attendee)
                    return


    def _acceptInvitation(self, href, attendee):
        self._accepting.remove(href)
        accepted = self._makeAcceptedAttendee(attendee)
        self._client.changeEventAttendee(href, attendee, accepted)


    def _makeAcceptedAttendee(self, attendee):
        accepted = ContentLine.duplicate(attendee)
        accepted.params[u'PARTSTAT'] = [u'ACCEPTED']
        try:
            del accepted.params[u'RSVP']
        except KeyError:
            msg("Duplicated an attendee with no RSVP: %r" % (attendee,))
        return accepted
