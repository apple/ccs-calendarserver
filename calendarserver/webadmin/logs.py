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

from __future__ import print_function

"""
Calendar Server Web Admin UI.
"""

__all__ = [
    "LogsResource",
    "LogEventsResource",
]

from collections import deque

from zope.interface import implementer

from twisted.python.log import FileLogObserver
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


    def render(self, request):
        self.element = LogsPageElement()
        return TemplateResource.render(self, request)



class LogEventsResource(Resource):
    """
    Log event vending resource.
    """

    addSlash = False


    def __init__(self):
        Resource.__init__(self)


    @property
    def events(self):
        if not hasattr(self, "_buffer"):
            buffer = deque(maxlen=400)

            AccessLogObserver(buffer).start()
            BufferingLogObserver(buffer).start()

            self._buffer = buffer

        return self._buffer


    def render(self, request):
        start = request.headers.getRawHeaders("last-event-id")

        if start is not None:
            try:
                start = int(start[0])
            except ValueError:
                start = None

        response = Response()
        response.stream = LogEventStream(self, start)
        response.headers.setHeader(
            "content-type", MimeType.fromString("text/event-stream")
        )
        return response



@implementer(IByteStream)
class LogEventStream(object):
    """
    L{IByteStream} that streams log events out as HTML5 EventSource events.
    """

    length = None


    def __init__(self, source, start):
        object.__init__(self)

        self._source = source
        self._start = start
        self._closed = False


    def read(self):
        if self._closed:
            return None

        start = self._start
        messageID = None

        for observer, eventClass, event in tuple(self._source.events):
            messageID = id(event)

            # If we have a start point, skip messages up to and including the
            # one at the start point.
            if start is not None:
                if messageID == start:
                    messageID = None
                    start = None

                continue

            self._start = messageID

            if eventClass == u"access":
                message = event["log-format"] % event
            else:
                message = observer.formatEvent(event)
                if message is None:
                    continue

            eventText = textAsEvent(
                message, eventID=messageID, eventClass=eventClass
            )

            return succeed(eventText)

        if messageID is not None:
            # We just scanned all the messages, and none are the last one the
            # client saw.
            self._start = None

            marker = "-"

            return succeed(
                textAsEvent(marker, eventID=0, eventClass=u"access") +
                textAsEvent(marker, eventID=0, eventClass=u"server")
            )

        return succeed(None)


    def split(self, point):
        return fallbackSplit(self, point)


    def close(self):
        self._closed = True



class BufferingLogObserver(FileLogObserver):
    """
    Log observer that captures events in a buffer instead of writing to a file.

    @note: L{BufferingLogObserver} is an old-style log observer, as it
        inherits from L{FileLogObserver}.
    """

    timeFormat = None


    def __init__(self, buffer):
        class FooIO(object):
            def write(_, s):
                self._lastMessage = s

            def flush(_):
                pass

        FileLogObserver.__init__(self, FooIO())

        self.lastMessage = None
        self._buffer = buffer


    def emit(self, event):
        self._buffer.append((self, u"server", event))


    def formatEvent(self, event):
        self._lastMessage = None
        FileLogObserver.emit(self, event)
        return self._lastMessage



class AccessLogObserver(CommonAccessLoggingObserverExtensions):
    """
    Log observer that captures apache-style access log text entries in a
    buffer.

    @note: L{AccessLogObserver} is an old-style log observer, as it
        ultimately inherits from L{txweb2.log.BaseCommonAccessLoggingObserver}.
    """

    def __init__(self, buffer):
        CommonAccessLoggingObserverExtensions.__init__(self)

        self._buffer = buffer


    def logStats(self, event):
        # Only look at access log events
        if event["type"] != "access-log":
            return

        self._buffer.append((self, u"access", event))



def textAsEvent(text, eventID=None, eventClass=None):
    event = []

    if eventID is not None:
        event.append(u"id: {0}".format(eventID))

    if eventClass is not None:
        event.append(u"event: {0}".format(eventClass))

    event.extend(
        u"data: {0}".format(l) for l in text.split("\n")
    )

    return u"\n".join(event).encode("utf-8") + "\n\n"
