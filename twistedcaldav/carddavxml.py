##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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
CardDAV XML Support.

This module provides XML utilities for use with CardDAV.

This API is considered private to static.py and is therefore subject to
change.

See draft spec: 
"""

from txdav.xml.element import registerElement, dav_namespace
from txdav.xml.element import WebDAVElement, PCDATAElement
from txdav.xml.element import WebDAVEmptyElement, WebDAVTextElement
from txdav.xml.element import ResourceType, Collection

from twistedcaldav.vcard import Component

##
# CardDAV objects
##

carddav_namespace = "urn:ietf:params:xml:ns:carddav"

carddav_compliance = (
    "addressbook",
)


class CardDAVElement (WebDAVElement):
    """
    CardDAV XML element.
    """
    namespace = carddav_namespace


class CardDAVEmptyElement (WebDAVEmptyElement):
    """
    CardDAV element with no contents.
    """
    namespace = carddav_namespace


class CardDAVTextElement (WebDAVTextElement):
    """
    CardDAV element containing PCDATA.
    """
    namespace = carddav_namespace


@registerElement
class AddressBookHomeSet (CardDAVElement):
    """
    The address book collections URLs for this principal.
    (CardDAV, RFC 6352 section 7.1.1)
    """
    name = "addressbook-home-set"
    hidden = True

    allowed_children = { (dav_namespace, "href"): (0, None) }


@registerElement
class AddressBookDescription (CardDAVTextElement):
    """
    Provides a human-readable description of what this address book collection
    represents.
    (CardDAV, RFC 6352 section 6.2.1)
    """
    name = "addressbook-description"
    hidden = True
    # May be protected; but we'll let the client set this if they like.


@registerElement
class SupportedAddressData (CardDAVElement):
    """
    Specifies restrictions on an address book collection.
    (CardDAV, RFC 6352 section 6.2.2)
    """
    name = "supported-address-data"
    hidden = True
    protected = True

    allowed_children = { (carddav_namespace, "address-data-type"): (0, None) }


@registerElement
class MaxResourceSize (CardDAVTextElement):
    """
    Specifies restrictions on an address book collection.
    (CardDAV, RFC 6352 section 6.2.3)
    """
    name = "max-resource-size"
    hidden = True
    protected = True


@registerElement
class AddressBook (CardDAVEmptyElement):
    """
    Denotes an address book collection.
    (CardDAV, RFC 6352 sections 5.2, 10.1)
    """
    name = "addressbook"


@registerElement
class AddressBookQuery (CardDAVElement):
    """
    Defines a report for querying address book data.
    (CardDAV, RFC 6352 section 10.3)
    """
    name = "addressbook-query"

    allowed_children = {
        (dav_namespace,     "allprop" ): (0, None),
        (dav_namespace,     "propname"): (0, None),
        (dav_namespace,     "prop"    ): (0, None),
        (carddav_namespace, "filter"  ): (0, 1), # Actually (1, 1) unless element is empty
        (carddav_namespace, "limit"    ): (0, None),
    }

    def __init__(self, *children, **attributes):
        super(AddressBookQuery, self).__init__(*children, **attributes)

        props = None
        filter = None
        limit = None

        for child in self.children:
            qname = child.qname()

            if qname in (
                (dav_namespace, "allprop" ),
                (dav_namespace, "propname"),
                (dav_namespace, "prop"    ),
            ):
                if props is not None:
                    raise ValueError("Only one of CardDAV:allprop, CardDAV:propname, CardDAV:prop allowed")
                props = child

            elif qname == (carddav_namespace, "filter"):
                filter = child
            elif qname == (carddav_namespace, "limit"):
                # type check 
                child.childOfType(NResults)
                limit = child

            else:
                raise AssertionError("We shouldn't be here")

        if len(self.children) > 0:
            if filter is None:
                raise ValueError("CARDDAV:filter required")

        self.props  = props
        self.filter = filter
        self.limit = limit


@registerElement
class AddressDataType (CardDAVEmptyElement):
    """
    Defines which parts of a address component object should be returned by a
    report.
    (CardDAV, RFC 6352 section 6.2.2)
    """
    name = "address-data-type"

    allowed_attributes = {
        "content-type": False,
        "version"     : False,
    }


@registerElement
class AddressData (CardDAVElement):
    """
    Defines which parts of a address component object should be returned by a
    report.
    (CardDAV, RFC 6352 section 10.4)
    """
    name = "address-data"

    allowed_children = {
        (carddav_namespace, "allprop"): (0, 1),
        (carddav_namespace, "prop"   ): (0, None),
        PCDATAElement                 : (0, None),
    }
    allowed_attributes = {
        "content-type": False,
        "version"     : False,
    }

    @classmethod
    def fromAddress(clazz, address):
        assert address.name() == "VCARD", "Not a vCard: %r" % (address,)
        return clazz(PCDATAElement(str(address)))

    @classmethod
    def fromAddressData(clazz, addressdata):
        """
        Return a AddressData element comprised of the supplied address data.
        @param addressdata: a string of valid address data.
        @return: a L{Addressata} element.
        """
        return clazz(PCDATAElement(addressdata))

    fromTextData = fromAddressData

    def __init__(self, *children, **attributes):
        super(AddressData, self).__init__(*children, **attributes)

        properties = None
        data       = None

        for child in self.children:
            qname = child.qname()

            if qname == (carddav_namespace, "allprop"):
                if properties is not None:
                    raise ValueError(
                        "CardDAV:allprop and CardDAV:prop may not be combined"
                    )
                properties = child

            elif qname == (carddav_namespace, "prop"):
                try:
                    properties.append(child)
                except AttributeError:
                    if properties is None:
                        properties = [child]
                    else:
                        raise ValueError("CardDAV:allprop and CardDAV:prop may not be combined")

            elif isinstance(child, PCDATAElement):
                if data is None:
                    data = child
                else:
                    data += child

            else: raise AssertionError("We shouldn't be here")


        self.properties = properties

        if data is not None:
            try:
                if properties is not None:
                    raise ValueError("Only one of allprop, prop (%r) or PCDATA (%r) allowed"% (properties, str(data)))
            except ValueError:
                if not data.isWhitespace(): raise
            else:
                # Since we've already combined PCDATA elements, we'd may as well
                # optimize them originals away
                self.children = (data,)

        if "content-type" in attributes:
            self.content_type = attributes["content-type"]
        else:
            self.content_type = "text/vcard"

        if "version" in attributes:
            self.version = attributes["version"]
        else:
            self.version = "3.0"

    def verifyTypeVersion(self, types_and_versions):
        """
        Make sure any content-type and version matches at least one of the supplied set.
        
        @param types_and_versions: a list of (content-type, version) tuples to test against.
        @return:                   True if there is at least one match, False otherwise.
        """
        for item in types_and_versions:
            if (item[0] == self.content_type) and (item[1] == self.version):
                return True
        
        return False

    def address(self):
        """
        Returns an address component derived from this element.
        """
        data = self.addressData()
        if data:
            return Component.fromString(data)
        else:
            return None

    generateComponent = address

    def addressData(self):
        """
        Returns an address component derived from this element.
        """
        for data in self.children:
            if not isinstance(data, PCDATAElement):
                return None
            else:
                # We guaranteed in __init__() that there is only one child...
                break

        return str(data)

    textData = addressData


@registerElement
class AllProperties (CardDAVEmptyElement):
    """
    Specifies that all properties shall be returned.
    (CardDAV, RFC 6352 section 10.4.1)
    """
    name = "allprop"


@registerElement
class Property (CardDAVEmptyElement):
    """
    Defines a property to return in a response.
    (CardDAV, RFC 6352 section 10.4.2)
    """
    name = "prop"

    allowed_attributes = {
        "name"   : True,
        "novalue": False,
    }

    def __init__(self, *children, **attributes):
        super(Property, self).__init__(*children, **attributes)

        self.property_name = attributes["name"]

        if "novalue" in attributes:
            novalue = attributes["novalue"]
            if novalue == "yes":
                self.novalue = True
            elif novalue == "no":
                self.novalue = False
            else:
                raise ValueError("Invalid novalue: %r" % (novalue,))
        else:
            self.novalue = False


@registerElement
class Filter (CardDAVElement):
    """
    Determines which matching components are returned.
    (CardDAV, RFC 6352 section 10.5)
    """
    name = "filter"

    allowed_children = { (carddav_namespace, "prop-filter"): (0, None) }
    allowed_attributes = { "test": False }
        

@registerElement
class PropertyFilter (CardDAVElement):
    """
    Limits a search to specific properties.
    (CardDAV-access-09, RFC 6352 section 10.5.1)
    """
    name = "prop-filter"

    allowed_children = {
        (carddav_namespace, "is-not-defined" ): (0, 1),
        (carddav_namespace, "text-match"     ): (0, None),
        (carddav_namespace, "param-filter"   ): (0, None),
    }
    allowed_attributes = {
        "name": True,
        "test": False,
    }


@registerElement
class ParameterFilter (CardDAVElement):
    """
    Limits a search to specific parameters.
    (CardDAV, RFC 6352 section 10.5.2)
    """
    name = "param-filter"

    allowed_children = {
        (carddav_namespace, "is-not-defined" ): (0, 1),
        (carddav_namespace, "text-match"     ): (0, 1),
    }
    allowed_attributes = { "name": True }


@registerElement
class Limit (WebDAVElement):
    """
    Client supplied limit for reports.
    """
    namespace = carddav_namespace
    name = "limit"
    allowed_children = {
        (carddav_namespace, "nresults" )  : (1, 1),
    }


@registerElement
class NResults (WebDAVTextElement):
    """
    Number of results limit.
    """
    namespace = carddav_namespace
    name = "nresults"



@registerElement
class IsNotDefined (CardDAVEmptyElement):
    """
    Specifies that the named vCard item does not exist.
    (CardDAV, RFC 6352 section 10.5.3)
    """
    name = "is-not-defined"


@registerElement
class TextMatch (CardDAVTextElement):
    """
    Specifies a substring match on a property or parameter value.
    (CardDAV, RFC 6352 section 10.5.4)
    """
    name = "text-match"

    def fromString(clazz, string): #@NoSelf
        if type(string) is str:
            return clazz(PCDATAElement(string))
        elif type(string) is unicode:
            return clazz(PCDATAElement(string.encode("utf-8")))
        else:
            return clazz(PCDATAElement(str(string)))

    fromString = classmethod(fromString)

    allowed_attributes = {
        "collation": False,
        "negate-condition": False,
        "match-type": False
    }


@registerElement
class AddressBookMultiGet (CardDAVElement):
    """
    CardDAV report used to retrieve specific vCard items via their URIs.
    (CardDAV, RFC 6352 section 10.7)
    """
    name = "addressbook-multiget"

    # To allow for an empty element in a supported-report-set property we need
    # to relax the child restrictions
    allowed_children = {
        (dav_namespace, "allprop" ): (0, 1),
        (dav_namespace, "propname"): (0, 1),
        (dav_namespace, "prop"    ): (0, 1),
        (dav_namespace, "href"    ): (0, None),    # Actually ought to be (1, None)
    }

    def __init__(self, *children, **attributes):
        super(AddressBookMultiGet, self).__init__(*children, **attributes)

        property = None
        resources = []

        for child in self.children:
            qname = child.qname()

            if qname in (
                (dav_namespace, "allprop" ),
                (dav_namespace, "propname"),
                (dav_namespace, "prop"    ),
            ):
                if property is not None:
                    raise ValueError("Only one of DAV:allprop, DAV:propname, DAV:prop allowed")
                property = child

            elif qname == (dav_namespace, "href"):
                resources.append(child)

        self.property  = property
        self.resources = resources


@registerElement
class NoUIDConflict(CardDAVElement):
    """
    CardDAV precondition used to indicate a UID conflict during PUT/COPY/MOVE.
    The conflicting resource href must be returned as a child.
    """
    name = "no-uid-conflict"

    allowed_children = { (dav_namespace, "href"): (1, 1) }
    

@registerElement
class SupportedFilter(CardDAVElement):
    """
    CardDAV precondition used to indicate an unsupported component type in a
    query filter.
    The conflicting filter elements are returned.
    """
    name = "supported-filter"

    allowed_children = {
        (carddav_namespace, "prop-filter" ): (0, None),
        (carddav_namespace, "param-filter"): (0, None)
    }
    

@registerElement
class DirectoryGateway(CardDAVElement):
    """
    CardDAV property on a principal to indicate where the directory gateway resource is.
    """
    name = "directory-gateway"
    hidden = True
    protected = True

    allowed_children = { (dav_namespace, "href"): (0, None) }
    

@registerElement
class Directory(CardDAVEmptyElement):
    """
    CardDAV property on a principal to indicate where the directory resource is.
    """
    name = "directory"
    

@registerElement
class DefaultAddressBookURL (CardDAVElement):
    """
    A single href indicating which addressbook is the default.
    """
    name = "default-addressbook-URL"

    allowed_children = { (dav_namespace, "href"): (0, 1) }

##
# Extensions to ResourceType
##

def _isAddressBook(self): return bool(self.childrenOfType(AddressBook))
ResourceType.isAddressBook = _isAddressBook

ResourceType.addressbook = ResourceType(Collection(), AddressBook())
ResourceType.directory   = ResourceType(Collection(), AddressBook(), Directory())
