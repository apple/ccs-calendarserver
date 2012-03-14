##
# Copyright (c) 2011-2012 Apple Inc. All rights reserved.
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
Virtual file system for data store objects.
"""

from cStringIO import StringIO

from twisted.python import log
from twisted.internet.defer import succeed
from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.common.icommondatastore import NotFoundError

from twistedcaldav.ical import InvalidICalendarDataError

from calendarserver.tools.tables import Table


class File(object):
    """
    Object in virtual data hierarchy.
    """
    def __init__(self, service, path):
        assert type(path) is tuple

        self.service = service
        self.path    = path

    def __str__(self):
        return "/" + "/".join(self.path)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self)

    def __eq__(self, other):
        if isinstance(other, File):
            return self.path == other.path
        else:
            return NotImplemented

    def describe(self):
        return succeed("%s (%s)" % (self, self.__class__.__name__))

    def list(self):
        return succeed((File, str(self)))


class Folder(File):
    """
    Location in virtual data hierarchy.
    """
    def __init__(self, service, path):
        File.__init__(self, service, path)

        self._children = {}
        self._childClasses = {}

    def __str__(self):
        if self.path:
            return "/" + "/".join(self.path) + "/"
        else:
            return "/"

    @inlineCallbacks
    def locate(self, path):
        if not path:
            returnValue(RootFolder(self.service))

        name = path[0]
        if name:
            target = (yield self.child(name))
            if len(path) > 1:
                target = (yield target.locate(path[1:]))
        else:
            target = (yield RootFolder(self.service).locate(path[1:]))

        returnValue(target)

    @inlineCallbacks
    def child(self, name):
        # FIXME: Move this logic to locate()
        #if not name:
        #    return succeed(self)
        #if name == ".":
        #    return succeed(self)
        #if name == "..":
        #    path = self.path[:-1]
        #    if not path:
        #        path = "/"
        #    return RootFolder(self.service).locate(path)

        if name in self._children:
            returnValue(self._children[name])

        if name in self._childClasses:
            child = (yield self._childClasses[name](self.service, self.path + (name,)))
            self._children[name] = child
            returnValue(child)

        raise NotFoundError("Folder %r has no child %r" % (str(self), name))

    def list(self):
        result = set()
        for name in self._children:
            result.add((self._children[name].__class__, name))
        for name in self._childClasses:
            result.add((self._childClasses[name], name))
        return succeed(result)


class RootFolder(Folder):
    """
    Root of virtual data hierarchy.

    Hierarchy:
      /                    RootFolder
        uids/              UIDsFolder
          <uid>/           PrincipalHomeFolder
            calendars/     CalendarHomeFolder
              <name>/      CalendarFolder
                <uid>      CalendarObject
            addressbooks/  AddressBookHomeFolder
              <name>/      AddressBookFolder
                <uid>      AddressBookObject
        users/             UsersFolder
          <name>/          PrincipalHomeFolder
            ...
        locations/         LocationsFolder
          <name>/          PrincipalHomeFolder
            ...
        resources/         ResourcesFolder
          <name>/          PrincipalHomeFolder
            ...
    """
    def __init__(self, service):
        Folder.__init__(self, service, ())

        self._childClasses["uids"     ] = UIDsFolder
        self._childClasses["users"    ] = UsersFolder
        self._childClasses["locations"] = LocationsFolder
        self._childClasses["resources"] = ResourcesFolder
        self._childClasses["groups"   ] = GroupsFolder


class UIDsFolder(Folder):
    """
    Folder containing all principals by UID.
    """
    def child(self, name):
        return PrincipalHomeFolder(self.service, self.path + (name,), name)

    @inlineCallbacks
    def list(self):
        result = set()

        # FIXME: This should be the merged total of calendar homes and address book homes.
        # FIXME: Merge in directory UIDs also?
        # FIXME: Add directory info (eg. name) to listing

        for txn, home in (yield self.service.store.eachCalendarHome()):
            result.add((PrincipalHomeFolder, home.uid()))

        returnValue(result)



class RecordFolder(Folder):
    def _recordForName(self, name):
        recordTypeAttr = "recordType_" + self.recordType
        recordType = getattr(self.service.directory, recordTypeAttr)
        return self.service.directory.recordWithShortName(recordType, name)

    def child(self, name):
        record = self._recordForName(name)

        if record is None:
            return Folder.child(self, name)

        return PrincipalHomeFolder(
            self.service,
            self.path + (name,),
            record.uid,
            record=record
        )

    @inlineCallbacks
    def list(self):
        result = set()

        # FIXME ...?

        returnValue(result)


class UsersFolder(RecordFolder):
    """
    Folder containing all user principals by name.
    """
    recordType = "users"


class LocationsFolder(RecordFolder):
    """
    Folder containing all location principals by name.
    """
    recordType = "locations"


class ResourcesFolder(RecordFolder):
    """
    Folder containing all resource principals by name.
    """
    recordType = "resources"


class GroupsFolder(RecordFolder):
    """
    Folder containing all group principals by name.
    """
    recordType = "groups"


class PrincipalHomeFolder(Folder):
    """
    Folder containing everything related to a given principal.
    """
    def __init__(self, service, path, uid, record=None):
        Folder.__init__(self, service, path)

        if record is not None:
            assert uid == record.uid

        self.uid = uid
        self.record = record

    @inlineCallbacks
    def _initChildren(self):
        if not hasattr(self, "_didInitChildren"):
            txn  = self.service.store.newTransaction()

            if (
                self.record is not None and
                self.service.config.EnableCalDAV and 
                self.record.enabledForCalendaring
            ):
                create = True
            else:
                create = False

            home = (yield txn.calendarHomeWithUID(self.uid, create=create))
            if home:
                self._children["calendars"] = CalendarHomeFolder(
                    self.service,
                    self.path + ("calendars",),
                    home,
                )

            if (
                self.record is not None and
                self.service.config.EnableCardDAV and 
                self.record.enabledForAddressBooks
            ):
                create = True
            else:
                create = False

            home = (yield txn.addressbookHomeWithUID(self.uid))
            if home:
                self._children["addressbooks"] = AddressBookHomeFolder(
                    self.service,
                    self.path + ("addressbooks",),
                    home,
                )

        self._didInitChildren = True

    def _needsChildren(m):
        def decorate(self, *args, **kwargs):
            d = self._initChildren()
            d.addCallback(lambda _: m(self, *args, **kwargs))
            return d
        return decorate

    @_needsChildren
    def child(self, name):
        return Folder.child(self, name)

    @_needsChildren
    def list(self):
        return Folder.list(self)

    @inlineCallbacks
    def describe(self):
        result = []
        result.append("Principal home for UID: %s\n" % (self.uid,))

        if self.record is not None:
            #
            # Basic record info
            #

            rows = []

            def add(name, value):
                if value:
                    rows.append((name, value))

            add("Service"    , self.record.service   )
            add("Record Type", self.record.recordType)

            for shortName in self.record.shortNames:
                add("Short Name", shortName)

            add("GUID"      , self.record.guid     )
            add("Full Name" , self.record.fullName )
            add("First Name", self.record.firstName)
            add("Last Name" , self.record.lastName )

            for email in self.record.emailAddresses:
                add("Email Address", email)

            for cua in self.record.calendarUserAddresses:
                add("Calendar User Address", cua)

            add("Server ID"           , self.record.serverID              )
            add("Partition ID"        , self.record.partitionID           )
            add("Enabled"             , self.record.enabled               )
            add("Enabled for Calendar", self.record.enabledForCalendaring )
            add("Enabled for Contacts", self.record.enabledForAddressBooks)

            if rows:
                result.append("Directory Record:")
                result.append(tableString(rows, header=("Name", "Value")))

            #
            # Group memberships
            #
            rows = []

            for group in self.record.groups():
                rows.append((group.uid, group.shortNames[0], group.fullName))

            if rows:
                def sortKey(row):
                    return (row[1], row[2])
                result.append("Group Memberships:")
                result.append(tableString(
                    sorted(rows, key=sortKey),
                    header=("UID", "Short Name", "Full Name")
                ))

            #
            # Proxy for...
            #

            # FIXME: This logic should be in the DirectoryRecord.

            def meAndMyGroups(record=self.record, groups=set((self.record,))):
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
                        proxyRecord = self.service.directory.recordWithUID(proxyUID)
                        rows.append((proxyUID, proxyRecord.recordType, proxyRecord.shortNames[0], proxyRecord.fullName, proxyType))
                        proxyInfoSeen.add((proxyUID, proxyType))

            if rows:
                def sortKey(row):
                    return (row[1], row[2], row[4])
                result.append("Proxy Access:")
                result.append(tableString(
                    sorted(rows, key=sortKey),
                    header=("UID", "Record Type", "Short Name", "Full Name", "Access")
                ))

        returnValue("\n".join(result))


class CalendarHomeFolder(Folder):
    """
    Calendar home folder.
    """
    def __init__(self, service, path, home):
        Folder.__init__(self, service, path)

        self.home = home

    @inlineCallbacks
    def child(self, name):
        calendar = (yield self.home.calendarWithName(name))
        if calendar:
            returnValue(CalendarFolder(self.service, self.path + (name,), calendar))
        else:
            raise NotFoundError("Calendar home %r has no calendar %r" % (self, name))

    @inlineCallbacks
    def list(self):
        calendars = (yield self.home.calendars())
        returnValue(((CalendarFolder, c.name()) for c in calendars))

    @inlineCallbacks
    def describe(self):
        # created() -> int
        # modified() -> int
        # properties -> IPropertyStore

        uid          = (yield self.home.uid())
        created      = (yield self.home.created())
        modified     = (yield self.home.modified())
        quotaUsed    = (yield self.home.quotaUsedBytes())
        quotaAllowed = (yield self.home.quotaAllowedBytes())
        properties   = (yield self.home.properties())

        result = []
        result.append("Calendar home for UID: %s\n" % (uid,))

        #
        # Attributes
        #
        rows = []
        if created is not None:
            # FIXME: convert to formatted string
            rows.append(("Created", str(created)))
        if modified is not None:
            # FIXME: convert to formatted string
            rows.append(("Last modified", str(modified)))
        if quotaUsed is not None:
            rows.append((
                "Quota",
                "%s of %s (%.2s%%)"
                % (quotaUsed, quotaAllowed, quotaUsed / quotaAllowed)
            ))

        if len(rows):
            result.append("Attributes:")
            result.append(tableString(rows, header=("Name", "Value")))

        #
        # Properties
        #
        if properties:
            result.append("Properties:")
            result.append(tableString(
                ((name, properties[name]) for name in sorted(properties)),
                header=("Name", "Value")
            ))

        returnValue("\n".join(result))


class CalendarFolder(Folder):
    """
    Calendar.
    """
    def __init__(self, service, path, calendar):
        Folder.__init__(self, service, path)

        self.calendar = calendar

    @inlineCallbacks
    def _childWithObject(self, object):
        uid = (yield object.uid())
        returnValue(CalendarObject(self.service, self.path + (uid,), object, uid))

    @inlineCallbacks
    def child(self, name):
        object = (yield self.calendar.calendarObjectWithUID(name))

        if not object:
            raise NotFoundError("Calendar %r has no object %r" % (str(self), name))

        child = (yield self._childWithObject(object))
        returnValue(child)

    @inlineCallbacks
    def list(self):
        result = []

        for object in (yield self.calendar.calendarObjects()):
            object = (yield self._childWithObject(object))
            items = (yield object.list())
            result.append(items[0])

        returnValue(result)


class CalendarObject(File):
    """
    Calendar object.
    """
    def __init__(self, service, path, calendarObject, uid):
        File.__init__(self, service, path)

        self.object = calendarObject
        self.uid    = uid

    @inlineCallbacks
    def lookup(self):
        if not hasattr(self, "component"):
            component = (yield self.object.component())

            try:
                mainComponent = component.mainComponent(allow_multiple=True)

                assert self.uid == mainComponent.propertyValue("UID")

                self.componentType = mainComponent.name()
                self.summary       = mainComponent.propertyValue("SUMMARY")
                self.mainComponent = mainComponent

            except InvalidICalendarDataError, e:
                log.err("%s: %s" % (self.path, e))

                self.componentType = "?"
                self.summary       = "** Invalid data **"
                self.mainComponent = None

            self.component = component

    @inlineCallbacks
    def list(self):
        (yield self.lookup())
        returnValue(((CalendarObject, self.uid, self.componentType, self.summary.replace("\n", " ")),))

    @inlineCallbacks
    def text(self):
        (yield self.lookup())
        returnValue(str(self.component))

    @inlineCallbacks
    def describe(self):
        (yield self.lookup())

        rows = []

        rows.append(("UID", self.uid))
        rows.append(("Component Type", self.componentType))
        rows.append(("Summary", self.summary))
        
        organizer = self.mainComponent.getProperty("ORGANIZER")
        if organizer:
            organizerName = organizer.parameterValue("CN")
            organizerEmail = organizer.parameterValue("EMAIL")

            name  = " (%s)" % (organizerName ,) if organizerName  else ""
            email = " <%s>" % (organizerEmail,) if organizerEmail else ""

            rows.append(("Organizer", "%s%s%s" % (organizer.value(), name, email)))

        #
        # Attachments
        #
#       attachments = (yield self.object.attachments())
#       log.msg("%r" % (attachments,))
#       for attachment in attachments:
#           log.msg("%r" % (attachment,))
#           # FIXME: Not getting any results here

        returnValue("Calendar object:\n%s" % tableString(rows))

class AddressBookHomeFolder(Folder):
    """
    Address book home folder.
    """
    # FIXME


def tableString(rows, header=None):
    table = Table()
    if header:
        table.addHeader(header)
    for row in rows:
        table.addRow(row)

    output = StringIO()
    table.printTable(os=output)
    return output.getvalue()
