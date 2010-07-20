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
WebDAV interfaces
"""

__all__ = [
    "PropertyStoreError",
    "PropertyChangeNotAllowedError",
    "AlreadyFinishedError",
    "IPropertyName",
    "IPropertyStore",
    "IDataStore",
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



class AlreadyFinishedError(Exception):
    """
    The transaction was already completed via an C{abort} or C{commit} and
    cannot be aborted or committed again.
    """


#
# Interfaces
#

class IPropertyName(Interface):
    """
    Property name.
    """
    namespace = Attribute("Namespace")
    name      = Attribute("Name")

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
        Write out any pending changes.
        """

    def abort():
        """
        Abort any pending changes.
        """



class IDataStore(Interface):
    """
    An L{IDataStore} is a storage of some objects.
    """

    def newTransaction():
        """
        Create a new transaction.

        @return: a new transaction which provides L{ITransaction}, as well as
            sub-interfaces to request appropriate data objects.

        @rtype: L{ITransaction}
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
