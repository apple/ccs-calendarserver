##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
Base property store.
"""

__all__ = [
    "AbstractPropertyStore",
    "PropertyName",
]

from twext.python.log import Logger
from txdav.xml import element as davxml
from txdav.xml.base import encodeXMLName
from txdav.xml.element import lookupElement
from txweb2.dav.resource import TwistedGETContentMD5, \
    TwistedQuotaRootProperty

from txdav.idav import IPropertyStore, IPropertyName

from UserDict import DictMixin

from zope.interface import implements

class PropertyName(object):
    """
    Property name.
    """
    log = Logger()

    implements(IPropertyName)

    @staticmethod
    def fromString(sname):
        index = sname.find("}")

        if (index is -1 or not len(sname) > index or not sname[0] == "{"):
            raise TypeError("Invalid sname: %r" % (sname,))

        return PropertyName(sname[1:index], sname[index + 1:])


    @staticmethod
    def fromElement(element):
        return PropertyName(element.namespace, element.name)


    def __init__(self, namespace, name):
        self.namespace = namespace
        self.name = name


    def _cmpval(self):
        """
        Return a value to use for hashing and comparisons.
        """
        return (self.namespace, self.name)


    # FIXME: need direct tests for presence-in-dictionary
    def __hash__(self):
        return hash(self._cmpval())


    def __eq__(self, other):
        if not isinstance(other, PropertyName):
            return NotImplemented
        return self._cmpval() == other._cmpval()


    def __ne__(self, other):
        if not isinstance(other, PropertyName):
            return NotImplemented
        return self._cmpval() != other._cmpval()


    def __repr__(self):
        return "<%s: %s>" % (
            self.__class__.__name__,
            self.toString(),
        )


    def toString(self):
        return encodeXMLName(self.namespace, self.name)


    def toElement(self):
        return lookupElement((self.namespace, self.name,))



class AbstractPropertyStore(DictMixin, object):
    """
    Base property store.
    """
    log = Logger()

    implements(IPropertyStore)

    _defaultShadowableKeys = frozenset()
    _defaultProxyOverrideKeys = frozenset()
    _defaultGlobalKeys = frozenset((
        PropertyName.fromElement(davxml.ACL),
        PropertyName.fromElement(davxml.ResourceID),
        PropertyName.fromElement(davxml.ResourceType),
        PropertyName.fromElement(davxml.GETContentType),
        PropertyName.fromElement(TwistedGETContentMD5),
        PropertyName.fromElement(TwistedQuotaRootProperty),
    ))

    def __init__(self, defaultUser, shareeUser=None, proxyUser=None):
        """
        Instantiate the property store for a user. The default is the default user
        (owner) property to read in the case of global or shadowable properties.
        The sharee user is a user sharing the user to read for per-user properties.

        @param defaultUser: the default user uid
        @type defaultUser: C{str}

        @param shareeUser: the per user uid or None if the same as defaultUser
        @type shareeUser: C{str}

        @param proxyUser: the proxy uid or None if no proxy
        @type proxyUser: C{str}
        """

        assert(defaultUser is not None or shareeUser is not None)
        self._defaultUser = shareeUser if defaultUser is None else defaultUser
        self._perUser = defaultUser if shareeUser is None else shareeUser
        self._proxyUser = self._perUser if proxyUser is None else proxyUser
        self._shadowableKeys = set(AbstractPropertyStore._defaultShadowableKeys)
        self._proxyOverrideKeys = set(AbstractPropertyStore._defaultProxyOverrideKeys)
        self._globalKeys = set(AbstractPropertyStore._defaultGlobalKeys)


    def __str__(self):
        return "<%s>" % (self.__class__.__name__)


    def _setDefaultUserUID(self, uid):
        self._defaultUser = uid


    def _setPerUserUID(self, uid):
        self._perUser = uid


    def _setProxyUID(self, uid):
        self._proxyUser = uid


    def setSpecialProperties(self, shadowableKeys, globalKeys, proxyOverrideKeys):
        self._shadowableKeys.update(shadowableKeys)
        self._proxyOverrideKeys.update(proxyOverrideKeys)
        self._globalKeys.update(globalKeys)


    #
    # Subclasses must override these
    #

    def _getitem_uid(self, key, uid):
        raise NotImplementedError()


    def _setitem_uid(self, key, value, uid):
        raise NotImplementedError()


    def _delitem_uid(self, key, uid):
        raise NotImplementedError()


    def _keys_uid(self, uid):
        raise NotImplementedError()


    def _removeResource(self):
        raise NotImplementedError()


    def flush(self):
        raise NotImplementedError()


    def abort(self):
        raise NotImplementedError()


    #
    # Required UserDict implementations
    #

    def __getitem__(self, key):
        # Return proxy value if it exists, else fall through to normal logic
        if self._proxyUser != self._perUser and self.isProxyOverrideProperty(key):
            try:
                return self._getitem_uid(key, self._proxyUser)
            except KeyError:
                pass

        # Handle per-user behavior
        if self.isShadowableProperty(key):
            try:
                result = self._getitem_uid(key, self._perUser)
            except KeyError:
                result = self._getitem_uid(key, self._defaultUser)
            return result
        elif self.isGlobalProperty(key):
            return self._getitem_uid(key, self._defaultUser)
        else:
            return self._getitem_uid(key, self._perUser)


    def __setitem__(self, key, value):
        # Handle per-user behavior
        if self.isGlobalProperty(key):
            return self._setitem_uid(key, value, self._defaultUser)
        # Handle proxy behavior
        elif self._proxyUser != self._perUser and self.isProxyOverrideProperty(key):
            return self._setitem_uid(key, value, self._proxyUser)
        # Remainder is per user
        else:
            return self._setitem_uid(key, value, self._perUser)


    def __delitem__(self, key):
        # Delete proxy value if it exists, else fall through to normal logic
        if self._proxyUser != self._perUser and self.isProxyOverrideProperty(key):
            try:
                self._delitem_uid(key, self._proxyUser)
                return
            except KeyError:
                pass

        # Handle per-user behavior
        if self.isShadowableProperty(key):
            try:
                self._delitem_uid(key, self._perUser)
            except KeyError:
                # It is OK for shadowable delete to fail
                pass
        elif self.isGlobalProperty(key):
            self._delitem_uid(key, self._defaultUser)
        else:
            self._delitem_uid(key, self._perUser)


    def keys(self):

        userkeys = list(self._keys_uid(self._perUser))
        if self._defaultUser != self._perUser:
            defaultkeys = self._keys_uid(self._defaultUser)
            for key in defaultkeys:
                if self.isShadowableProperty(key) and key not in userkeys:
                    userkeys.append(key)
        return tuple(userkeys)


    def update(self, other):
        # FIXME: direct tests.
        # FIXME: support positional signature (although since strings aren't
        # valid, it should just raise an error.
        for key in other:
            self[key] = other[key]


    def isShadowableProperty(self, key):
        return key in self._shadowableKeys


    def isProxyOverrideProperty(self, key):
        return key in self._proxyOverrideKeys


    def isGlobalProperty(self, key):
        return key in self._globalKeys


    def copyAllProperties(self, other):
        """
        Copy all the properties from another store into this one. This needs to be done
        independently of the UID. Each underlying store will need to implement this.
        """
        pass



# FIXME: Actually, we should replace this with calls to IPropertyName()
def validKey(key):
    # Used by implementations to verify that keys are valid
    if not isinstance(key, PropertyName):
        raise TypeError("Not a PropertyName: %r" % (key,))
