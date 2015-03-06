# -*- test-case-name: twext.enterprise.dal.test.test_record -*-
##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.record import SerializableRecord, fromTable
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks
from txdav.common.datastore.sql_tables import schema
from txdav.common.icommondatastore import InvalidSubscriptionValues

log = Logger()

"""
Classes and methods that relate to APN objects in the SQL store.
"""

class APNSubscriptionsRecord(SerializableRecord, fromTable(schema.APN_SUBSCRIPTIONS)):
    """
    @DynamicAttrs
    L{Record} for L{schema.APN_SUBSCRIPTIONS}.
    """
    pass



class APNSubscriptionsMixin(object):
    """
    A mixin for L{CommonStoreTransaction} that covers the APN API.
    """

    @inlineCallbacks
    def addAPNSubscription(
        self, token, key, timestamp, subscriber,
        userAgent, ipAddr
    ):
        if not (token and key and timestamp and subscriber):
            raise InvalidSubscriptionValues()

        # Cap these values at 255 characters
        userAgent = userAgent[:255]
        ipAddr = ipAddr[:255]

        records = yield APNSubscriptionsRecord.querysimple(
            self,
            token=token, resourceKey=key
        )
        if not records:  # Subscription does not yet exist
            try:
                yield APNSubscriptionsRecord.create(
                    self,
                    token=token,
                    resourceKey=key,
                    modified=timestamp,
                    subscriberGUID=subscriber,
                    userAgent=userAgent,
                    ipAddr=ipAddr
                )
            except Exception:
                # Subscription may have been added by someone else, which is fine
                pass

        else:  # Subscription exists, so update with new timestamp and subscriber
            try:
                yield records[0].update(
                    modified=timestamp,
                    subscriberGUID=subscriber,
                    userAgent=userAgent,
                    ipAddr=ipAddr,
                )
            except Exception:
                # Subscription may have been added by someone else, which is fine
                pass


    def removeAPNSubscription(self, token, key):
        return APNSubscriptionsRecord.deletesimple(
            self,
            token=token,
            resourceKey=key
        )


    def purgeOldAPNSubscriptions(self, olderThan):
        return APNSubscriptionsRecord.deletesome(
            self,
            APNSubscriptionsRecord.modified < olderThan,
        )


    def apnSubscriptionsByToken(self, token):
        return APNSubscriptionsRecord.querysimple(
            self,
            token=token,
        )


    def apnSubscriptionsByKey(self, key):
        return APNSubscriptionsRecord.querysimple(
            self,
            resourceKey=key,
        )


    def apnSubscriptionsBySubscriber(self, guid):
        return APNSubscriptionsRecord.querysimple(
            self,
            subscriberGUID=guid,
        )
