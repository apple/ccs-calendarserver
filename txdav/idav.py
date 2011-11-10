##
# Copyright (c) 2010-2011 Apple Inc. All rights reserved.
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
]

from zope.interface import Attribute, Interface
from zope.interface.common.mapping import IMapping

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

    def toString():
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

    def flush():
        """
        Flush the property store.
        @return: C{None}
        """

    def abort():
        """
        Abort changes to the property store.
        @return: C{None}
        """


class IDataStore(Interface):
    """
    An L{IDataStore} is a storage of some objects.
    """

    def newTransaction(label=None):
        """
        Create a new transaction.

        @param label: A label to assign to this transaction for diagnostic
            purposes.
        @type label: C{str}

        @return: a new transaction which provides L{ITransaction}, as well as
            sub-interfaces to request appropriate data objects.

        @rtype: L{ITransaction}
        """


class IDataStoreObject(Interface):
    """
    An L{IDataStoreObject} are the objects stored in an L{IDataStore}.
    """

    def name():
        """
        Identify the name of the object

        @return: the name of this object.
        @rtype: C{str}
        """

    def contentType():
        """
        The content type of the object's content.

        @rtype: L{MimeType}
        """

    def md5():
        """
        The MD5 hex digest of this object's content.

        @rtype: C{str}
        """

    def size():
        """
        The octet-size of this object's content.

        @rtype: C{int}
        """

    def created():
        """
        The creation date-time stamp of this object.

        @rtype: C{int}
        """

    def modified():
        """
        The last modification date-time stamp of this object.

        @rtype: C{int}
        """

    def properties():
        """
        Retrieve the property store for this object.

        @return: an L{IPropertyStore}.
        """



class ITransaction(Interface):
    """
    Transaction that can be aborted and either succeeds or fails in
    its entirety.
    """

    def abort():
        """
        Abort this transaction.

        @raise AlreadyFinishedError: The transaction was already finished with
            an 'abort' or 'commit' and cannot be aborted again.
        """


    def commit():
        """
        Perform this transaction.

        @raise AlreadyFinishedError: The transaction was already finished with
            an 'abort' or 'commit' and cannot be committed again.
        """


    def postCommit(operation):
        """
        Registers an operation to be executed after the transaction is
        committed.

        postCommit can be called multiple times, and operations are executed
        in the order which they were registered.

        @param operation: a callable.
        """


    def postAbort(operation):
        """
        Registers an operation to be executed after the transaction is
        aborted.

        postAbort can be called multiple times, and operations are executed
        in the order which they were registered.

        @param operation: a callable.
        """


    def store():
        """
        The store that this transaction was initiated from.

        @rtype: L{IDataStore}
        """



class INotifier(Interface):
    """
    Push notification interface
    """

    def notifierID(label):
        """
        Return a push notification id.

        Data store objects can have an associated Notifier object which is
        responsible for the actual communication with the outside world.
        Clients determine what notification service to subscribe to by
        querying the server for various DAV properties.  These properties
        include unique IDs from each resource, and the source of truth for
        these IDs is the data store.  This method returns the notification
        related ID for a given data store object.

        Sharing introduces the need for a data store object to have multiple
        notifier IDs because a subscriber sees the ID for the particular
        collection being shared while the sharer sees the ID of the parent
        home.  Therefore there is a label parameter to identify which ID is
        being requested: "default" (what a sharer sees), or "collection"
        for the collection itself (what a subscriber sees).

        @return: a string (or None if notifications are disabled)
        """

    def nodeName(label):
        """
        Returns a pubsub node path.

        A pubsub node path is comprised of the following values:

        /<protocol>/<hostname>/<notifierID>/

        <protocol> is either CalDAV or CardDAV
        <hostname> is the name of the calendar server
        <notifierID> is a unique string representing the resource

        This method builds this string based on pubsub configuration
        that was passed to the NotifierFactory, and it also attempts
        to create and configure the node in the pubsub server.  If that
        fails, a value of None will be returned. This is used when a client
        requests push-related DAV properties.

        @return: a deferred to a string (or None if notifications are disabled
        or the node could not be created)
        """
