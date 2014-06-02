##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
Object model of CARDDAV:filter element used in an addressbook-query.
"""

__all__ = [
    "Filter",
]

from twext.python.log import Logger

from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.vcard import Property

log = Logger()

class FilterBase(object):
    """
    Determines which matching components are returned.
    """

    serialized_name = None
    deserialize_names = {}

    @classmethod
    def serialize_register(cls, register):
        cls.deserialize_names[register.serialized_name] = register


    def __init__(self, xml_element):
        pass


    @classmethod
    def deserialize(cls, data):
        """
        Convert a JSON compatible serialization of this object into the actual object.
        """
        obj = cls.deserialize_names[data["type"]](None)
        obj._deserialize(data)
        return obj


    def _deserialize(self, data):
        """
        Convert a JSON compatible serialization of this object into the actual object.
        """
        pass


    def serialize(self):
        """
        Create a JSON compatible serialization of this object - will be used in a cross-pod request.
        """
        return {
            "type": self.serialized_name,
        }


    def match(self, item, access=None):
        raise NotImplementedError


    def valid(self, level=0):
        raise NotImplementedError



class Filter(FilterBase):
    """
    Determines which matching components are returned.
    """

    serialized_name = "Filter"

    def __init__(self, xml_element):

        super(Filter, self).__init__(xml_element)
        if xml_element is None:
            return

        filter_test = xml_element.attributes.get("test", "anyof")
        if filter_test not in ("anyof", "allof"):
            raise ValueError("Test must be only one of anyof, allof")

        self.filter_test = filter_test

        self.children = [PropertyFilter(child) for child in xml_element.children]


    def _deserialize(self, data):
        """
        Convert a JSON compatible serialization of this object into the actual object.
        """
        self.filter_test = data["filter_test"]
        self.child = [FilterBase.deserialize(child) for child in data["children"]]


    def serialize(self):
        """
        Create a JSON compatible serialization of this object - will be used in a cross-pod request.
        """
        result = super(Filter, self).serialize()
        result.update({
            "filter_test": self.filter_test,
            "children": [child.serialize() for child in self.children],
        })
        return result


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

FilterBase.serialize_register(Filter)



class FilterChildBase(FilterBase):
    """
    CardDAV filter element.
    """

    def __init__(self, xml_element):

        super(FilterChildBase, self).__init__(xml_element)
        if xml_element is None:
            return

        qualifier = None
        filters = []

        for child in xml_element.children:
            qname = child.qname()

            if qname in (
                (carddav_namespace, "is-not-defined"),
            ):
                if qualifier is not None:
                    raise ValueError("Only one of CardDAV:is-not-defined allowed")
                qualifier = IsNotDefined(child)

            elif qname == (carddav_namespace, "text-match"):
                filters.append(TextMatch(child))

            elif qname == (carddav_namespace, "param-filter"):
                filters.append(ParameterFilter(child))
            else:
                raise ValueError("Unknown child element: %s" % (qname,))

        if xml_element.qname() == (carddav_namespace, "prop-filter"):
            propfilter_test = xml_element.attributes.get("test", "anyof")
            if propfilter_test not in ("anyof", "allof"):
                raise ValueError("Test must be only one of anyof, allof")
        else:
            propfilter_test = "anyof"

        if qualifier and isinstance(qualifier, IsNotDefined) and (len(filters) != 0) and propfilter_test == "allof":
            raise ValueError("When test is allof, no other tests allowed when CardDAV:is-not-defined is present")

        self.propfilter_test = propfilter_test
        self.qualifier = qualifier
        self.filters = filters
        self.filter_name = xml_element.attributes["name"]
        if isinstance(self.filter_name, unicode):
            self.filter_name = self.filter_name.encode("utf-8")
        self.defined = not self.qualifier or not isinstance(qualifier, IsNotDefined) or len(filters)


    def _deserialize(self, data):
        """
        Convert a JSON compatible serialization of this object into the actual object.
        """
        self.propfilter_test = data["propfilter_test"]
        self.qualifier = FilterBase.deserialize(data["qualifier"]) if data["qualifier"] else None
        self.filters = [FilterBase.deserialize(filter) for filter in data["filters"]]
        self.filter_name = data["filter_name"]
        self.defined = data["defined"]


    def serialize(self):
        """
        Create a JSON compatible serialization of this object - will be used in a cross-pod request.
        """
        result = super(FilterChildBase, self).serialize()
        result.update({
            "propfilter_test": self.propfilter_test,
            "qualifier": self.qualifier.serialize() if self.qualifier else None,
            "filters": [filter.serialize() for filter in self.filters],
            "filter_name": self.filter_name,
            "defined": self.defined,
        })
        return result


    def match(self, item):
        """
        Returns True if the given address book item (either a property or parameter value)
        matches this filter, False otherwise.
        """

        allof = self.propfilter_test == "allof"
        if self.qualifier and allof and not self.qualifier.match(item):
            return False

        if len(self.filters) > 0:
            for filter in self.filters:
                if allof != filter._match(item):
                    return not allof
            return allof
        else:
            return not allof



class PropertyFilter (FilterChildBase):
    """
    Limits a search to specific properties.
    """

    serialized_name = "PropertyFilter"

    def _match(self, vcard):
        # At least one property must match (or is-not-defined is set)
        for property in vcard.properties():
            if property.name().upper() == self.filter_name.upper() and self.match(property):
                break
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

FilterBase.serialize_register(PropertyFilter)



class ParameterFilter (FilterChildBase):
    """
    Limits a search to specific parameters.
    """

    serialized_name = "ParameterFilter"

    def _match(self, property):

        # At least one parameter must match (or is-not-defined is set)
        result = not self.defined
        for parameterName in property.parameterNames():
            if parameterName.upper() == self.filter_name.upper() and self.match([property.parameterValues(parameterName)]):
                result = self.defined
                break

        return result

FilterBase.serialize_register(ParameterFilter)



class IsNotDefined (FilterBase):
    """
    Specifies that the named iCalendar item does not exist.
    """

    serialized_name = "IsNotDefined"

    def match(self, component, access=None):
        # Oddly, this needs always to return True so that it appears there is
        # a match - but we then "negate" the result if is-not-defined is set.
        # Actually this method should never be called as we special case the
        # is-not-defined option.
        return True

FilterBase.serialize_register(IsNotDefined)



class TextMatch (FilterBase):
    """
    Specifies a substring match on a property or parameter value.
    """
    serialized_name = "TextMatch"

    def __init__(self, xml_element):

        super(TextMatch, self).__init__(xml_element)
        if xml_element is None:
            return

        self.text = str(xml_element)

        if "collation" in xml_element.attributes:
            self.collation = xml_element.attributes["collation"]
        else:
            self.collation = "i;unicode-casemap"

        if "negate-condition" in xml_element.attributes:
            self.negate = xml_element.attributes["negate-condition"]
            if self.negate not in ("yes", "no"):
                self.negate = "no"
            self.negate = {"yes": True, "no": False}[self.negate]
        else:
            self.negate = False

        if "match-type" in xml_element.attributes:
            self.match_type = xml_element.attributes["match-type"]
            if self.match_type not in (
                "equals",
                "contains",
                "starts-with",
                "ends-with",
            ):
                self.match_type = "contains"
        else:
            self.match_type = "contains"


    def _deserialize(self, data):
        """
        Convert a JSON compatible serialization of this object into the actual object.
        """
        self.text = data["text"]
        self.collation = data["collation"]
        self.negate = data["negate"]
        self.match_type = data["match_type"]


    def serialize(self):
        """
        Create a JSON compatible serialization of this object - will be used in a cross-pod request.
        """
        result = super(TextMatch, self).serialize()
        result.update({
            "text": self.text,
            "collation": self.collation,
            "negate": self.negate,
            "match_type": self.match_type,
        })
        return result


    def _match(self, item):
        """
        Match the text for the item.
        If the item is a property, then match the property value,
        otherwise it may be a list of parameter values - try to match anyone of those
        """
        if item is None:
            return False

        if isinstance(item, Property):
            values = [item.strvalue()]
        else:
            values = item

        test = unicode(self.text, "utf-8").lower()


        def _textCompare(s):
            # Currently ignores the collation and does caseless matching
            s = s.lower()

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
            # so we need to check for that and iterate over the list.
            if isinstance(value, list):
                for subvalue in value:
                    if _textCompare(unicode(subvalue, "utf-8")):
                        return not self.negate
            else:
                if _textCompare(unicode(value, "utf-8")):
                    return not self.negate

        return self.negate

FilterBase.serialize_register(TextMatch)
