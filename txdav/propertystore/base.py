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
Base property store.
"""

__all__ = [
    "AbstractPropertyStore",
]

from zope.interface import implements

from twext.log import LoggingMixIn

from txdav.idav import IPropertyStore, IPropertyName


class PropertyName(LoggingMixIn):
    """
    Property name.
    """
    implements(IPropertyName)

    @staticmethod
    def fromString(sname):
        index = sname.find("}")

        if (index is -1 or not len(sname) > index or not sname[0] == "{"):
            raise TypeError("Invalid sname: %r" % (sname,))

        return (sname[1:index], sname[index+1:])

    def __init__(self, namespace, name):
        self.namespace = namespace
        self.name = name

    def __hash__(self):
        return hash((self.namespace, self.name))

    def __repr__(self):
        return "<%s: %s>" % (
            self.__class__.__name__,
            self.toString(),
        )

    def toString(self):
        return "{%s}%s" % (self.namespace, self.name)


class AbstractPropertyStore(LoggingMixIn):
    """
    Base property store.
    """
    implements(IPropertyStore)

    #
    # Subclasses must override these
    #

    def __delitem__(self, key):
        raise NotImplementedError()

    def __getitem__(self, key):
        raise NotImplementedError()

    def __contains__(self, key):
        raise NotImplementedError()

    def __setitem__(key, value):
        raise NotImplementedError()

    def __iter__(self):
        raise NotImplementedError()

    def __len__(self):
        raise NotImplementedError()

    def flush(self):
        raise NotImplementedError()

    def abort(self):
        raise NotImplementedError()

    #
    # Subclasses may override these
    #

    def len(self, key):
        return self.__len__(key)

    def clear(self):
        for key in self.__iter__():
            self.__delitem__(key)

    def get(self, key, default=None):
        if self.__contains__(key):
            return self.__getitem__(key)
        else:
            return default

    def iter(self):
        return self.__iter__()

    def iteritems(self):
        return (
            (key, self.get(key))
            for key in self.__iter__()
        )

    def items(self):
        return list(self.iteritems())

    iterkeys = iter
    __iterkeys__ = iter

    def keys(self):
        return tuple(self.__iter__())

    def itervalues(self):
        return (
            self.get(key)
            for key in self.__iter__()
        )

    def values(self):
        return list(self.itervalues())

    def pop(self, key, default=None):
        try:
            value = self.__getitem__(key)
        except KeyError:
            if default is None:
                raise
            return default

        self.__delitem__(key)

        return value

    def popitem(self):
        for key in self.__iter__():
            self.__delitem__(key)
            break

    def setdefault(self, key, default=None):
        if self.__contains__(key):
            return key

        self.__setitem__(key, default)

        return default

    def update(other=None):
        # FIXME
        raise NotImplementedError()
