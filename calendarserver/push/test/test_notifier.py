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

from twistedcaldav.test.util import TestCase
from calendarserver.push.notifier import PushDistributor
from calendarserver.push.notifier import getPubSubAPSConfiguration
from calendarserver.push.notifier import PushNotificationWork
from twisted.internet.defer import inlineCallbacks, succeed
from twistedcaldav.config import ConfigDict
from txdav.common.datastore.test.util import buildStore


class StubService(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.history = []

    def enqueue(self, transaction, id):
        self.history.append(id)
        return(succeed(None))

class PushDistributorTests(TestCase):

    @inlineCallbacks
    def test_enqueue(self):
        stub = StubService()
        dist = PushDistributor([stub])
        yield dist.enqueue(None, "testing")
        self.assertEquals(stub.history, ["testing"])

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
        result = getPubSubAPSConfiguration("CalDAV|foo", config)
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

    def enqueue(self, transaction, pushID):
        self.history.append(pushID)

class PushNotificationWorkTests(TestCase):

    @inlineCallbacks
    def test_work(self):
        self.store = yield buildStore(self, None)

        pushDistributor = StubDistributor()

        def decorateTransaction(txn):
            txn._pushDistributor = pushDistributor

        self.store.callWithNewTransactions(decorateTransaction)

        txn = self.store.newTransaction()
        wp = (yield txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/foo/",
        ))
        yield txn.commit()
        yield wp.whenExecuted()
        self.assertEquals(pushDistributor.history, ["/CalDAV/localhost/foo/"])

        pushDistributor.reset()
        txn = self.store.newTransaction()
        wp = (yield txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
        ))
        wp = (yield txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
        ))
        wp = (yield txn.enqueue(PushNotificationWork,
            pushID="/CalDAV/localhost/bar/",
        ))
        yield txn.commit()
        yield wp.whenExecuted()
        self.assertEquals(pushDistributor.history, ["/CalDAV/localhost/bar/"])
