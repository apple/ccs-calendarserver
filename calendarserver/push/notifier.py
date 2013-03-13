##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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
Notification framework for Calendar Server
"""

import datetime
from twext.python.log import LoggingMixIn, Logger
from twisted.internet.defer import inlineCallbacks, succeed
from twext.enterprise.dal.record import fromTable
from twext.enterprise.queue import WorkItem
from txdav.common.datastore.sql_tables import schema
from twext.enterprise.dal.syntax import Delete


log = Logger()


class PushNotificationWork(WorkItem, fromTable(schema.PUSH_NOTIFICATION_WORK)):

    group = property(lambda self: self.pushID)

    @inlineCallbacks
    def doWork(self):

        # Delete all other work items with the same pushID
        yield Delete(From=self.table,
                     Where=self.table.PUSH_ID == self.pushID 
                    ).on(self.transaction)

        pushDistributor = self.transaction._pushDistributor
        if pushDistributor is not None:
            yield pushDistributor.enqueue(self.pushID)



# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# Classes used within calendarserver itself
#

class Notifier(LoggingMixIn):
    """
    Provides a hook for sending change notifications to the
    L{NotifierFactory}.
    """

    def __init__(self, notifierFactory, label="default", id=None, prefix=None):
        self._notifierFactory = notifierFactory
        self._ids = { label : self.normalizeID(id) }
        self._notify = True
        self._prefix = prefix

    def normalizeID(self, id):
        urn = "urn:uuid:"
        try:
            if id.startswith(urn):
                return id[len(urn):]
        except AttributeError:
            pass
        return id

    def enableNotify(self, arg):
        self.log_debug("enableNotify: %s" % (self._ids['default'][1],))
        self._notify = True

    def disableNotify(self):
        self.log_debug("disableNotify: %s" % (self._ids['default'][1],))
        self._notify = False

    @inlineCallbacks
    def notify(self):
        for label in self._ids.iterkeys():
            id = self.getID(label=label)
            if id is not None:
                if self._notify:
                    self.log_debug("Notifications are enabled: %s %s" %
                        (label, id))
                    yield self._notifierFactory.send(id)
                else:
                    self.log_debug("Skipping notification for: %s" % (id,))

    def clone(self, label="default", id=None):
        newNotifier = self.__class__(self._notifierFactory)
        newNotifier._ids = self._ids.copy()
        newNotifier._ids[label] = id
        newNotifier._prefix = self._prefix
        return newNotifier

    def addID(self, label="default", id=None):
        self._ids[label] = self.normalizeID(id)

    def getID(self, label="default"):
        id = self._ids.get(label, None)
        if self._prefix is None:
            return id
        else:
            return "%s|%s" % (self._prefix, id)

    def nodeName(self, label="default"):
        id = self.getID(label=label)
        return succeed(self._notifierFactory.pushKeyForId(id))


class NotifierFactory(LoggingMixIn):
    """
    Notifier Factory

    Creates Notifier instances and forwards notifications from them to the
    work queue.
    """

    def __init__(self, store, hostname, coalesceSeconds, reactor=None):
        self.store = store
        self.hostname = hostname
        self.coalesceSeconds = coalesceSeconds

        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor

    @inlineCallbacks
    def send(self, id):
        txn = self.store.newTransaction()
        notBefore = datetime.datetime.utcnow() + datetime.timedelta(
            seconds=self.coalesceSeconds)
        yield txn.enqueue(PushNotificationWork, pushID=self.pushKeyForId(id),
            notBefore=notBefore)
        yield txn.commit()

    def newNotifier(self, label="default", id=None, prefix=None):
        return Notifier(self, label=label, id=id, prefix=prefix)

    def pushKeyForId(self, id):
        path = "/"

        try:
            prefix, id = id.split("|", 1)
            path += "%s/" % (prefix,)
        except ValueError:
            # id has no prefix
            pass

        path += "%s/" % (self.hostname,)
        if id:
            path += "%s/" % (id,)
        return path



def getPubSubAPSConfiguration(pushKey, config):
    """
    Returns the Apple push notification settings specific to the pushKey
    """
    try:
        protocol, ignored = pushKey.split("|", 1)
    except ValueError:
        # id has no protocol, so we can't look up APS config
        return None

    # If we are directly talking to apple push, advertise those settings
    applePushSettings = config.Notifications.Services.APNS
    if applePushSettings.Enabled:
        settings = {}
        settings["APSBundleID"] = applePushSettings[protocol]["Topic"]
        if config.EnableSSL:
            url = "https://%s:%s/%s" % (config.ServerHostName, config.SSLPort,
                applePushSettings.SubscriptionURL)
        else:
            url = "http://%s:%s/%s" % (config.ServerHostName, config.HTTPPort,
                applePushSettings.SubscriptionURL)
        settings["SubscriptionURL"] = url
        settings["SubscriptionRefreshIntervalSeconds"] = applePushSettings.SubscriptionRefreshIntervalSeconds
        settings["APSEnvironment"] = applePushSettings.Environment
        return settings

    return None


class PushDistributor(object):
    """
    Distributes notifications to the protocol-specific subservices
    """

    def __init__(self, observers):
        """
        @param observers: the list of observers to distribute pushKeys to
        @type observers: C{list} 
        """
        # TODO: add an IPushObservers interface?
        self.observers = observers 

    @inlineCallbacks
    def enqueue(self, pushKey):
        """
        Pass along enqueued pushKey to any observers

        @param pushKey: the push key to distribute to the observers
        @type pushKey: C{str}
        """
        for observer in self.observers:
            yield observer.enqueue(pushKey)
