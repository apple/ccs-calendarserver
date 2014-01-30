# -*- test-case-name: txdav.who -*-
##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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
Calendar and contacts directory extentions to L{twext.who.xml}.
"""

__all__ = [
    "DirectoryService",
]

from twisted.python.constants import Values, ValueConstant

from twext.who.xml import DirectoryService as BaseDirectoryService
from twext.who.util import ConstantsContainer

from .idirectory import RecordType, FieldName



#
# Directory Service
#

class DirectoryService(BaseDirectoryService):
    """
    XML directory service with calendar and contacts attributes.
    """

    recordType = ConstantsContainer(
        (BaseDirectoryService.recordType, RecordType)
    )

    fieldName = ConstantsContainer(
        (BaseDirectoryService.fieldName, FieldName)
    )



#
# XML constants
#

class Element(Values):
    """
    XML calendar and contacts element names.
    """

    # Field names

    serviceNodeUID = ValueConstant(u"service-node")
    serviceNodeUID.fieldName = FieldName.serviceNodeUID

    loginAllowed = ValueConstant(u"login-allowed")
    loginAllowed.fieldName = FieldName.loginAllowed

    hasCalendars = ValueConstant(u"has-calendars")
    hasCalendars.fieldName = FieldName.hasCalendars

    hasContacts = ValueConstant(u"has-contacts")
    hasContacts.fieldName = FieldName.hasContacts

    autoScheduleMode = ValueConstant(u"auto-schedule-mode")
    autoScheduleMode.fieldName = FieldName.autoScheduleMode

    autoAcceptGroup = ValueConstant(u"auto-accept-group")
    autoAcceptGroup.fieldName = FieldName.autoAcceptGroup



class Attribute(Values):
    """
    XML calendar and contacts attribute names.
    """



class RecordTypeValue(Values):
    """
    XML attribute values for calendar and contacts record types.
    """

    location = ValueConstant(u"location")
    location.fieldName = FieldName.location

    resource = ValueConstant(u"resource")
    resource.fieldName = FieldName.resource

    address = ValueConstant(u"address")
    address.fieldName = FieldName.address



class AutoScheduleValue(Values):
    """
    XML attribute values for auto-schedule modes.
    """
    # default -> ?

    # none -> ?

    accept = ValueConstant(u"accept")

    decline = ValueConstant(u"decline")

    acceptIfFree = ValueConstant(u"accept-if-free")

    declineIfBusy = ValueConstant(u"decline-if-busy")

    # automatic -> ?
