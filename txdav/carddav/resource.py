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
CardDAV resources.
"""

__all__ = [
    "CardDAVResource",
    "AddressBookHomeResource",
    "AddressBookCollectionResource",
    "AddressBookObjectResource",
]

from twext.python.log import LoggingMixIn
from txdav.xml.base import dav_namespace

from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.config import config
from twistedcaldav.extensions import DAVResource

class CardDAVResource(DAVResource, LoggingMixIn):
    """
    CardDAV resource.
    """
    def davComplianceClasses(self):
        return (
            tuple(super(CardDAVResource, self).davComplianceClasses())
            + config.CardDAVComplianceClasses
        )


class AddressBookHomeResource(CardDAVResource):
    """
    AddressBook home resource.

    This resource is backed by an L{IAddressBookHome} implementation.
    """


class AddressBookCollectionResource(CardDAVResource):
    """
    AddressBook collection resource.

    This resource is backed by an L{IAddressBook} implementation.
    """
    #
    # HTTP
    #

    #
    # WebDAV
    #

    def liveProperties(self):
        
        return super(AddressBookCollectionResource, self).liveProperties() + (
            (dav_namespace,     "owner"),
            (carddav_namespace, "supported-addressbook-data"),
        )




class AddressBookObjectResource(CardDAVResource):
    """
    AddressBook object resource.

    This resource is backed by an L{IAddressBookObject} implementation.
    """
