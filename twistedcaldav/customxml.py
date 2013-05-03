##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
Custom CalDAV XML Support.

This module provides custom XML utilities for use with CalDAV.

This API is considered private to static.py and is therefore subject to
change.
"""

from txdav.xml.element import registerElement, dav_namespace
from txdav.xml.element import twisted_dav_namespace, twisted_private_namespace
from txdav.xml.element import WebDAVElement, PCDATAElement
from txdav.xml.element import WebDAVEmptyElement, WebDAVTextElement
from txdav.xml.element import PrincipalPropertySearch, Match
from txdav.xml.element import ResourceType, Collection, Principal

from twistedcaldav import caldavxml, carddavxml
from twistedcaldav.caldavxml import caldav_namespace
from twistedcaldav.ical import Component as iComponent

from pycalendar.datetime import PyCalendarDateTime


calendarserver_namespace = "http://calendarserver.org/ns/"

calendarserver_proxy_compliance = (
    "calendar-proxy",
)

calendarserver_private_events_compliance = (
    "calendarserver-private-events",
)

calendarserver_private_comments_compliance = (
    "calendarserver-private-comments",
)

calendarserver_principal_property_search_compliance = (
    "calendarserver-principal-property-search",
)

calendarserver_principal_search_compliance = (
    "calendarserver-principal-search",
)

calendarserver_sharing_compliance = (
    "calendarserver-sharing",
)

# TODO: This is only needed whilst we do not support scheduling in shared calendars
calendarserver_sharing_no_scheduling_compliance = (
    "calendarserver-sharing-no-scheduling",
)

calendarserver_partstat_changes_compliance = (
    "calendarserver-partstat-changes",
)


@registerElement
class TwistedCalendarSupportedComponents (WebDAVTextElement):
    """
    Contains the calendar supported components list.
    """
    namespace = twisted_dav_namespace
    name = "calendar-supported-components"
    hidden = True

    def getValue(self):
        return str(self)



@registerElement
class TwistedCalendarAccessProperty (WebDAVTextElement):
    """
    Contains the calendar access level (private events) for the resource.
    """
    namespace = twisted_dav_namespace
    name = "calendar-access"
    hidden = True

    def getValue(self):
        return str(self)



@registerElement
class TwistedSchedulingObjectResource (WebDAVTextElement):
    """
    Indicates that the resource is a scheduling object resource.
    """
    namespace = twisted_private_namespace
    name = "scheduling-object-resource"
    hidden = True



@registerElement
class TwistedScheduleMatchETags(WebDAVElement):
    """
    List of ETags that can be used for a "weak" If-Match comparison.
    """
    namespace = twisted_private_namespace
    name = "scheduling-match-etags"
    hidden = True

    allowed_children = {(dav_namespace, "getetag"): (0, None)}



@registerElement
class TwistedCalendarHasPrivateCommentsProperty (WebDAVEmptyElement):
    """
    Indicates that a calendar resource has private comments.

    NB This MUST be a private property as we don't want to expose the presence of private comments
    in private events.

    """
    namespace = twisted_private_namespace
    name = "calendar-has-private-comments"
    hidden = True



@registerElement
class CalendarProxyRead (WebDAVEmptyElement):
    """
    A read-only calendar user proxy principal resource.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "calendar-proxy-read"



@registerElement
class CalendarProxyWrite (WebDAVEmptyElement):
    """
    A read-write calendar user proxy principal resource.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "calendar-proxy-write"



@registerElement
class CalendarProxyReadFor (WebDAVElement):
    """
    List of principals granting read-only proxy status.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "calendar-proxy-read-for"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



@registerElement
class CalendarProxyWriteFor (WebDAVElement):
    """
    List of principals granting read-write proxy status.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "calendar-proxy-write-for"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



@registerElement
class DropBoxHome (WebDAVEmptyElement):
    """
    Denotes a drop box home collection (a collection that will contain drop boxes).
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "dropbox-home"



@registerElement
class DropBox (WebDAVEmptyElement):
    """
    Denotes a drop box collection.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "dropbox"



@registerElement
class DropBoxHomeURL (WebDAVElement):
    """
    A principal property to indicate the location of the drop box home.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "dropbox-home-URL"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, 1)}



@registerElement
class GETCTag (WebDAVTextElement):
    """
    Contains the calendar collection entity tag.
    """
    namespace = calendarserver_namespace
    name = "getctag"
    protected = True



@registerElement
class CalendarAvailability (WebDAVTextElement):
    """
    Contains the calendar availability property.
    """
    namespace = calendarserver_namespace
    name = "calendar-availability"
    hidden = True


    def calendar(self):
        """
        Returns a calendar component derived from this element.
        """
        return iComponent.fromString(str(self))


    def valid(self):
        """
        Determine whether the content of this element is a valid single VAVAILABILITY component,
        with zero or more VTIEMZONE components.

        @return: True if valid, False if not.
        """

        try:
            calendar = self.calendar()
            if calendar is None:
                return False
        except ValueError:
            return False

        found = False
        for subcomponent in calendar.subcomponents():
            if subcomponent.name() == "VAVAILABILITY":
                if found:
                    return False
                else:
                    found = True
            elif subcomponent.name() == "VTIMEZONE":
                continue
            else:
                return False

        return found



@registerElement
class MaxCollections (WebDAVTextElement):
    """
    Maximum number of child collections in a home collection
    """
    namespace = calendarserver_namespace
    name = "max-collections"
    hidden = True
    protected = True



@registerElement
class MaxResources (WebDAVTextElement):
    """
    Maximum number of child resources in a collection
    """
    namespace = calendarserver_namespace
    name = "max-resources"
    hidden = True
    protected = True



@registerElement
class Timezones (WebDAVEmptyElement):
    """
    Denotes a timezone service resource.
    (Apple Extension to CalDAV)
    """
    namespace = calendarserver_namespace
    name = "timezones"



@registerElement
class TZIDs (WebDAVElement):
    """
    Wraps a list of timezone ids.
    """
    namespace = calendarserver_namespace
    name = "tzids"
    allowed_children = {(calendarserver_namespace, "tzid"): (0, None)}



@registerElement
class TZID (WebDAVTextElement):
    """
    A timezone id.
    """
    namespace = calendarserver_namespace
    name = "tzid"



@registerElement
class TZData (WebDAVElement):
    """
    Wraps a list of timezone observances.
    """
    namespace = calendarserver_namespace
    name = "tzdata"
    allowed_children = {(calendarserver_namespace, "observance"): (0, None)}



@registerElement
class Observance (WebDAVElement):
    """
    A timezone observance.
    """
    namespace = calendarserver_namespace
    name = "observance"
    allowed_children = {
        (calendarserver_namespace, "onset")     : (1, 1),
        (calendarserver_namespace, "utc-offset"): (1, 1),
    }



@registerElement
class Onset (WebDAVTextElement):
    """
    The onset date-time for a DST transition.
    """
    namespace = calendarserver_namespace
    name = "onset"



@registerElement
class UTCOffset (WebDAVTextElement):
    """
    A UTC offset value for a timezone observance.
    """
    namespace = calendarserver_namespace
    name = "utc-offset"



@registerElement
class PubSubPushTransportsProperty (WebDAVTextElement):
    """
    A calendar property describing the available push notification transports
    available.
    """
    namespace = calendarserver_namespace
    name = "push-transports"
    protected = True
    hidden = True
    allowed_children = {
        (calendarserver_namespace, "transport") : (0, 1),
    }



@registerElement
class PubSubTransportProperty (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "transport"
    protected = True
    hidden = True
    allowed_attributes = {
        "type" : True,
    }
    allowed_children = {
        (calendarserver_namespace, "subscription-url") : (1, 1),
        (calendarserver_namespace, "apsbundleid") : (1, 1),
        (calendarserver_namespace, "env") : (1, 1),
    }



@registerElement
class PubSubSubscriptionProperty (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "subscription-url"
    protected = True
    hidden = True
    allowed_children = {(dav_namespace, "href"): (0, 1)}



@registerElement
class PubSubAPSBundleIDProperty (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "apsbundleid"
    protected = True
    hidden = True



@registerElement
class PubSubAPSEnvironmentProperty (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "env"
    protected = True
    hidden = True



@registerElement
class PubSubAPSRefreshIntervalProperty (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "refresh-interval"
    protected = True
    hidden = True



@registerElement
class PubSubXMPPPushKeyProperty (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "pushkey"
    protected = True
    hidden = True



PrincipalPropertySearch.allowed_children[(calendarserver_namespace, "limit")] = (0, 1)
PrincipalPropertySearch.allowed_attributes["type"] = False
Match.allowed_attributes = {
    "caseless": False,
    "match-type": False,
}


@registerElement
class Limit (WebDAVElement):
    """
    Client supplied limit for reports.
    """
    namespace = calendarserver_namespace
    name = "limit"
    allowed_children = {
        (calendarserver_namespace, "nresults")  : (1, 1),
    }



@registerElement
class NResults (WebDAVTextElement):
    """
    Number of results limit.
    """
    namespace = calendarserver_namespace
    name = "nresults"



@registerElement
class FirstNameProperty (WebDAVTextElement):
    """
    A property representing first name of a principal
    """
    namespace = calendarserver_namespace
    name = "first-name"
    protected = True
    hidden = True



@registerElement
class LastNameProperty (WebDAVTextElement):
    """
    A property representing last name of a principal
    """
    namespace = calendarserver_namespace
    name = "last-name"
    protected = True
    hidden = True



@registerElement
class EmailAddressProperty (WebDAVTextElement):
    """
    A property representing email address of a principal
    """
    namespace = calendarserver_namespace
    name = "email-address"
    protected = True
    hidden = True



@registerElement
class EmailAddressSet (WebDAVElement):
    """
    The list of email addresses of a principal
    """
    namespace = calendarserver_namespace
    name = "email-address-set"
    hidden = True

    allowed_children = {(calendarserver_namespace, "email-address"): (0, None)}



@registerElement
class ExpandedGroupMemberSet (WebDAVElement):
    """
    The expanded list of members of a (group) principal
    """
    namespace = calendarserver_namespace
    name = "expanded-group-member-set"
    protected = True
    hidden = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



@registerElement
class ExpandedGroupMembership (WebDAVElement):
    """
    The expanded list of groups a principal is a member of
    """
    namespace = calendarserver_namespace
    name = "expanded-group-membership"
    protected = True
    hidden = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



@registerElement
class IScheduleInbox (WebDAVEmptyElement):
    """
    Denotes the resourcetype of a iSchedule Inbox.
    (CalDAV-s2s-xx, section x.x.x)
    """
    namespace = calendarserver_namespace
    name = "ischedule-inbox"



@registerElement
class FreeBusyURL (WebDAVEmptyElement):
    """
    Denotes the resourcetype of a free-busy URL resource.
    (CalDAV-s2s-xx, section x.x.x)
    """
    namespace = calendarserver_namespace
    name = "free-busy-url"



@registerElement
class ScheduleChanges (WebDAVElement):
    """
    Change indicator for a scheduling message.
    """
    namespace = calendarserver_namespace
    name = "schedule-changes"
    protected = True
    hidden = True
    allowed_children = {
        (calendarserver_namespace, "dtstamp")     : (0, 1), # Have to allow 0 as element is empty in PROPFIND requests
        (calendarserver_namespace, "action")      : (0, 1), # Have to allow 0 as element is empty in PROPFIND requests
    }



@registerElement
class ScheduleDefaultTasksURL (WebDAVElement):
    """
    A single href indicating which calendar is the default for VTODO scheduling.
    """
    namespace = calendarserver_namespace
    name = "schedule-default-tasks-URL"

    allowed_children = {(dav_namespace, "href"): (0, 1)}



@registerElement
class DTStamp (WebDAVTextElement):
    """
    A UTC timestamp in iCal format.
    """
    namespace = calendarserver_namespace
    name = "dtstamp"

    def __init__(self, *children):
        super(DTStamp, self).__init__(children)
        self.children = (PCDATAElement(PyCalendarDateTime.getNowUTC().getText()),)



@registerElement
class Action (WebDAVElement):
    """
    A UTC timestamp in iCal format.
    """
    namespace = calendarserver_namespace
    name = "action"
    allowed_children = {
        (calendarserver_namespace, "create") : (0, 1),
        (calendarserver_namespace, "update") : (0, 1),
        (calendarserver_namespace, "cancel") : (0, 1),
        (calendarserver_namespace, "reply")  : (0, 1),
    }



@registerElement
class Create (WebDAVEmptyElement):
    """
    Event created.
    """
    namespace = calendarserver_namespace
    name = "create"



@registerElement
class Update (WebDAVElement):
    """
    Event updated.
    """
    namespace = calendarserver_namespace
    name = "update"
    allowed_children = {
        (calendarserver_namespace, "recurrence") : (1, None),
    }



@registerElement
class Cancel (WebDAVElement):
    """
    Event cancelled.
    """
    namespace = calendarserver_namespace
    name = "cancel"
    allowed_children = {
        (calendarserver_namespace, "recurrence") : (0, 1),
    }



@registerElement
class Reply (WebDAVElement):
    """
    Event replied to.
    """
    namespace = calendarserver_namespace
    name = "reply"
    allowed_children = {
        (calendarserver_namespace, "attendee")        : (1, 1),
        (calendarserver_namespace, "recurrence")      : (1, None),
    }



@registerElement
class Recurrence (WebDAVElement):
    """
    Changes to an event.
    """
    namespace = calendarserver_namespace
    name = "recurrence"
    allowed_children = {
        (calendarserver_namespace, "master")       : (0, 1),
        (calendarserver_namespace, "recurrenceid") : (0, None),
        (calendarserver_namespace, "changes")      : (0, 1),
    }



@registerElement
class Master (WebDAVEmptyElement):
    """
    Master instance changed.
    """
    namespace = calendarserver_namespace
    name = "master"



@registerElement
class RecurrenceID (WebDAVTextElement):
    """
    A recurrence instance changed.
    """
    namespace = calendarserver_namespace
    name = "recurrenceid"



@registerElement
class Changes (WebDAVElement):
    """
    Changes to an event.
    """
    namespace = calendarserver_namespace
    name = "changes"
    allowed_children = {
        (calendarserver_namespace, "changed-property")  : (0, None),
    }



@registerElement
class ChangedProperty (WebDAVElement):
    """
    Changes to a property.
    """
    namespace = calendarserver_namespace
    name = "changed-property"

    allowed_children = {
        (calendarserver_namespace, "changed-parameter")  : (0, None),
    }

    allowed_attributes = {
        "name" : True,
    }



@registerElement
class ChangedParameter (WebDAVEmptyElement):
    """
    Changes to a parameter.
    """
    namespace = calendarserver_namespace
    name = "changed-parameter"

    allowed_attributes = {
        "name" : True,
    }



@registerElement
class Attendee (WebDAVTextElement):
    """
    An attendee calendar user address.
    """
    namespace = calendarserver_namespace
    name = "attendee"



@registerElement
class RecordType (WebDAVTextElement):
    """
    Exposes the type of a record
    """
    namespace = calendarserver_namespace
    name = "record-type"
    protected = True
    hidden = True



@registerElement
class AutoSchedule (WebDAVTextElement):
    """
    Whether the principal automatically accepts invitations
    """
    namespace = calendarserver_namespace
    name = "auto-schedule"



@registerElement
class AutoScheduleMode (WebDAVTextElement):
    """
    The principal's auto-schedule mode
    """
    namespace = calendarserver_namespace
    name = "auto-schedule-mode"



##
# Sharing
##

@registerElement
class ReadAccess (WebDAVEmptyElement):
    """
    Denotes read and update attendee partstat on a shared calendar.
    """
    namespace = calendarserver_namespace
    name = "read"



@registerElement
class ReadWriteAccess (WebDAVEmptyElement):
    """
    Denotes read and write access on a shared calendar.
    """
    namespace = calendarserver_namespace
    name = "read-write"



@registerElement
class UID (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "uid"



@registerElement
class InReplyTo (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "in-reply-to"



@registerElement
class SharedOwner (WebDAVEmptyElement):
    """
    Denotes a shared collection.
    """
    namespace = calendarserver_namespace
    name = "shared-owner"



@registerElement
class Shared (WebDAVEmptyElement):
    """
    Denotes a shared collection.
    """
    namespace = calendarserver_namespace
    name = "shared"



@registerElement
class Subscribed (WebDAVEmptyElement):
    """
    Denotes a subscribed calendar collection.
    """
    namespace = calendarserver_namespace
    name = "subscribed"



@registerElement
class SharedURL (WebDAVTextElement):
    """
    The source url for a shared calendar.
    """
    namespace = calendarserver_namespace
    name = "shared-url"
    protected = True
    hidden = True



@registerElement
class SharedAs (WebDAVElement):
    """
    The url for a shared calendar.
    """
    namespace = calendarserver_namespace
    name = "shared-as"

    allowed_children = {
        (dav_namespace, "href")    : (1, 1),
    }



@registerElement
class SharedAcceptEmailNotification (WebDAVTextElement):
    """
    The accept email flag for a shared calendar.
    """
    namespace = calendarserver_namespace
    name = "shared-accept-email-notification"



@registerElement
class Birthday (WebDAVEmptyElement):
    """
    Denotes a birthday calendar collection.
    """
    namespace = calendarserver_namespace
    name = "birthday"



@registerElement
class AllowedSharingModes (WebDAVElement):
    namespace = calendarserver_namespace
    name = "allowed-sharing-modes"
    protected = True
    hidden = True

    allowed_children = {
        (calendarserver_namespace, "can-be-shared")    : (0, 1),
        (calendarserver_namespace, "can-be-published") : (0, 1),
    }



@registerElement
class CanBeShared (WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "can-be-shared"



@registerElement
class CanBePublished (WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "can-be-published"



@registerElement
class InviteShare (WebDAVElement):
    namespace = calendarserver_namespace
    name = "share"

    allowed_children = {
        (calendarserver_namespace, "set")    : (0, None),
        (calendarserver_namespace, "remove") : (0, None),
    }



@registerElement
class InviteSet (WebDAVElement):
    namespace = calendarserver_namespace
    name = "set"

    allowed_children = {
        (dav_namespace, "href")                           : (1, 1),
        (calendarserver_namespace, "common-name")         : (0, 1),
        (calendarserver_namespace, "summary")             : (0, 1),
        (calendarserver_namespace, "read")                : (0, 1),
        (calendarserver_namespace, "read-write")          : (0, 1),
        (calendarserver_namespace, "read-write-schedule") : (0, 1),
    }



@registerElement
class InviteRemove (WebDAVElement):
    namespace = calendarserver_namespace
    name = "remove"

    allowed_children = {
        (dav_namespace, "href")                           : (1, 1),
        (calendarserver_namespace, "read")                : (0, 1),
        (calendarserver_namespace, "read-write")          : (0, 1),
        (calendarserver_namespace, "read-write-schedule") : (0, 1),
    }



@registerElement
class InviteUser (WebDAVElement):
    namespace = calendarserver_namespace
    name = "user"

    allowed_children = {
        (calendarserver_namespace, "uid")               : (0, 1),
        (dav_namespace, "href")                         : (1, 1),
        (calendarserver_namespace, "common-name")       : (0, 1),
        (calendarserver_namespace, "invite-noresponse") : (0, 1),
        (calendarserver_namespace, "invite-deleted")    : (0, 1),
        (calendarserver_namespace, "invite-accepted")   : (0, 1),
        (calendarserver_namespace, "invite-declined")   : (0, 1),
        (calendarserver_namespace, "invite-invalid")    : (0, 1),
        (calendarserver_namespace, "access")            : (1, 1),
        (calendarserver_namespace, "summary")           : (0, 1),
    }



@registerElement
class InviteAccess (WebDAVElement):
    namespace = calendarserver_namespace
    name = "access"

    allowed_children = {
        (calendarserver_namespace, "read")                : (0, 1),
        (calendarserver_namespace, "read-write")          : (0, 1),
        (calendarserver_namespace, "read-write-schedule") : (0, 1),
    }



@registerElement
class Invite (WebDAVElement):
    namespace = calendarserver_namespace
    name = "invite"

    allowed_children = {
        (calendarserver_namespace, "organizer") : (0, 1),
        (calendarserver_namespace, "user")      : (0, None),
    }



@registerElement
class InviteSummary (WebDAVTextElement):
    namespace = calendarserver_namespace
    name = "summary"



@registerElement
class InviteStatusNoResponse (WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "invite-noresponse"



@registerElement
class InviteStatusDeleted (WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "invite-deleted"



@registerElement
class InviteStatusAccepted (WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "invite-accepted"



@registerElement
class InviteStatusDeclined (WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "invite-declined"



@registerElement
class InviteStatusInvalid (WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "invite-invalid"



@registerElement
class HostURL (WebDAVElement):
    """
    The source for a shared calendar
    """
    namespace = calendarserver_namespace
    name = "hosturl"

    allowed_children = {
        (dav_namespace, "href") : (0, None)
    }



@registerElement
class Organizer (WebDAVElement):
    """
    The organizer for a shared calendar
    """
    namespace = calendarserver_namespace
    name = "organizer"

    allowed_children = {
        (dav_namespace, "href") : (0, None),
        (calendarserver_namespace, "common-name")  : (0, 1)
    }



@registerElement
class CommonName (WebDAVTextElement):
    """
    Common name for Sharer or Sharee
    """
    namespace = calendarserver_namespace
    name = "common-name"



@registerElement
class InviteNotification (WebDAVElement):
    namespace = calendarserver_namespace
    name = "invite-notification"

    allowed_children = {
        (calendarserver_namespace, "uid")               : (0, 1),
        (dav_namespace, "href")                         : (0, 1),
        (calendarserver_namespace, "invite-noresponse") : (0, 1),
        (calendarserver_namespace, "invite-deleted")    : (0, 1),
        (calendarserver_namespace, "invite-accepted")   : (0, 1),
        (calendarserver_namespace, "invite-declined")   : (0, 1),
        (calendarserver_namespace, "access")            : (0, 1),
        (calendarserver_namespace, "hosturl")           : (0, 1),
        (calendarserver_namespace, "organizer")         : (0, 1),
        (calendarserver_namespace, "summary")           : (0, 1),
        (caldav_namespace, "supported-calendar-component-set") : (0, 1),
    }

    allowed_attributes = {
        "shared-type" : True,
    }



@registerElement
class InviteReply (WebDAVElement):
    namespace = calendarserver_namespace
    name = "invite-reply"

    allowed_children = {
        (dav_namespace, "href")                       : (0, 1),
        (calendarserver_namespace, "common-name")     : (0, 1),
        (calendarserver_namespace, "first-name")      : (0, 1),
        (calendarserver_namespace, "last-name")       : (0, 1),
        (calendarserver_namespace, "invite-accepted") : (0, 1),
        (calendarserver_namespace, "invite-declined") : (0, 1),
        (calendarserver_namespace, "hosturl")         : (0, 1),
        (calendarserver_namespace, "in-reply-to")     : (0, 1),
        (calendarserver_namespace, "summary")         : (0, 1),
    }



@registerElement
class ResourceUpdateNotification (WebDAVElement):
    namespace = calendarserver_namespace
    name = "resource-update-notification"

    allowed_children = {
        (dav_namespace, "href")                                     : (0, 1),
        (calendarserver_namespace, "uid")                           : (0, 1),
        (calendarserver_namespace, "resource-added-notification")   : (0, 1),
        (calendarserver_namespace, "resource-updated-notification") : (0, 1),
        (calendarserver_namespace, "resource-deleted-notification") : (0, 1),
    }



@registerElement
class ResourceUpdateAdded(WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "resource-added-notification"



@registerElement
class ResourceUpdateUpdated(WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "resource-updated-notification"



@registerElement
class ResourceUpdateDeleted(WebDAVEmptyElement):
    namespace = calendarserver_namespace
    name = "resource-deleted-notification"



@registerElement
class SharedCalendarUpdateNotification (WebDAVElement):
    namespace = calendarserver_namespace
    name = "shared-update-notification"

    allowed_children = {
        (calendarserver_namespace, "hosturl")           : (0, 1), # The shared calendar url
        (dav_namespace, "href")                         : (0, 1), # Email userid that was invited
        (calendarserver_namespace, "invite-deleted")    : (0, 1), # What the user did...
        (calendarserver_namespace, "invite-accepted")   : (0, 1),
        (calendarserver_namespace, "invite-declined")   : (0, 1),
    }



##
# Notifications
##

@registerElement
class Notification (WebDAVElement):
    """
    Denotes a notification collection, or a notification message.
    """
    namespace = calendarserver_namespace
    name = "notification"

    allowed_children = {
        (calendarserver_namespace, "dtstamp")                       : (0, None),
        (calendarserver_namespace, "invite-notification")           : (0, None),
        (calendarserver_namespace, "invite-reply")                  : (0, None),
        (calendarserver_namespace, "resource-update-notification")  : (0, None),
        (calendarserver_namespace, "shared-update-notification")    : (0, None),
    }



@registerElement
class NotificationURL (WebDAVElement):
    """
    A principal property to indicate the notification collection for the principal.
    """
    namespace = calendarserver_namespace
    name = "notification-URL"
    hidden = True
    protected = True

    allowed_children = {
        (dav_namespace, "href") : (0, 1)
    }



@registerElement
class NotificationType (WebDAVElement):
    """
    A property to indicate what type of notification the resource represents.
    """
    namespace = calendarserver_namespace
    name = "notificationtype"
    hidden = True
    protected = True

    allowed_children = {
        (calendarserver_namespace, "invite-notification")   : (0, None),
        (calendarserver_namespace, "invite-reply")          : (0, None),
    }



@registerElement
class Link (WebDAVEmptyElement):
    """
    Denotes a linked resource.
    """
    namespace = calendarserver_namespace
    name = "link"


mm_namespace = "http://me.com/_namespace/"

@registerElement
class Multiput (WebDAVElement):
    namespace = mm_namespace
    name = "multiput"

    allowed_children = {
        (mm_namespace, "resource")   : (1, None),
    }



@registerElement
class Resource (WebDAVElement):
    namespace = mm_namespace
    name = "resource"

    allowed_children = {
        (dav_namespace, "href")     : (0, 1),
        (mm_namespace, "if-match") : (0, 1),
        (dav_namespace, "set")      : (0, 1),
        (dav_namespace, "remove")   : (0, 1),
        (mm_namespace, "delete")   : (0, 1),
    }



@registerElement
class IfMatch (WebDAVElement):
    namespace = mm_namespace
    name = "if-match"

    allowed_children = {
        (dav_namespace, "getetag")   : (1, 1),
    }



@registerElement
class Delete (WebDAVEmptyElement):
    namespace = mm_namespace
    name = "delete"



@registerElement
class BulkRequests (WebDAVElement):
    namespace = mm_namespace
    name = "bulk-requests"
    hidden = True
    protected = True

    allowed_children = {
        (mm_namespace, "simple")   : (0, 1),
        (mm_namespace, "crud")     : (0, 1),
    }



@registerElement
class Simple (WebDAVElement):
    namespace = mm_namespace
    name = "simple"
    hidden = True
    protected = True

    allowed_children = {
        (mm_namespace, "max-resources")   : (1, 1),
        (mm_namespace, "max-bytes")       : (1, 1),
    }



@registerElement
class CRUD (WebDAVElement):
    namespace = mm_namespace
    name = "crud"
    hidden = True
    protected = True

    allowed_children = {
        (mm_namespace, "max-resources")   : (1, 1),
        (mm_namespace, "max-bytes")       : (1, 1),
    }



@registerElement
class MaxBulkResources (WebDAVTextElement):
    namespace = mm_namespace
    name = "max-resources"



@registerElement
class MaxBulkBytes (WebDAVTextElement):
    namespace = mm_namespace
    name = "max-bytes"



#
# Client properties we might care about
#

@registerElement
class CalendarColor(WebDAVTextElement):
    namespace = "http://apple.com/ns/ical/"
    name = "calendar-color"



#
# calendarserver-principal-search REPORT
#

@registerElement
class CalendarServerPrincipalSearchToken (WebDAVTextElement):
    """
    Contains a search token.
    """
    namespace = calendarserver_namespace
    name = "search-token"



@registerElement
class CalendarServerPrincipalSearch (WebDAVElement):

    namespace = calendarserver_namespace
    name = "calendarserver-principal-search"

    allowed_children = {
        (calendarserver_namespace, "search-token"): (0, None),
        (calendarserver_namespace, "limit"): (0, 1),
        (dav_namespace, "prop"): (0, 1),
        (dav_namespace, "apply-to-principal-collection-set"): (0, 1),
    }
    allowed_attributes = {"context": False}

##
# Extensions to ResourceType
##

ResourceType.dropboxhome = ResourceType(Collection(), DropBoxHome())
ResourceType.dropbox = ResourceType(Collection(), DropBox())

ResourceType.calendarproxyread = ResourceType(Principal(), Collection(), CalendarProxyRead())
ResourceType.calendarproxywrite = ResourceType(Principal(), Collection(), CalendarProxyWrite())

ResourceType.timezones = ResourceType(Timezones())

ResourceType.ischeduleinbox = ResourceType(IScheduleInbox())

ResourceType.freebusyurl = ResourceType(FreeBusyURL())

ResourceType.notification = ResourceType(Collection(), Notification())

ResourceType.sharedownercalendar = ResourceType(Collection(), caldavxml.Calendar(), SharedOwner())
ResourceType.sharedcalendar = ResourceType(Collection(), caldavxml.Calendar(), Shared())
ResourceType.sharedowneraddressbook = ResourceType(Collection(), carddavxml.AddressBook(), SharedOwner())
ResourceType.sharedaddressbook = ResourceType(Collection(), carddavxml.AddressBook(), Shared())

ResourceType.link = ResourceType(Link())
