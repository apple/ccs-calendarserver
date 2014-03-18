##
# Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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
Directory tools
"""

__all__ = [
    "findRecords",
    "recordInfo",
    "recordBasicInfo",
    "recordGroupMembershipInfo",
    "recordProxyAccessInfo",
]


import operator

from twisted.internet.defer import succeed
from twisted.internet.defer import inlineCallbacks, returnValue

from calendarserver.tools.tables import Table


@inlineCallbacks
def findRecords(directory, terms):
    records = tuple((yield directory.recordsMatchingTokens(terms)))
    returnValue(sorted(records, key=operator.attrgetter("fullName")))



@inlineCallbacks
def recordInfo(directory, record):
    """
    Complete record information.
    """
    info = []

    def add(name, subInfo):
        if subInfo:
            info.append("%s:" % (name,))
            info.append(subInfo)

    add("Directory record" , (yield recordBasicInfo(directory, record)))
    add("Group memberships", (yield recordGroupMembershipInfo(directory, record)))
    add("Proxy access"     , (yield recordProxyAccessInfo(directory, record)))

    returnValue("\n".join(info))



def recordBasicInfo(directory, record):
    """
    Basic information for a record.
    """
    table = Table()

    def add(name, value):
        if value:
            table.addRow((name, value))

    add("Service"    , record.service   )
    add("Record Type", record.recordType)

    for shortName in record.shortNames:
        add("Short Name", shortName)

    add("GUID"      , record.guid     )
    add("Full Name" , record.fullName )
    add("First Name", record.firstName)
    add("Last Name" , record.lastName )

    try:
        for email in record.emailAddresses:
            add("Email Address", email)
    except AttributeError:
        pass

    try:
        for cua in record.calendarUserAddresses:
            add("Calendar User Address", cua)
    except AttributeError:
        pass

    add("Server ID"           , record.serverID)
    add("Enabled"             , record.enabled)
    add("Enabled for Calendar", record.hasCalendars)
    add("Enabled for Contacts", record.hasContacts)

    return succeed(table.toString())



def recordGroupMembershipInfo(directory, record):
    """
    Group membership info for a record.
    """
    rows = []

    for group in record.groups():
        rows.append((group.uid, group.shortNames[0], group.fullName))

    if not rows:
        return succeed(None)

    rows = sorted(rows,
        key=lambda row: (row[1], row[2])
    )

    table = Table()
    table.addHeader(("UID", "Short Name", "Full Name"))
    for row in rows:
        table.addRow(row)

    return succeed(table.toString())



@inlineCallbacks
def recordProxyAccessInfo(directory, record):
    """
    Group membership info for a record.
    """
    # FIXME: This proxy finding logic should be in DirectoryRecord.

    def meAndMyGroups(record=record, groups=set((record,))):
        for group in record.groups():
            groups.add(group)
            meAndMyGroups(group, groups)
        return groups

    # FIXME: This module global is really gross.
    from twistedcaldav.directory.calendaruserproxy import ProxyDBService

    rows = []
    proxyInfoSeen = set()
    for record in meAndMyGroups():
        proxyUIDs = (yield ProxyDBService.getMemberships(record.uid))

        for proxyUID in proxyUIDs:
            # These are of the form: F153A05B-FF27-4B6C-BD6D-D1239D0082B0#calendar-proxy-read
            # I don't know how to get DirectoryRecord objects for the proxyUID here, so, let's cheat for now.
            proxyUID, proxyType = proxyUID.split("#")
            if (proxyUID, proxyType) not in proxyInfoSeen:
                proxyRecord = directory.recordWithUID(proxyUID)
                rows.append((proxyUID, proxyRecord.recordType, proxyRecord.shortNames[0], proxyRecord.fullName, proxyType))
                proxyInfoSeen.add((proxyUID, proxyType))

    if not rows:
        returnValue(None)

    rows = sorted(rows,
        key=lambda row: (row[1], row[2], row[4])
    )

    table = Table()
    table.addHeader(("UID", "Record Type", "Short Name", "Full Name", "Access"))
    for row in rows:
        table.addRow(row)

    returnValue(table.toString())



def summarizeRecords(directory, records):
    table = Table()

    table.addHeader((
        "UID",
        "Record Type",
        "Short Names",
        "Email Addresses",
        "Full Name",
    ))

    def formatItems(items):
        if items:
            return ", ".join(items)
        else:
            return None

    for record in records:
        table.addRow((
            record.uid,
            record.recordType,
            formatItems(record.shortNames),
            formatItems(record.emailAddresses),
            record.fullName,
        ))

    if table.rows:
        return succeed(table.toString())
    else:
        return succeed(None)
