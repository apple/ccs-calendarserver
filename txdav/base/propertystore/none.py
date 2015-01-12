# -*- test-case-name: txdav.base.propertystore.test.test_none,txdav.caldav.datastore,txdav.carddav.datastore -*-
##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
Always-empty property store.
"""

__all__ = [
    "PropertyStore",
]

from txdav.idav import PropertyChangeNotAllowedError
from txdav.base.propertystore.base import AbstractPropertyStore, validKey

class PropertyStore(AbstractPropertyStore):
    """
    Always-empty property store.
    Writing properties is not allowed.
    """
    #
    # We override the UserDict items directly here rather than the _uid methods
    #

    def __getitem__(self, key):
        validKey(key)
        raise KeyError(key)


    def __setitem__(self, key, value):
        validKey(key)
        raise PropertyChangeNotAllowedError("Property store is read-only.", (key,))


    def __delitem__(self, key):
        validKey(key)
        raise KeyError(key)


    def keys(self):
        return ()


    def _removeResource(self):
        pass


    #
    # I/O
    #

    def flush(self):
        return None


    def abort(self):
        return None
