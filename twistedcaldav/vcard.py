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
vCard Utilities
"""

__all__ = [
    "Property",
    "Component",
]

import cStringIO as StringIO

from vobject import newFromBehavior, readComponents
from vobject.base import Component as vComponent
from vobject.base import ContentLine as vContentLine
from vobject.base import ParseError as vParseError

from twisted.web2.stream import IStream
from twisted.web2.dav.util import allDataFromStream

vCardProductID = "-//CALENDARSERVER.ORG//NONSGML Version 1//EN"

class Property (object):
    """
    vCard Property
    """
    def __init__(self, name, value, params={}, group=None, encoded=False, **kwargs):
        """
        @param name: the property's name
        @param value: the property's value
        @param params: a dictionary of parameters, where keys are parameter names and
            values are (possibly empty) lists of parameter values.
        """
        if name is None:
            assert value  is None
            assert params is None

            vobj = kwargs["vobject"]

            if not isinstance(vobj, vContentLine):
                raise TypeError("Not a vContentLine: %r" % (property,))

            self._vobject = vobj
        else:
            # Convert params dictionary to list of lists format used by vobject
            lparams = [[key] + lvalue for key, lvalue in params.items()]
            self._vobject = vContentLine(name, lparams, value, isNative=True, group=group, encoded=encoded )

    def __str__ (self): return self._vobject.serialize()
    def __repr__(self): return "<%s: %r: %r>" % (self.__class__.__name__, self.name(), self.value())

    def __hash__(self): return hash((self.name(), self.value()))

    def __ne__(self, other): return not self.__eq__(other)
    def __eq__(self, other):
        if not isinstance(other, Property): return False
        return self.name() == other.name() and self.value() == other.value()

    def __gt__(self, other): return not (self.__eq__(other) or self.__lt__(other))
    def __lt__(self, other):
        my_name = self.name()
        other_name = other.name()

        if my_name < other_name: return True
        if my_name > other_name: return False

        return self.value() < other.value()

    def __ge__(self, other): return self.__eq__(other) or self.__gt__(other)
    def __le__(self, other): return self.__eq__(other) or self.__lt__(other)

    def name  (self): return self._vobject.name

    def value (self): return self._vobject.value
    def setValue(self, value):
        self._vobject.value = value

    def params(self): return self._vobject.params

    def transformAllFromNative(self):
        transformed = self._vobject.isNative
        if transformed:
            self._vobject = self._vobject.transformFromNative()
            self._vobject.transformChildrenFromNative()
        return transformed
        
    def transformAllToNative(self):
        transformed = not self._vobject.isNative
        if transformed:
            self._vobject = self._vobject.transformToNative()
            self._vobject.transformChildrenToNative()
        return transformed

class Component (object):
    """
    X{vCard} component.
    """
    @classmethod
    def fromString(clazz, string):
        """
        Construct a L{Component} from a string.
        @param string: a string containing vCard data.
        @return: a L{Component} representing the first component described by
            C{string}.
        """
        if type(string) is unicode:
            string = string.encode("utf-8")
        return clazz.fromStream(StringIO.StringIO(string))

    @classmethod
    def fromStream(clazz, stream):
        """
        Construct a L{Component} from a stream.
        @param stream: a C{read()}able stream containing vCard data.
        @return: a L{Component} representing the first component described by
            C{stream}.
        """
        try:
            return clazz(None, vobject=readComponents(stream).next())
        except vParseError, e:
            raise ValueError(e)
        except StopIteration, e:
            raise ValueError(e)

    @classmethod
    def fromIStream(clazz, stream):
        """
        Construct a L{Component} from a stream.
        @param stream: an L{IStream} containing vCard data.
        @return: a deferred returning a L{Component} representing the first
            component described by C{stream}.
        """
        #
        # FIXME:
        #   This reads the request body into a string and then parses it.
        #   A better solution would parse directly and incrementally from the
        #   request stream.
        #
        def parse(data): return clazz.fromString(data)
        return allDataFromStream(IStream(stream), parse)

    def __init__(self, name, **kwargs):
        """
        Use this constructor to initialize an empty L{Component}.
        To create a new L{Component} from X{vCard} data, don't use this
        constructor directly.  Use one of the factory methods instead.
        @param name: the name (L{str}) of the X{iCalendar} component type for the
            component.
        """
        if name is None:
            if "vobject" in kwargs:
                vobj = kwargs["vobject"]

                if vobj is not None:
                    if not isinstance(vobj, vComponent):
                        raise TypeError("Not a vComponent: %r" % (vobj,))

                self._vobject = vobj
            else:
                raise AssertionError("name may not be None")

            # FIXME: _parent is not use internally, and appears to be used elsewhere,
            # even though it's names as a private variable.
            if "parent" in kwargs:
                parent = kwargs["parent"]
                
                if parent is not None:
                    if not isinstance(parent, Component):
                        raise TypeError("Not a Component: %r" % (parent,))
                    
                self._parent = parent
            else:
                self._parent = None
        else:
            self._vobject = newFromBehavior(name)
            self._parent = None

    def __str__ (self): return self._vobject.serialize()
    def __repr__(self): return "<%s: %r>" % (self.__class__.__name__, str(self._vobject))

    def __hash__(self):
        return hash(tuple(sorted(self.properties())))

    def __ne__(self, other): return not self.__eq__(other)
    def __eq__(self, other):
        if not isinstance(other, Component):
            return False

        my_properties = set(self.properties())
        for property in other.properties():
            if property in my_properties:
                my_properties.remove(property)
            else:
                return False
        if my_properties:
            return False

        return True

    # FIXME: Should this not be in __eq__?
    def same(self, other):
        return self._vobject == other._vobject
    
    def name(self):
        """
        @return: the name of the iCalendar type of this component.
        """
        return self._vobject.name

    def setBehavior(self, behavior):
        """
        Set the behavior of the underlying iCal obtecy.
        @param behavior: the behavior type to set.
        """
        self._vobject.setBehavior(behavior)

    def duplicate(self):
        """
        Duplicate this object and all its contents.
        @return: the duplicated vcard.
        """
        return Component(None, vobject=vComponent.duplicate(self._vobject))
        
    def hasProperty(self, name):
        """
        @param name: the name of the property whose existence is being tested.
        @return: True if the named property exists, False otherwise.
        """
        try:
            return len(self._vobject.contents[name.lower()]) > 0
        except KeyError:
            return False

    def getProperty(self, name):
        """
        Get one property from the property list.
        @param name: the name of the property to get.
        @return: the L{Property} found or None.
        @raise: L{ValueError} if there is more than one property of the given name.
        """
        properties = tuple(self.properties(name))
        if len(properties) == 1: return properties[0]
        if len(properties) > 1: raise ValueError("More than one %s property in component %r" % (name, self))
        return None
        
    def properties(self, name=None):
        """
        @param name: if given and not C{None}, restricts the returned properties
            to those with the given C{name}.
        @return: an iterable of L{Property} objects, one for each property of
            this component.
        """
        if name is None:
            properties = self._vobject.getChildren()
        else:
            try:
                properties = self._vobject.contents[name.lower()]
            except KeyError:
                return ()

        return (
            Property(None, None, None, vobject=p)
            for p in properties
            if isinstance(p, vContentLine)
        )

    def propertyValue(self, name):
        properties = tuple(self.properties(name))
        if len(properties) == 1: return properties[0].value()
        if len(properties) > 1: raise ValueError("More than one %s property in component %r" % (name, self))
        return None


    def propertyNativeValue(self, name):
        """
        Return the native property value for the named property in the supplied component.
        NB Assumes a single property exists in the component.
        @param name: the name of the property whose value is required
        @return: the native property value
        """
        properties = tuple(self.properties(name))

        if len(properties) == 1:
            transormed = properties[0].transformAllToNative()
    
            result = properties[0].value()
    
            if transormed:
                properties[0].transformAllFromNative()
                
            return result

        elif len(properties) > 1:
            raise ValueError("More than one %s property in component %r" % (name, self))
        else:
            return None

    def addProperty(self, property):
        """
        Adds a property to this component.
        @param property: the L{Property} to add to this component.
        """
        self._vobject.add(property._vobject)

    def removeProperty(self, property):
        """
        Remove a property from this component.
        @param property: the L{Property} to remove from this component.
        """
        self._vobject.remove(property._vobject)

    def resourceUID(self):
        """
        @return: the UID of the subcomponents in this component.
        """
        assert self.name() == "VCARD", "Not a vcard: %r" % (self,)

        if not hasattr(self, "_resource_uid"):
            self._resource_uid = self.propertyValue("UID")

        return self._resource_uid

    def validForCardDAV(self):
        """
        @raise ValueError: if the given vcard data is not valid.
        """
        if self.name() != "VCARD": raise ValueError("Not a vcard")

        version = self.propertyValue("VERSION")
        if version != "3.0": raise ValueError("Not a version 2.0 vCard (version=%s)" % (version,))

        uid = self.propertyValue("UID")
        if uid is None:
            raise ValueError("All vCards must have UIDs")

    def transformAllFromNative(self):
        self._vobject = self._vobject.transformFromNative()
        self._vobject.transformChildrenFromNative(False)
        
    def transformAllToNative(self):
        self._vobject = self._vobject.transformToNative()
        self._vobject.transformChildrenToNative()
