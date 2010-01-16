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
Address book store interfaces
"""

__all__ = [
]

from zope.interface import Interface #, Attribute

from twext.ical import Component
from txdav.idav import IPropertyStore

#
# Exceptions
#

class AddressBookStoreError(RuntimeError):
    """
    Address book store generic error.
    """

class AlreadyExistsError(AddressBookStoreError):
    """
    Attempt to create an object that already exists.
    """

class AddressBookAlreadyExistsError(AlreadyExistsError):
    """
    Address book already exists.
    """

class ContactCardNameAlreadyExistsError(AlreadyExistsError):
    """
    A contact card with the requested name already exists.
    """

class ContactCardUIDAlreadyExistsError(AlreadyExistsError):
    """
    A contact card with the requested UID already exists.
    """

class NotFoundError(AddressBookStoreError):
    """
    Requested data not found.
    """

class NoSuchAddressBookError(NotFoundError):
    """
    The requested address book does not exist.
    """

class NoSuchContactCardError(NotFoundError):
    """
    The requested contact card does not exist.
    """

class InvalidCardComponentError(AddressBookStoreError):
    """
    Invalid card component.
    """

#
# Interfaces
#

class IAddressBookHome(Interface):
    """
    Address book home
    """
    def addressBooks(self):
        """
        Retrieve address books contained in this address book home.

        @return: an iterable of L{IAddressBook}s.
        """

    def addressBookWithName(self, name):
        """
        Retrieve the address book with the given C{name} contained in
        this address book home.

        @param name: a string.
        @return: an L{IAddressBook} or C{None} if no such address book
            exists.
        """

    def createAddressBookWithName(self, name):
        """
        Create an address book with the given C{name} in this address
        book home.

        @param name: a string.
        @raise AddressBookAlreadyExistsError: if an address book
            with the given C{name} already exists.
        """

    def properties(self):
        """
        Retrieve the property store for this address book home.

        @return: an L{IPropertyStore}.
        """

class IAddressBook(Interface):
    """
    Address book
    """
    def contactCards(self):
        """
        Retrieve the contact cards contains in this address book.

        @return: an iterable of L{IContactCard}s.
        """

    def contactCardWithName(self, name):
        """
        Retrieve the contact card with the given C{name} in this
        address book.

        @param name: a string.
        @return: an L{IContactCard} or C{None} is no such contact card
            exists.
        """

    def contactCardWithUID(self, uid):
        """
        Retrieve the contact card with the given C{uid} in this
        address book.

        @param uid: a string.
        @return: an L{IContactCard} or C{None} is no such contact card
            exists.
        """

    def createContactCardWithName(self, name):
        """
        Create a contact card with the given C{name} in this address
        book from the given C{component}.

        @param name: a string.
        @param component: a C{VCARD} L{Component}.
        @raise ContactCardNameAlreadyExistsError: if a contact card
            with the given C{name} already exists.
        @raise ContactCardUIDAlreadyExistsError: if a contact card
            with the same UID as the given C{component} already
            exists.
        @raise InvalidCardComponentError: if the given C{component} is
            not a valid C{VCARD} L{Component} for a contact card.
        """

    def syncToken(self):
        """
        Retrieve the current sync token for this address book.

        @return: a sync token.
        """

    def contactCardsSinceToken(self, token):
        """
        Retrieve all contact cards in this address book that have
        changed since the given C{token} was last valid.

        @return: a 3-tuple containing an iterable of L{IContactCard}s
            that have changed, an iterable of uids that have been
            removed, and the current sync token.
        """

    def properties(self):
        """
        Retrieve the property store for this address book.

        @return: an L{IPropertyStore}.
        """

class IContactCard(Interface):
    """
    Contact card
    """
    def setComponent(self):
        """
        Rewrite this contact card to match the given C{component}.
        C{component} must have the same UID as this contact card.

        @param component: a C{VCARD} L{Component}.
        @raise InvalidCardComponentError: if the given C{component} is
            not a valid C{VCARD} L{Component} for a contact card.
        """

    def component(self):
        """
        Retrieve the contact component for this contact card.

        @return: a C{VCARD} L{Component}.
        """

    def vCardText(self):
        """
        Retrieve the vCard text data for this contact card.

        @return: a string containing vCard data for a single vCard
            contact.
        """

    def uid(self):
        """
        Retrieve the UID for this contact card.

        @return: a string containing a UID.
        """

    def properties(self):
        """
        Retrieve the property store for this contact card.

        @return: an L{IPropertyStore}.
        """
