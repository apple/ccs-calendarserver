# -*- test-case-name: txdav.base.propertystore.test.test_none,txdav.caldav.datastore,txdav.carddav.datastore -*-
##
# Copyright (c) 2010-2011 Apple Inc. All rights reserved.
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

from __future__ import absolute_import

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
    def __init__(self, defaultuser, pathFactory):
        super(PropertyStore, self).__init__(defaultuser)
        del self.__setitem__
        del self.__delitem__

    #
    # Required implementations
    #

    def _getitem_uid(self, key, uid):
        validKey(key)
        raise KeyError(key)

    def _setitem_uid(self, key, value, uid):
        validKey(key)
        raise PropertyChangeNotAllowedError("Property store is read-only.", (key,))

    def _delitem_uid(self, key, uid):
        validKey(key)
        raise KeyError(key)

    def _keys_uid(self, uid):
        return ()

    #
    # I/O
    #

    def flush(self):
        return None

    def abort(self):
        return None
