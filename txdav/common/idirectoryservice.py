##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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
Common directory service interfaces
"""

from zope.interface.interface import Interface, Attribute


__all__ = [
    "IStoreDirectoryService",
    "IStoreDirectoryRecord",
]

class IStoreDirectoryService(Interface):
    """
    Directory Service for looking up users.
    """

    def recordWithUID(uid): #@NoSelf
        """
        Return the record for the specified store uid.

        @return: the record.
        @rtype: L{IStoreDirectoryRecord}
        """

    def recordWithGUID(guid): #@NoSelf
        """
        Return the record for the specified store guid.

        @return: the record.
        @rtype: L{IStoreDirectoryRecord}
        """



class IStoreDirectoryRecord(Interface):
    """
    Directory record object

    A record identifies a "user" in the system.
    """

    uid = Attribute("The record UID: C{str}")

    shortNames = Attribute("Short names of the record: C{tuple}")

    fullName = Attribute("Full name for the entity associated with the record: C{str}")

    displayName = Attribute("Display name for entity associated with the record: C{str}")
