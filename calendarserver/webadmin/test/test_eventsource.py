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
##

"""
Tests for L{calendarserver.webadmin.eventsource}.
"""

from __future__ import print_function

from zope.interface import implementer

from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from txweb2.server import Request
from txweb2.http_headers import Headers

from ..eventsource import textAsEvent, EventSourceResource, IEventDecoder



class EventGenerationTests(TestCase):
    """
    Tests for emitting HTML5 EventSource events.
    """

    def test_textAsEvent(self):
        """
        Generate an event from some text.
        """
        self.assertEquals(
            textAsEvent(u"Hello, World!"),
            b"data: Hello, World!\n\n"
        )


    def test_textAsEvent_newlines(self):
        """
        Text with newlines generates multiple C{data:} lines in event.
        """
        self.assertEquals(
            textAsEvent(u"AAPL\nApple Inc.\n527.10"),
            b"data: AAPL\ndata: Apple Inc.\ndata: 527.10\n\n"
        )


    def test_textAsEvent_newlineTrailing(self):
        """
        Text with trailing newline generates trailing blank C{data:} line.
        """
        self.assertEquals(
            textAsEvent(u"AAPL\nApple Inc.\n527.10\n"),
            b"data: AAPL\ndata: Apple Inc.\ndata: 527.10\ndata: \n\n"
        )


    def test_textAsEvent_encoding(self):
        """
        Event text is encoded as UTF-8.
        """
        self.assertEquals(
            textAsEvent(u"S\xe1nchez"),
            b"data: S\xc3\xa1nchez\n\n"
        )


    def test_textAsEvent_emptyText(self):
        """
        Text may not be L{None}.
        """
        self.assertEquals(
            textAsEvent(u""),
            b"data: \n\n"  # Note that b"data\n\n" is a valid result here also
        )


    def test_textAsEvent_NoneText(self):
        """
        Text may not be L{None}.
        """
        self.assertRaises(TypeError, textAsEvent, None)


    def test_textAsEvent_eventID(self):
        """
        Event ID goes into the C{id} field.
        """
        self.assertEquals(
            textAsEvent(u"", eventID=u"1234"),
            b"id: 1234\ndata: \n\n"  # Note order is allowed to vary
        )


    def test_textAsEvent_eventClass(self):
        """
        Event class goes into the C{event} field.
        """
        self.assertEquals(
            textAsEvent(u"", eventClass=u"buckets"),
            b"event: buckets\ndata: \n\n"  # Note order is allowed to vary
        )



class EventSourceResourceTests(TestCase):
    """
    Tests for L{EventSourceResource}.
    """

    def eventSourceResource(self):
        return EventSourceResource(DictionaryEventDecoder, None)


    def render(self, resource):
        headers = Headers()

        request = Request(
            chanRequest=None,
            command=None,
            path="/",
            version=None,
            contentLength=None,
            headers=headers
        )

        return resource.render(request)


    def test_status(self):
        """
        Response status is C{200}.
        """
        resource = self.eventSourceResource()
        response = self.render(resource)

        self.assertEquals(response.code, 200)


    def test_contentType(self):
        """
        Response content type is C{text/event-stream}.
        """
        resource = self.eventSourceResource()
        response = self.render(resource)

        self.assertEquals(
            response.headers.getRawHeaders(b"Content-Type"),
            ["text/event-stream"]
        )


    def test_contentLength(self):
        """
        Response content length is not provided.
        """
        resource = self.eventSourceResource()
        response = self.render(resource)

        self.assertEquals(
            response.headers.getRawHeaders(b"Content-Length"),
            None
        )


    @inlineCallbacks
    def test_streamBufferedEvents(self):
        """
        Events already buffered are vended immediately, then we get EOF.
        """
        events = (
            dict(eventID=u"1", eventText=u"A"),
            dict(eventID=u"2", eventText=u"B"),
            dict(eventID=u"3", eventText=u"C"),
            dict(eventID=u"4", eventText=u"D"),
        )

        resource = self.eventSourceResource()
        resource.addEvents(events)

        response = self.render(resource)

        # Each result from read() is another event
        for i in range(len(events)):
            result = yield response.stream.read()
            self.assertEquals(
                result,
                textAsEvent(
                    text=events[i]["eventText"],
                    eventID=events[i]["eventID"]
                )
            )


    @inlineCallbacks
    def test_streamWaitForEvents(self):
        """
        Stream reading blocks on additional events.
        """
        resource = self.eventSourceResource()
        response = self.render(resource)

        # Read should block on new events.
        d = response.stream.read()
        self.assertFalse(d.called)

        d.addErrback(lambda f: None)
        d.cancel()

    test_streamWaitForEvents.todo = "Feature disabled; needs debugging"


    @inlineCallbacks
    def test_streamNewEvents(self):
        """
        Events not already buffered are vended after they are posted.
        """
        events = (
            dict(eventID=u"1", eventText=u"A"),
            dict(eventID=u"2", eventText=u"B"),
            dict(eventID=u"3", eventText=u"C"),
            dict(eventID=u"4", eventText=u"D"),
        )

        resource = self.eventSourceResource()

        response = self.render(resource)

        # The first read should block on new events.
        d = response.stream.read()
        self.assertFalse(d.called)

        # Add some events
        resource.addEvents(events)

        # We should now be unblocked
        self.assertTrue(d.called)

        # Each result from read() is another event
        for i in range(len(events)):
            if d is None:
                result = yield response.stream.read()
            else:
                result = yield d
                d = None

            self.assertEquals(
                result,
                textAsEvent(
                    text=events[i]["eventText"],
                    eventID=(events[i]["eventID"])
                )
            )

        # The next read should block on new events.
        d = response.stream.read()
        self.assertFalse(d.called)

        d.addErrback(lambda f: None)
        d.cancel()

    test_streamNewEvents.todo = "Feature disabled; needs debugging"



@implementer(IEventDecoder)
class DictionaryEventDecoder(object):
    """
    Decodes events represented as dictionaries.
    """

    @staticmethod
    def idForEvent(event):
        return event.get("eventID")


    @staticmethod
    def classForEvent(event):
        return event.get("eventClass")


    @staticmethod
    def textForEvent(event):
        return event.get("eventText")


    @staticmethod
    def retryForEvent(event):
        return None
