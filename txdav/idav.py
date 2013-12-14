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
WebDAV interfaces
"""

__all__ = [
    "PropertyStoreError",
    "PropertyChangeNotAllowedError",
    "IPropertyName",
    "IPropertyStore",
    "IDataStore",
    "IDataStoreObject",
    "ITransaction",
    "INotifier",
    "IStoreNotifierFactory",
    "IStoreNotifier",
]

from zope.interface import Attribute, Interface
from zope.interface.common.mapping import IMapping

from twisted.python.constants import Values, ValueConstant
from calendarserver.push.util import PushPriority

#
# Exceptions
#

class PropertyStoreError(RuntimeError):
    """
    Property store error.
    """



class PropertyChangeNotAllowedError(PropertyStoreError):
    """
    Property cannot be edited.
    """
    def __init__(self, message, keys):
        PropertyStoreError.__init__(self, message)
        self.keys = keys



#
# Interfaces
#

class IPropertyName(Interface):
    """
    Property name.
    """
    namespace = Attribute("Namespace")
    name = Attribute("Name")

    def toString(): #@NoSelf
        """
        Returns the string representation of the property name.

        @return: a string
        """



class IPropertyStore(IMapping):
    """
    WebDAV property store

    This interface is based on L{IMapping}, but any changed to data
    are not persisted until C{flush()} is called, and can be undone
    using C{abort()}.

    Also, keys must be L{IPropertyName} providers and values must be
    L{twext.web2.element.dav.base.WeDAVElement}s.
    """
    # FIXME: the type for values isn't quite right, there should be some more
    # specific interface for that.

    def flush(): #@NoSelf
        """
        Flush the property store.
        @return: C{None}
        """

    def abort(): #@NoSelf
        """
        Abort changes to the property store.
        @return: C{None}
        """



class IDataStore(Interface):
    """
    An L{IDataStore} is a storage of some objects.
    """

    def newTransaction(label=None): #@NoSelf
        """
        Create a new transaction.

        @param label: A label to assign to this transaction for diagnostic
            purposes.
        @type label: C{str}

        @return: a new transaction which provides L{ITransaction}, as well as
            sub-interfaces to request appropriate data objects.

        @rtype: L{ITransaction}
        """

    def setMigrating(state): #@NoSelf
        """
        Set the "migrating" state to either True or False.  This state is
        used to supress push notifications and etag changes.

        @param state: the boolean value to set the migrating state to
        @type state: C{boolean}
        """



class IDataStoreObject(Interface):
    """
    An L{IDataStoreObject} are the objects stored in an L{IDataStore}.
    """

    def name(): #@NoSelf
        """
        Identify the name of the object

        @return: the name of this object.
        @rtype: C{str}
        """

    def contentType(): #@NoSelf
        """
        The content type of the object's content.

        @rtype: L{MimeType}
        """

    def md5(): #@NoSelf
        """
        The MD5 hex digest of this object's content.

        @rtype: C{str}
        """

    def size(): #@NoSelf
        """
        The octet-size of this object's content.

        @rtype: C{int}
        """

    def created(): #@NoSelf
        """
        The creation date-time stamp of this object.

        @rtype: C{int}
        """

    def modified(): #@NoSelf
        """
        The last modification date-time stamp of this object.

        @rtype: C{int}
        """

    def properties(): #@NoSelf
        """
        Retrieve the property store for this object.

        @return: an L{IPropertyStore}.
        """



class ITransaction(Interface):
    """
    Transaction that can be aborted and either succeeds or fails in
    its entirety.
    """

    def abort(): #@NoSelf
        """
        Abort this transaction.

        @raise AlreadyFinishedError: The transaction was already finished with
            an 'abort' or 'commit' and cannot be aborted again.
        """

    def commit(): #@NoSelf
        """
        Perform this transaction.

        @raise AlreadyFinishedError: The transaction was already finished with
            an 'abort' or 'commit' and cannot be committed again.
        """

    def postCommit(operation): #@NoSelf
        """
        @see: L{IAsyncTransaction.postCommit}
        """

    def postAbort(operation): #@NoSelf
        """
        @see: L{IAsyncTransaction.postAbort}
        """

    def store(): #@NoSelf
        """
        The store that this transaction was initiated from.

        @rtype: L{IDataStore}
        """



class ChangeCategory(Values):
    """
    Constants to use for notifyChanged's category parameter.  Maps
    types of changes to the appropriate push priority level.
    TODO: make these values configurable in plist perhaps.
    """
    default             = ValueConstant(PushPriority.high)
    inbox               = ValueConstant(PushPriority.medium)
    attendeeITIPUpdate  = ValueConstant(PushPriority.medium)
    organizerITIPUpdate = ValueConstant(PushPriority.medium)



class INotifier(Interface):
    """
    Interface for an object that can send change notifications. Notifiers are associated with specific notifier factories
    and stored in a dict with keys matching the factory name.
    """

    _notifiers = Attribute("Dict of L{IStoreNotifier}'s to send notifications to.")

    def addNotifier(factory_name, notifier): #@NoSelf
        """
        Add an L{IStoreNotifier} to the list of notifiers for this object.

        @param factory_name: the "type" of notifier based on its factory name
        @type factory_name: C{str}
        @param notifier: the notifier
        @type notifier: L{IStoreNotifier}
        """

    def getNotifier(factory_name): #@NoSelf
        """
        Return a notifier for the specified factory name if it exists.

        @param factory_name: the factory name for a notifier to look for.
        @type factory_name: C{str}

        @return: the notifier if found, else C{None}
        @rtype: L{IStoreNotifier} or C{None}
        """

    def notifyChanged(category): #@NoSelf
        """
        Send a change notification to any notifiers assigned to the object.

        @param category: the kind of change triggering this notification
        @type: L{ChangeCategory}
        """

    def notifierID(): #@NoSelf
        """
        Return a notification id. This is a tuple of two C{str}'s. The first item is the overall
        service type "CalDAV" or "CardDAV". The second is the object identifier. For a home that
        is the home's ownerUID, for a home child the ownerUID/name.

        @return: a tuple of two C[str}
        """



class IStoreNotifierFactory(Interface):
    """
    A factory class for a particular type of store notification. App-layer clients of the store may need
    to be notified of changes happening to objects in the store, and act in a particular way when such changes
    occur (e.g., send a push notification, invalidate an app-layer cache etc). To do that they create a class
    for the interface defined here and pass that in when the store itself is created. When the store creates
    a home object, it will pass in the list of factories and the home will instantiate an L{IStoreNotifier} to use
    for sending notifications. Home child resources "inherit" notifiers from their home parent using the
    IStoreNotifier.clone() method - object resources do not have notifiers.
    """

    store = Attribute("The store associated with the notifier factory")

    def newNotifier(storeObject): #@NoSelf
        """
        Generate a notifier for the corresponding store object.

        @param storeObject: the store object.
        @type storeObject: L{CommonHome} or L{CommonHomeChild}
        """



class IStoreNotifier(Interface):
    """
    A notifier provided by the app-layer through an L{IStoreNotifierFactory} that the store uses to indicate
    a change to a store home or home child object.
    """

    _storeObject = Attribute("The store object associated with the notifier: L{CommonHome} or L{CommonHomeChild}")

    def notify(): #@NoSelf
        """
        Called by the store when the object associated with the notifier is changed.
        """

    def clone(storeObject): #@NoSelf
        """
        Called by the store when a home child is created and used to give the home child a notifier
        "inherited" from the home.

        @param label: a new label to use for the home child.
        @type label: C{str}
        @param storeObject: the store object associated with the notifier.
        @type storeObject: L{CommonHome} or L{CommonHomeChild}
        """
