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

from random import choice, gauss

from vobject.base import ContentLine
from vobject.icalendar import VEvent

from twisted.internet.defer import succeed
from twisted.internet.task import LoopingCall


class Inviter(object):
    """
    A Calendar user who invites and de-invites other users to events.
    """
    def __init__(self, reactor, client, userNumber):
        self._reactor = reactor
        self._client = client
        self._number = userNumber


    def run(self):
        self._call = LoopingCall(self._invite)
        self._call.clock = self._reactor
        self._call.start(3)


    def _addAttendee(self, event, attendees):
        """
        Create a new attendeed to add to the list of attendees for the
        given event.
        """
        invitee = max(1, int(gauss(self._number, 30)))
        if invitee == self._number:
            # This will bias the distribution a little... it is the
            # end of the world, probably.
            invitee += 1
        user = u'User %02d' % (invitee,)
        email = u'user%02d@example.com' % (invitee,)
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
        # Pick an event at random
        if self._client._events:
            uuid = choice(self._client._events.keys())
            event = self._client._events[uuid].vevent

            # Find out who might attend
            attendees = event.contents['vevent'][0].contents.get('attendee', [])

            if len(attendees) < 2 or choice([False, True]):
                d = self._addAttendee(event, attendees)
                d.addCallback(
                    lambda attendee:
                        self._client.addEventAttendee(
                            uuid, attendee))
                return d
            else:
                # XXX
                # self._removeAttendee(attendees)
                return

