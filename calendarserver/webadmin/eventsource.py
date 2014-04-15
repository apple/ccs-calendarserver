# -*- test-case-name: calendarserver.webadmin.test.test_principals -*-
##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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
##

from __future__ import print_function

"""
Calendar Server principal management web UI.
"""

__all__ = [
    "textAsEvent",
    "EventSourceResource",
]

from collections import deque

from zope.interface import implementer, Interface

from twisted.internet.defer import Deferred, succeed

from txweb2.stream import IByteStream, fallbackSplit
from txweb2.resource import Resource
from txweb2.http_headers import MimeType
from txweb2.http import Response



def textAsEvent(text, eventID=None, eventClass=None, eventRetry=None):
    """
    Format some text as an HTML5 EventSource event.  Since the EventSource data
    format is text-oriented, this function expects L{unicode}, not L{bytes};
    binary data should be encoded as text if it is to be used in an EventSource
    stream.

    UTF-8 encoded L{bytes} are returned because
    http://www.w3.org/TR/eventsource/ states that the only allowed encoding
    for C{text/event-stream} is UTF-8.


    @param text: The text (ie. the message) to send in the event.
    @type text: L{unicode}

    @param eventID: An unique identifier for the event.
    @type eventID: L{unicode}

    @param eventClass: A class name (ie. a categorization) for the event.
    @type eventClass: L{unicode}

    @param eventRetry: The retry interval (in milliseconds) for the client to
        wait before reconnecting if it gets disconnected.
    @type eventRetry: L{int}

    @return: An HTML5 EventSource event as text.
    @rtype: UTF-8 encoded L{bytes}
    """
    if text is None:
        raise TypeError("text may not be None")

    event = []

    if eventID is not None:
        event.append(u"id: {0}".format(eventID))

    if eventClass is not None:
        event.append(u"event: {0}".format(eventClass))

    if eventRetry is not None:
        event.append(u"retry: {0:d}".format(eventRetry))

    event.extend(
        u"data: {0}".format(l) for l in text.split("\n")
    )

    return (u"\n".join(event) + u"\n\n").encode("utf-8")



class IEventDecoder(Interface):
    """
    An object that can be used to extract data from an application-specific
    event object for encoding into an EventSource data stream.
    """

    def idForEvent(event):
        """
        @return: An unique identifier for the given event.
        @rtype: L{unicode}
        """

    def classForEvent(event):
        """
        @return: A class name (ie. a categorization) for the event.
        @rtype: L{unicode}
        """

    def textForEvent(event):
        """
        @return: The text (ie. the message) to send in the event.
        @rtype: L{unicode}
        """

    def retryForEvent(event):
        """
        @return: The retry interval (in milliseconds) for the client to wait
            before reconnecting if it gets disconnected.
        @rtype: L{int}
        """


class EventSourceResource(Resource):
    """
    Resource that vends HTML5 EventSource events.

    Events are stored in a ring buffer and streamed to clients.
    """

    addSlash = False


    def __init__(self, eventDecoder, bufferSize=400):
        """
        @param eventDecoder: An object that can be used to extract data from
            an event for encoding into an EventSource data stream.
        @type eventDecoder: L{IEventDecoder}

        @param bufferSize: The maximum number of events to keep in the ring
            buffer.
        @type bufferSize: L{int}
        """
        Resource.__init__(self)

        self._eventDecoder = eventDecoder
        self._events = deque(maxlen=bufferSize)
        self._streams = set()


    def addEvents(self, events):
        self._events.extend(events)

        # Notify outbound streams that there is new data to vend
        for stream in self._streams:
            stream.didAddEvents()


    def render(self, request):
        lastID = request.headers.getRawHeaders(u"last-event-id")

        response = Response()
        response.stream = EventStream(self._eventDecoder, self._events, lastID)
        response.headers.setHeader(
            b"content-type", MimeType.fromString(b"text/event-stream")
        )

        # Keep track of the event streams
        def cleanupFilter(_request, _response):
            self._streams.remove(response.stream)
            return _response

        request.addResponseFilter(cleanupFilter)
        self._streams.add(response.stream)

        return response



@implementer(IByteStream)
class EventStream(object):
    """
    L{IByteStream} that streams out HTML5 EventSource events.
    """

    length = None


    def __init__(self, eventDecoder, events, lastID):
        """
        @param eventDecoder: An object that can be used to extract data from
            an event for encoding into an EventSource data stream.
        @type eventDecoder: L{IEventDecoder}

        @param events: Application-specific event objects.
        @type events: sequence of L{object}

        @param lastID: The identifier for the last event that was vended from
            C{events}.  Vending will resume starting from the following event.
        @type lastID: L{int}
        """
        object.__init__(self)

        self._eventDecoder = eventDecoder
        self._events = events
        self._lastID = lastID
        self._closed = False
        self._deferredRead = None


    def didAddEvents(self):
        d = self._deferredRead
        if d is not None:
            d.addCallback(lambda _: self.read())
            d.callback(None)


    def read(self):
        if self._closed:
            return succeed(None)

        lastID = self._lastID
        eventID = None

        idForEvent = self._eventDecoder.idForEvent
        classForEvent = self._eventDecoder.classForEvent
        textForEvent = self._eventDecoder.textForEvent
        retryForEvent = self._eventDecoder.retryForEvent

        for event in self._events:
            eventID = idForEvent(event)

            # If lastID is not None, skip messages up to and including the one
            # referenced by lastID.
            if lastID is not None:
                if eventID == lastID:
                    eventID = None
                    lastID = None

                continue

            eventClass = classForEvent(event)
            eventText = textForEvent(event)
            eventRetry = retryForEvent(event)

            self._lastID = eventID

            return succeed(
                textAsEvent(eventText, eventID, eventClass, eventRetry)
            )


        if eventID is not None:
            # We just scanned all the messages, and none are the last one the
            # client saw.
            self._lastID = None

            return succeed(b"")

        # # This causes the client to poll, which is undesirable, but the
        # # deferred below doesn't seem to work in real use...
        # return succeed(None)

        d = Deferred()
        self._deferredRead = d
        return d


    def split(self, point):
        return fallbackSplit(self, point)


    def close(self):
        self._closed = True
