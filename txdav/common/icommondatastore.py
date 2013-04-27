##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
Storage interfaces that are not implied by DAV, but are shared between the
requirements for both CalDAV and CardDAV extensions.
"""

from zope.interface import Interface
from txdav.idav import ITransaction

__all__ = [
    # Exceptions
    "CommonStoreError",
    "NameNotAllowedError",
    "HomeChildNameNotAllowedError",
    "ObjectResourceNameNotAllowedError",
    "AlreadyExistsError",
    "HomeChildNameAlreadyExistsError",
    "ObjectResourceNameAlreadyExistsError",
    "ObjectResourceUIDAlreadyExistsError",
    "NotFoundError",
    "NoSuchHomeChildError",
    "NoSuchObjectResourceError",
    "ConcurrentModification",
    "InvalidObjectResourceError",
    "InternalDataStoreError",
]

#
# Exceptions
#

class CommonStoreError(RuntimeError):
    """
    Store generic error.
    """



class NameNotAllowedError(CommonStoreError):
    """
    Attempt to create an object with a name that is not allowed.
    """



class HomeChildNameNotAllowedError(NameNotAllowedError):
    """
    Home child name not allowed.
    """



class ObjectResourceNameNotAllowedError(NameNotAllowedError):
    """
    Object resource name not allowed.
    """



class AlreadyExistsError(CommonStoreError):
    """
    Attempt to create an object that already exists.
    """



class HomeChildNameAlreadyExistsError(AlreadyExistsError):
    """
    Home child already exists.
    """



class ObjectResourceNameAlreadyExistsError(AlreadyExistsError):
    """
    An object resource with the requested name already exists.
    """



class ObjectResourceUIDAlreadyExistsError(AlreadyExistsError):
    """
    An object resource with the requested UID already exists.
    """



class TooManyObjectResourcesError(CommonStoreError):
    """
    Home child has maximum allowed count of resources.
    """



class NotFoundError(CommonStoreError):
    """
    Requested data not found.
    """



class NoSuchHomeChildError(NotFoundError):
    """
    The requested home child does not exist.
    """



class NoSuchObjectResourceError(NotFoundError):
    """
    The requested object resource does not exist.
    """



class ConcurrentModification(NotFoundError):
    """
    Despite being loaded in the current transaction, the object whose data is
    being requested has been deleted or modified in another transaction, and
    therefore that data can no longer be retrieved.

    (Note: in the future we should be able to avoid these types of errors with
    more usage of locking, but until the impact of that on performance is
    determined, callers of C{component()} need to be aware that this can
    happen.)
    """



class InvalidObjectResourceError(CommonStoreError):
    """
    Invalid object resource data.
    """



class InvalidComponentForStoreError(CommonStoreError):
    """
    Invalid component for an object resource.
    """



class ObjectResourceTooBigError(CommonStoreError):
    """
    Object resource data is larger than allowed limit.
    """



class InvalidUIDError(CommonStoreError):
    """
    The UID of the component in a store operation does not match the existing value.
    """



class UIDExistsError(CommonStoreError):
    """
    The UID of the component in a store operation exists in the same calendar belonging to the owner.
    """



class UIDExistsElsewhereError(CommonStoreError):
    """
    The UID of the component in a store operation exists in different calendar belonging to the owner.
    """



class InvalidResourceMove(CommonStoreError):
    """
    Moving a resource failed.
    """



class InternalDataStoreError(CommonStoreError):
    """
    Uh, oh.
    """



class AllRetriesFailed(CommonStoreError):
    """
    In a re-tried subtransaction, all attempts failed to produce useful
    progress.  Other exceptions will be logged.
    """


# Indexing / sync tokens



class ReservationError(LookupError):
    """
    Attempt to reserve a UID which is already reserved or to unreserve a UID
    which is not reserved.
    """



class IndexedSearchException(ValueError):
    pass



class SyncTokenValidException(ValueError):
    pass


# APN Subscriptions



class InvalidSubscriptionValues(ValueError):
    """
    Invalid APN subscription values passed in.
    """


# IMIP Tokens



class InvalidIMIPTokenValues(ValueError):
    """
    Invalid IMIP token values passed in.
    """


#
# Interfaces
#



class ICommonTransaction(ITransaction):
    """
    Transaction functionality shared in common by calendar and addressbook
    stores.
    """

    def notificationsWithUID(uid): #@NoSelf
        """
        Retrieve the notification collection for the principal with the given
        C{uid}.

        @return: an L{INotificationCollection} or C{None} if no such
            notification collection exists.
        """

    def addAPNSubscription(token, key, timestamp, subscriber, userAgent, ipAddr): #@NoSelf
        """
        Add (or update) a subscription entry in the database.

        @param token: The device token of the subscriber
        @type token: C{str}

        @param key: The push key to subscribe to
        @type key: C{str}

        @param timestamp: The number of seconds since the epoch
        @type timestamp: C{int}

        @param subscriber: The GUID of the subscribing principal
        @type subscrbier: C{str}

        @param userAgent: The user agent requesting the subscription
        @type userAgent: C{str}

        @param ipAddr: The ip address requesting the subscription
        @type ipAddr: C{str}
        """

    def removeAPNSubscription(token, key): #@NoSelf
        """
        Remove a subscription entry from the database.

        @param token: The device token of the subscriber
        @type token: C{str}

        @param key: The push key
        @type key: C{str}
        """

    def purgeOldAPNSubscriptions(olderThan): #@NoSelf
        """
        Remove all subscription entries whose modified timestamp
        is older than the provided timestamp.

        @param olderThan: The cutoff timestamp in seconds
        @type token: C{int}
        """

    def apnSubscriptionsByToken(token): #@NoSelf
        """
        Retrieve all subscription entries for the token.

        @param token: The device token of the subscriber
        @type token: C{str}

        @return: tuples of (key, timestamp, guid)
        """

    def apnSubscriptionsByKey(key): #@NoSelf
        """
        Retrieve all subscription entries for the key.

        @param key: The push key
        @type key: C{str}

        @return: tuples of (token, guid)
        """

    def apnSubscriptionsBySubscriber(guid): #@NoSelf
        """
        Retrieve all subscription entries for the subscriber.

        @param guid: The GUID of the subscribed principal
        @type guid: C{str}

        @return: tuples of (token, key, timestamp, userAgent, ipAddr)
        """

    def imipCreateToken(organizer, attendee, icaluid, token=None): #@NoSelf
        """
        Add an entry in the database; if no token is provided, one will be
        generated.

        @param organizer: the CUA of the organizer
        @type organizer: C{str}
        @param attendee: the mailto: CUA of the attendee
        @type organizer: C{str}
        @param icaluid: the icalendar UID of the VEVENT
        @type organizer: C{str}
        @param token: the value to use in the "plus address" of the reply-to
        @type token: C{str}
        """

    def imipLookupByToken(token): #@NoSelf
        """
        Returns the organizer, attendee, and icaluid corresponding to the token

        @param token: the token to look up
        @type token: C{str}
        """

    def imipGetToken(organizer, attendee, icaluid): #@NoSelf
        """
        Returns the token (if any) corresponding to the given organizer, attendee,
        and icaluid combination

        @param organizer: the CUA of the organizer
        @type organizer: C{str}
        @param attendee: the mailto: CUA of the attendee
        @type organizer: C{str}
        @param icaluid: the icalendar UID of the VEVENT
        @type organizer: C{str}
        """

    def imipRemoveToken(token): #@NoSelf
        """
        Removes the entry for the given token.

        @param token: the token to remove
        @type token: C{str}
        """

    def purgeOldIMIPTokens(olderThan): #@NoSelf
        """
        Removes all tokens whose access time is before olderThan
        """



class IShareableCollection(Interface):
    """
    A collection resource which may be shared.
    """
