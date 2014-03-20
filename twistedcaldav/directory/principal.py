# -*- test-case-name: twistedcaldav.directory.test.test_principal -*-
##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
Implements a directory-backed principal hierarchy.
"""

__all__ = [
    "DirectoryProvisioningResource",
    "DirectoryPrincipalProvisioningResource",
    "DirectoryPrincipalTypeProvisioningResource",
    "DirectoryPrincipalUIDProvisioningResource",
    "DirectoryPrincipalResource",
    "DirectoryCalendarPrincipalResource",
]

from urllib import quote, unquote
from urlparse import urlparse
import uuid

from twext.python.log import Logger
from twisted.cred.credentials import UsernamePassword
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.defer import succeed
from twisted.python.modules import getModule
from twisted.web.template import XMLFile, Element, renderer
from twistedcaldav import caldavxml, customxml
from twistedcaldav.cache import DisabledCacheNotifier, PropfindCacheMixin
from twistedcaldav.config import config
from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.directory.augment import allowedAutoScheduleModes
from twistedcaldav.directory.common import uidsResourceName
from twistedcaldav.directory.util import NotFoundResource
from twistedcaldav.directory.util import (
    formatLink, formatLinks, formatPrincipals, formatList
)
from twistedcaldav.directory.wiki import getWikiACL
from twistedcaldav.extensions import (
    ReadOnlyResourceMixIn, DAVPrincipalResource, DAVResourceWithChildrenMixin
)
from twistedcaldav.extensions import DirectoryElement
from twistedcaldav.resource import CalendarPrincipalCollectionResource, CalendarPrincipalResource
from txdav.caldav.datastore.scheduling.cuaddress import normalizeCUAddr
from txdav.who.directory import CalendarDirectoryRecordMixin
from txdav.xml import element as davxml
from txweb2 import responsecode
from txweb2.auth.digest import DigestedCredentials
from txweb2.dav.noneprops import NonePropertyStore
from txweb2.dav.util import joinURL
from txweb2.http import HTTPError

try:
    from twistedcaldav.authkerb import NegotiateCredentials
    NegotiateCredentials  # sigh, pyflakes
except ImportError:
    NegotiateCredentials = None

thisModule = getModule(__name__)
log = Logger()


class PermissionsMixIn (ReadOnlyResourceMixIn):
    def defaultAccessControlList(self):
        return succeed(authReadACL)


    @inlineCallbacks
    def accessControlList(self, request, inheritance=True, expanding=False, inherited_aces=None):

        try:
            wikiACL = (yield getWikiACL(self, request))
        except HTTPError:
            wikiACL = None

        if wikiACL is not None:
            # ACL depends on wiki server...
            log.debug("Wiki ACL: %s" % (wikiACL.toxml(),))
            returnValue(wikiACL)
        else:
            # ...otherwise permissions are fixed, and are not subject to
            # inheritance rules, etc.
            returnValue((yield self.defaultAccessControlList()))



# Converter methods for recordsMatchingFields()
#
# A DAV property can be associated with one of these converter methods,
# which take the string being matched and return the appropriate record
# field name to match against, as well as a new match string which has been
# converted to the appropriate form.

def cuTypeConverter(cuType):
    """ Converts calendar user types to OD type names """

    return "recordType", CalendarDirectoryRecordMixin.fromCUType(cuType)



def cuAddressConverter(origCUAddr):
    """ Converts calendar user addresses to OD-compatible form """

    cua = normalizeCUAddr(origCUAddr)

    if cua.startswith("urn:uuid:"):
        return "guid", cua[9:]

    elif cua.startswith("mailto:"):
        return "emailAddresses", cua[7:]

    elif cua.startswith("/") or cua.startswith("http"):
        ignored, collection, id = cua.rsplit("/", 2)
        if collection == "__uids__":
            return "uid", id
        else:
            return "recordName", id

    else:
        raise ValueError("Invalid calendar user address format: %s" %
            (origCUAddr,))



class DirectoryProvisioningResource (
    PermissionsMixIn,
    CalendarPrincipalCollectionResource,
):
    def __init__(self, url, directory):
        """
        @param url: the canonical URL for the resource.
        @param directory: an L{IDirectoryService} to provision principals from.
        """
        assert url.endswith("/"), "Collection URL must end in '/'"

        CalendarPrincipalCollectionResource.__init__(self, url)
        DAVResourceWithChildrenMixin.__init__(self)

        # MOVE2WHO
        # self.directory = IDirectoryService(directory)
        self.directory = directory


    def __repr__(self):
        return "<%s: %s %s>" % (self.__class__.__name__, self.directory, self._url)


    @inlineCallbacks
    def locateChild(self, req, segments):
        child = (yield self.getChild(segments[0]))
        if child is not None:
            returnValue((child, segments[1:]))
        returnValue((NotFoundResource(principalCollections=self.principalCollections()), ()))


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(None)


    @inlineCallbacks
    def principalForShortName(self, recordType, name):
        record = (yield self.directory.recordWithShortName(recordType, name))
        returnValue((yield self.principalForRecord(record)))


    def principalForUser(self, user):
        return self.principalForShortName(self.directory.recordType.lookupByName("user"), user)


    def principalForAuthID(self, user):
        # Basic/Digest creds -> just lookup user name
        if isinstance(user, UsernamePassword) or isinstance(user, DigestedCredentials):
            return self.principalForUser(user.username)
        elif NegotiateCredentials is not None and isinstance(user, NegotiateCredentials):
            authID = "Kerberos:%s" % (user.principal,)
            principal = self.principalForRecord(self.directory.recordWithAuthID(authID))
            if principal:
                return principal
            elif user.username:
                return self.principalForUser(user.username)

        return None


    def principalForUID(self, uid):
        raise NotImplementedError("Subclass must implement principalForUID()")


    def principalForCalendarUserAddress(self, address):
        raise NotImplementedError("Subclass must implement principalForCalendarUserAddress()")


    def principalForRecord(self, record):
        if record is None or not record.enabled:
            return succeed(None)
        return self.principalForUID(record.uid)

    ##
    # DAV-property-to-record-field mapping
    ##

    _cs_ns = "http://calendarserver.org/ns/"
    _fieldMap = {
        ("DAV:" , "displayname") :
            ("fullNames", None, "Display Name", davxml.DisplayName),
        ("urn:ietf:params:xml:ns:caldav" , "calendar-user-type") :
            ("", cuTypeConverter, "Calendar User Type",
            caldavxml.CalendarUserType),
        ("urn:ietf:params:xml:ns:caldav" , "calendar-user-address-set") :
            ("", cuAddressConverter, "Calendar User Address Set",
            caldavxml.CalendarUserAddressSet),
        (_cs_ns, "first-name") :
            ("firstName", None, "First Name", customxml.FirstNameProperty),
        (_cs_ns, "last-name") :
            ("lastName", None, "Last Name", customxml.LastNameProperty),
        (_cs_ns, "email-address-set") :
            ("emailAddresses", None, "Email Addresses",
            customxml.EmailAddressSet),
    }
    _fieldList = [v for _ignore_k, v in sorted(_fieldMap.iteritems(), key=lambda x:x[0])]


    def propertyToField(self, property, match):
        """
        If property is a DAV property that maps to a directory field, return
        that field's name, otherwise return None
        """
        field, converter, _ignore_description, _ignore_xmlClass = self._fieldMap.get(
            property.qname(), (None, None, None, None))
        if field is None:
            return (None, None)
        elif converter is not None:
            field, match = converter(match)
        return (field, match)


    def principalSearchPropertySet(self):
        props = []
        for _ignore_field, _ignore_converter, description, xmlClass in self._fieldList:
            props.append(
                davxml.PrincipalSearchProperty(
                    davxml.PropertyContainer(
                        xmlClass()
                    ),
                    davxml.Description(
                        davxml.PCDATAElement(description),
                        **{"xml:lang": "en"}
                    ),
                )
            )

        return davxml.PrincipalSearchPropertySet(*props)



class DirectoryPrincipalProvisioningResource (DirectoryProvisioningResource):
    """
    Collection resource which provisions directory principals as its children.
    """
    def __init__(self, url, directory):
        DirectoryProvisioningResource.__init__(self, url, directory)

        # FIXME: Smells like a hack
        self.directory.setPrincipalCollection(self)

        #
        # Create children
        #
        for name, recordType in [
            (self.directory.recordTypeToOldName(r), r)
            for r in self.directory.recordTypes()
        ]:
            self.putChild(
                name,
                DirectoryPrincipalTypeProvisioningResource(
                    self, name, recordType
                )
            )

        self.putChild(uidsResourceName, DirectoryPrincipalUIDProvisioningResource(self))


    @inlineCallbacks
    def principalForUID(self, uid):
        child = (yield self.getChild(uidsResourceName))
        returnValue((yield child.getChild(uid)))


    @inlineCallbacks
    def _principalForURI(self, uri):
        scheme, netloc, path, _ignore_params, _ignore_query, _ignore_fragment = urlparse(uri)

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

            if (host != config.ServerHostName and
                host not in config.Scheduling.Options.PrincipalHostAliases):
                returnValue(None)

            if port != {
                "http" : config.HTTPPort,
                "https": config.SSLPort,
            }[scheme]:
                returnValue(None)

        elif scheme == "urn":
            if path.startswith("uuid:"):
                returnValue((yield self.principalForUID(path[5:])))
            else:
                returnValue(None)
        else:
            returnValue(None)

        if not path.startswith(self._url):
            returnValue(None)

        path = path[len(self._url) - 1:]

        segments = [unquote(s) for s in path.rstrip("/").split("/")]
        if segments[0] == "" and len(segments) == 3:
            typeResource = yield self.getChild(segments[1])
            if typeResource is not None:
                principalResource = yield typeResource.getChild(segments[2])
                if principalResource:
                    returnValue(principalResource)

        returnValue(None)


    @inlineCallbacks
    def principalForCalendarUserAddress(self, address):
        # First see if the address is a principal URI
        principal = yield self._principalForURI(address)
        if principal:
            if (
                isinstance(principal, DirectoryCalendarPrincipalResource) and
                principal.record.hasCalendars
            ):
                returnValue(principal)
        else:
            # Next try looking it up in the directory
            record = yield self.directory.recordWithCalendarUserAddress(address)
            if record is not None and record.hasCalendars:
                returnValue((yield self.principalForRecord(record)))

        log.debug("No principal for calendar user address: %r" % (address,))
        returnValue(None)


    @inlineCallbacks
    def principalForRecord(self, record):
        child = (yield self.getChild(uidsResourceName))
        returnValue((yield child.principalForRecord(record)))


    ##
    # Static
    ##

    def createSimilarFile(self, path):
        log.error("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)


    def getChild(self, name):
        if name == "":
            return succeed(self)
        else:
            return succeed(self.putChildren.get(name, None))


    def listChildren(self):
        return [
            self.directory.recordTypeToOldName(r)
            for r in self.directory.recordTypes()
        ]


    ##
    # ACL
    ##

    def principalCollections(self):
        return (self,)


    ##
    # Proxy callback from directory service
    ##

    def isProxyFor(self, record1, record2):
        """
        Test whether the principal identified by directory record1 is a proxy for the principal identified by
        record2.

        @param record1: directory record for a user
        @type record1: L{DirectoryRecord}
        @param record2: directory record to test with
        @type record2: L{DirectoryRercord}

        @return: C{True} if record1 is a proxy for record2, otherwise C{False}
        @rtype: C{bool}
        """

        principal1 = self.principalForUID(record1.uid)
        principal2 = self.principalForUID(record2.uid)
        return principal1.isProxyFor(principal2)



class DirectoryPrincipalTypeProvisioningResource (DirectoryProvisioningResource):
    """
    Collection resource which provisions directory principals of a
    specific type as its children, indexed by short name.
    """
    def __init__(self, parent, name, recordType):
        """
        @param parent: the parent L{DirectoryPrincipalProvisioningResource}.
        @param recordType: the directory record type to provision.
        """
        DirectoryProvisioningResource.__init__(
            self,
            joinURL(parent.principalCollectionURL(), name) + "/",
            parent.directory
        )

        self.recordType = recordType
        self.parent = parent


    def principalForUID(self, uid):
        return self.parent.principalForUID(uid)


    def principalForCalendarUserAddress(self, address):
        return self.parent.principalForCalendarUserAddress(address)


    def principalForRecord(self, record):
        return self.parent.principalForRecord(record)

    ##
    # Static
    ##


    def createSimilarFile(self, path):
        log.error("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)


    def getChild(self, name):
        if name == "":
            return succeed(self)
        else:
            return self.principalForShortName(self.recordType, name)


    @inlineCallbacks
    def listChildren(self):
        children = []
        if config.EnablePrincipalListings:
            try:
                for record in (
                    yield self.directory.recordsWithRecordType(self.recordType)
                ):
                    for shortName in record.shortNames:
                        children.append(shortName)
            except AttributeError:
                log.warn("Cannot list children of record type {rt}",
                         rt=self.recordType.name)
            returnValue(children)

        else:
            # Not a listable collection
            raise HTTPError(responsecode.FORBIDDEN)

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
    def __init__(self, parent):
        """
        @param directory: an L{IDirectoryService} to provision calendars from.
        @param recordType: the directory record type to provision.
        """
        DirectoryProvisioningResource.__init__(
            self,
            joinURL(parent.principalCollectionURL(), uidsResourceName) + "/",
            parent.directory
        )

        self.parent = parent


    def principalForUID(self, uid):
        return self.parent.principalForUID(uid)


    def principalForCalendarUserAddress(self, address):
        return self.parent.principalForCalendarUserAddress(address)


    def principalForRecord(self, record):
        # MOVE2WHO
        if record is None: #  or not record.enabled:
            return succeed(None)

        # MOVE2WHO
        if record.hasCalendars or record.hasContacts:
            # XXX these are different features and one should not automatically
            # imply the other...
            principal = DirectoryCalendarPrincipalResource(self, record)
        else:
            principal = DirectoryPrincipalResource(self, record)
        return succeed(principal)

    ##
    # Static
    ##


    def createSimilarFile(self, path):
        log.error("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)


    @inlineCallbacks
    def getChild(self, name):
        if name == "":
            returnValue(self)

        if "#" in name:
            # This UID belongs to a sub-principal
            primaryUID, subType = name.split("#")
        else:
            primaryUID = name
            subType = None

        record = (yield self.directory.recordWithUID(primaryUID))
        primaryPrincipal = (yield self.principalForRecord(record))
        if primaryPrincipal is None:
            log.info("No principal found for UID: %s" % (name,))
            returnValue(None)

        if subType is None:
            returnValue(primaryPrincipal)
        else:
            returnValue((yield primaryPrincipal.getChild(subType)))


    def listChildren(self):
        # Not a listable collection
        raise HTTPError(responsecode.FORBIDDEN)

    ##
    # ACL
    ##


    def principalCollections(self):
        return self.parent.principalCollections()



class DirectoryPrincipalDetailElement(Element):
    """
    Element that can render the details of a
    L{CalendarUserDirectoryPrincipalResource}.
    """

    loader = XMLFile(thisModule.filePath.sibling(
        "directory-principal-resource.html")
    )


    def __init__(self, resource):
        super(DirectoryPrincipalDetailElement, self).__init__()
        self.resource = resource


    @renderer
    def serversEnabled(self, request, tag):
        """
        Renderer for when servers are enabled.
        """
        if not config.Servers.Enabled:
            return ""
        record = self.resource.record
        return tag.fillSlots(
            hostedAt=str(record.serverURI()),
        )


    @renderer
    def principal(self, request, tag):
        """
        Top-level renderer in the template.
        """
        record = self.resource.record
        try:
            if isinstance(record.guid, uuid.UUID):
                guid = str(record.guid).upper()
            else:
                guid = record.guid
        except AttributeError:
            guid = ""
        try:
            emailAddresses = record.emailAddresses
        except AttributeError:
            emailAddresses = []
        return tag.fillSlots(
            directoryGUID=str(record.service.guid),
            realm=str(record.service.realmName),
            principalGUID=guid,
            recordType=record.service.recordTypeToOldName(record.recordType),
            shortNames=",".join(record.shortNames),
            # MOVE2WHO: need this?
            # securityIDs=",".join(record.authIDs),
            fullName=str(record.displayName),
            # MOVE2WHO: need this?
            # firstName=str(record.firstName),
            # MOVE2WHO: need this?
            # lastName=str(record.lastName),
            emailAddresses=formatList(emailAddresses),
            principalUID=str(self.resource.principalUID()),
            principalURL=formatLink(self.resource.principalURL()),
            alternateURIs=formatLinks(self.resource.alternateURIs()),
            groupMembers=self.resource.groupMembers().addCallback(
                formatPrincipals
            ),
            groupMemberships=self.resource.groupMemberships().addCallback(
                formatPrincipals
            ),
            readWriteProxyFor=self.resource.proxyFor(True).addCallback(
                formatPrincipals
            ),
            readOnlyProxyFor=self.resource.proxyFor(False).addCallback(
                formatPrincipals
            ),
        )


    @renderer
    def extra(self, request, tag):
        """
        No-op; implemented in subclass.
        """
        return ''


    @renderer
    def enabledForCalendaring(self, request, tag):
        """
        No-op; implemented in subclass.
        """
        return ''


    @renderer
    def enabledForAddressBooks(self, request, tag):
        """
        No-op; implemented in subclass.
        """
        return ''



class DirectoryPrincipalElement(DirectoryElement):
    """
    L{DirectoryPrincipalElement} is a renderer for directory details.
    """

    @renderer
    def resourceDetail(self, request, tag):
        """
        Render the directory principal's details.
        """
        return DirectoryPrincipalDetailElement(self.resource)



class DirectoryCalendarPrincipalDetailElement(DirectoryPrincipalDetailElement):

    @renderer
    def extra(self, request, tag):
        """
        Renderer for extra directory body items for calendar/addressbook
        principals.
        """
        return tag


    @renderer
    def enabledForCalendaring(self, request, tag):
        """
        Renderer which returns its tag when the wrapped record is enabled for
        calendaring.
        """
        resource = self.resource
        record = resource.record
        if record.hasCalendars:
            return tag.fillSlots(
                calendarUserAddresses=formatLinks(
                    sorted(resource.calendarUserAddresses())
                ),
                calendarHomes=formatLinks(resource.calendarHomeURLs())
            )
        return ''


    @renderer
    def enabledForAddressBooks(self, request, tag):
        """
        Renderer which returnst its tag when the wrapped record is enabled for
        addressbooks.
        """
        resource = self.resource
        record = resource.record
        if record.hasContacts:
            return tag.fillSlots(
                addressBookHomes=formatLinks(resource.addressBookHomeURLs())
            )
        return ''



class DirectoryCalendarPrincipalElement(DirectoryPrincipalElement):
    """
    L{DirectoryPrincipalElement} is a renderer for directory details, with
    calendaring additions.
    """

    @renderer
    def resourceDetail(self, request, tag):
        """
        Render the directory calendar principal's details.
        """
        return DirectoryCalendarPrincipalDetailElement(self.resource)



class DirectoryPrincipalResource (
        PropfindCacheMixin, PermissionsMixIn, DAVPrincipalResource):
    """
    Directory principal resource.
    """

    def liveProperties(self):

        return super(DirectoryPrincipalResource, self).liveProperties() + (
            (calendarserver_namespace, "first-name"),
            (calendarserver_namespace, "last-name"),
            (calendarserver_namespace, "email-address-set"),
            # MOVE2WHO
            # davxml.ResourceID.qname(),
        )

    cacheNotifierFactory = DisabledCacheNotifier


    def __init__(self, parent, record):
        """
        @param parent: the parent of this resource.
        @param record: the L{IDirectoryRecord} that this resource represents.
        """
        super(DirectoryPrincipalResource, self).__init__()

        self.cacheNotifier = self.cacheNotifierFactory(self, cacheHandle="PrincipalToken")

        if self.isCollection():
            slash = "/"
        else:
            slash = ""

        assert record is not None, "Principal must have a directory record"

        self.record = record
        self.parent = parent

        url = joinURL(parent.principalCollectionURL(), self.principalUID()) + slash
        self._url = url

        # MOVE2WHO - hack: just adding an "s" using recordType.name (need a mapping)
        self._alternate_urls = tuple([
            joinURL(
                parent.parent.principalCollectionURL(),
                (record.recordType.name + "s"),
                quote(shortName.encode("utf-8"))
            ) + slash
            for shortName in record.shortNames
        ])


    def __str__(self):
        return "(%s)%s" % (self.record.recordType, self.record.shortNames[0])


    def __eq__(self, other):
        """
        Principals are the same if their principalURLs are the same.
        """
        if isinstance(other, DirectoryPrincipalResource):
            return (self.principalURL() == other.principalURL())
        else:
            return False


    def __ne__(self, other):
        return not self.__eq__(other)


    def __hash__(self):
        return hash(self.principalUID())


    @inlineCallbacks
    def readProperty(self, property, request):
        if type(property) is tuple:
            qname = property
        else:
            qname = property.qname()

        namespace, name = qname

        # MOVE2WHO -- does principal need ResourceID ?
        # if qname == davxml.ResourceID.qname():
        #     returnValue(davxml.ResourceID(davxml.HRef.fromString("urn:uuid:%s" % (self.record.guid,))))
        if namespace == calendarserver_namespace:

            # MOVE2WHO
            # if name == "first-name":
            #     firstName = self.record.firstName
            #     if firstName is not None:
            #         returnValue(customxml.FirstNameProperty(firstName))
            #     else:
            #         returnValue(None)

            # elif name == "last-name":
            #     lastName = self.record.lastName
            #     if lastName is not None:
            #         returnValue(customxml.LastNameProperty(lastName))
            #     else:
            #         returnValue(None)

            if name == "email-address-set":
                try:
                    emails = self.record.emailAddresses
                except AttributeError:
                    emails = []
                returnValue(customxml.EmailAddressSet(
                    *[customxml.EmailAddressProperty(addr) for addr in sorted(emails)]
                ))

        result = (yield super(DirectoryPrincipalResource, self).readProperty(property, request))
        returnValue(result)


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(None)

    ##
    # HTTP
    ##


    def htmlElement(self):
        """
        Customize HTML rendering for directory principals.
        """
        return DirectoryPrincipalElement(self)

    ##
    # DAV
    ##


    def isCollection(self):
        return True


    def displayName(self):
        return self.record.displayName

    ##
    # ACL
    ##


    def _calendar_user_proxy_index(self):
        """
        Return the SQL database for calendar user proxies.

        @return: the L{ProxyDB} for the principal collection.
        """

        # The db is located in the principal collection root
        from twistedcaldav.directory.calendaruserproxy import ProxyDBService
        return ProxyDBService


    def alternateURIs(self):
        # FIXME: Add API to IDirectoryRecord for getting a record URI?
        return self._alternate_urls


    def principalURL(self):
        return self._url


    def url(self):
        return self.principalURL()


    def notifierID(self):
        return self.principalURL()


    @inlineCallbacks
    def isProxyFor(self, principal):
        """
        Determine whether this principal is a read-only or read-write proxy for the
        specified principal.
        """

        read_uids = (yield self.proxyFor(False))
        if principal in read_uids:
            returnValue(True)

        write_uids = (yield self.proxyFor(True))
        if principal in write_uids:
            returnValue(True)

        returnValue(False)


    @inlineCallbacks
    def proxyMode(self, principal):
        """
        Determine whether what proxy mode this principal has in relation to the one specified.
        """

        read_uids = (yield self.proxyFor(False))
        if principal in read_uids:
            returnValue("read")

        write_uids = (yield self.proxyFor(True))
        if principal in write_uids:
            returnValue("write")

        returnValue("none")


    @inlineCallbacks
    def proxyFor(self, readWrite):
        """
        Returns the set of principals currently delegating to this principal
        with the access indicated by the readWrite argument.  If readWrite is
        True, then write-access delegators are returned, otherwise the read-
        only-access delegators are returned.

        @param readWrite: Whether to look up read-write delegators, or
            read-only delegators
        @type readWrite: C{bool}

        @return: A Deferred firing with a set of principals
        """
        proxyFors = set()

        if config.EnableProxyPrincipals:
            childName = "calendar-proxy-{rw}-for".format(
                rw=("write" if readWrite else "read")
            )
            proxyForGroup = yield self.getChild(childName)
            if proxyForGroup:
                proxyFors = yield proxyForGroup.groupMembers()

                uids = set()
                for principal in tuple(proxyFors):
                    if principal.principalUID() in uids:
                        proxyFors.remove(principal)
                    else:
                        uids.add(principal.principalUID())

        returnValue(proxyFors)


    @inlineCallbacks
    def _getRelatives(self, method, record=None, relatives=None, records=None, proxy=None, infinity=False):
        if record is None:
            record = self.record
        if relatives is None:
            relatives = set()
        if records is None:
            records = set()

        if record not in records:
            records.add(record)
            for relative in (yield getattr(record, method)()):
                if relative not in records:
                    found = (yield self.parent.principalForRecord(relative))
                    if found is None:
                        log.error("No principal found for directory record: %r" % (relative,))
                    else:
                        if proxy:
                            if proxy == "read-write":
                                found = (yield found.getChild("calendar-proxy-write"))
                            else:
                                found = (yield found.getChild("calendar-proxy-read"))
                        relatives.add(found)

                    if infinity:
                        yield self._getRelatives(method, relative, relatives, records,
                            infinity=infinity)

        returnValue(relatives)


    def groupMembers(self):
        return self._getRelatives("members")


    def expandedGroupMembers(self):
        return self._getRelatives("members", infinity=True)


    @inlineCallbacks
    def groupMemberships(self, infinity=False):

        # cache = getattr(self.record.service, "groupMembershipCache", None)
        # if cache:
        #     log.debug("groupMemberships is using groupMembershipCache")
        #     guids = (yield self.record.cachedGroups())
        #     groups = set()
        #     for guid in guids:
        #         principal = yield self.parent.principalForUID(guid)
        #         if principal:
        #             groups.add(principal)
        # else:
        groups = yield self._getRelatives("groups", infinity=infinity)

        # MOVE2WHO
        # if config.EnableProxyPrincipals:
        #     # Get proxy group UIDs and map to principal resources
        #     proxies = []
        #     memberships = (yield self._calendar_user_proxy_index().getMemberships(self.principalUID()))
        #     for uid in memberships:
        #         subprincipal = yield self.parent.principalForUID(uid)
        #         if subprincipal:
        #             proxies.append(subprincipal)
        #         else:
        #             yield self._calendar_user_proxy_index().removeGroup(uid)

        #     groups.update(proxies)

        returnValue(groups)


    def expandedGroupMemberships(self):
        return self.groupMemberships(infinity=True)


    def groupsChanged(self):
        """
        A callback indicating the directory group membership for this principal
        has changed.  Update the cache token for this principal so the PROPFIND
        response cache is invalidated.
        """
        return self.cacheNotifier.changed()


    def principalCollections(self):
        return self.parent.principalCollections()


    def principalUID(self):
        return self.record.uid


    def serverURI(self):
        return self.record.serverURI()


    def server(self):
        return self.record.server()


    def thisServer(self):
        return self.record.thisServer()


    ##
    # Extra resource info
    ##

    @inlineCallbacks
    def setAutoSchedule(self, autoSchedule):
        self.record.autoSchedule = autoSchedule
        augmentRecord = (yield self.record.service.augmentService.getAugmentRecord(self.record.guid, self.record.recordType))
        augmentRecord.autoSchedule = autoSchedule
        (yield self.record.service.augmentService.addAugmentRecords([augmentRecord]))


    def getAutoSchedule(self):
        # MOVE2WHO
        return True
        # return self.record.autoSchedule


    def canAutoSchedule(self, organizer=None):
        """
        Determine the auto-schedule state based on record state, type and config settings.

        @param organizer: the CUA of the organizer trying to schedule this principal
        @type organizer: C{str}
        """
        return self.record.canAutoSchedule(organizer)


    @inlineCallbacks
    def setAutoScheduleMode(self, autoScheduleMode):
        self.record.autoScheduleMode = autoScheduleMode if autoScheduleMode in allowedAutoScheduleModes else "default"
        augmentRecord = (yield self.record.service.augmentService.getAugmentRecord(self.record.guid, self.record.recordType))
        augmentRecord.autoScheduleMode = autoScheduleMode
        (yield self.record.service.augmentService.addAugmentRecords([augmentRecord]))


    def getAutoScheduleMode(self, organizer=None):
        """
        Return the auto schedule mode value for the principal.  If the optional
        organizer is provided, and that organizer is a member of the principal's
        auto-accept group, return "automatic" instead; this allows specifying a
        priliveged group whose scheduling requests are automatically accepted or
        declined, regardless of whether the principal is normally managed by a
        delegate.

        @param organizer: the CUA of the organizer scheduling this principal
        @type organizer: C{str}
        @return: auto schedule mode; one of: none, accept-always, decline-always,
            accept-if-free, decline-if-busy, automatic (see stdconfig.py)
        @rtype: C{str}
        """
        return self.record.getAutoScheduleMode(organizer)


    @inlineCallbacks
    def setAutoAcceptGroup(self, autoAcceptGroup):
        """
        Sets the group whose members can automatically schedule with this principal
        even if this principal's auto-schedule is False (assuming no conflicts).

        @param autoAcceptGroup:  GUID of the group
        @type autoAcceptGroup: C{str}
        """
        self.record.autoAcceptGroup = autoAcceptGroup
        augmentRecord = (yield self.record.service.augmentService.getAugmentRecord(self.record.guid, self.record.recordType))
        augmentRecord.autoAcceptGroup = autoAcceptGroup
        (yield self.record.service.augmentService.addAugmentRecords([augmentRecord]))


    def getAutoAcceptGroup(self):
        """
        Returns the GUID of the auto accept group assigned to this principal, or empty
        string if not assigned
        """
        return self.record.autoAcceptGroup


    def autoAcceptFromOrganizer(self, organizer):
        """
        Is the organizer a member of this principal's autoAcceptGroup?

        @param organizer: CUA of the organizer
        @type organizer: C{str}
        @return: True if the autoAcceptGroup is assigned, and the organizer is a member
            of that group.  False otherwise.
        @rtype: C{bool}
        """
        return self.record.autoAcceptFromOrganizer()


    def getCUType(self):
        return self.record.getCUType()

    ##
    # Static
    ##


    def createSimilarFile(self, path):
        log.error("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)


    @inlineCallbacks
    def locateChild(self, req, segments):
        child = (yield self.getChild(segments[0]))
        if child is not None:
            returnValue((child, segments[1:]))
        returnValue((None, ()))


    def getChild(self, name):
        if name == "":
            return succeed(self)

        return succeed(None)


    def listChildren(self):
        return ()



class DirectoryCalendarPrincipalResource(DirectoryPrincipalResource,
                                         CalendarPrincipalResource):
    """
    Directory calendar principal resource.
    """

    def liveProperties(self):
        return DirectoryPrincipalResource.liveProperties(self) + CalendarPrincipalResource.liveProperties(self)


    def calendarsEnabled(self):
        return self.record.calendarsEnabled()


    def addressBooksEnabled(self):
        return config.EnableCardDAV and self.record.hasContacts


    @inlineCallbacks
    def readProperty(self, property, request):
        # Ouch, multiple inheritance.
        result = (yield DirectoryPrincipalResource.readProperty(self, property, request))
        if not result:
            result = (yield CalendarPrincipalResource.readProperty(self, property, request))
        returnValue(result)


    ##
    # CalDAV
    ##


    def calendarUserAddresses(self):
        return self.record.calendarUserAddresses


    def htmlElement(self):
        """
        Customize HTML generation for calendar principals.
        """
        return DirectoryCalendarPrincipalElement(self)


    def canonicalCalendarUserAddress(self):
        """
        Return a CUA for this principal, preferring in this order:
            urn:uuid: form
            mailto: form
            first in calendarUserAddresses( ) list
        """
        return self.record.canonicalCalendarUserAddress()


    def enabledAsOrganizer(self):
        return self.record.enabledAsOrganizer()


    @inlineCallbacks
    def scheduleInbox(self, request):
        home = yield self.calendarHome(request)
        if home is None:
            returnValue(None)

        inbox = yield home.getChild("inbox")
        if inbox is None:
            returnValue(None)

        returnValue(inbox)


    @inlineCallbacks
    def notificationCollection(self, request):

        notification = None
        if config.Sharing.Enabled:
            home = yield self.calendarHome(request)
            if home is not None:
                notification = yield home.getChild("notification")
        returnValue(notification)


    def calendarHomeURLs(self):
        if self.record.hasCalendars:
            homeURL = self._homeChildURL(None)
        else:
            homeURL = ""
        return (homeURL,) if homeURL else ()


    def scheduleInboxURL(self):
        return self._homeChildURL("inbox/")


    def scheduleOutboxURL(self):
        return self._homeChildURL("outbox/")


    def dropboxURL(self):
        if config.EnableDropBox or config.EnableManagedAttachments:
            return self._homeChildURL("dropbox/")
        else:
            return None


    def notificationURL(self):
        if config.Sharing.Enabled:
            return self._homeChildURL("notification/")
        else:
            return None


    def addressBookHomeURLs(self):
        if self.record.hasContacts:
            homeURL = self._addressBookHomeChildURL(None)
        else:
            homeURL = ""
        return (homeURL,) if homeURL else ()


    def _homeChildURL(self, name):
        if not hasattr(self, "calendarHomeURL"):
            if not hasattr(self.record.service, "calendarHomesCollection"):
                return None
            self.calendarHomeURL = joinURL(
                self.record.service.calendarHomesCollection.url(),
                uidsResourceName,
                self.record.uid
            ) + "/"

            # Prefix with other server if needed
            if not self.thisServer():
                self.calendarHomeURL = joinURL(self.serverURI(), self.calendarHomeURL)

        url = self.calendarHomeURL
        if url is None:
            return None
        else:
            return joinURL(url, name) if name else url


    def calendarHome(self, request):
        # FIXME: self.record.service.calendarHomesCollection smells like a hack
        service = self.record.service
        if hasattr(service, "calendarHomesCollection"):
            return service.calendarHomesCollection.homeForDirectoryRecord(self.record, request)
        else:
            return succeed(None)


    def _addressBookHomeChildURL(self, name):
        if not hasattr(self, "addressBookHomeURL"):
            if not hasattr(self.record.service, "addressBookHomesCollection"):
                return None
            self.addressBookHomeURL = joinURL(
                self.record.service.addressBookHomesCollection.url(),
                uidsResourceName,
                self.record.uid
            ) + "/"

            # Prefix with other server if needed
            if not self.thisServer():
                self.addressBookHomeURL = joinURL(self.serverURI(), self.addressBookHomeURL)

        url = self.addressBookHomeURL
        if url is None:
            return None
        else:
            return joinURL(url, name) if name else url


    def addressBookHome(self, request):
        # FIXME: self.record.service.addressBookHomesCollection smells like a hack
        service = self.record.service
        if hasattr(service, "addressBookHomesCollection"):
            return service.addressBookHomesCollection.homeForDirectoryRecord(self.record, request)
        else:
            return succeed(None)

    ##
    # Static
    ##


    def getChild(self, name):
        if name == "":
            return succeed(self)

        if config.EnableProxyPrincipals and name in (
            "calendar-proxy-read", "calendar-proxy-write",
            "calendar-proxy-read-for", "calendar-proxy-write-for",
            ):
            # name is required to be str
            from twistedcaldav.directory.calendaruserproxy import (
                CalendarUserProxyPrincipalResource
            )
            return succeed(CalendarUserProxyPrincipalResource(self, str(name)))
        else:
            return succeed(None)


    def listChildren(self):
        if config.EnableProxyPrincipals:
            return (
                "calendar-proxy-read", "calendar-proxy-write",
                "calendar-proxy-read-for", "calendar-proxy-write-for",
            )
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



