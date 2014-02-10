# -*- test-case-name: calendarserver.webadmin.test.test_log -*-
##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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
Calendar Server Web Admin UI.
"""

__all__ = [
    "LogsResource",
    "LogEventsResource",
]

from collections import deque

from zope.interface import implementer

from twisted.internet.defer import succeed

from txweb2.stream import IByteStream, fallbackSplit
from txweb2.resource import Resource
from txweb2.http_headers import MimeType
from txweb2.http import Response

from calendarserver.accesslog import CommonAccessLoggingObserverExtensions

from .resource import PageElement, TemplateResource



class LogsPageElement(PageElement):
    """
    Logs page element.
    """

    def __init__(self):
        PageElement.__init__(self, "logs")


    def pageSlots(self):
        return {
            u"title": u"Calendar & Contacts Server Logs",
        }



class LogsResource(TemplateResource):
    """
    Logs page resource.
    """

    addSlash = True


    def __init__(self):
        TemplateResource.__init__(self, LogsPageElement())

        self.putChild("events", LogEventsResource())



class LogEventsResource(Resource):
    """
    Log event vending resource.
    """

    addSlash = False


    def __init__(self):
        Resource.__init__(self)

        self._observer = AccessLoggingObserver()


    def render(self, request):
        response = Response()
        response.stream = LogObservingEventStream(self._observer)
        response.headers.setHeader(
            "content-type", MimeType.fromString("text/event-stream")
        )
        return response



@implementer(IByteStream)
class LogObservingEventStream(object):
    """
    L{IStream} that observes log events and streams them out as HTML5
    EventSource events.
    """

    length = None


    def __init__(self, observer, start=None):
        object.__init__(self)

        self._observer = observer
        self._start = start
        self._closed = False


    def read(self):
        if self._closed:
            return None

        start = self._start

        events = []

        for message in self._observer.messages():
            # If we have a start point, skip messages up to and including the
            # one at the start point.
            if start is not None:
                if id(message) == start:
                    start = None
                continue

            events.append(textAsEvent(message))

        if events:
            # Remember the ID of the last event read at our start point
            self._start = id(events[-1])

            return succeed("".join(events))

        if self._start is not None:
            # We have a start point and no data... maybe if fell off of the
            # buffer; remove the start point and try again.
            self._start = None
            return self.read()

        # No start point and no events == EOF
        return succeed(None)


    def split(self, point):
        return fallbackSplit(self, point)


    def close(self):
        self._closed = True



class AccessLoggingObserver(CommonAccessLoggingObserverExtensions):
    """
    Log observer that captures apache-style access log text entries in a
    buffer.
    """
    def __init__(self):
        CommonAccessLoggingObserverExtensions.__init__(self)

        self._buffer = deque(maxlen=400)


    def logMessage(self, message):
        self._buffer.append(message)


    def messages(self):
        return iter(self._buffer)



def textAsEvent(text):
    return (
        u"id: {id}\n"
        u"data: {text}\n"
        u"\n"
        .format(id=id(text), text=text).encode("utf-8")
    )
