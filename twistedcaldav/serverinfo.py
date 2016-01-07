##
# Copyright (c) 2015-2016 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, succeed, returnValue
from twistedcaldav import caldavxml, carddavxml, mkcolxml
from twistedcaldav import customxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.customxml import calendarserver_namespace
from txdav.xml import element as davxml
from txdav.xml.element import dav_namespace, WebDAVUnknownElement
from txweb2.dav.noneprops import NonePropertyStore
from txweb2.http_headers import MimeType, ETag
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn
from twistedcaldav.extensions import DAVResource, \
    DAVResourceWithoutChildrenMixin
from txweb2.http import XMLResponse
from twistedcaldav.config import config
from txweb2 import responsecode
import hashlib
from twistedcaldav.serverinfoxml import Class1_Feature, AccessControl_Feature, \
    Quota_Feature, SyncCollection_Feature, AddMember_Feature, Name_Service, \
    Features, ServerInfo, Token, Applications, Application

"""
draft-douglass-server-info: "DAV Server Information Object"
"""

def buildServerInfo(config):
    """
    Build the DAV compliance header, server-info document, and server-info-token value
    based on the supplied L{config}.

    @param config: config to use
    @type config: L{twistedcaldav.config}

    @return: tuple of three items: compliance value, server-info XML document root
        element, server-info-token value
    @rtype: L{tuple}
    """
    global_features = [
        Class1_Feature(),
        AccessControl_Feature(),
        Quota_Feature(),
        SyncCollection_Feature(),
        AddMember_Feature(),
    ]
    compliance = ()
    applications = []
    if config.EnableCalDAV:
        if config.Scheduling.CalDAV.OldDraftCompatibility:
            compliance = caldavxml.caldav_full_compliance
        else:
            compliance = caldavxml.caldav_implicit_compliance
        features = [
            WebDAVUnknownElement.withName(caldav_namespace, "calendar-access"),
            WebDAVUnknownElement.withName(caldav_namespace, "calendar-auto-schedule"),
            WebDAVUnknownElement.withName(calendarserver_namespace, "calendar-availability"),
            WebDAVUnknownElement.withName(calendarserver_namespace, "inbox-availability"),
        ]

        if config.EnableProxyPrincipals:
            compliance += customxml.calendarserver_proxy_compliance
            features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_proxy_compliance[0]))

        if config.EnablePrivateEvents:
            compliance += customxml.calendarserver_private_events_compliance
            features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_private_events_compliance[0]))

        if config.Scheduling.CalDAV.EnablePrivateComments:
            compliance += customxml.calendarserver_private_comments_compliance
            features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_private_comments_compliance[0]))

        if config.Sharing.Enabled:
            compliance += customxml.calendarserver_sharing_compliance
            # TODO: This is only needed whilst we do not support scheduling in shared calendars
            compliance += customxml.calendarserver_sharing_no_scheduling_compliance
            if config.Sharing.Calendars.Enabled and config.Sharing.Calendars.Groups.Enabled:
                compliance += customxml.calendarserver_group_sharee_compliance

            sharing = WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_sharing_compliance[0])
            # TODO: This is only needed whilst we do not support scheduling in shared calendars
            sharing.children += (WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_sharing_no_scheduling_compliance[0]),)
            if config.Sharing.Calendars.Enabled and config.Sharing.Calendars.Groups.Enabled:
                sharing.children += (WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_group_sharee_compliance[0]),)
            features.append(sharing)

        if config.EnableCalendarQueryExtended:
            compliance += caldavxml.caldav_query_extended_compliance
            features.append(WebDAVUnknownElement.withName(caldav_namespace, caldavxml.caldav_query_extended_compliance[0]))

        if config.EnableDefaultAlarms:
            compliance += caldavxml.caldav_default_alarms_compliance
            features.append(WebDAVUnknownElement.withName(caldav_namespace, caldavxml.caldav_default_alarms_compliance[0]))

        if config.EnableManagedAttachments:
            compliance += caldavxml.caldav_managed_attachments_compliance
            features.append(WebDAVUnknownElement.withName(caldav_namespace, caldavxml.caldav_managed_attachments_compliance[0]))

        if config.Scheduling.Options.TimestampAttendeePartStatChanges:
            compliance += customxml.calendarserver_partstat_changes_compliance
            features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_partstat_changes_compliance[0]))

        if config.GroupAttendees.Enabled:
            compliance += customxml.calendarserver_group_attendee_compliance
            features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_group_attendee_compliance[0]))

        if config.EnableTimezonesByReference:
            compliance += caldavxml.caldav_timezones_by_reference_compliance
            features.append(WebDAVUnknownElement.withName(caldav_namespace, caldavxml.caldav_timezones_by_reference_compliance[0]))

        compliance += customxml.calendarserver_recurrence_split
        features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_recurrence_split[0]))

        applications.append(
            Application(
                Name_Service.fromString("caldav"),
                Features(*features),
            )
        )

    if config.EnableCardDAV:
        compliance += carddavxml.carddav_compliance
        features = [
            WebDAVUnknownElement.withName(carddav_namespace, "addressbook"),
        ]

        applications.append(
            Application(
                Name_Service.fromString("carddav"),
                Features(*features),
            )
        )

    if config.EnableCardDAV:
        compliance += carddavxml.carddav_compliance

    if config.EnableCalDAV or config.EnableCardDAV:
        compliance += mkcolxml.mkcol_compliance
        global_features.append(WebDAVUnknownElement.withName(dav_namespace, mkcolxml.mkcol_compliance[0]))

    # Principal property search is always enabled
    compliance += customxml.calendarserver_principal_property_search_compliance
    global_features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_principal_property_search_compliance[0]))

    compliance += customxml.calendarserver_principal_search_compliance
    global_features.append(WebDAVUnknownElement.withName(calendarserver_namespace, customxml.calendarserver_principal_search_compliance[0]))

    # Home Depth:1 sync report will include WebDAV property changes on home child resources
    compliance += customxml.calendarserver_home_sync_compliance

    def _createServerInfo(token):
        return ServerInfo(
            Token.fromString(token),
            Features(*global_features),
            Applications(*applications)
        )

    token = hashlib.md5(_createServerInfo("").toxml()).hexdigest()

    return compliance, _createServerInfo(token), token



class ServerInfoResource (ReadOnlyNoCopyResourceMixIn, DAVResourceWithoutChildrenMixin, DAVResource):
    """
    Server-info resource.

    Extends L{DAVResource} to allow server-info document retrieval.
    """

    def __init__(self, parent):
        """
        @param parent: the parent resource of this one.
        """
        assert parent is not None

        DAVResource.__init__(self, principalCollections=parent.principalCollections())

        self.parent = parent


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(ETag(config.ServerInfoToken))


    def checkPreconditions(self, request):
        return None


    def checkPrivileges(self, request, privileges, recurse=False, principal=None, inherited_aces=None):
        return succeed(None)


    def defaultAccessControlList(self):
        return succeed(
            davxml.ACL(
                # DAV:Read for all principals (includes anonymous)
                davxml.ACE(
                    davxml.Principal(davxml.All()),
                    davxml.Grant(
                        davxml.Privilege(davxml.Read()),
                    ),
                    davxml.Protected(),
                ),
            )
        )


    def contentType(self):
        return MimeType.fromString("text/xml; charset=utf-8")


    def resourceType(self):
        return None


    def isCollection(self):
        return False


    def isCalendarCollection(self):
        return False


    def isPseudoCalendarCollection(self):
        return False


    @inlineCallbacks
    def http_GET(self, request):
        """
        The server-info GET method.
        """

        yield self.authorize(request, (davxml.Read(),))

        returnValue(XMLResponse(responsecode.OK, config.ServerInfo))
