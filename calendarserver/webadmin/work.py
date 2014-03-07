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

from txdav.caldav.datastore.scheduling.imip.inbound import (
    IMIPPollingWork, IMIPReplyWork
)

from txdav.who.groups import GroupCacherPollingWork
from calendarserver.push.notifier import PushNotificationWork

from txdav.caldav.datastore.scheduling.work import (
    ScheduleOrganizerWork, ScheduleRefreshWork,
    ScheduleReplyWork, ScheduleAutoReplyWork,
)

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

    def __init__(self, store, pollInterval=1000):
        EventSourceResource.__init__(self, EventDecoder, bufferSize=100)

        self._store = store
        self._pollInterval = pollInterval


    @inlineCallbacks
    def render(self, request):
        yield self.poll()
        returnValue(super(WorkEventsResource, self).render(request))


    @inlineCallbacks
    def poll(self):
        txn = self._store.newTransaction()

        # Look up all of the jobs

        events = []

        jobsByTypeName = {}

        for job in (yield JobItem.all(txn)):
            jobsByTypeName.setdefault(job.workType, []).append(job)

        totalsByTypeName = {}

        for workType in JobItem.workTypes():
            typeName = workType.table.model.name
            jobs = jobsByTypeName.get(typeName, [])
            totalsByTypeName[typeName] = len(jobs)

            jobDicts = []

            for job in jobs:
                jobDict = dict(
                    jobID=job.jobID,
                    priority=job.priority,
                    notBefore=job.notBefore.ctime(),  # FIXME: Use HTTP format
                    notAfter=job.notAfter,
                )

                work = yield job.workItem()

                if work is not None:
                    if workType == PushNotificationWork:
                        attrs = ("pushID", "priority")
                    elif workType == ScheduleOrganizerWork:
                        attrs = ("icalendarUid", "attendeeCount")
                    elif workType == ScheduleRefreshWork:
                        attrs = ("icalendarUid", "attendeeCount")
                    elif workType == ScheduleReplyWork:
                        attrs = ("icalendarUid",)
                    elif workType == ScheduleAutoReplyWork:
                        attrs = ("icalendarUid",)
                    elif workType == GroupCacherPollingWork:
                        attrs = ()
                    elif workType == IMIPPollingWork:
                        attrs = ()
                    elif workType == IMIPReplyWork:
                        attrs = ("organizer", "attendee")
                    else:
                        attrs = ()

                    for attr in attrs:
                        jobDict["work_{}".format(attr)] = getattr(work, attr)

                jobDicts.append(jobDict)

            if jobDicts:
                events.append(dict(
                    eventClass=typeName,
                    eventID=time(),
                    eventText=asJSON(jobDicts),
                ))

        events.append(dict(
            eventClass=u"work-total",
            eventID=time(),
            eventText=asJSON(totalsByTypeName),
            eventRetry=(self._pollInterval),
        ))

        # Send data

        self.addEvents(events)

        # Schedule the next poll

        if not hasattr(self, "_clock"):
            from twisted.internet import reactor
            self._clock = reactor

        self._clock.callLater(self._pollInterval / 1000, self.poll)



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
