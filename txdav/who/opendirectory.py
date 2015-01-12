# -*- test-case-name: txdav.who.test.test_xml -*-
##
# Copyright (c) 2014-2015 Apple Inc. All rights reserved.
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

from __future__ import print_function
from __future__ import absolute_import

"""
Calendar and contacts directory extensions to L{twext.who.opendirectory}.
"""

__all__ = [
    "DirectoryService",
]

from twext.who.opendirectory import DirectoryService

DirectoryService    # Something has to use the import

# Hoorj OMG haxx
from twext.who.opendirectory._constants import ODRecordType as _ODRecordType
from .idirectory import RecordType as _CSRecordType

_ODRecordType.place.recordType = _CSRecordType.location     # Use dsRecTypeStandard:Places for calendar locations
_ODRecordType.resource.recordType = _CSRecordType.resource
