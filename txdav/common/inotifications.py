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
Common notification interfaces
"""

from zope.interface.interface import Interface
from txdav.idav import IDataStoreObject


__all__ = [
    "INotificationCollection",
    "INotificationObject",
]

class INotificationCollection(Interface):
    """
    NotificationCollection

    A notification collection is a container for notification objects.
    A notification collection belongs to a specific principal.
    """

    def name(): #@NoSelf
        """
        Identify this notification collection.

        @return: the name of this notification collection.
        @rtype: C{str}
        """

    def notificationObjects(): #@NoSelf
        """
        Retrieve the notification objects contained in this notification
        collection with the given C{componentType}.

        @param componentType: a string.
        @return: an iterable of L{INotificationObject}s.
        """

    def notificationObjectWithName(name): #@NoSelf
        """
        Retrieve the notification object with the given C{name} contained
        in this notification collection.

        @param name: a string.
        @return: an L{INotificationObject} or C{None} if no such notification
            object exists.
        """

    def notificationObjectWithUID(uid): #@NoSelf
        """
        Retrieve the notification object with the given C{uid} contained
        in this notification collection.

        @param uid: a string.
        @return: an L{INotificationObject} or C{None} if no such notification
            object exists.
        """

    def writeNotificationObject(uid, xmltype, xmldata): #@NoSelf
        """
        Write a notification with the given C{uid} in this notification
        collection from the given C{xmldata} with given C{xmltype}.  If a
        L{INotificationObject} with the same uid already exists in this
        L{INotificationCollection}, it will be overwritten.

        @param uid: a string uniquely identifying the notification to be
            written.
        @type uid: C{str}

        @param xmltype: the node within the notification payload, emptied of
            its children, to indicate the type of notification and fill out the
            C{CS:notificationtype} property.

        @type xmltype: an instance of
            L{txdav.xml.base.WebDAVElement},
            most likely a subclass like L{twistedcaldav.customxml.InviteReply},
            L{twistedcaldav.customxml.InviteRemove}, etc.

        @param xmldata: the serialized representation of the C{CS:notification}
            node.
        @type xmldata: C{str}
        """

    def removeNotificationObjectWithName(name): #@NoSelf
        """
        Remove the notification object with the given C{name} from this
        notification collection. If C{deleteOnly} is C{True} then do not

        @param name: a string.
        @type name: C{str}

        @raise NoSuchObjectResourceError: if no such NoSuchObjectResourceError
            object exists.
        """

    def removeNotificationObjectWithUID(uid): #@NoSelf
        """
        Remove the notification object with the given C{uid} from this
        notification collection.

        @param uid: a string.
        @raise NoSuchObjectResourceError: if the notification object does
            not exist.
        """

    def syncToken(): #@NoSelf
        """
        Retrieve the current sync token for this notification.

        @return: a string containing a sync token.
        """

    def properties(): #@NoSelf
        """
        Retrieve the property store for this notification.

        @return: an L{IPropertyStore}.
        """



class INotificationObject(IDataStoreObject):
    """
    Notification object

    An notification object describes an XML notification.
    """

    def setData(uid, xmltype, xmldata, inserting=False): #@NoSelf
        """
        Rewrite this notification object to match the given C{xmltype} and
        C{xmldata}. C{xmldata} must have the same UID as this notification object.

        @param xmltype: a string.
        @param xmldata: a string.
        @raise InvalidObjectResourceError: if the given
            C{xmltype} or C{xmldata} is not a valid for
            an notification object.
        """

    def xmldata(): #@NoSelf
        """
        Retrieve the notification data for this notification object.

        @return: a string.
        """

    def uid(): #@NoSelf
        """
        Retrieve the UID for this notification object.

        @return: a string containing a UID.
        """

    def notificationCollection(): #@NoSelf
        """
        @return: the parent L{INotificationCollection} which this
            L{INotificationObject} was retrieved from.

        @rtype: L{INotificationCollection}
        """
