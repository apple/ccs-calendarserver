##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Common notification interfaces
"""

from zope.interface.interface import Interface


__all__ = [
    "INotificationCollection",
    "INotification",
]

class INotificationCollection(Interface):
    """
    NotificationCollection

    A notification collection is a container for notification objects.
    A notification collection belongs to a specific principal.
    """

    def name():
        """
        Identify this notification collection.

        @return: the name of this notification collection.
        @rtype: C{str}
        """

    def notificationObjects():
        """
        Retrieve the notification objects contained in this notification
        collection with the given C{componentType}.

        @param componentType: a string.
        @return: an iterable of L{INotificationObject}s.
        """

    def notificationObjectWithName(name):
        """
        Retrieve the notification object with the given C{name} contained
        in this notification collection.

        @param name: a string.
        @return: an L{INotificationObject} or C{None} if no such notification
            object exists.
        """

    def notificationObjectWithUID(uid):
        """
        Retrieve the notification object with the given C{uid} contained
        in this notification collection.

        @param uid: a string.
        @return: an L{INotificationObject} or C{None} if no such notification
            object exists.
        """

    def writeNotificationObject(uid, xmltype, xmldata):
        """
        Write a notification with the given C{uid} in this
        notification collection from the given C{xmldata} with
        given C{xmltype}. Create or overwrite are OK.

        @param uid: a string.
        @param xmltype: a string.
        @param xmldata: a string.
        @param component: a C{VCARD} L{Component}
        """

    def removeNotificationObjectWithName(name):
        """
        Remove the notification object with the given C{name} from this
        notification collection. If C{deleteOnly} is C{True} then do not
        

        @param name: a string.
        @raise NoSuchObjectResourceError: if no such NoSuchObjectResourceError object
            exists.
        """

    def removeNotificationObjectWithUID(uid):
        """
        Remove the notification object with the given C{uid} from this
        notification collection.

        @param uid: a string.
        @raise NoSuchObjectResourceError: if the notification object does
            not exist.
        """

    def syncToken():
        """
        Retrieve the current sync token for this notification.

        @return: a string containing a sync token.
        """

    def notificationObjectsSinceToken(token):
        """
        Retrieve all notification objects in this notification collection that have
        changed since the given C{token} was last valid.

        @param token: a sync token.
        @return: a 3-tuple containing an iterable of
            L{INotificationObject}s that have changed, an iterable of uids
            that have been removed, and the current sync token.
        """

    def properties():
        """
        Retrieve the property store for this notification.

        @return: an L{IPropertyStore}.
        """


class INotificationObject(Interface):
    """
    Notification object

    An notification object describes an XML notification.
    """

    def setData(uid, xmltype, xmldata):
        """
        Rewrite this notification object to match the given C{xmltype} and
        C{xmldata}. C{xmldata} must have the same UID as this notification object.

        @param xmltype: a string.
        @param xmldata: a string.
        @raise InvalidObjectResourceError: if the given
            C{xmltype} or C{xmldata} is not a valid for
            an notification object.
        """

    def xmldata():
        """
        Retrieve the notification data for this notification object.

        @return: a string.
        """

    def uid():
        """
        Retrieve the UID for this notification object.

        @return: a string containing a UID.
        """

    def properties():
        """
        Retrieve the property store for this notification object.

        @return: an L{IPropertyStore}.
        """
