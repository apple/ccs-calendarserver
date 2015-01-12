#
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue
from twext.python.log import Logger
from txdav.caldav.icalendarstore import ComponentRemoveState
from uuid import UUID

log = Logger()

@inlineCallbacks
def getCalendarObjectForRecord(txn, record, uid):
    """
    Get a copy of the event for a calendar user identified by a directory record.

    NOTE: if more than one resource with the same UID is found, we will delete all but
    one of them to avoid scheduling problems.
    """

    if record and record.thisServer():
        # Get record's calendar-home
        calendar_home = yield txn.calendarHomeWithUID(record.uid)
        if calendar_home is None:
            returnValue(None)

        # Get matching newstore objects
        objectResources = (yield calendar_home.getCalendarResourcesForUID(uid))

        if len(objectResources) > 1:
            # Delete all but the first one
            log.debug("Should only have zero or one scheduling object resource with UID '%s' in calendar home: %s" % (uid, calendar_home,))
            for resource in objectResources[1:]:
                yield resource._removeInternal(internal_state=ComponentRemoveState.INTERNAL)
            objectResources = objectResources[:1]

        returnValue(objectResources[0] if len(objectResources) == 1 else None)
    else:
        returnValue(None)



def normalizeCUAddr(addr):
    """
    Normalize a cuaddr string by lower()ing it if it's a mailto:, or
    removing trailing slash if it's a URL.
    @param addr: a cuaddr string to normalize
    @return: normalized string
    """
    lower = addr.lower()
    if lower.startswith("mailto:"):
        addr = lower
    if (
        addr.startswith("/") or
        addr.startswith("http:") or
        addr.startswith("https:")
    ):
        return addr.rstrip("/")
    else:
        return addr



def uidFromCalendarUserAddress(address):
    """
    Try to extract a record UID from a calendar user address of the appropriate format.
    Allowed formats are urn:x-uid, urn:uuid, or /principals/(__uids__).

    @param address: calendar user address to operate on
    @type address: L{str}

    @return: the extracted uid or L{None}
    @rtype: L{str} or L{None}
    """

    address = normalizeCUAddr(address)

    if address.startswith("urn:x-uid:"):
        return address[10:]

    elif address.startswith("urn:uuid:"):
        try:
            UUID(address[9:])
        except ValueError:
            log.info("Invalid GUID: {guid}", guid=address[9:])
            return address[9:]
        else:
            return address[9:]

    elif address.startswith("/principals/__uids__"):
        parts = address.split("/")
        if len(parts) == 4:
            return parts[3]

    return None



def extractEmailDomain(mailtoURI):
    try:
        addr = mailtoURI[7:].split("?")[0]
        _ignore_account, addrDomain = addr.split("@")
    except ValueError:
        addrDomain = ""
    return addrDomain
