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
    "WorkMonitorResource",
]

from time import time
from json import dumps

from zope.interface import implementer

from twisted.internet.defer import inlineCallbacks, returnValue
# from twisted.web.template import tags as html, renderer

# from txdav.caldav.datastore.scheduling.imip.inbound import (
#     IMIPPollingWork, IMIPReplyWork
# )

# from twistedcaldav.directory.directory import GroupCacherPollingWork
# from calendarserver.push.notifier import PushNotificationWork

# from txdav.caldav.datastore.scheduling.work import (
#     ScheduleOrganizerWork, ScheduleReplyWork, ScheduleRefreshWork
# )

from twext.enterprise.jobqueue import JobItem

from .eventsource import EventSourceResource, IEventDecoder
from .resource import PageElement, TemplateResource



class WorkMonitorPageElement(PageElement):
    """
    Principal management page element.
    """

    def __init__(self):
        PageElement.__init__(self, u"work")


    def pageSlots(self):
        return {
            u"title": u"Workload Monitor",
        }



class WorkMonitorResource(TemplateResource):
    """
    Principal management page resource.
    """

    addSlash = True


    def __init__(self, store):
        TemplateResource.__init__(
            self, lambda: WorkMonitorPageElement()
        )

        self.putChild(u"events", WorkEventsResource(store))



class WorkEventsResource(EventSourceResource):
    """
    Resource that vends work queue information via HTML5 EventSource events.
    """

    def __init__(self, store, pollInterval=1):
        EventSourceResource.__init__(self, EventDecoder, bufferSize=1)

        self._store = store
        self._pollInterval = pollInterval


    @inlineCallbacks
    def render(self, request):
        yield self.poll()
        returnValue(super(WorkEventsResource, self).render(request))


    @inlineCallbacks
    def poll(self):
        txn = self._store.newTransaction()

        jobData = yield JobItem.histogram(txn)

        self.addEvents((
            dict(
                eventClass=u"work-total",
                eventID=time(),
                eventText=asJSON(jobData),
                eventRetry=(self._pollInterval * 1000),
            ),
        ))

        if not hasattr(self, "_clock"):
            from twisted.internet import reactor
            self._clock = reactor

        self._clock.callLater(self._pollInterval, self.poll)



@implementer(IEventDecoder)
class EventDecoder(object):
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
        return event.get("eventRetry")



def asJSON(obj):
    return dumps(obj, separators=(',', ':'))
