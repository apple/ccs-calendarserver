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
Property store with no storage.
"""

__all__ = [
    "PropertyStore",
]

from txdav.base.propertystore.base import AbstractPropertyStore, validKey

class PropertyStore(AbstractPropertyStore):
    """
    Property store with no storage.
    """
    
    properties = {}

    def __init__(self, defaultuser):
        super(PropertyStore, self).__init__(defaultuser)

        self.modified = {}
        self.removed = set()

    def __str__(self):
        return "<%s>" % (self.__class__.__name__,)

    #
    # Required implementations
    #

    def _getitem_uid(self, key, uid):
        validKey(key)
        effectiveKey = (key, uid)

        if effectiveKey in self.modified:
            return self.modified[effectiveKey]

        if effectiveKey in self.removed:
            raise KeyError(key)

        return self.properties[effectiveKey]

    def _setitem_uid(self, key, value, uid):
        validKey(key)
        effectiveKey = (key, uid)

        if effectiveKey in self.removed:
            self.removed.remove(effectiveKey)
        self.modified[effectiveKey] = value

    def _delitem_uid(self, key, uid):
        validKey(key)
        effectiveKey = (key, uid)

        if effectiveKey in self.modified:
            del self.modified[effectiveKey]
        elif effectiveKey not in self.properties:
            raise KeyError(key)

        self.removed.add(effectiveKey)

    def _keys_uid(self, uid):
        seen = set()

        for effectivekey in self.properties:
            if effectivekey[1] == uid and effectivekey not in self.removed:
                seen.add(effectivekey)
                yield effectivekey[0]

        for effectivekey in self.modified:
            if effectivekey[1] == uid and effectivekey not in seen:
                yield effectivekey[0]

    #
    # I/O
    #

    def flush(self):
        props    = self.properties
        removed  = self.removed
        modified = self.modified

        for effectivekey in removed:
            assert effectivekey not in modified
            try:
                del props[effectivekey]
            except KeyError:
                pass

        for effectivekey in modified:
            assert effectivekey not in removed
            value = modified[effectivekey]
            props[effectivekey] = value
        
        self.removed.clear()
        self.modified.clear()        

    def abort(self):
        self.removed.clear()
        self.modified.clear()
