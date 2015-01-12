# -*- test-case-name: calendarserver.webadmin.test.test_principals -*-
##
# Copyright (c) 2014-2015 Apple Inc. All rights reserved.
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

from twext.python.log import Logger
from twext.enterprise.jobqueue import JobItem

from txdav.caldav.datastore.scheduling.imip.inbound import (
    IMIPPollingWork, IMIPReplyWork
)

from txdav.who.groups import GroupCacherPollingWork
from calendarserver.push.notifier import PushNotificationWork

from txdav.caldav.datastore.scheduling.work import (
    ScheduleOrganizerWork, ScheduleRefreshWork,
    ScheduleReplyWork, ScheduleAutoReplyWork,
)

from .eventsource import EventSourceResource, IEventDecoder
from .resource import PageElement, TemplateResource



class WorkMonitorPageElement(PageElement):
    """
    Principal management page element.
    """

    def __init__(self):
        super(WorkMonitorPageElement, self).__init__(u"work")


    def pageSlots(self):
        return {
            u"title": u"Workload Monitor",
        }



class WorkMonitorResource(TemplateResource):
    """
    Principal management page resource.
    """

    addSlash = True


    def __init__(self, store, principalCollections):
        super(WorkMonitorResource, self).__init__(
            lambda: WorkMonitorPageElement(), principalCollections, isdir=False
        )

        self.putChild(u"events", WorkEventsResource(store, principalCollections))



class WorkEventsResource(EventSourceResource):
    """
    Resource that vends work queue information via HTML5 EventSource events.
    """

    log = Logger()


    def __init__(self, store, principalCollections, pollInterval=1000):
        super(WorkEventsResource, self).__init__(EventDecoder, principalCollections, bufferSize=100)

        self._store = store
        self._pollInterval = pollInterval
        self._polling = False


    @inlineCallbacks
    def render(self, request):
        yield self.poll()
        returnValue(super(WorkEventsResource, self).render(request))


    @inlineCallbacks
    def poll(self):
        if self._polling:
            return

        self._polling = True

        txn = self._store.newTransaction()
        try:

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
                    def formatTime(datetime):
                        if datetime is None:
                            return None
                        else:
                            # FIXME: Use HTTP time format
                            return datetime.ctime()

                    jobDict = dict(
                        job_jobID=job.jobID,
                        job_priority=job.priority,
                        job_weight=job.weight,
                        job_notBefore=formatTime(job.notBefore),
                    )

                    work = yield job.workItem()

                    attrs = ("workID", "group")

                    if workType == PushNotificationWork:
                        attrs += ("pushID", "priority")
                    elif workType == ScheduleOrganizerWork:
                        attrs += ("icalendarUid", "attendeeCount")
                    elif workType == ScheduleRefreshWork:
                        attrs += ("icalendarUid", "attendeeCount")
                    elif workType == ScheduleReplyWork:
                        attrs += ("icalendarUid",)
                    elif workType == ScheduleAutoReplyWork:
                        attrs += ("icalendarUid",)
                    elif workType == GroupCacherPollingWork:
                        attrs += ()
                    elif workType == IMIPPollingWork:
                        attrs += ()
                    elif workType == IMIPReplyWork:
                        attrs += ("organizer", "attendee")
                    else:
                        attrs = ()

                    if attrs:
                        if work is None:
                            self.log.error(
                                "workItem() returned None for job: {job}",
                                job=job
                            )
                            # jobDict.update((attr, None) for attr in attrs)
                            for attr in attrs:
                                jobDict["work_{}".format(attr)] = None
                        else:
                            # jobDict.update(
                            #     ("work_{}".format(attr), getattr(work, attr))
                            #     for attr in attrs
                            # )
                            for attr in attrs:
                                jobDict["work_{}".format(attr)] = (
                                    getattr(work, attr)
                                )

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

        except:
            self._polling = False
            yield txn.abort()
            raise
        else:
            yield txn.commit()

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
