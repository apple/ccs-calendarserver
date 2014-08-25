# -*- test-case-name: txdav.who.test -*-
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
Calendar and contacts directory extensions to L{twext.who.idirectory}.
"""

__all__ = [
    "AutoScheduleMode",
    "RecordType",
    "FieldName",
]

from twisted.python.constants import Names, NamedConstant

from twext.who.idirectory import FieldName as BaseFieldName



#
# Data types
#

class AutoScheduleMode(Names):
    """
    Constants for automatic scheduling modes.

    @cvar none: Invitations are not automatically handled.

    @cvar accept: Accept all invitations.

    @cvar decline: Decline all invitations.

    @cvar acceptIfFree: Accept invitations that do not conflict with a busy
        time slot.  Other invitations are not automatically handled.

    @cvar declineIfBusy: Decline invitations that conflict with a busy time
        slot.  Other invitations are not automatically handled.

    @cvar acceptIfFreeDeclineIfBusy: Accept invitations that do not conflict
        with a busy time slot.  Decline invitations that conflict with a busy
        time slot.  Other invitations are not automatically handled.
    """

    none = NamedConstant()
    none.description = u"no action"

    accept = NamedConstant()
    accept.description = u"accept"

    decline = NamedConstant()
    decline.description = u"decline"

    acceptIfFree = NamedConstant()
    acceptIfFree.description = u"accept if free"

    declineIfBusy = NamedConstant()
    declineIfBusy.description = u"decline if busy"

    acceptIfFreeDeclineIfBusy = NamedConstant()
    acceptIfFreeDeclineIfBusy.description = u"accept if free, decline if busy"



class RecordType(Names):
    """
    Constants for calendar and contacts directory record types.

    @cvar location: Location record.
        Represents a schedulable location (eg. a meeting room).

    @cvar resource: Resource record.
        Represents a schedulable resource (eg. a projector, conference line,
        etc.).

    @cvar address: Address record.
        Represents a physical address (street address and/or geolocation).
    """

    location = NamedConstant()
    location.description = u"location"

    resource = NamedConstant()
    resource.description = u"resource"

    address = NamedConstant()
    address.description = u"physical address"



class FieldName(Names):
    """
    Constants for calendar and contacts directory record field names.

    Fields as associated with either a single value or an iterable of values.

    @cvar serviceNodeUID: For a calendar and contacts service with multiple
        nodes, this denotes the node that the user's data resides on.
        The associated value must be a L{unicode}.

    @cvar loginAllowed: Determines whether a record can log in.
        The associated value must be a L{bool}.

    @cvar hasCalendars: Determines whether a record has calendar data.
        The associated value must be a L{bool}.

    @cvar hasContacts: Determines whether a record has contact data.
        The associated value must be a L{bool}.

    @cvar autoScheduleMode: Determines the auto-schedule mode for a record.
        The associated value must be a L{NamedConstant}.

    @cvar autoAcceptGroup: Contains the UID for a group record which contains
        members for whom auto-accept will behave as "accept if free", even if
        auto-accept is set to "manual".
        The associated value must be a L{NamedConstant}.
    """

    serviceNodeUID = NamedConstant()
    serviceNodeUID.description = u"service node UID"

    loginAllowed = NamedConstant()
    loginAllowed.description = u"login permitted"
    loginAllowed.valueType = bool

    hasCalendars = NamedConstant()
    hasCalendars.description = u"has calendars"
    hasCalendars.valueType = bool

    hasContacts = NamedConstant()
    hasContacts.description = u"has contacts"
    hasContacts.valueType = bool

    autoScheduleMode = NamedConstant()
    autoScheduleMode.description = u"auto-schedule mode"
    autoScheduleMode.valueType = AutoScheduleMode

    autoAcceptGroup = NamedConstant()
    autoAcceptGroup.description = u"auto-accept group"
    autoAcceptGroup.valueType = BaseFieldName.valueType(BaseFieldName.uid)

    readOnlyProxy = NamedConstant()
    readOnlyProxy.description = u"read-only proxy group"
    readOnlyProxy.valueType = BaseFieldName.valueType(BaseFieldName.uid)

    readWriteProxy = NamedConstant()
    readWriteProxy.description = u"read-write proxy group"
    readWriteProxy.valueType = BaseFieldName.valueType(BaseFieldName.uid)

    # For "locations", i.e., scheduled spaces:

    associatedAddress = NamedConstant()
    associatedAddress.description = u"associated address UID"

    capacity = NamedConstant()
    capacity.description = u"room capacity"
    capacity.valueType = int

    floor = NamedConstant()
    floor.description = u"building floor"

    # For "addresses", i.e., non-scheduled areas containing locations:

    abbreviatedName = NamedConstant()
    abbreviatedName.description = u"abbreviated name"

    geographicLocation = NamedConstant()
    geographicLocation.description = u"geographic location URI"

    streetAddress = NamedConstant()
    streetAddress.description = u"street address"
