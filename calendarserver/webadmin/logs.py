# -*- test-case-name: calendarserver.webadmin.test.test_logs -*-
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
Calendar Server log viewing web UI.
"""

__all__ = [
    "LogsResource",
    "LogEventsResource",
]

from zope.interface import implementer

from twisted.python.log import FileLogObserver

from calendarserver.accesslog import CommonAccessLoggingObserverExtensions

from .eventsource import EventSourceResource, IEventDecoder
from .resource import PageElement, TemplateResource



class LogsPageElement(PageElement):
    """
    Logs page element.
    """

    def __init__(self):
        super(LogsPageElement, self).__init__(u"logs")


    def pageSlots(self):
        return {
            u"title": u"Server Logs",
        }



class LogsResource(TemplateResource):
    """
    Logs page resource.
    """

    addSlash = True


    def __init__(self, principalCollections):
        super(LogsResource, self).__init__(LogsPageElement, principalCollections, isdir=False)

        self.putChild(u"events", LogEventsResource(principalCollections))



class LogEventsResource(EventSourceResource):
    """
    Log event vending resource.
    """

    def __init__(self, principalCollections):
        super(LogEventsResource, self).__init__(EventDecoder, principalCollections)

        self.observers = (
            AccessLogObserver(self),
            ServerLogObserver(self),
        )

        for observer in self.observers:
            observer.start()



class ServerLogObserver(FileLogObserver):
    """
    Log observer that sends events to an L{EventSourceResource} instead of
    writing to a file.

    @note: L{ServerLogObserver} is an old-style log observer, as it inherits
        from L{FileLogObserver}.
    """

    timeFormat = None


    def __init__(self, resource):
        class FooIO(object):
            def write(_, s):
                self._lastMessage = s

            def flush(_):
                pass

        FileLogObserver.__init__(self, FooIO())

        self.lastMessage = None
        self._resource = resource


    def emit(self, event):
        self._resource.addEvents(((self, u"server", event),))


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

    def __init__(self, resource):
        super(AccessLogObserver, self).__init__()

        self._resource = resource


    def logStats(self, event):
        # Only look at access log events
        if event[u"type"] != u"access-log":
            return

        self._resource.addEvents(((self, u"access", event),))



@implementer(IEventDecoder)
class EventDecoder(object):
    """
    Decodes logging events.
    """

    @staticmethod
    def idForEvent(event):
        _ignore_observer, _ignore_eventClass, logEvent = event
        return id(logEvent)


    @staticmethod
    def classForEvent(event):
        _ignore_observer, eventClass, _ignore_logEvent = event
        return eventClass


    @staticmethod
    def textForEvent(event):
        observer, eventClass, logEvent = event

        try:
            if eventClass == u"access":
                text = logEvent[u"log-format"] % logEvent
            else:
                text = observer.formatEvent(logEvent)
                if text is None:
                    text = u""
        except:
            text = u"*** Error while formatting event ***"

        return text


    @staticmethod
    def retryForEvent(event):
        return None
