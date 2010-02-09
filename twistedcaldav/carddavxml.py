##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

from twistedcaldav.vcard import Property as iProperty
from twistedcaldav.vcard import Component

from twisted.web2.dav import davxml

##
# CardDAV objects
##

carddav_namespace = "urn:ietf:params:xml:ns:carddav"
addressbookserver_namespace = "http://addressbookserver.org/ns/"

carddav_compliance = (
    "addressbook",
)

class CardDAVElement (davxml.WebDAVElement):
    """
    CardDAV XML element.
    """
    namespace = carddav_namespace

class CardDAVEmptyElement (davxml.WebDAVEmptyElement):
    """
    CardDAV element with no contents.
    """
    namespace = carddav_namespace

class CardDAVTextElement (davxml.WebDAVTextElement):
    """
    CardDAV element containing PCDATA.
    """
    namespace = carddav_namespace

class CardDAVFilterElement (CardDAVElement):
    """
    CardDAV filter element.
    """
    def __init__(self, *children, **attributes):

        super(CardDAVFilterElement, self).__init__(*children, **attributes)

        qualifier = None
        filters = []

        for child in self.children:
            qname = child.qname()
            
            if qname in (
                (carddav_namespace, "is-not-defined"),
            ):
                if qualifier is not None:
                    raise ValueError("Only one of CardDAV:is-not-defined allowed")
                qualifier = child

            else:
                filters.append(child)

        if qualifier and (len(filters) != 0):
            raise ValueError("No other tests allowed when CardDAV:is-not-defined is present")
        
        if self.qname() == (carddav_namespace, "prop-filter"):
            propfilter_test = attributes.get("test", "anyof")
            if propfilter_test not in ("anyof", "allof"):
                raise ValueError("Test must be only one of anyof, allof")
        else:
            propfilter_test = "anyof"

        self.propfilter_test = propfilter_test
        self.qualifier   = qualifier
        self.filters     = filters
        self.filter_name = attributes["name"]
        if isinstance(self.filter_name, unicode):
            self.filter_name = self.filter_name.encode("utf-8")
        self.defined     = not self.qualifier or (self.qualifier.qname() != (carddav_namespace, "is-not-defined"))

    def match(self, item):
        """
        Returns True if the given address book item (either a property or parameter value)
        matches this filter, False otherwise.
        """
        
        # Always return True for the is-not-defined case as the result of this will
        # be negated by the caller
        if not self.defined: return True

        if self.qualifier and not self.qualifier.match(item): return False

        if len(self.filters) > 0:
            allof = self.propfilter_test == "allof"
            for filter in self.filters:
                if allof != filter._match(item):
                    return not allof
            return allof
        else:
            return True

class AddressBookHomeSet (CardDAVElement):
    """
    The address book collections URLs for this principal.
    (CardDAV, section 7.1.1)
    """
    name = "addressbook-home-set"
    hidden = True

    allowed_children = { (davxml.dav_namespace, "href"): (0, None) }

class AddressBookDescription (CardDAVTextElement):
    """
    Provides a human-readable description of what this address book collection
    represents.
    (CardDAV, section 62.1)
    """
    name = "addressbook-description"
    hidden = True
    # May be protected; but we'll let the client set this if they like.

class SupportedAddressData (CardDAVElement):
    """
    Specifies restrictions on an address book collection.
    (CardDAV, section 6.2.2)
    """
    name = "supported-address-data"
    hidden = True
    protected = True

    allowed_children = { (carddav_namespace, "addressbook-data"): (0, None) }

class MaxResourceSize (CardDAVTextElement):
    """
    Specifies restrictions on an address book collection.
    (CardDAV, section 6.2.3)
    """
    name = "max-resource-size"
    hidden = True
    protected = True

class AddressBook (CardDAVEmptyElement):
    """
    Denotes an address book collection.
    (CardDAV, sections 5.2)
    """
    name = "addressbook"

class SearchAddressBook (CardDAVEmptyElement):
    """
    Denotes a search address book collection, that will respond 
    to query reports by querying the user-readable address books 
    on this server not cached by AddressBook.app.
    For version 1.0, this object simply redirects queries to the open directory address book
    """
    name = "searchaddressbook"

class SearchAllAddressBook (CardDAVEmptyElement):
    """
    Denotes a search address book collection, that will respond 
    to query reports by querying the user-readable address books 
    on this server.
    For version 1.0, this will include the user's private address book,
    the open directory address book, and user-readable group (shared) address books.
    """
    name = "searchalladdressbook"

class AddressBookQuery (CardDAVElement):
    """
    Defines a report for querying address book data.
    (CardDAV, section 8.6)
    """
    name = "addressbook-query"

    allowed_children = {
        (davxml.dav_namespace, "allprop" ): (0, None),
        (davxml.dav_namespace, "propname"): (0, None),
        (davxml.dav_namespace, "prop"    ): (0, None),
        (carddav_namespace,    "filter"  ): (0, 1), # Actually (1, 1) unless element is empty
        (carddav_namespace,    "limit"    ): (0, None),
    }

    def __init__(self, *children, **attributes):
        super(AddressBookQuery, self).__init__(*children, **attributes)

        query = None
        filter = None
        limit = None

        for child in self.children:
            qname = child.qname()

            if qname in (
                (davxml.dav_namespace, "allprop" ),
                (davxml.dav_namespace, "propname"),
                (davxml.dav_namespace, "prop"    ),
            ):
                if query is not None:
                    raise ValueError("Only one of CardDAV:allprop, CardDAV:propname, CardDAV:prop allowed")
                query = child

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

        self.query  = query
        self.filter = filter
        self.limit = limit

class AddressData (CardDAVElement):
    """
    Defines which parts of a address component object should be returned by a
    report.
    (CardDAV, section 10.4)
    """
    name = "address-data"

    allowed_children = {
        (carddav_namespace, "allprop"): (0, 1),
        (carddav_namespace, "prop"): (0, None),
        davxml.PCDATAElement:        (0, None),
    }
    allowed_attributes = {
        "content-type": False,
        "version"     : False,
    }

    @classmethod
    def fromAddress(clazz, address):
        assert address.name() == "VCARD", "Not a vCard: %r" % (address,)
        return clazz(davxml.PCDATAElement(str(address)))

    @classmethod
    def fromAddressData(clazz, addressdata):
        """
        Return a AddressData element comprised of the supplied address data.
        @param addressdata: a string of valid address data.
        @return: a L{Addressata} element.
        """
        return clazz(davxml.PCDATAElement(addressdata))

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

            elif isinstance(child, davxml.PCDATAElement):
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

    def elementFromResource(self, resource):
        """
        Return a new AddressData element comprised of the possibly filtered
        address data from the specified resource. If no filter is being applied
        read the data directly from the resource without parsing it. If a filter
        is required, parse the vCard data and filter using this AddressData.
        @param resource: the resource whose address data is to be returned.
        @return: an L{AddressData} with the (filtered) address data.
        """
        # Check for filtering or not
        if self.children:
            filtered = self.getFromvCard(resource.vCard())
            return AddressData.fromAddress(filtered)
        else:
            return resource.vCardXML()

    def elementFromAddress(self, address):
        """
        Return a new AddressData element comprised of the possibly filtered
        address.
        @param address: the address that is to be filtered and returned.
        @return: an L{AddressData} with the (filtered) address data.
        """
        
        # Check for filtering or not
        filtered = self.getFromvCard(address)
        return AddressData.fromAddress(filtered)

    def getFromvCard(self, address):
        """
        Returns an address object containing the data in the given vCard
        which is specified by this AddressData.
        """
        if address.name() != "VCARD":
            raise ValueError("Not a vCard: %r" % (address,))

        # Empty element: get all data
        if not self.children: return address

        # property filtering
        # copy requested properties
        vcard = Component("VCARD")
        allProps = True
        for property in self.children:
            if isinstance(property, Property):
                allProps = False
                for addressProperty in address.properties(property.attributes["name"]):
                    vcard.addProperty(addressProperty)
        
        # add required properties
        if allProps:
            vcard = address
        else:
            for requiredProperty in ('N', 'FN', 'VERSION'):
                if not vcard.hasProperty(requiredProperty):
                    vcard.addProperty(address.getProperty(requiredProperty))

        return vcard

    def address(self):
        """
        Returns an address component derived from this element.
        """
        for data in self.children:
            if not isinstance(data, davxml.PCDATAElement):
                return None
            else:
                # We guaranteed in __init__() that there is only one child...
                break

        return None # TODO: iComponent.fromString(str(data))


class AllProperties (CardDAVEmptyElement):
    """
    Specifies that all properties shall be returned.
    (CardDAV, section 10.4.1)
    """
    name = "allprop"

class Property (CardDAVEmptyElement):
    """
    Defines a property to return in a response.
    (CardDAV, section 10.4.2)
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

class Filter (CardDAVElement):
    """
    Determines which matching components are returned.
    (CardDAV, section 10.5)
    """
    name = "filter"

    allowed_children = { (carddav_namespace, "prop-filter"): (0, None) }
    allowed_attributes = { "test": False }


    def __init__(self, *children, **attributes):

        super(Filter, self).__init__(*children, **attributes)

        filter_test = attributes.get("test", "anyof")
        if filter_test not in ("anyof", "allof"):
            raise ValueError("Test must be only one of anyof, allof")
        
        self.filter_test = filter_test

    def match(self, vcard):
        """
        Returns True if the given address property matches this filter, False
        otherwise. Empty element means always match.
        """
 
        if len(self.children) > 0:
            allof = self.filter_test == "allof"
            for propfilter in self.children:
                if allof != propfilter._match(vcard):
                    return not allof
            return allof
        else:
            return True

    def valid(self):
        """
        Indicate whether this filter element's structure is valid wrt vCard
        data object model.
        
        @return: True if valid, False otherwise
        """
        
        # Test each property
        for propfilter in self.children:
            if not propfilter.valid():
                return False
        else:
            return True
        
class PropertyFilter (CardDAVFilterElement):
    """
    Limits a search to specific properties.
    (CardDAV-access-09, section 10.5.1)
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

    def _match(self, vcard):
        # At least one property must match (or is-not-defined is set)
        for property in vcard.properties():
            if property.name() == self.filter_name and self.match(property): break
        else:
            return not self.defined
        return self.defined

    def valid(self):
        """
        Indicate whether this filter element's structure is valid wrt vCard
        data object model.
        
        @return:      True if valid, False otherwise
        """
        
        # No tests
        return True

class ParameterFilter (CardDAVFilterElement):
    """
    Limits a search to specific parameters.
    (CardDAV, section 10.5.2)
    """
    name = "param-filter"

    allowed_children = {
        (carddav_namespace, "is-not-defined" ): (0, 1),
        (carddav_namespace, "text-match"     ): (0, 1),
    }
    allowed_attributes = { "name": True }

    def _match(self, property):

        # At least one parameter must match (or is-not-defined is set)
        result = not self.defined
        for parameterName in property.params().keys():
            if parameterName == self.filter_name and self.match(property.params()[parameterName]):
                result = self.defined
                break

        return result

class Limit (davxml.WebDAVElement):
    """
    Client supplied limit for reports.
    """
    namespace = carddav_namespace
    name = "limit"
    allowed_children = {
        (carddav_namespace, "nresults" )  : (1, 1),
    }

class NResults (davxml.WebDAVTextElement):
    """
    Number of results limit.
    """
    namespace = carddav_namespace
    name = "nresults"


class IsNotDefined (CardDAVEmptyElement):
    """
    Specifies that the named vCard item does not exist.
    (CardDAV, section 10.5.3)
    """
    name = "is-not-defined"

    def match(self, component):
        # Oddly, this needs always to return True so that it appears there is
        # a match - but we then "negate" the result if is-not-defined is set.
        # Actually this method should never be called as we special case the
        # is-not-defined option.
        return True

class TextMatch (CardDAVTextElement):
    """
    Specifies a substring match on a property or parameter value.
    (CardDAV, section 10.5.4)
    """
    name = "text-match"

    def fromString(clazz, string): #@NoSelf
        if type(string) is str:
            return clazz(davxml.PCDATAElement(string))
        elif type(string) is unicode:
            return clazz(davxml.PCDATAElement(string.encode("utf-8")))
        else:
            return clazz(davxml.PCDATAElement(str(string)))

    fromString = classmethod(fromString)

    allowed_attributes = {
        "collation": False,
        "negate-condition": False,
        "match-type": False
    }

    def __init__(self, *children, **attributes):
        super(TextMatch, self).__init__(*children, **attributes)

        if "collation" in attributes:
            self.collation = attributes["collation"]
        else:
            self.collation = "i;unicode-casemap"

        if "negate-condition" in attributes:
            self.negate = attributes["negate-condition"]
            if self.negate not in ("yes", "no"):
                self.negate = "no"
            self.negate = {"yes": True, "no": False}[self.negate]
        else:
            self.negate = False

        if "match-type" in attributes:
            self.match_type = attributes["match-type"]
            if self.match_type not in (
                "equals",
                "contains",
                "starts-with",
                "ends-with",
            ):
                self.match_type = "contains"
        else:
            self.match_type = "contains"

    def _match(self, item):
        """
        Match the text for the item.
        If the item is a property, then match the property value,
        otherwise it may be a list of parameter values - try to match anyone of those
        """
        if item is None: return False

        if isinstance(item, iProperty):
            values = [item.value()]
        else:
            values = item

        test = unicode(str(self), "utf-8").lower()

        def _textCompare(s):
            s = s.lower()
            
            #print("test=%r, s=%r, matchType=%r" % (test, s, self.match_type))
            
            if self.match_type == "equals":
                return s == test
            elif self.match_type == "contains":
                return s.find(test) != -1 
            elif self.match_type == "starts-with":
                return s.startswith(test)
            elif self.match_type == "ends-with":
                return s.endswith(test)
            else:
                return False

        for value in values:
            # NB Its possible that we have a text list value which appears as a Python list,
            # so we need to check for that an iterate over the list.
            if isinstance(value, list):
                for subvalue in value:
                    if _textCompare(unicode(subvalue)):
                        return not self.negate
            else:
                if _textCompare(unicode(value)):
                    return not self.negate
        
        return self.negate

    def match(self, item):
        return self._match(item)

class AddressBookMultiGet (CardDAVElement):
    """
    CardDAV report used to retrieve specific vCard items via their URIs.
    (CardDAV, section 10.6)
    """
    name = "addressbook-multiget"

    # To allow for an empty element in a supported-report-set property we need
    # to relax the child restrictions
    allowed_children = {
        (davxml.dav_namespace, "allprop" ): (0, 1),
        (davxml.dav_namespace, "propname"): (0, 1),
        (davxml.dav_namespace, "prop"    ): (0, 1),
        (davxml.dav_namespace, "href"    ): (0, None),    # Actually ought to be (1, None)
    }

    def __init__(self, *children, **attributes):
        super(AddressBookMultiGet, self).__init__(*children, **attributes)

        property = None
        resources = []

        for child in self.children:
            qname = child.qname()

            if qname in (
                (davxml.dav_namespace, "allprop" ),
                (davxml.dav_namespace, "propname"),
                (davxml.dav_namespace, "prop"    ),
            ):
                if property is not None:
                    raise ValueError("Only one of DAV:allprop, DAV:propname, DAV:prop allowed")
                property = child

            elif qname == (davxml.dav_namespace, "href"):
                resources.append(child)

        self.property  = property
        self.resources = resources

class AddressBookFindShared (davxml.WebDAVElement):
    """
    Report used to retrieve shared address books accessible for a user principal
    """
    name = "addressbook-findshared"
    namespace = addressbookserver_namespace

    allowed_children = {
#         (davxml.dav_namespace, "href"    ): (0, None),    # Actually ought to be (1, None)
    }


class NoUIDConflict(CardDAVElement):
    """
    CardDAV precondition used to indicate a UID conflict during PUT/COPY/MOVE.
    The conflicting resource href must be returned as a child.
    """
    name = "no-uid-conflict"

    allowed_children = { (davxml.dav_namespace, "href"): (1, 1) }
    
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
    
##
# Extensions to davxml.ResourceType
##

def _isAddressBook(self): return bool(self.childrenOfType(AddressBook))
davxml.ResourceType.isAddressBook = _isAddressBook
davxml.ResourceType.addressbook = davxml.ResourceType(davxml.Collection(), AddressBook())
davxml.ResourceType.searchaddressbook = davxml.ResourceType(davxml.Collection(), SearchAddressBook())
davxml.ResourceType.searchalladdressbook = davxml.ResourceType(davxml.Collection(), SearchAllAddressBook())
