##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Implements a directory-backed principal hierarchy.
"""

__all__ = [
    "DirectoryPrincipalProvisioningResource",
    "DirectoryPrincipalTypeProvisioningResource",
    "DirectoryPrincipalResource",
    "DirectoryCalendarPrincipalResource",
]

from cgi import escape
from urllib import unquote
from urlparse import urlparse

from twisted.python import log
from twisted.python.failure import Failure
from twisted.internet.defer import succeed
from twisted.web2 import responsecode
from twisted.web2.http import HTTPError
from twisted.web2.dav import davxml
from twisted.web2.dav.element.base import twisted_private_namespace
from twisted.web2.dav.util import joinURL

from twistedcaldav.config import config
from twistedcaldav.directory.calendaruserproxy import CalendarUserProxyDatabase
from twistedcaldav.directory.calendaruserproxy import CalendarUserProxyPrincipalResource
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.extensions import ReadOnlyResourceMixIn, DAVFile, DAVPrincipalResource
from twistedcaldav.resource import CalendarPrincipalCollectionResource, CalendarPrincipalResource
from twistedcaldav.static import AutoProvisioningFileMixIn
from twistedcaldav.directory.idirectory import IDirectoryService

# Use __underbars__ convention to avoid conflicts with directory resource types.
uidsResourceName = "__uids__"

# FIXME: These should not be tied to DAVFile
# The reason that they is that web2.dav only implements DAV methods on
# DAVFile instead of DAVResource.  That should change.

class PermissionsMixIn (ReadOnlyResourceMixIn):
    def defaultAccessControlList(self):
        return authReadACL

    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):
        # Permissions here are fixed, and are not subject to inherritance rules, etc.
        return succeed(self.defaultAccessControlList())

class DirectoryProvisioningResource(
    AutoProvisioningFileMixIn,
    PermissionsMixIn,
    CalendarPrincipalCollectionResource,
    DAVFile,
):
    def __init__(self, path, url, directory):
        """
        @param path: the path to the file which will back the resource.
        @param url: the canonical URL for the resource.
        @param directory: an L{IDirectoryService} to provision principals from.
        """
        assert url.endswith("/"), "Collection URL must end in '/'"

        CalendarPrincipalCollectionResource.__init__(self, url)
        DAVFile.__init__(self, path)

        self.directory = IDirectoryService(directory)

    def principalForShortName(self, recordType, name):
        return self.principalForRecord(self.directory.recordWithShortName(recordType, name))

    def principalForUser(self, user):
        return self.principalForShortName(DirectoryService.recordType_users, user)

    def principalForGUID(self, guid):
        return self.principalForUID(guid)

    def principalForUID(self, uid):
        raise NotImplementedError("Subclass must implement principalForUID()")

    def principalForRecord(self, record):
        if record is None:
            return None
        return self.principalForGUID(record.guid)

    def principalForCalendarUserAddress(self, address):
        raise NotImplementedError("Subclass must implement principalForCalendarUserAddress()")

class DirectoryPrincipalProvisioningResource (DirectoryProvisioningResource):
    """
    Collection resource which provisions directory principals as its children.
    """
    def __init__(self, path, url, directory):
        DirectoryProvisioningResource.__init__(self, path, url, directory)

        # FIXME: Smells like a hack
        self.directory.principalCollection = self

        #
        # Create children
        #
        for recordType in self.directory.recordTypes():
            self.putChild(recordType, DirectoryPrincipalTypeProvisioningResource(self, recordType))

        self.putChild(uidsResourceName, DirectoryPrincipalUIDProvisioningResource(self))

    def principalForUID(self, uid):
        return self.getChild(uidsResourceName).getChild(uid)

    def _principalForURI(self, uri):
        scheme, netloc, path, params, query, fragment = urlparse(uri)

        if scheme == "":
            pass

        elif scheme in ("http", "https"):
            # Get rid of possible user/password nonsense
            netloc = netloc.split("@", 1)[-1]

            # Get host/port
            netloc = netloc.split(":", 1)

            host = netloc[0]
            if len(netloc) == 1 or netloc[1] == "":
                port = 80
            else:
                port = int(netloc[1])

            if host != config.ServerHostName:
                return None

            if port != {
                "http" : config.HTTPPort,
                "https": config.SSLPort,
            }[scheme]:
                return None

        elif scheme == "urn":
            if path.startswith("uuid:"):
                return self.principalForGUID(path[5:])
            else:
                return None
        else:
            return None

        if not path.startswith(self._url):
            return None

        path = path[len(self._url) - 1:]

        segments = [unquote(s) for s in path.rstrip("/").split("/")]
        if segments[0] == "" and len(segments) == 3:
            typeResource = self.getChild(segments[1])
            if typeResource is not None:
                principalResource = typeResource.getChild(segments[2])
                if principalResource:
                    return principalResource
            
        return None

    def principalForCalendarUserAddress(self, address):
        # First see if the address is a principal URI
        principal = self._principalForURI(address)
        if principal and isinstance(principal, DirectoryCalendarPrincipalResource):
            return principal

        # Next try looking it up in the directory
        record = self.directory.recordWithCalendarUserAddress(address)
        if record is not None:
            return self.principalForRecord(record)

        return None

    ##
    # Static
    ##

    def createSimilarFile(self, path):
        log.err("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name):
        self.provision()
        if name == "":
            return self
        else:
            return self.putChildren.get(name, None)

    def listChildren(self):
        return self.directory.recordTypes()

    ##
    # ACL
    ##

    def principalCollections(self):
        return (self,)

class DirectoryPrincipalTypeProvisioningResource (DirectoryProvisioningResource):
    """
    Collection resource which provisions directory principals of a
    specific type as its children, indexed by short name.
    """
    def __init__(self, parent, recordType):
        """
        @param path: the path to the file which will back the resource.
        @param parent: the parent L{DirectoryPrincipalProvisioningResource}.
        @param recordType: the directory record type to provision.
        """
        DirectoryProvisioningResource.__init__(
            self,
            parent.fp.child(recordType).path,
            joinURL(parent.principalCollectionURL(), recordType) + "/",
            parent.directory
        )

        self.recordType = recordType
        self.parent = parent

    def principalForUID(self, uid):
        return self.parent.principalForUID(uid)

    def principalForCalendarUserAddress(self, address):
        return self.parent.principalForCalendarUserAddress(address)

    ##
    # Static
    ##

    def createSimilarFile(self, path):
        log.err("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name):
        self.provision()
        if name == "":
            return self
        else:
            return self.principalForShortName(self.recordType, name)

    def listChildren(self):
        return (record.shortName for record in self.directory.listRecords(self.recordType))

    ##
    # ACL
    ##

    def principalCollections(self):
        return self.parent.principalCollections()

class DirectoryPrincipalUIDProvisioningResource (DirectoryProvisioningResource):
    """
    Collection resource which provisions directory principals indexed
    by UID.
    """
    # FIXME: Remove path argument
    def __init__(self, parent):
        """
        @param path: the path to the file which will back the resource.
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param recordType: the directory record type to provision.
        """
        DirectoryProvisioningResource.__init__(
            self,
            parent.fp.child(uidsResourceName).path,
            joinURL(parent.principalCollectionURL(), uidsResourceName) + "/",
            parent.directory
        )

        self.parent = parent

    def principalForUID(self, uid):
        return self.parent.principalForUID(uid)

    def principalForCalendarUserAddress(self, address):
        return self.parent.principalForCalendarUserAddress(address)

    ##
    # Static
    ##

    def createSimilarFile(self, path):
        log.err("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name):
        self.provision()
        if name == "":
            return self

        if "#" in name:
            # This UID belongs to a sub-principal
            primaryUID, subType = name.split("#")
        else:
            primaryUID = name
            subType = None

        record = self.directory.recordWithGUID(primaryUID)

        if record is None:
            log.err("No principal found for UID: %s" % (name,))
            return None

        if record.enabledForCalendaring:
            primaryPrincipal = DirectoryCalendarPrincipalResource(self.fp.child(name).path, self, record)
        else:
            primaryPrincipal = DirectoryPrincipalResource(self.fp.child(name).path, self, record)

        if subType is None:
            return primaryPrincipal
        else:
            return primaryPrincipal.getChild(subType)

    def listChildren(self):
        # Not a listable collection
        raise HTTPError(responsecode.FORBIDDEN)

    ##
    # ACL
    ##

    def principalCollections(self):
        return self.parent.principalCollections()

class DirectoryPrincipalResource (AutoProvisioningFileMixIn, PermissionsMixIn, DAVPrincipalResource, DAVFile):
    """
    Directory principal resource.
    """
    def __init__(self, path, parent, record):
        """
        @param path: them path to the file which will back this resource.
        @param parent: the parent of this resource.
        @param record: the L{IDirectoryRecord} that this resource represents.
        """
        super(DirectoryPrincipalResource, self).__init__(path)

        if self.isCollection():
            slash = "/"
        else:
            slash = ""

        assert record is not None, "Principal must have a directory record: %s" % (path,)

        url = joinURL(parent.principalCollectionURL(), record.guid) + slash

        self.record = record
        self.parent = parent
        self._url   = url

        self._alternate_urls = (
            joinURL(parent.parent.principalCollectionURL(), record.recordType, record.shortName) + slash,
        )

        # Provision in __init__() because principals are used prior to request
        # lookups.
        self.provision()

    def __str__(self):
        return "(%s) %s" % (self.record.recordType, self.record.shortName)

    def provisionFile(self):
        
        result = super(DirectoryPrincipalResource, self).provisionFile()
        if result:
            self.writeDeadProperty(RecordTypeProperty(self.record.recordType))
            self.writeDeadProperty(RecordNameProperty(self.record.shortName))
        return result

    ##
    # HTTP
    ##

    def renderDirectoryBody(self, request):
        def format_list(items, *args):
            def genlist():
                try:
                    item = None
                    for item in items:
                        yield " -> %s\n" % (item,)
                    if item is None:
                        yield " '()\n"
                except Exception, e:
                    log.err("Exception while rendering: %s" % (e,))
                    Failure().printTraceback()
                    yield "  ** %s **: %s\n" % (e.__class__.__name__, e)
            return "".join(genlist())

        def format_principals(principals):
            return format_list(
                """<a href="%s">%s</a>""" % (principal.principalURL(), escape(str(principal)))
                for principal in principals
            )

        def link(url):
            return """<a href="%s">%s</a>""" % (url, url)

        def gotSuper(output):
            return "".join((
                """<div class="directory-listing">"""
                """<h1>Principal Details</h1>"""
                """<pre><blockquote>"""
                """Directory Information\n"""
                """---------------------\n"""
                """Directory GUID: %s\n"""         % (self.record.service.guid,),
                """Realm: %s\n"""                  % (self.record.service.realmName,),
                """\n"""
                """Principal Information\n"""
                """---------------------\n"""
                """GUID: %s\n"""                   % (self.record.guid,),
                """Record type: %s\n"""            % (self.record.recordType,),
                """Short name: %s\n"""             % (self.record.shortName,),
                """Full name: %s\n"""              % (self.record.fullName,),
                """Principal UID: %s\n"""          % (self.principalUID(),),
                """Principal URL: %s\n"""          % (link(self.principalURL()),),
                """\nAlternate URIs:\n"""          , format_list(link(u) for u in self.alternateURIs()),
                """\nGroup members:\n"""           , format_principals(self.groupMembers()),
                """\nGroup memberships:\n"""       , format_principals(self.groupMemberships()),
                """</pre></blockquote></div>""",
                output
            ))

        d = super(DirectoryPrincipalResource, self).renderDirectoryBody(request)
        d.addCallback(gotSuper)
        return d

    ##
    # DAV
    ##

    def isCollection(self):
        return True

    def displayName(self):
        if self.record.fullName:
            return self.record.fullName
        else:
            return self.record.shortName

    ##
    # ACL
    ##

    def _calendar_user_proxy_index(self):
        """
        Return the SQL database for calendar user proxies.
        
        @return: the L{CalendarUserProxyDatabase} for the principal collection.
        """
        
        # Get the principal collection we are contained in
        pcollection = self.parent.parent
        
        # The db is located in the principal collection root
        if not hasattr(pcollection, "calendar_user_proxy_db"):
            setattr(pcollection, "calendar_user_proxy_db", CalendarUserProxyDatabase(pcollection.fp.path))
        return pcollection.calendar_user_proxy_db

    def alternateURIs(self):
        # FIXME: Add API to IDirectoryRecord for getting a record URI?
        return self._alternate_urls

    def principalURL(self):
        return self._url

    def _getRelatives(self, method, record=None, relatives=None, records=None, proxy=False):
        if record is None:
            record = self.record
        if relatives is None:
            relatives = set()
        if records is None:
            records = set()

        if record not in records:
            records.add(record)
            myRecordType = self.record.recordType
            for relative in getattr(record, method)():
                if relative not in records:
                    found = self.parent.principalForRecord(relative)
                    if found is None:
                        log.err("No principal found for directory record: %r" % (relative,))
                    else:
                        if proxy:
                            found = found.getChild("calendar-proxy-write")
                        relatives.add(found)

                    self._getRelatives(method, relative, relatives, records)

        return relatives

    def groupMembers(self):
        return self._getRelatives("members")

    def groupMemberships(self):
        groups = self._getRelatives("groups")

        if config.EnableProxyPrincipals:
            # Get any directory specified proxies
            groups.update(self._getRelatives("proxyFor", proxy=True))

            # Get proxy group UIDs and map to principal resources
            proxies = []
            for uid in self._calendar_user_proxy_index().getMemberships(self.principalUID()):
                subprincipal = self.parent.principalForUID(uid)
                if subprincipal:
                    proxies.append(subprincipal)

            groups.update(proxies)

        return groups


    def principalCollections(self):
        return self.parent.principalCollections()

    def principalUID(self):
        return self.record.guid
        
    ##
    # Static
    ##

    def createSimilarFile(self, path):
        log.err("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)

    def getChild(self, name):
        if name == "":
            return self

        return None

    def listChildren(self):
        return ()

class DirectoryCalendarPrincipalResource (DirectoryPrincipalResource, CalendarPrincipalResource):
    """
    Directory calendar principal resource.
    """
    def renderDirectoryBody(self, request):
        def format_list(items, *args):
            def genlist():
                try:
                    item = None
                    for item in items:
                        yield " -> %s\n" % (item,)
                    if item is None:
                        yield " '()\n"
                except Exception, e:
                    log.err("Exception while rendering: %s" % (e,))
                    Failure().printTraceback()
                    yield "  ** %s **: %s\n" % (e.__class__.__name__, e)
            return "".join(genlist())

        def format_principals(principals):
            return format_list(
                """<a href="%s">%s</a>""" % (principal.principalURL(), escape(str(principal)))
                for principal in principals
            )

        def link(url):
            return """<a href="%s">%s</a>""" % (url, url)

        def gotSuper(output):
            return "".join((
                """<div class="directory-listing">"""
                """<h1>Principal Details</h1>"""
                """<pre><blockquote>"""
                """Directory Information\n"""
                """---------------------\n"""
                """Directory GUID: %s\n"""         % (self.record.service.guid,),
                """Realm: %s\n"""                  % (self.record.service.realmName,),
                """\n"""
                """Principal Information\n"""
                """---------------------\n"""
                """GUID: %s\n"""                   % (self.record.guid,),
                """Record type: %s\n"""            % (self.record.recordType,),
                """Short name: %s\n"""             % (self.record.shortName,),
                """Full name: %s\n"""              % (self.record.fullName,),
                """Principal UID: %s\n"""          % (self.principalUID(),),
                """Principal URL: %s\n"""          % (link(self.principalURL()),),
                """\nAlternate URIs:\n"""          , format_list(link(u) for u in self.alternateURIs()),
                """\nGroup members:\n"""           , format_principals(self.groupMembers()),
                """\nGroup memberships:\n"""       , format_principals(self.groupMemberships()),
                """\nCalendar homes:\n"""          , format_list(link(u) for u in self.calendarHomeURLs()),
                """\nCalendar user addresses:\n""" , format_list(link(a) for a in self.calendarUserAddresses()),
                """</pre></blockquote></div>""",
                output
            ))

        d = super(DirectoryPrincipalResource, self).renderDirectoryBody(request)
        d.addCallback(gotSuper)
        return d

    ##
    # CalDAV
    ##

    def calendarUserAddresses(self):
        # Get any CUAs defined by the directory implementation.
        addresses = set(self.record.calendarUserAddresses)

        # Add the principal URL and alternate URIs to the list.
        for uri in ((self.principalURL(),) + tuple(self.alternateURIs())):
            addresses.add(uri)
            if config.HTTPPort:
                addresses.add("http://%s:%s%s" % (config.ServerHostName, config.HTTPPort, uri))
            if config.SSLPort:
                addresses.add("https://%s:%s%s" % (config.ServerHostName, config.SSLPort, uri))

        # Add a UUID URI based on the record's GUID to the list.
        addresses.add("urn:uuid:%s" % (self.record.guid,))

        return addresses

    def autoSchedule(self):
        return self.record.autoSchedule
    
    def proxies(self):
        return self._getRelatives("proxies")

    def hasEditableProxyMembership(self):
        return self.record.hasEditableProxyMembership()

    def scheduleInbox(self, request):
        home = self._calendarHome()
        if home is None:
            return succeed(None)

        inbox = home.getChild("inbox")
        if inbox is None:
            return succeed(None)

        return succeed(inbox)

    def calendarHomeURLs(self):
        home = self._calendarHome()
        if home is None:
            return ()
        else:
            return (home.url(),)

    def scheduleInboxURL(self):
        return self._homeChildURL("inbox/")

    def scheduleOutboxURL(self):
        return self._homeChildURL("outbox/")

    def dropboxURL(self):
        if config.EnableDropBox:
            return self._homeChildURL("dropbox/")
        else:
            return None

    def notificationsURL(self):
        if config.EnableNotifications:
            return self._homeChildURL("notifications/")
        else:
            return None

    def _homeChildURL(self, name):
        home = self._calendarHome()
        if home is None:
            return None
        else:
            return joinURL(home.url(), name)

    def _calendarHome(self):
        # FIXME: self.record.service.calendarHomesCollection smells like a hack
        # See CalendarHomeProvisioningFile.__init__()
        service = self.record.service
        if hasattr(service, "calendarHomesCollection"):
            return service.calendarHomesCollection.homeForDirectoryRecord(self.record)
        else:
            return None

    ##
    # Static
    ##

    def getChild(self, name):
        if name == "":
            return self

        if config.EnableProxyPrincipals and name in ("calendar-proxy-read", "calendar-proxy-write"):
            return CalendarUserProxyPrincipalResource(self.fp.child(name).path, self, name)
        else:
            return None

    def listChildren(self):
        if config.EnableProxyPrincipals:
            return ("calendar-proxy-read", "calendar-proxy-write")
        else:
            return ()

##
# Utilities
##

authReadACL = davxml.ACL(
    # Read access for authenticated users.
    davxml.ACE(
        davxml.Principal(davxml.Authenticated()),
        davxml.Grant(davxml.Privilege(davxml.Read())),
        davxml.Protected(),
    ),
)

class RecordTypeProperty (davxml.WebDAVTextElement):
    namespace = twisted_private_namespace
    name = "record-type"

davxml.registerElement(RecordTypeProperty)

class RecordNameProperty (davxml.WebDAVTextElement):
    namespace = twisted_private_namespace
    name = "record-name"

davxml.registerElement(RecordNameProperty)
