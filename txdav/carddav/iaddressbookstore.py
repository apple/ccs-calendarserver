# -*- test-case-name: txdav.carddav.datastore,txdav.carddav.datastore.test.test_sql.AddressBookSQLStorageTests -*-
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
Address book store interfaces
"""

from txdav.common.icommondatastore import ICommonTransaction, \
    IShareableCollection, CommonStoreError
from txdav.idav import INotifier
from txdav.idav import IDataStoreObject

__all__ = [
    # Classes
    "GroupForSharedAddressBookDeleteNotAllowedError"
    "GroupWithUnsharedAddressNotAllowedError",
    "SharedGroupDeleteNotAllowedError",
    "IAddressBookTransaction",
    "IAddressBookHome",
    "IAddressBook",
    "IAddressBookObject",
]


class GroupForSharedAddressBookDeleteNotAllowedError(CommonStoreError):
    """
    Sharee cannot delete the group for a shared address book
    """


class GroupWithUnsharedAddressNotAllowedError(CommonStoreError):
    """
    Sharee cannot add or modify group vcard such that result contains addresses of unshared vcards.
    """


class SharedGroupDeleteNotAllowedError(CommonStoreError):
    """
    Sharee cannot delete a shared group
    """


class IAddressBookTransaction(ICommonTransaction):
    """
    Transaction interface that addressbook stores must provide.
    """

    def addressbookHomeWithUID(uid, create=False):
        """
        Retrieve the addressbook home for the principal with the given C{uid}.

        If C{create} is C{True}, create the addressbook home if it doesn't
        already exist.

        @return: a L{Deferred} which fires with an L{IAddressBookHome} or
            C{None} if no such addressbook home exists.
        """


#
# Interfaces
#


class IAddressBookHome(INotifier, IDataStoreObject):
    """
    AddressBook home

    An addressbook home belongs to a specific principal and contains the
    addressbooks which that principal has direct access to.  This
    includes both addressbooks owned by the principal as well as
    addressbooks that have been shared with and accepts by the principal.
    """

    def uid():
        """
        Retrieve the unique identifier for this addressbook home.

        @return: a string.
        """


    def addressbooks():
        """
        Retrieve addressbooks contained in this addressbook home.

        @return: an iterable of L{IAddressBook}s.
        """


    def loadAddressbooks():
        """
        Pre-load all addressbooks Depth:1.

        @return: an iterable of L{IAddressBook}s.
        """


    def addressbookWithName(name):
        """
        Retrieve the addressbook with the given C{name} contained in this
        addressbook home.

        @param name: a string.
        @return: an L{IAddressBook} or C{None} if no such addressbook
            exists.
        """


    def createAddressBookWithName(name):
        """
        Create an addressbook with the given C{name} in this addressbook
        home.

        @param name: a string.
        @raise AddressBookAlreadyExistsError: if an addressbook with the
            given C{name} already exists.
        """


    def removeAddressBookWithName(name):
        """
        Remove the addressbook with the given C{name} from this addressbook
        home.  If this addressbook home owns the addressbook, also remove
        the addressbook from all addressbook homes.

        @param name: a string.
        @raise NoSuchAddressBookObjectError: if no such addressbook exists.
        """



class IAddressBook(INotifier, IShareableCollection, IDataStoreObject):
    """
    AddressBook

    An addressbook is a container for addressbook objects (contacts),
    An addressbook belongs to a specific principal but may be
    shared with other principals, granting them read-only or
    read/write access.
    """

    def rename(name):
        """
        Change the name of this addressbook.
        """


    def ownerAddressBookHome():
        """
        Retrieve the addressbook home for the owner of this addressbook.
        AddressBooks may be shared from one (the owner's) addressbook home
        to other (the sharee's) addressbook homes.

        @return: an L{IAddressBookHome}.
        """


    def addressbookObjects():
        """
        Retrieve the addressbook objects contained in this addressbook.

        @return: an iterable of L{IAddressBookObject}s.
        """


    def addressbookObjectWithName(name):
        """
        Retrieve the addressbook object with the given C{name} contained
        in this addressbook.

        @param name: a string.

        @return: a L{Deferred} that fires with an L{IAddressBookObject} or
            C{None} if no such addressbook object exists.
        """

    def addressbookObjectWithUID(uid):
        """
        Retrieve the addressbook object with the given C{uid} contained
        in this addressbook.

        @param uid: a string.
        @return: an L{IAddressBookObject} or C{None} if no such addressbook
            object exists.
        """


    def createAddressBookObjectWithName(name, component):
        """
        Create an addressbook component with the given C{name} in this
        addressbook from the given C{component}.

        @param name: a string.
        @param component: a C{VCARD} L{Component}
        @raise AddressBookObjectNameAlreadyExistsError: if an addressbook
            object with the given C{name} already exists.
        @raise AddressBookObjectUIDAlreadyExistsError: if an addressbook
            object with the same UID as the given C{component} already
            exists.
        @raise InvalidAddressBookComponentError: if the given
            C{component} is not a valid C{VCARD} L{VComponent} for
            an addressbook object.
        """


    def removeAddressBookObjectWithName(name):
        """
        Remove the addressbook object with the given C{name} from this
        addressbook.

        @param name: a string.
        @raise NoSuchAddressBookObjectError: if no such addressbook object
            exists.
        """


    def removeAddressBookObjectWithUID(uid):
        """
        Remove the addressbook object with the given C{uid} from this
        addressbook.

        @param uid: a string.
        @raise NoSuchAddressBookObjectError: if the addressbook object does
            not exist.
        """


    def syncToken():
        """
        Retrieve the current sync token for this addressbook.

        @return: a string containing a sync token.
        """


    def addressbookObjectsSinceToken(token):
        """
        Retrieve all addressbook objects in this addressbook that have
        changed since the given C{token} was last valid.

        @param token: a sync token.
        @return: a 3-tuple containing an iterable of
            L{IAddressBookObject}s that have changed, an iterable of uids
            that have been removed, and the current sync token.
        """



class IAddressBookObject(IDataStoreObject):
    """
    AddressBook object

    An addressbook object describes a contact (vCard).
    """

    def addressbook():
        """
        @return: The address book which this address book object is a part of.
        @rtype: L{IAddressBook}
        """


    def setComponent(component):
        """
        Rewrite this addressbook object to match the given C{component}.
        C{component} must have the same UID as this addressbook object.

        @param component: a C{VCARD} L{VComponent}.
        @raise InvalidAddressBookComponentError: if the given
            C{component} is not a valid C{VCARD} L{VComponent} for
            an addressbook object.
        """


    def component():
        """
        Retrieve the addressbook component for this addressbook object.

        @raise ConcurrentModification: if this L{IAddressBookObject} has been
            deleted and committed by another transaction between its creation
            and the first call to this method.

        @return: a C{VCARD} L{VComponent}.
        """


    def uid():
        """
        Retrieve the UID for this addressbook object.

        @return: a string containing a UID.
        """
