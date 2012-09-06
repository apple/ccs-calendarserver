##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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

from twistedcaldav.carddavxml import AllProperties
from twistedcaldav.datafilters.filter import AddressFilter
from twistedcaldav.vcard import Component

__all__ = [
    "AddressDataFilter",
]

class AddressDataFilter(AddressFilter):
    """
    Filter using the CARDDAV:address-data element specification
    """

    def __init__(self, addressdata):
        """
        
        @param addressdata: the XML element describing how to filter
        @type addressdata: L{AddressData}
        """
        
        self.addressdata = addressdata
    
    def filter(self, vcard):
        """
        Filter the supplied vCard object using the request information.

        @param vcard: vCard object
        @type vcard: L{Component} or C{str}
        
        @return: L{Component} for the filtered vcard data
        """
        
        # Empty element: get all data
        if not self.addressdata.children:
            return vcard

        # Make sure input is valid
        vcard = self.validAddress(vcard)

        # Filter data based on any provided CARDAV:prop element, or use all current data
        if self.addressdata.properties:
            vcard = self.propFilter(self.addressdata.properties, vcard)
        
        return vcard

    def propFilter(self, properties, vcard):
        """
        Returns a vCard component object filtered according to the properties.
        """

        result = Component("VCARD")

        xml_properties = properties

        # Empty element means do all properties and components
        if xml_properties is None:
            xml_properties = AllProperties()

        if xml_properties is not None:
            if xml_properties == AllProperties():
                for vcard_property in vcard.properties():
                    result.addProperty(vcard_property)
            else:
                for xml_property in xml_properties:
                    name = xml_property.property_name
                    for vcard_property in vcard.properties(name):
                        result.addProperty(vcard_property)
                        
                # add required properties
                for requiredProperty in ('N', 'FN', 'VERSION'):
                    if not result.hasProperty(requiredProperty):
                        result.addProperty(vcard.getProperty(requiredProperty))

        return result

    def merge(self, vcardnew, vcardold):
        """
        Address-data merging does not happen
        """
        raise NotImplementedError
