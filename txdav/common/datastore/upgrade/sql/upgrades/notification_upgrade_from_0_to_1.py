# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks

from twistedcaldav import caldavxml, customxml
from twistedcaldav.config import config

from txdav.common.datastore.sql_tables import schema, _BIND_STATUS_INVITED
from txdav.common.datastore.upgrade.sql.upgrades.util import updateNotificationDataVersion, \
    doToEachHomeNotAtVersion
from txdav.xml import element
from txdav.xml.parser import WebDAVDocument
from twistedcaldav.sharing import invitationBindStatusFromXMLMap, \
    invitationBindModeFromXMLMap
import json

"""
Data upgrade from database version 0 to 1
"""

UPGRADE_TO_VERSION = 1

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    Do the required upgrade steps.
    """
    yield updateNotificationHomes(sqlStore, config.UpgradeHomePrefix)

    # Don't do remaining upgrade if we are only process a subset of the homes
    if not config.UpgradeHomePrefix:
        # Always bump the DB value
        yield updateNotificationDataVersion(sqlStore, UPGRADE_TO_VERSION)



@inlineCallbacks
def updateNotificationHomes(sqlStore, prefix=None):
    """
    For each calendar home, update the associated properties on the home or its owned calendars.
    """

    yield doToEachHomeNotAtVersion(sqlStore, schema.NOTIFICATION_HOME, UPGRADE_TO_VERSION, updateNotificationHome, "Update Notification Home", filterOwnerUID=prefix)



@inlineCallbacks
def updateNotificationHome(txn, homeResourceID):
    """
    For this notification home, update the associated child resources.
    """

    home = yield txn.notificationsWithResourceID(homeResourceID)
    notifications = (yield home.notificationObjects())
    for notification in notifications:
        yield updateNotification(txn, notification)



@inlineCallbacks
def updateNotification(txn, notification):
    """
    For this notification home, update the associated child resources.
    """

    # Convert the type value to JSON
    xmltype = WebDAVDocument.fromString(notification._xmlType).root_element
    shared_type = "calendar"
    if xmltype.children[0].qname() == customxml.InviteNotification.qname():
        jsontype = {"notification-type": "invite-notification"}
        if "shared-type" in xmltype.children[0].attributes:
            shared_type = xmltype.children[0].attributes["shared-type"]
        jsontype["shared-type"] = shared_type
    elif xmltype.children[0].qname() == customxml.InviteReply.qname():
        jsontype = {"notification-type": "invite-reply"}

    # Convert the data value to JSON
    xmldata = (yield notification.xmldata())
    xmldata = WebDAVDocument.fromString(xmldata).root_element

    def _extract_UID(uri):
        if uri.startswith("urn:uuid:"):
            return uri[len("urn:uuid:"):]
        elif uri[0] == "/":
            return uri.rstrip("/").split("/")[-1]
        elif uri.startswith("mailto:"):
            return uri[7:].split("@")[0]
        else:
            return ""

    if xmldata.childOfType(customxml.InviteNotification) is not None:
        ntype = xmldata.childOfType(customxml.InviteNotification)
        dtstamp = str(xmldata.childOfType(customxml.DTStamp))
        owner = _extract_UID(str(ntype.childOfType(customxml.Organizer).childOfType(element.HRef)))
        sharee = _extract_UID(str(ntype.childOfType(element.HRef)))
        uid = str(ntype.childOfType(customxml.UID))
        for xml in invitationBindStatusFromXMLMap.keys():
            if ntype.childOfType(xml) is not None:
                state = invitationBindStatusFromXMLMap[xml]
                break
        else:
            state = _BIND_STATUS_INVITED
        mode = invitationBindModeFromXMLMap[type(ntype.childOfType(customxml.InviteAccess).children[0])]
        name = str(ntype.childOfType(customxml.HostURL).childOfType(element.HRef)).rstrip("/").split("/")[-1]
        summary = str(ntype.childOfType(customxml.InviteSummary))

        jsondata = {
            "notification-type": "invite-notification",
            "shared-type": shared_type,
            "dtstamp": dtstamp,
            "owner": owner,
            "sharee": sharee,
            "uid": uid,
            "status": state,
            "access": mode,
            "name": name,
            "summary": summary,
        }
        if ntype.childOfType(caldavxml.SupportedCalendarComponentSet):
            comps = [child.attributes["name"] for child in ntype.childOfType(caldavxml.SupportedCalendarComponentSet).children]
            jsondata["supported-components"] = ",".join(comps)

    elif xmldata.childOfType(customxml.InviteReply) is not None:
        ntype = xmldata.childOfType(customxml.InviteReply)
        dtstamp = str(xmldata.childOfType(customxml.DTStamp))
        sharee = _extract_UID(str(ntype.childOfType(element.HRef)))
        for xml in invitationBindStatusFromXMLMap.keys():
            if ntype.childOfType(xml) is not None:
                state = invitationBindStatusFromXMLMap[xml]
                break
        else:
            state = _BIND_STATUS_INVITED
        name = str(ntype.childOfType(customxml.HostURL).childOfType(element.HRef)).rstrip("/").split("/")[-1]
        inreplyto = str(ntype.childOfType(customxml.InReplyTo))
        summary = str(ntype.childOfType(customxml.InviteSummary)) if ntype.childOfType(customxml.InviteSummary) is not None else ""

        owner = str(ntype.childOfType(customxml.HostURL).childOfType(element.HRef)).rstrip("/").split("/")[-2]

        jsondata = {
            "notification-type": "invite-reply",
            "shared-type": shared_type,
            "dtstamp": dtstamp,
            "owner": owner,
            "sharee": sharee,
            "status": state,
            "name": name,
            "in-reply-to": inreplyto,
            "summary": summary,
        }

    jsontype = json.dumps(jsontype)
    jsondata = json.dumps(jsondata)
    yield notification.setData(notification.uid(), jsontype, jsondata)
