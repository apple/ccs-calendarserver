##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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

#
# Interfaces
#

class ICommonTransaction(ITransaction):
    """
    Transaction functionality shared in common by calendar and addressbook
    stores.
    """

    def notificationsWithUID(uid):
        """
        Retrieve the notification collection for the principal with the given
        C{uid}.

        @return: an L{INotificationCollection} or C{None} if no such
            notification collection exists.
        """

    def addAPNSubscription(token, key, timestamp, subscriber):
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
        """

    def removeAPNSubscription(token, key):
        """
        Remove a subscription entry from the database.

        @param token: The device token of the subscriber
        @type token: C{str}

        @param key: The push key
        @type key: C{str}
        """

    def apnSubscriptionsByToken(token):
        """
        Retrieve all subscription entries for the token.

        @param token: The device token of the subscriber
        @type token: C{str}

        @return: tuples of (key, timestamp, guid)
        """

    def apnSubscriptionsByKey(key):
        """
        Retrieve all subscription entries for the key.

        @param key: The push key
        @type key: C{str}

        @return: tuples of (token, guid)
        """

    def apnSubscriptionsBySubscriber(guid):
        """
        Retrieve all subscription entries for the subscriber.

        @param guid: The GUID of the subscribed principal
        @type guid: C{str}

        @return: tuples of (token, key, timestamp)
        """


class IShareableCollection(Interface):
    """
    A collection resource which may be shared.
    """

    def setSharingUID(shareeUID):
        """
        This is a temporary shim method due to the way L{twistedcaldav.sharing}
        works, which is that it expects to look in the 'sharesDB' object to
        find what calendars are shared by whom, separately looks up the owner's
        calendar home based on  that information, then sets the sharee's UID on
        that calendar, the main effect of which is to change the per-user uid
        of the properties for that calendar object.

        What I{should} be happening is that the calendars
        just show up in the sharee's calendar home, and have a separate methods
        to determine the sharee's and the owner's calendar homes, so the front
        end can tell it's shared.

        @param shareeUID: the UID of the sharee.
        @type shareeUID: C{str}
        """
