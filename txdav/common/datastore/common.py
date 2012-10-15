# -*- test-case-name: txdav -*-
##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
Common functionality that is the same for different data store
implementations.
"""

__all__ = [
]


from txdav.xml.element import DisplayName
from txdav.base.propertystore.base import PropertyName


class HomeChildBase(object):
    """
    Home child (address book or calendar) common functionality.
    """

    def displayName(self):
        name = self.properties().get(PropertyName.fromElement(DisplayName), None)
        if name is None:
            return None
        else:
            return name.toString()


    def setDisplayName(self, name):
        if name is None:
            del self.properties()[PropertyName.fromElement(DisplayName)]
        else:
            if not isinstance(name, unicode):
                raise ValueError("Display name must be unicode: %r" % (name,))

            self.properties()[
                PropertyName.fromElement(DisplayName)
            ] = DisplayName.fromString(name)

        return None
