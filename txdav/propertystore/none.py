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

from __future__ import absolute_import

__all__ = [
    "PropertyStore",
]

from txdav.propertystore.base import AbstractPropertyStore, validKey
from txdav.idav import PropertyChangeNotAllowedError


class PropertyStore(AbstractPropertyStore):
    """
    Property store with no storage.
    """
    def __init__(self):
        self.modified = {}

    def __str__(self):
        return "<%s>" % (self.__class__.__name__,)

    #
    # Accessors
    #

    def __delitem__(self, key):
        validKey(key)

        if key in self.modified:
            del self.modified[key]
        else:
            raise KeyError(key)

    def __getitem__(self, key):
        validKey(key)

        if key in self.modified:
            return self.modified[key]
        else:
            raise KeyError(key)

    def __contains__(self, key):
        validKey(key)

        return key in self.modified

    def __setitem__(self, key, value):
        validKey(key)

        self.modified[key] = value

    def __iter__(self):
        return (k for k in self.modified)

    def __len__(self):
        return len(self.modified)

    #
    # I/O
    #

    def flush(self):
        if self.modified:
            raise PropertyChangeNotAllowedError(
                "None property store cannot flush changes.",
                keys = self.modified.keys()
            )

    def abort(self):
        self.modified.clear()
