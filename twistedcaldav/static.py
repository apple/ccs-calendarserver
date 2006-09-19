##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
CalDAV-aware static resources.
"""

__version__ = "0.0"

__all__ = [
    "CalDAVFile",
    "ScheduleInboxFile",
    "ScheduleOutboxFile",
    "CalendarHomeFile",
    "CalendarHomeProvisioningFile",
    "CalendarPrincipalFile",
    "CalendarUserPrincipalProvisioningResource",
    "CalendarPrincipalProvisioningResource",
]

import os
import errno
from urlparse import urlsplit

from twisted.internet.defer import deferredGenerator, fail, succeed, waitForDeferred
from twisted.python import log
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.auth import TwistedPasswordProperty
from twisted.web2.dav.fileop import mkcollection, rmdir
from twisted.web2.dav.http import ErrorResponse
from twisted.web2.dav.idav import IDAVResource
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.dav.resource import TwistedACLProperty
from twisted.web2.dav.static import DAVFile
from twisted.web2.dav.util import parentForURL, joinURL, bindMethods
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav import caldavxml
from twistedcaldav import customxml
from twistedcaldav.ical import Component as iComponent
from twistedcaldav.ical import Property as iProperty
from twistedcaldav.icaldav import ICalDAVResource
from twistedcaldav.index import Index, IndexSchedule, db_basename
from twistedcaldav.resource import CalDAVResource, isPseudoCalendarCollectionResource, CalendarPrincipalResource
from twistedcaldav.resource import ScheduleInboxResource, ScheduleOutboxResource, CalendarPrincipalCollectionResource
from twistedcaldav.resource import isCalendarCollectionResource

class CalDAVFile (CalDAVResource, DAVFile):
    """
    CalDAV-accessible L{DAVFile} resource.
    """

    def __repr__(self):
        if self.isCalendarCollection():
            return "<%s (calendar collection): %s>" % (self.__class__.__name__, self.fp.path)
        else:
            return super(CalDAVFile, self).__repr__()

    ##
    # CalDAV
    ##

    def createCalendar(self, request):
        #
        # request object is required because we need to validate against parent
        # resources, and we need the request in order to locate the parents.
        #

        if self.fp.exists():
            log.err("Attempt to create collection where file exists: %s" % (self.fp.path,))
            raise HTTPError(StatusResponse(responsecode.NOT_ALLOWED, "File exists"))

        if not os.path.isdir(os.path.dirname(self.fp.path)):
            log.err("Attempt to create collection with no parent: %s" % (self.fp.path,))
            raise HTTPError(StatusResponse(responsecode.CONFLICT, "No parent collection"))

        #
        # Verify that no parent collection is a calendar also
        #
        log.msg("Creating calendar collection %s" % (self,))

        def _defer(parent):
            if parent is not None:
                log.err("Cannot create a calendar collection within a calendar collection %s" % (parent,))
                raise HTTPError(ErrorResponse(
                    responsecode.FORBIDDEN,
                    (caldavxml.caldav_namespace, "calendar-collection-location-ok")
                ))
    
            return self.createCalendarCollection()
            
        parent = self._checkParents(request, isPseudoCalendarCollectionResource)
        parent.addCallback(_defer)
        return parent

    def createCalendarCollection(self):
        #
        # Create the collection once we know it is safe to do so
        #
        def _deferOK(result):
            if result != responsecode.CREATED:
                raise HTTPError(result)
    
            self.writeDeadProperty(davxml.ResourceType.calendar)
            return responsecode.CREATED
        
        def _deferErr(f):
            try:
                rmdir(self.fp)
            except Exception, e:
                log.err("Unable to clean up after failed MKCALENDAR: %s" % e)
    
            if isinstance(f.value, HTTPError):
                return f.value.response
    
            f.raiseException()
            
        d = mkcollection(self.fp)
        d.addCallback(_deferOK)
        d.addErrback(_deferErr)
        return d
 
    def iCalendarRolledup(self, request):
        if self.isPseudoCalendarCollection():
            # Generate a monolithic calendar
            calendar = iComponent("VCALENDAR")
            calendar.addProperty(iProperty("VERSION", "2.0"))

            # Do some optimisation of access control calculation by determining any inherited ACLs outside of
            # the child resource loop and supply those to the checkPrivileges on each child.
            filteredaces = waitForDeferred(self.inheritedACEsforChildren(request))
            yield filteredaces
            filteredaces = filteredaces.getResult()

            # Must verify ACLs which means we need a request object at this point
            for name, uid, type in self.index().search(None): #@UnusedVariable
                try:
                    child_url = joinURL(request.uri, str(name))
                    child = waitForDeferred(request.locateResource(child_url))
                    yield child
                    child = child.getResult()
                    child = IDAVResource(child)
                except TypeError:
                    child = None
    
                if child is not None:
                    # Check privileges of child - skip if access denied
                    try:
                        d = waitForDeferred(child.checkPrivileges(request, (davxml.Read(),), inherited_aces=filteredaces))
                        yield d
                        d.getResult()
                    except:
                        continue
                    subcalendar = self.iCalendar(name)
                    assert subcalendar.name() == "VCALENDAR"

                    for component in subcalendar.subcomponents():
                        calendar.addComponent(component)
                        
            yield calendar
            return

        yield fail(HTTPError((ErrorResponse(responsecode.BAD_REQUEST))))

    iCalendarRolledup = deferredGenerator(iCalendarRolledup)

    def iCalendarText(self, name=None):
        if self.isPseudoCalendarCollection():
            if name is None:
                return str(self.iCalendar())

            try:
                calendar_file = self.fp.child(name).open()
            except IOError, e:
                if e[0] == errno.ENOENT: return None
                raise

        elif self.isCollection():
            return None

        else:
            if name is not None:
                raise AssertionError("name must be None for non-collection calendar resource")

            calendar_file = self.fp.open()

        # FIXME: This is blocking I/O
        try:
            calendar_data = calendar_file.read()
        finally:
            calendar_file.close()

        return calendar_data

    def iCalendarXML(self, name=None):
        return caldavxml.CalendarData.fromCalendarData(self.iCalendarText(name))

    def supportedPrivileges(self, request):
        if not hasattr(CalDAVFile, "_supportedCalendarPrivilegeSet"):
            CalDAVFile._supportedCalendarPrivilegeSet = davxml.SupportedPrivilegeSet(
                davxml.SupportedPrivilege(
                    davxml.Privilege(davxml.All()),
                    davxml.Description("all privileges", **{"xml:lang": "en"}),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Read()),
                        davxml.Description("read resource", **{"xml:lang": "en"}),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(caldavxml.ReadFreeBusy()),
                            davxml.Description("allow free busy report query", **{"xml:lang": "en"}),
                        ),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Write()),
                        davxml.Description("write resource", **{"xml:lang": "en"}),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.WriteProperties()),
                            davxml.Description("write resource properties", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.WriteContent()),
                            davxml.Description("write resource content", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.Bind()),
                            davxml.Description("add child resource", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.Unbind()),
                            davxml.Description("remove child resource", **{"xml:lang": "en"}),
                        ),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Unlock()),
                        davxml.Description("unlock resource without ownership", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.ReadACL()),
                        davxml.Description("read resource access control list", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.WriteACL()),
                        davxml.Description("write resource access control list", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                        davxml.Description("read privileges for current principal", **{"xml:lang": "en"}),
                    ),
                ),
            )
            
        # read-free-busy support on calendar collection and calendar object resources
        if self.isCollection():
            return succeed(CalDAVFile._supportedCalendarPrivilegeSet)
        else:
            def _callback(parent):
                if parent and isCalendarCollectionResource(parent):
                    return succeed(CalDAVFile._supportedCalendarPrivilegeSet)
                else:
                    return super(CalDAVFile, self).supportedPrivileges(request)

            d = self.locateParent(request, request.urlForResource(self))
            d.addCallback(_callback)
            return d
        
        return super(CalDAVFile, self).supportedPrivileges(request)


    ##
    # Public additions
    ##

    def index(self):
        """
        Obtains the index for a calendar collection resource.
        @return: the index object for this resource.
        @raise AssertionError: if this resource is not a calendar collection
            resource.
        """
        return Index(self)

    ##
    # File
    ##

    def listChildren(self):
        return [
            child for child in super(CalDAVFile, self).listChildren()
            if child != db_basename
        ]

    ##
    # Utilities
    ##

    @staticmethod
    def _isChildURI(request, uri, immediateChild=True):
        """
        Verify that the supplied URI represents a resource that is a child
        of the request resource.
        @param request: the request currently in progress
        @param uri: the URI to test
        @return: True if the supplied URI is a child resource
                 False if not
        """
        if uri is None: return False

        #
        # Parse the URI
        #
    
        (scheme, host, path, query, fragment) = urlsplit(uri) #@UnusedVariable
    
        # Request hostname and child uri hostname have to be the same.
        if host and host != request.headers.getHeader("host"):
            return False
        
        # Child URI must start with request uri text.
        parent = request.uri
        if not parent.endswith("/"):
            parent += "/"
            
        return path.startswith(parent) and (len(path) > len(parent)) and (not immediateChild or (path.find("/", len(parent)) == -1))
    
    def _checkParents(self, request, test):
        """
        @param request: the request being processed.
        @param test: a callable
        @return: the closest parent for this resource using the request URI from
            the given request for which C{test(parent)} evaluates to a true
            value, or C{None} if no parent matches.
        """
        parent = self
        parent_uri = request.uri

        while True:
            parent_uri = parentForURL(parent_uri)
            if not parent_uri: break

            parent = waitForDeferred(request.locateResource(parent_uri))
            yield parent
            parent = parent.getResult()

            if test(parent):
                yield parent
                return

        yield None
    
    _checkParents = deferredGenerator(_checkParents)

class ScheduleInboxFile (ScheduleInboxResource, CalDAVFile):
    """
    L{CalDAVFile} calendar inbox collection resource.
    """
    def __repr__(self):
        return "<%s (calendar inbox collection): %s>" % (self.__class__.__name__, self.fp.path)

    def index(self):
        """
        Obtains the index for an schedule collection resource.
        @return: the index object for this resource.
        @raise AssertionError: if this resource is not a calendar collection
            resource.
        """
        return IndexSchedule(self)

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return ScheduleInboxFile(path)
        else:
            return CalDAVFile(path)

    def http_COPY       (self, request): return responsecode.FORBIDDEN
    def http_MOVE       (self, request): return responsecode.FORBIDDEN
    def http_DELETE     (self, request): return responsecode.FORBIDDEN
    def http_MKCOL      (self, request): return responsecode.FORBIDDEN
    def http_MKCALENDAR (self, request): return responsecode.FORBIDDEN

    def supportedPrivileges(self, request):
        if not hasattr(ScheduleInboxFile, "_supportedSchedulePrivilegeSet"):
            ScheduleInboxFile._supportedSchedulePrivilegeSet = davxml.SupportedPrivilegeSet(
                davxml.SupportedPrivilege(
                    davxml.Privilege(davxml.All()),
                    davxml.Description("all privileges", **{"xml:lang": "en"}),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Read()),
                        davxml.Description("read resource", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Write()),
                        davxml.Description("write resource", **{"xml:lang": "en"}),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.WriteProperties()),
                            davxml.Description("write resource properties", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.WriteContent()),
                            davxml.Description("write resource content", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.Bind()),
                            davxml.Description("add child resource", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.Unbind()),
                            davxml.Description("remove child resource", **{"xml:lang": "en"}),
                        ),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Unlock()),
                        davxml.Description("unlock resource without ownership", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.ReadACL()),
                        davxml.Description("read resource access control list", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.WriteACL()),
                        davxml.Description("write resource access control list", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                        davxml.Description("read privileges for current principal", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(caldavxml.Schedule()),
                        davxml.Description("schedule privileges for current principal", **{"xml:lang": "en"}),
                    ),
                ),
            )
            
        return succeed(ScheduleInboxFile._supportedSchedulePrivilegeSet)

class ScheduleOutboxFile (ScheduleOutboxResource, CalDAVFile):
    """
    L{CalDAVFile} calendar outbox collection resource.
    """
    def __repr__(self):
        return "<%s (calendar outbox collection): %s>" % (self.__class__.__name__, self.fp.path)

    def index(self):
        """
        Obtains the index for an iTIP collection resource.
        @return: the index object for this resource.
        @raise AssertionError: if this resource is not a calendar collection
            resource.
        """
        return IndexSchedule(self)

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            return CalDAVFile(path)

    def http_COPY       (self, request): return responsecode.FORBIDDEN
    def http_MOVE       (self, request): return responsecode.FORBIDDEN
    def http_DELETE     (self, request): return responsecode.FORBIDDEN
    def http_MKCOL      (self, request): return responsecode.FORBIDDEN
    def http_MKCALENDAR (self, request): return responsecode.FORBIDDEN

    def supportedPrivileges(self, request):
        if not hasattr(ScheduleOutboxFile, "_supportedSchedulePrivilegeSet"):
            ScheduleOutboxFile._supportedSchedulePrivilegeSet = davxml.SupportedPrivilegeSet(
                davxml.SupportedPrivilege(
                    davxml.Privilege(davxml.All()),
                    davxml.Description("all privileges", **{"xml:lang": "en"}),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Read()),
                        davxml.Description("read resource", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Write()),
                        davxml.Description("write resource", **{"xml:lang": "en"}),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.WriteProperties()),
                            davxml.Description("write resource properties", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.WriteContent()),
                            davxml.Description("write resource content", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.Bind()),
                            davxml.Description("add child resource", **{"xml:lang": "en"}),
                        ),
                        davxml.SupportedPrivilege(
                            davxml.Privilege(davxml.Unbind()),
                            davxml.Description("remove child resource", **{"xml:lang": "en"}),
                        ),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.Unlock()),
                        davxml.Description("unlock resource without ownership", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.ReadACL()),
                        davxml.Description("read resource access control list", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.WriteACL()),
                        davxml.Description("write resource access control list", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                        davxml.Description("read privileges for current principal", **{"xml:lang": "en"}),
                    ),
                    davxml.SupportedPrivilege(
                        davxml.Privilege(caldavxml.Schedule()),
                        davxml.Description("schedule privileges for current principal", **{"xml:lang": "en"}),
                    ),
                ),
            )
            
        return succeed(ScheduleOutboxFile._supportedSchedulePrivilegeSet)

class CalendarHomeFile (CalDAVFile):
    """
    L{CalDAVFile} calendar home collection resource.
    """
    def __init__(self, path):
        """
        @param path: the path to the file which will back the resource.
        """
        super(CalendarHomeFile, self).__init__(path)

        assert self.exists(), "%s should exist" % (self,)
        assert self.isCollection(), "%s should be a collection" % (self,)

        # Create children
        for name, clazz in (
            ("inbox" , ScheduleInboxFile),
            ("outbox", ScheduleOutboxFile),
        ):
            child_fp = self.fp.child(name)
            if not child_fp.exists(): child_fp.makedirs()
            self.putChild(name, clazz(child_fp.path))

    def createSimilarFile(self, path):
        return CalDAVFile(path)

class CalendarHomeProvisioningFile (CalDAVFile):
    """
    L{CalDAVFile} resource which provisions calendar home collections as needed.
    """
    def __init__(self, path):
        """
        @param path: the path to the file which will back the resource.
        """
        super(CalendarHomeProvisioningFile, self).__init__(path)

    def render(self, request):
        return StatusResponse(
            responsecode.OK,
            "This collection contains user calendar home collections",
            title=self.displayName()
        )

    def getChild(self, name):
        if name == "": return self

        child_fp = self.fp.child(name)
        if child_fp.exists():
            assert child_fp.isdir()
        else:
            assert self.exists()
            assert self.isCollection()

            # FIXME: Do a real lookup of what's valid here
            if name[0] == ".": return None
            if len(name) > 8: return None

            child_fp.makedirs()

        return CalendarHomeFile(child_fp.path)

    def createSimilarFile(self, path):
        return CalDAVFile(path)

    def http_PUT        (self, request): return responsecode.FORBIDDEN
    def http_MKCOL      (self, request): return responsecode.FORBIDDEN
    def http_MKCALENDAR (self, request): return responsecode.FORBIDDEN

class CalendarPrincipalFile (CalendarPrincipalResource, CalDAVFile):
    """
    Calendar principal resource.
    """
    def __init__(self, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  This is the url which
            will be returned by L{principalURL}.
        """
        super(CalendarPrincipalFile, self).__init__(path)

        self._url = url

    def createSimilarFile(self, path):
        return self.__class__(path, self._url)

    ##
    # ACL
    ##

    def alternateURIs(self):
        return ()

    def principalURL(self):
        return self._url

    def groupMembers(self):
        return ()

    def groupMemberships(self):
        return ()

    ##
    # CalDAV
    ##

    def principalUID(self):
        """
        @return: the user id for this principal.
        """
        return self.fp.basename()

    def provisionCalendarAccount(self, name, pswd, resetacl, cuaddrs, cuhome, cuhomeacls, cals, autorespond):
        """
        Provision the principal and a calendar account for it.
        
        @param name: C{str} name (uid) of principal.
        @param pswd: C{str} password for BASIC authentication, of C{None}.
        @param resetacl: C{True} if ACLs on the principal resource should be reset.
        @param cuaddrs: C{list} list of calendar user addresses, or C{None}
        @param cuhome: C{tuple} of (C{str} - URI of calendar home root, L{DAVResource} - resource of home root)
        @param cuhomeacls: L{ACL} acls to use on calendar home when resetting ACLs, or C{None} to use default set.
        @param cals: C{list} list of calendar names to create in the calendar home for this prinicpal.
        @param autorespond: C{True} if iTIP auto-response is required, C{False} otherwise.
        """
        
        if pswd:
            self.writeDeadProperty(TwistedPasswordProperty.fromString(pswd))
        else:
            self.removeDeadProperty(TwistedPasswordProperty())
        if name:
            self.writeDeadProperty(davxml.DisplayName.fromString(name))
        else:
            self.removeDeadProperty(davxml.DisplayName())
        if cuaddrs:
            self.writeDeadProperty(caldavxml.CalendarUserAddressSet(*[davxml.HRef(addr) for addr in cuaddrs]))
        else:
            self.removeDeadProperty(caldavxml.CalendarUserAddressSet())

        if resetacl:
            self.setAccessControlList(
                davxml.ACL(
                    davxml.ACE(
                        davxml.Principal(davxml.HRef.fromString(self._url)),
                        davxml.Grant(
                            davxml.Privilege(davxml.Read()),
                        ),
                    ),
                )
            )

        # If the user does not have any calendar user addresses we do not create a calendar home for them
        if not cuaddrs and not cals:
            return

        # Create calendar home
        homeURL = joinURL(cuhome[0], self.principalUID())
        home = FilePath(os.path.join(cuhome[1].fp.path, self.principalUID()))
        home_exists = home.exists()
        if not home_exists:
            home.createDirectory()
        home = CalendarHomeFile(home.path)

        if resetacl or not home_exists:
            if cuhomeacls:
                home.setAccessControlList(cuhomeacls.acl)
            else:
                home.setAccessControlList(
                    davxml.ACL(
                        davxml.ACE(
                            davxml.Principal(davxml.Authenticated()),
                            davxml.Grant(
                                davxml.Privilege(davxml.Read()),
                            ),
                        ),
                        davxml.ACE(
                            davxml.Principal(davxml.HRef.fromString(self._url)),
                            davxml.Grant(
                                davxml.Privilege(davxml.All()),
                            ),
                            TwistedACLInheritable(),
                        ),
                    )
                )
        
        # Save the calendar-home-set, schedule-inbox and schedule-outbox properties
        self.writeDeadProperty(caldavxml.CalendarHomeSet(davxml.HRef.fromString(homeURL + "/")))
        self.writeDeadProperty(caldavxml.ScheduleInboxURL(davxml.HRef.fromString(joinURL(homeURL, "inbox/"))))
        self.writeDeadProperty(caldavxml.ScheduleOutboxURL(davxml.HRef.fromString(joinURL(homeURL, "outbox/"))))
        
        # Set ACLs on inbox and outbox
        if resetacl or not home_exists:
            inbox = home.getChild("inbox")
            inbox.setAccessControlList(
                davxml.ACL(
                    davxml.ACE(
                        davxml.Principal(davxml.Authenticated()),
                        davxml.Grant(
                            davxml.Privilege(caldavxml.Schedule()),
                        ),
                    ),
                )
            )
            if autorespond:
                inbox.writeDeadProperty(customxml.TwistedScheduleAutoRespond())

            outbox = home.getChild("outbox")
            if outbox.hasDeadProperty(TwistedACLProperty()):
                outbox.removeDeadProperty(TwistedACLProperty())

        calendars = []
        for calendar in cals:
            childURL = joinURL(homeURL, calendar)
            child = CalDAVFile(os.path.join(home.fp.path, calendar))
            child_exists = child.exists()
            if not child_exists:
                c = child.createCalendarCollection()
                assert c.called
                c = c.result
            calendars.append(childURL)
            if (resetacl or not child_exists):
                child.setAccessControlList(
                    davxml.ACL(
                        davxml.ACE(
                            davxml.Principal(davxml.Authenticated()),
                            davxml.Grant(
                                davxml.Privilege(caldavxml.ReadFreeBusy()),
                            ),
                            TwistedACLInheritable(),
                        ),
                    )
                )
        
        # Set calendar-free-busy-set on Inbox if not already present
        inbox = home.getChild("inbox")
        if not inbox.hasDeadProperty(caldavxml.CalendarFreeBusySet()):
            fbset = caldavxml.CalendarFreeBusySet(*[davxml.HRef.fromString(uri) for uri in calendars])
            inbox.writeDeadProperty(fbset)


class CalendarUserPrincipalProvisioningResource (CalendarPrincipalCollectionResource, DAVFile):
    """
    L{DAVFile} resource which provisions user L{CalendarPrincipalFile} resources
    as needed.
    """
    def __init__(self, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  Provisioned child
            resources will use a URL based on C{url} as their primary URLs.
        """
        CalendarPrincipalCollectionResource.__init__(self, url)
        DAVFile.__init__(self, path)

    def initialize(self, homeuri, home):
        """
        May be called during repository account initialization.
        This implementation does nothing.
        
        @param homeuri: C{str} uri of the calendar home root.
        @param home: L{DAVFile} of the calendar home root.
        """
        pass
    
    def render(self, request):
        return StatusResponse(
            responsecode.OK,
            "This collection contains user principal resources",
            title=self.displayName()
        )

    def getChild(self, name):
        if name == "": return self

        child_fp = self.fp.child(name)
        if child_fp.exists():
            assert child_fp.isfile()
        else:
            assert self.exists()
            assert self.isCollection()

            # FIXME: Do a real lookup of what's valid here
            if name[0] == ".": return None
            if len(name) > 8: return None

            child_fp.open("w").close()

        return CalendarPrincipalFile(child_fp.path, joinURL(self._url, name))

    def principalSearchPropertySet(self):
        """
        See L{IDAVResource.principalSearchPropertySet}.
        
        This implementation returns None. Principal collection resources MUST override
        and return their own suitable response.
        
        """
        return davxml.PrincipalSearchPropertySet(
            davxml.PrincipalSearchProperty(
                davxml.PropertyContainer(
                    davxml.DisplayName()
                ),
                davxml.Description(
                    davxml.PCDATAElement("Display Name"),
                    **{"xml:lang":"en"}
                ),
            ),
            davxml.PrincipalSearchProperty(
                davxml.PropertyContainer(
                    caldavxml.CalendarUserAddressSet()
                ),
                davxml.Description(
                    davxml.PCDATAElement("Calendar User Addresses"),
                    **{"xml:lang":"en"}
                ),
            ),
        )

    def createSimilarFile(self, path):
        if path == self.fp.path:
            return self
        else:
            # TODO: Fix this - not sure how to get URI for second argument of __init__
            return CalendarPrincipalFile(path, "")

    def http_PUT        (self, request): return responsecode.FORBIDDEN
    def http_MKCOL      (self, request): return responsecode.FORBIDDEN
    def http_MKCALENDAR (self, request): return responsecode.FORBIDDEN

class CalendarPrincipalProvisioningResource (DAVFile):
    """
    L{DAVFile} resource which provisions calendar principal resources as needed.
    """
    def __init__(self, path, url):
        """
        @param path: the path to the file which will back the resource.
        @param url: the primary URL for the resource.  Provisioned child
            resources will use a URL based on C{url} as their primary URLs.
        """
        super(CalendarPrincipalProvisioningResource, self).__init__(path)

        assert self.exists(), "%s should exist" % (self,)
        assert self.isCollection(), "%s should be a collection" % (self,)

        # FIXME: I don't think we need this anymore nwo that we have static & OD repository builders.
        # Create children
        for name, clazz in (
            ("users/" , CalendarUserPrincipalProvisioningResource),
        ):
            child_fp = self.fp.child(name)
            if not child_fp.exists(): child_fp.makedirs()
            principalCollection = clazz(child_fp.path, joinURL(url, name))
            self.putChild(name, principalCollection)

    def initialize(self, homeuri, home):
        """
        May be called during repository account initialization.
        This implementation does nothing.
        
        @param homeuri: C{str} uri of the calendar home root.
        @param home: L{DAVFile} of the calendar home root.
        """
        pass
    
    def createSimilarFile(self, path):
        return DAVFile(path)

    def render(self, request):
        return StatusResponse(
            responsecode.OK,
            "This collection contains principal resources",
            title=self.displayName()
        )

##
# Attach methods
##

import twistedcaldav.method

bindMethods(twistedcaldav.method, CalDAVFile)

# FIXME: Little bit of a circular dependency here...
twistedcaldav.method.copymove.CalDAVFile = CalDAVFile
twistedcaldav.method.delete.CalDAVFile   = CalDAVFile
twistedcaldav.method.mkcol.CalDAVFile    = CalDAVFile
twistedcaldav.method.put.CalDAVFile      = CalDAVFile
