##
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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

from twistedcaldav.test.util import StoreTestCase
from calendarserver.push.notifier import PushDistributor
from calendarserver.push.notifier import getPubSubAPSConfiguration
from calendarserver.push.notifier import PushNotificationWork
from twisted.internet.defer import inlineCallbacks, succeed, gatherResults
from twistedcaldav.config import ConfigDict
from txdav.common.datastore.test.util import populateCalendarsFrom
from txdav.common.datastore.sql_tables import _BIND_MODE_WRITE
from calendarserver.push.util import PushPriority
from txdav.idav import ChangeCategory

class StubService(object):
    def __init__(self):
        self.reset()


    def reset(self):
        self.history = []


    def enqueue(self, transaction, id, dataChangedTimestamp=None,
        priority=None):
        self.history.append((id, priority))
        return(succeed(None))



class PushDistributorTests(StoreTestCase):

    @inlineCallbacks
    def test_enqueue(self):
        stub = StubService()
        dist = PushDistributor([stub])
        yield dist.enqueue(None, "testing", PushPriority.high)
        self.assertEquals(stub.history, [("testing", PushPriority.high)])


    def test_getPubSubAPSConfiguration(self):
        config = ConfigDict({
            "EnableSSL" : True,
            "ServerHostName" : "calendars.example.com",
            "SSLPort" : 8443,
            "HTTPPort" : 8008,
            "Notifications" : {
                "Services" : {
                    "APNS" : {
                        "CalDAV" : {
                            "Topic" : "test topic",
                        },
                        "SubscriptionRefreshIntervalSeconds" : 42,
                        "SubscriptionURL" : "apns",
                        "Environment" : "prod",
                        "Enabled" : True,
                    },
                },
            },
        })
        result = getPubSubAPSConfiguration(("CalDAV", "foo",), config)
        self.assertEquals(
            result,
            {
                "SubscriptionRefreshIntervalSeconds": 42,
                "SubscriptionURL": "https://calendars.example.com:8443/apns",
                "APSBundleID": "test topic",
                "APSEnvironment": "prod"
            }
        )



class StubDistributor(object):
    def __init__(self):
        self.reset()


    def reset(self):
        self.history = []


    def enqueue(self, transaction, pushID, dataChangedTimestamp=None,
        priority=None):
        self.history.append((pushID, priority))
        return(succeed(None))


class PushNotificationWorkTests(StoreTestCase):

    @inlineCallbacks
    def test_work(self):

        pushDistributor = StubDistributor()

        def decorateTransaction(txn):
            txn._pushDistributor = pushDistributor

        self._sqlCalendarStore.callWithNewTransactions(decorateTransaction)

        txn = self._sqlCalendarStore.newTransaction()
        wp = (yield txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/foo/",
            priority=PushPriority.high.value
        ))
        yield txn.commit()
        yield wp.whenExecuted()
        self.assertEquals(pushDistributor.history,
            [("/CalDAV/localhost/foo/", PushPriority.high)])

        pushDistributor.reset()
        txn = self._sqlCalendarStore.newTransaction()
        proposals = []
        wp = txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
            priority=PushPriority.high.value
        )
        proposals.append(wp.whenExecuted())
        wp = txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
            priority=PushPriority.high.value
        )
        proposals.append(wp.whenExecuted())
        wp = txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
            priority=PushPriority.high.value
        )
        proposals.append(wp.whenExecuted())
        # Enqueue a different pushID to ensure those are not grouped with
        # the others:
        wp = txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/baz/",
            priority=PushPriority.high.value
        )
        proposals.append(wp.whenExecuted())

        yield txn.commit()
        yield gatherResults(proposals)
        self.assertEquals(set(pushDistributor.history),
            set([("/CalDAV/localhost/bar/", PushPriority.high),
             ("/CalDAV/localhost/baz/", PushPriority.high)]))

        # Ensure only the high-water-mark priority push goes out, by
        # enqueuing low, medium, and high notifications
        pushDistributor.reset()
        txn = self._sqlCalendarStore.newTransaction()
        proposals = []
        wp = txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
            priority=PushPriority.low.value
        )
        proposals.append(wp.whenExecuted())
        wp = txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
            priority=PushPriority.high.value
        )
        proposals.append(wp.whenExecuted())
        wp = txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
            priority=PushPriority.medium.value
        )
        proposals.append(wp.whenExecuted())
        yield txn.commit()
        yield gatherResults(proposals)
        self.assertEquals(pushDistributor.history,
            [("/CalDAV/localhost/bar/", PushPriority.high)])


class NotifierFactory(StoreTestCase):

    requirements = {
        "home1" : {
            "calendar_1" : {}
        },
        "home2" : {
            "calendar_1" : {}
        },
    }

    @inlineCallbacks
    def populate(self):

        # Need to bypass normal validation inside the store
        yield populateCalendarsFrom(self.requirements, self.storeUnderTest())
        self.notifierFactory.reset()


    def test_storeInit(self):

        self.assertTrue("push" in self._sqlCalendarStore._notifierFactories)


    @inlineCallbacks
    def test_homeNotifier(self):

        home = yield self.homeUnderTest()
        yield home.notifyChanged(category=ChangeCategory.default)
        self.assertEquals(self.notifierFactory.history,
            [("/CalDAV/example.com/home1/", PushPriority.high)])
        yield self.commit()


    @inlineCallbacks
    def test_calendarNotifier(self):

        calendar = yield self.calendarUnderTest()
        yield calendar.notifyChanged(category=ChangeCategory.default)
        self.assertEquals(
            set(self.notifierFactory.history),
            set([
                ("/CalDAV/example.com/home1/", PushPriority.high),
                ("/CalDAV/example.com/home1/calendar_1/", PushPriority.high)])
        )
        yield self.commit()


    @inlineCallbacks
    def test_shareWithNotifier(self):

        calendar = yield self.calendarUnderTest()
        home2 = yield self.homeUnderTest(name="home2")
        yield calendar.shareWith(home2, _BIND_MODE_WRITE)
        self.assertEquals(
            set(self.notifierFactory.history),
            set([
                ("/CalDAV/example.com/home1/", PushPriority.high),
                ("/CalDAV/example.com/home1/calendar_1/", PushPriority.high),
                ("/CalDAV/example.com/home2/", PushPriority.high),
            ])
        )
        yield self.commit()

        calendar = yield self.calendarUnderTest()
        home2 = yield self.homeUnderTest(name="home2")
        yield calendar.unshareWith(home2)
        self.assertEquals(
            set(self.notifierFactory.history),
            set([
                ("/CalDAV/example.com/home1/", PushPriority.high),
                ("/CalDAV/example.com/home1/calendar_1/", PushPriority.high),
                ("/CalDAV/example.com/home2/", PushPriority.high),
            ])
        )
        yield self.commit()


    @inlineCallbacks
    def test_sharedCalendarNotifier(self):

        calendar = yield self.calendarUnderTest()
        home2 = yield self.homeUnderTest(name="home2")
        shareName = yield calendar.shareWith(home2, _BIND_MODE_WRITE)
        yield self.commit()
        self.notifierFactory.reset()

        shared = yield self.calendarUnderTest(home="home2", name=shareName)
        yield shared.notifyChanged(category=ChangeCategory.default)
        self.assertEquals(
            set(self.notifierFactory.history),
            set([
                ("/CalDAV/example.com/home1/", PushPriority.high),
                ("/CalDAV/example.com/home1/calendar_1/", PushPriority.high)])
        )
        yield self.commit()


    @inlineCallbacks
    def test_notificationNotifier(self):

        notifications = yield self.transactionUnderTest().notificationsWithUID("home1")
        yield notifications.notifyChanged(category=ChangeCategory.default)
        self.assertEquals(
            set(self.notifierFactory.history),
            set([
                ("/CalDAV/example.com/home1/", PushPriority.high),
                ("/CalDAV/example.com/home1/notification/", PushPriority.high)])
        )
        yield self.commit()
