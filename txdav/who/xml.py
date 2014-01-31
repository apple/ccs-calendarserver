# -*- test-case-name: txdav.who.test.test_xml -*-
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

from .idirectory import RecordType, FieldName, AutoScheduleMode



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
    location.recordType = RecordType.location

    resource = ValueConstant(u"resource")
    resource.recordType = RecordType.resource

    address = ValueConstant(u"address")
    address.recordType = RecordType.address



class AutoScheduleValue(Values):
    """
    XML element values for auto-schedule modes.
    """

    none = ValueConstant(u"none")
    none.mode = AutoScheduleMode.none

    accept = ValueConstant(u"accept")
    accept.mode = AutoScheduleMode.accept

    decline = ValueConstant(u"decline")
    decline.mode = AutoScheduleMode.decline

    acceptIfFree = ValueConstant(u"accept-if-free")
    acceptIfFree.mode = AutoScheduleMode.acceptIfFree

    declineIfBusy = ValueConstant(u"decline-if-busy")
    declineIfBusy.mode = AutoScheduleMode.declineIfBusy

    acceptIfFreeDeclineIfBusy = ValueConstant(
        u"accept-if-free-decline-if-busy"
    )
    acceptIfFreeDeclineIfBusy.mode = AutoScheduleMode.acceptIfFreeDeclineIfBusy



#
# Directory Service
#

class DirectoryService(BaseDirectoryService):
    """
    XML directory service with calendar and contacts data.
    """

    recordType = ConstantsContainer(
        (BaseDirectoryService.recordType, RecordType)
    )

    fieldName = ConstantsContainer(
        (BaseDirectoryService.fieldName, FieldName)
    )

    # XML schema constants

    element = ConstantsContainer(
        (BaseDirectoryService.element, Element)
    )

    attribute = ConstantsContainer(
        (BaseDirectoryService.attribute, Attribute)
    )

    recordTypeValue = ConstantsContainer(
        (BaseDirectoryService.recordTypeValue, RecordTypeValue)
    )
