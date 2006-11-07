##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Initial setup of CalDAV repository resource hierarchy, together with optional
auto-provisioning of user calendar home collections and principals, with appropriate
properties, access control etc setup.
"""

__all__ = ["RepositoryBuilder"]

from twisted.application.internet import SSLServer, TCPServer
from twisted.application.service import Application, IServiceCollection, MultiService
from twisted.cred.portal import Portal
from twisted.internet.ssl import DefaultOpenSSLContextFactory
from twisted.python import log
from twisted.python.filepath import FilePath
from twisted.python.reflect import namedObject
from twisted.web2.auth import basic, digest
from twisted.web2.channel.http import HTTPFactory
from twisted.web2.dav import auth, davxml
from twisted.web2.dav.element.base import PCDATAElement
from twisted.web2.dav.element.parser import lookupElement
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.dav.util import joinURL
from twisted.web2.log import LogWrapperResource
from twisted.web2.server import Site

from twistedcaldav import caldavxml, customxml
from twistedcaldav import authkerb
from twistedcaldav.logging import RotatingFileAccessLoggingObserver
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.static import CalDAVFile, CalendarHomeFile, CalendarPrincipalFile
from twistedcaldav.directory.cred import DirectoryCredentialsChecker

import os

from xml.dom.minidom import Element
from xml.dom.minidom import Text
import xml.dom.minidom

ELEMENT_REPOSITORY = "repository"

ELEMENT_DOCROOT = "docroot"
ELEMENT_COLLECTION = "collection"
ELEMENT_PYTYPE = "pytype"
ELEMENT_PARAMS = "params"
ELEMENT_PARAM = "param"
ELEMENT_KEY = "key"
ELEMENT_VALUE = "value"
ELEMENT_PROPERTIES = "properties"
ELEMENT_PROP = "prop"
ELEMENT_MEMBERS = "members"

ELEMENT_ACL = "acl"
ELEMENT_ACE = "ace"
ELEMENT_PRINCIPAL = "principal"
ELEMENT_HREF = "href"
ELEMENT_ALL = "all"
ELEMENT_AUTHENTICATED = "authenticated"
ELEMENT_UNAUTHENTICATED = "unauthenticated"
ELEMENT_GRANT = "grant"
ELEMENT_DENY = "deny"
ELEMENT_PRIVILEGE = "privilege"
ELEMENT_PROTECTED = "protected"
ELEMENT_INHERITABLE = "inheritable"

ELEMENT_READ = "read"

ATTRIBUTE_VALUE_YES = "yes"
ATTRIBUTE_VALUE_NO = "no"

ATTRIBUTE_AUTO_PCS = "auto-principal-collection-set"

ATTRIBUTE_NAME = "name"
ATTRIBUTE_TAG = "tag"
ATTRIBUTE_ACCOUNT = "account"
ATTRIBUTE_INITIALIZE = "initialize"

ATTRVALUE_NONE = "none"
ATTRVALUE_PRINCIPALS = "principals"
ATTRVALUE_CALENDARS = "calendars"

ELEMENT_AUTHENTICATION = "authentication"
ELEMENT_BASIC = "basic"
ELEMENT_DIGEST = "digest"
ELEMENT_KERBEROS = "kerberos"
ELEMENT_REALM = "realm"
ELEMENT_SERVICE = "service"

ATTRIBUTE_ENABLE = "enable"
ATTRIBUTE_ONLYSSL = "onlyssl"
ATTRIBUTE_CREDENTIALS = "credentials"

ATTRIBUTE_VALUE_PROPERTY = "property"
ATTRIBUTE_VALUE_DIRECTORY = "directory"
ATTRIBUTE_VALUE_KERBEROS = "kerberos"

ELEMENT_ACCOUNTS = "accounts"
ELEMENT_USER = "user"
ELEMENT_USERID = "uid"
ELEMENT_PASSWORD = "pswd"
ELEMENT_NAME = "name"
ELEMENT_CUADDR = "cuaddr"
ELEMENT_CUHOME = "cuhome"
ELEMENT_CALENDAR = "calendar"
ELEMENT_QUOTA = "quota"
ELEMENT_AUTORESPOND = "autorespond"
ELEMENT_CANPROXY = "canproxy"
ATTRIBUTE_REPEAT = "repeat"

def startServer(docroot, repo, doacct, doacl, dossl, keyfile, certfile, onlyssl, port, sslport, maxsize, quota, serverlogfile, manhole):
    """
    Start the server using XML-based configuration details and supplied .plist based options.
    """
    
    # Make sure SSL options make sense
    if not dossl and onlyssl:
        dossl = True
    
    # Check the file paths for validity
    if os.path.exists(docroot):
        print "Document root is: %s" % (docroot,)
    else:
        raise IOError("No such docroot: %s" % (docroot,))
    
    if os.path.exists(repo):
        print "Repository configuration is: %s" % (repo,)
    else:
        raise IOError("No such repo: %s" % (repo,))
    
    if dossl:
        if os.path.exists(keyfile):
            print "Using SSL private key file: %s" % (keyfile,)
        else:
            raise IOError("SSL Private Key file does not exist: %s" % (keyfile,))
    
        if os.path.exists(certfile):
            print "Using SSL certificate file: %s" % (certfile,)
        else:
            raise IOError("SSL Certificate file does not exist: %s" % (certfile,))
    
    # We need a special service for the access log
    class Web2Service(MultiService):
        def __init__(self, logObserver):
            self.logObserver = logObserver
            MultiService.__init__(self)
    
        def startService(self):
            MultiService.startService(self)
            self.logObserver.start()
    
        def stopService(self):
            MultiService.stopService(self)
            self.logObserver.stop()
    
    # Build the server
    builder = RepositoryBuilder(docroot,
                                doAccounts=doacct,
                                resetACLs=doacl,
                                maxsize=maxsize,
                                quota=quota)
    builder.buildFromFile(repo)
    rootresource = builder.docRoot.collection.resource
    
    application = Application("CalDAVServer")
    parent      = IServiceCollection(application)
    web2        = Web2Service(RotatingFileAccessLoggingObserver(serverlogfile))
    web2.setServiceParent(parent)
    parent = web2
    
    # Configure appropriate authentication 
    authenticator = builder.authentication.getEnabledAuthenticator()
    
    portal = Portal(auth.DavRealm())
    if authenticator.credentials == ATTRIBUTE_VALUE_PROPERTY:
        portal.registerChecker(auth.TwistedPropertyChecker())
        print "Using property-based password checker."
    elif authenticator.credentials == ATTRIBUTE_VALUE_DIRECTORY:
        portal.registerChecker(DirectoryCredentialsChecker())
        print "Using directory-based password checker."
    elif authenticator.credentials == ATTRIBUTE_VALUE_KERBEROS:
        if authenticator.type == "basic":
            portal.registerChecker(authkerb.BasicKerberosCredentialsChecker())
        elif authenticator.type == "kerberos":
            portal.registerChecker(authkerb.NegotiateCredentialsChecker())
        print "Using Kerberos-based password checker."
    
    if authenticator.type == "basic":
        if authenticator.credentials == ATTRIBUTE_VALUE_KERBEROS:
            credentialFactories = (authkerb.BasicKerberosCredentialFactory(authenticator.service, authenticator.realm),)
        else:
            credentialFactories = (basic.BasicCredentialFactory(authenticator.realm),)
        print "Using HTTP BASIC authentication."
    elif authenticator.type == "digest":
        credentialFactories = (digest.DigestCredentialFactory("md5", authenticator.realm),)
        print "Using HTTP DIGEST authentication."
    elif authenticator.type == "kerberos":
        credentialFactories = (authkerb.NegotiateCredentialFactory(authenticator.service),)
        print "Using HTTP NEGOTIATE authentication."
    
    loginInterfaces = (auth.IPrincipal,)
    
    # Build the site and server instances
    site = Site(LogWrapperResource(auth.AuthenticationWrapper(rootresource, 
                                                              portal,
                                                              credentialFactories,
                                                              loginInterfaces)))
    
    factory = HTTPFactory(site)
    
    if not onlyssl:
        print "Starting http server"
        TCPServer(port, factory).setServiceParent(parent)
    
    if dossl:
        print "Starting https server"
        sslContext = DefaultOpenSSLContextFactory(keyfile, certfile)
        SSLServer(sslport, factory, sslContext).setServiceParent(parent)

    if manhole:
        print "Starting manhole on port %d" % (manhole,)
        from twisted.manhole.telnet import ShellFactory
        from twisted.internet import reactor
        manhole_factory = ShellFactory()
        reactor.listenTCP(manhole, manhole_factory)
        manhole_factory.username = "admin"
        manhole_factory.password = ""
        manhole_factory.namespace["site"] = site
        manhole_factory.namespace["portal"] = portal

    return application, site

class RepositoryBuilder (object):
    """
    Builds a repository hierarchy at a supplied document root file system path,
    and optionally provisions accounts.
    """
    
    def __init__(self, docroot, doAccounts, resetACLs = False, maxsize = None, quota = None):
        """
        @param docroot:    file system path to use as the root.
        @param doAccounts: if True accounts will be auto-provisioned, if False
            no auto-provisioning is done
        @param resetACLs:  if True, when auto-provisioning access control privileges are initialised
            in an appropriate fashion for user accounts, if False no privileges are set or changed.
        @param maxsize:    maximum size in bytes for any calendar object resource, C{int} to set size,
            if <= 0, then no limit will be set.
        @param quota:    maximum quota size in bytes for a user's calendar home, C{int} to set size,
            if <= 0, then no limit will be set.
        """
        self.docRoot = DocRoot(docroot)
        self.doAccounts = doAccounts
        self.authentication = Authentication()
        self.accounts = Provisioner()
        self.resetACLs = resetACLs
        self.maxsize = maxsize
        self.quota = quota
        
        if self.maxsize <= 0:
            self.maxsized = None
        if self.quota <= 0:
            self.quota = None
        
    def buildFromFile(self, file):
        """
        Parse the required information from an XML file.
        @param file: the path of the XML file to parse.
        """
        # Read in XML
        fd = open(file, "r")
        doc = xml.dom.minidom.parse( fd )
        fd.close()

        # Verify that top-level element is correct
        repository_node = doc._get_documentElement()
        if repository_node._get_localName() != ELEMENT_REPOSITORY:
            self.log("Ignoring file \"%s\" because it is not a repository builder file" % (file,))
            return
        self.parseXML(repository_node)
        
        self.docRoot.build()
        if self.doAccounts:
            self.accounts.provision(
                self.docRoot.principalCollections,
                self.docRoot.accountCollection,
                self.docRoot.initCollections,
                self.docRoot.calendarHome,
                self.resetACLs)
            
        # Handle global quota value
        CalendarHomeFile.quotaLimit = self.quota
        CalDAVResource.sizeLimit = self.maxsize

    def parseXML(self, node):
        """
        Parse the XML root node from the repository configuration document.
        @param node: the L{Node} to parse.
        """
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_DOCROOT:
                self.docRoot.parseXML(child)
            elif child._get_localName() == ELEMENT_AUTHENTICATION:
                self.authentication.parseXML(child)
            elif child._get_localName() == ELEMENT_ACCOUNTS:
                self.accounts.parseXML(child)

class DocRoot (object):
    """
    Represents the hierarchy of resource collections that form the CalDAV repository.
    """
    def __init__(self, docroot):
        """
        @param docroot: the file system path for the root of the hierarchy.
        """
        self.collection = None
        self.path = docroot
        self.principalCollections = []
        self.accountCollection = None
        self.initCollections = []
        self.calendarHome = None
        self.autoPrincipalCollectionSet = True
        
    def parseXML(self, node):
        """
        Parse the XML collection nodes from the repository configuration document.
        @param node: the L{Node} to parse.
        """
        if node.hasAttribute(ATTRIBUTE_AUTO_PCS):
            self.autoPrincipalCollectionSet = (node.getAttribute(ATTRIBUTE_AUTO_PCS) == ATTRIBUTE_VALUE_YES)

        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_COLLECTION:
                self.collection = Collection()
                self.collection.parseXML(child, self)
                break

    def build(self):
        """
        Build the entire repository starting at the root resource.
        """
        self.collection.build(self.path, "/")
        
        # Setup the principal-collection-set property if required
        if self.autoPrincipalCollectionSet:
            # Check that a principal collection was actually created and 'tagged'
            if not self.principalCollections:
                log.msg("Cannot create a DAV:principal-collection-set property on the root resource because there are no principal collections.")
                return
            
            # Create the private property
            hrefs = []
            for collection in self.principalCollections:
                hrefs.append(davxml.HRef.fromString(collection.uri))
            pcs = davxml.PrincipalCollectionSet(*hrefs)
            self.collection.resource.writeDeadProperty(pcs)

class Collection (object):
    """
    Contains information about a collection in the repository.
    """
    def __init__(self):
        self.name = None
        self.pytype = "twistedcaldav.static.CalDAVFile" # FIXME: Why not None?
        self.params = {}
        self.properties = []
        self.acl = None
        self.members = []
        self.resource = None
        self.uri = None

    def parseXML(self, node, builder):
        """
        Parse the XML collection node from the repository configuration document.
        @param node:    the L{Node} to parse.
        @param builder: the L{RepositoryBuilder} in use.
        """
        if node.hasAttribute(ATTRIBUTE_NAME):
            self.name = node.getAttribute(ATTRIBUTE_NAME).encode("utf-8")
        if node.hasAttribute(ATTRIBUTE_TAG):
            tag = node.getAttribute(ATTRIBUTE_TAG)
            if tag == ATTRVALUE_PRINCIPALS:
                builder.principalCollections.append(self)
            elif tag == ATTRVALUE_CALENDARS:
                builder.calendarHome = self
        if node.hasAttribute(ATTRIBUTE_ACCOUNT) and node.getAttribute(ATTRIBUTE_ACCOUNT) == ATTRIBUTE_VALUE_YES:
            builder.accountCollection = self
        if node.hasAttribute(ATTRIBUTE_INITIALIZE) and node.getAttribute(ATTRIBUTE_INITIALIZE) == ATTRIBUTE_VALUE_YES:
            builder.initCollections.append(self)
        
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_PYTYPE:
                if child.firstChild is not None:
                   self.pytype = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_PARAMS:
                self.parseParamsXML(child)
            elif child._get_localName() == ELEMENT_PROPERTIES:
                self.parsePropertiesXML(child)
            elif child._get_localName() == ELEMENT_MEMBERS:
                for member in child._get_childNodes():
                    if member._get_localName() == ELEMENT_COLLECTION:
                        collection = Collection()
                        collection.parseXML(member, builder)
                        self.members.append(collection)
    
    def parseParamsXML(self, node):
        """
        Parse the XML node for parameters for the collection.
         @param node: the L{Node} to parse.
        """
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_PARAM:
                self.parseParamXML(child)

    def parseParamXML(self, node):
        """
        Parse the XML node for a parameter for the collection.
         @param node: the L{Node} to parse.
        """
        key = None
        value = None
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_KEY:
                if child.firstChild is not None:
                   key = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_VALUE:
                if child.firstChild is not None:
                   value = child.firstChild.data.encode("utf-8")

        if (key is not None) and (value is not None):
            self.params[key] = value

    def parsePropertiesXML(self, node):
        """
        Parse the XML node for properties in the collection.
        @param node: the L{Node} to parse.
        """
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_ACL:
                self.acl = ACL()
                self.acl.parseXML(child)
            elif child._get_localName() == ELEMENT_PROP:
                self.properties.append(Prop())
                self.properties[-1].parseXML(child)

    def build(self, docroot, urlroot):
        """
        Create this collection, initialising any properties and then create any child
        collections.
        @param docroot: the file system path to create the collection in.
        @param urlroot: the URI path root to create the collection resource in.
        """
        mypath = docroot
        myurl = urlroot
        if self.name is not None:
            mypath = os.path.join(mypath, self.name)
            myurl = joinURL(urlroot, self.name + "/")

        if not os.path.exists(mypath):
            os.mkdir(mypath)

        try:
            resource_class = namedObject(self.pytype)
        except:
            log.err("Unable to locate Python class %r" % (self.pytype,))
            raise
        kwargs = {}
        argnames = resource_class.__init__.func_code.co_varnames
        for name, value in (
            ("path", mypath),
            ("url" , myurl ),
        ):
            if name in argnames:
                kwargs[name] = value
        if self.params:
            kwargs["params"] = self.params
        self.resource = resource_class(**kwargs)

        self.uri = myurl
        
        # Set properties now
        for prop in self.properties:
            self.resource.writeDeadProperty(prop.prop)

        # Set ACL now
        if self.acl is not None:
            self.resource.setAccessControlList(self.acl.acl)

        for member in self.members:
            child = member.build(mypath, myurl)
            # Only putChild if one does not already exists
            if self.resource.putChildren.get(member.name, None) is None:
                self.resource.putChild(member.name, child)

        return self.resource

class Prop (object):
    """
    Parses a property from XML.
    """
    def __init__(self):
        self.prop = None

    def parseXML(self, node):
        """
        Parse the XML node for a property.
        @param node: the L{Node} to parse.
        """
    
        self.prop = self.toWebDAVElement(node.firstChild)

    def toWebDAVElement(self, node):
        """
        Convert XML dom element to WebDAVElement.
        """
        ns = node.namespaceURI
        name = node._get_localName()
        children = []
        for child in node._get_childNodes():
            if isinstance(child, Element):
                children.append(self.toWebDAVElement(child))
            elif isinstance(child, Text):
                children.append(PCDATAElement(child.data))
    
        propClazz = lookupElement((ns, name,))

        return propClazz(*children)
        
class ACL (object):
    """
    Parses a DAV:ACL from XML.
    """
    def __init__(self):
        self.acl = None

    def parseXML(self, node):
        """
        Parse the XML node for an ACL.
        @param node: the L{Node} to parse.
        """
        aces = []
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_ACE:
                aces.append(self.parseACEXML(child))
        self.acl = davxml.ACL(*aces)

    def parseACEXML(self, node):
        """
        Parse the XML node for an ACE.
        @param node: the L{Node} to parse.
        """
        principal = None
        grant = None
        deny = None
        protected = None
        inheritable = False
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_PRINCIPAL:
                principal = self.parsePrincipalXML(child)
            elif child._get_localName() == ELEMENT_GRANT:
                grant = self.parseGrantDenyXML(child)
            elif child._get_localName() == ELEMENT_DENY:
                deny = self.parseGrantDenyXML(child)
            elif child._get_localName() == ELEMENT_PROTECTED:
                protected = davxml.Protected()
            elif child._get_localName() == ELEMENT_INHERITABLE:
                inheritable = True
        items = []
        if principal is not None:
            items.append(principal)
        if grant is not None:
            items.append(grant)
        if deny is not None:
            items.append(deny)
        if protected is not None:
            items.append(protected)
        if inheritable:
            items.append(TwistedACLInheritable())
        return davxml.ACE(*items)
    
    def parsePrincipalXML(self, node):
        """
        Parse the XML node for a Principal.
        @param node: the L{Node} to parse.
        """
        item = None
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_HREF:
                if child.firstChild is not None:
                   item = davxml.HRef.fromString(child.firstChild.data)
                else:
                   item = davxml.HRef.fromString("")
            elif child._get_localName() == ELEMENT_ALL:
                item = davxml.All()
            elif child._get_localName() == ELEMENT_AUTHENTICATED:
                item = davxml.Authenticated()
            elif child._get_localName() == ELEMENT_UNAUTHENTICATED:
                item = davxml.Unauthenticated()
        return davxml.Principal(item)
    
    def parseGrantDenyXML(self, node):
        """
        Parse the XML node for Grant/Deny items.
        @param node: the L{Node} to parse.
        """
        items = []
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_PRIVILEGE:
                for privilege in child._get_childNodes():
                    if privilege._get_localName() == ELEMENT_ALL:
                        items.append(davxml.All())
                    elif privilege._get_localName() == ELEMENT_READ:
                        items.append(davxml.Read())
        if node._get_localName() == ELEMENT_GRANT:
            return davxml.Grant(davxml.Privilege(*items))
        else:
            return davxml.Deny(davxml.Privilege(*items))
        
    def parseInheritedXML(self, node):
        """
        Parse the XML node for inherited items.
        @param node: the L{Node} to parse.
        """
        item = None
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_HREF:
                if child.firstChild is not None:
                   item = davxml.HRef.fromString(child.firstChild.data)
                else:
                   item = davxml.HRef.fromString("")
        return davxml.Inherited(item)
    
class Provisioner (object):
    """
    Manages account provisioning.
    """

    def __init__(self):
        self.items = []
        self.principalCollections = None
        self.accountCollection = None
        self.initCollections = None
        self.calendarHome = None
        
    def parseXML( self, node ):
        """
        Parse the XML node for account information.
        @param node: the L{Node} to parse.
        """
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_USER:
                if child.hasAttribute( ATTRIBUTE_REPEAT ):
                    repeat = int(child.getAttribute( ATTRIBUTE_REPEAT ))
                else:
                    repeat = 1

                principal = ProvisionPrincipal("", "", "", [], "", [], None, None, False)
                principal.parseXML( child )
                self.items.append((repeat, principal))
    
    def provision(self, principalCollections, accountCollection, initCollections, calendarHome, resetACLs):
        """
        Carry out provisioning operation.
        @param principalCollections: a C{list} of L{Collection}'s for the principal collections.
        @param accountCollection: the L{Collection} of the principal collection in which to
            create user principals.
        @param initCollections: a C{list} of L{Collection}'s for the principal collections to be initialized.
        @param calendarHome:  the L{Collection} for the calendar home of principals.
        @param resetACLs: if True, ACL privileges on all resources related to the
            accounts being created are reset, if False no ACL privileges are changed.
        """
        self.principalCollections = principalCollections
        self.accountCollection = accountCollection
        self.initCollections = initCollections
        self.calendarHome = calendarHome

        if self.initCollections and self.calendarHome is not None:
            for collection in self.initCollections:
                collection.resource.initialize(
                    self.calendarHome.uri,
                    self.calendarHome.resource,
                )

        # Check for proper account home
        if not self.accountCollection:
            log.err("Accounts cannot be created: no principal collection was marked with an account attribute.")
            raise ValueError, "Accounts cannot be created."

        # Provision each user
        for repeat, principal in self.items:
            if repeat == 1:
                self.provisionOne(principal, resetACLs)
            else:
                for ctr in range(1, repeat+1):
                    self.provisionOne(principal.repeat(ctr), resetACLs)
    
    def provisionOne(self, item, resetACLs):
        """
        Provision one user account/
        @param item:      The account to provision.
        @param resetACLs: if True, ACL privileges on all resources related to the
            accounts being created are reset, if False no ACL privileges are changed.
        """
        principalURL = joinURL(self.accountCollection.uri, item.uid)

        # Create principal resource
        principal = FilePath(os.path.join(self.accountCollection.resource.fp.path, item.uid))
        principal_exists = principal.exists()
        if not principal_exists:
            principal.open("w").close()
            log.msg("Created principal: %s" % principalURL)
        principal = CalendarPrincipalFile(principal.path, principalURL)
        if len(item.pswd):
            principal.writeDeadProperty(auth.TwistedPasswordProperty.fromString(item.pswd))
        else:
            principal.removeDeadProperty(auth.TwistedPasswordProperty())
        if len(item.name):
            principal.writeDeadProperty(davxml.DisplayName.fromString(item.name))
        else:
            principal.removeDeadProperty(davxml.DisplayName())
        if len(item.cuaddrs):
            principal.writeDeadProperty(caldavxml.CalendarUserAddressSet(*[davxml.HRef(addr) for addr in item.cuaddrs]))
        else:
            principal.removeDeadProperty(caldavxml.CalendarUserAddressSet())

        if resetACLs or not principal_exists:
            principal.setAccessControlList(
                davxml.ACL(
                    davxml.ACE(
                        davxml.Principal(davxml.HRef.fromString(principalURL)),
                        davxml.Grant(
                            davxml.Privilege(davxml.Read()),
                        ),
                    ),
                )
            )

        # If the user does not have any calendar user addresses we do not create a calendar home for them
        if not item.cuaddrs and not item.calendars:
            return

        if item.cuhome:
            principal.writeDeadProperty(caldavxml.CalendarHomeSet(davxml.HRef.fromString(item.cuhome)))
        else:
            # Create calendar home
            homeURL = joinURL(self.calendarHome.uri, item.uid)
            home = FilePath(os.path.join(self.calendarHome.resource.fp.path, item.uid))
            home_exists = home.exists()
            if not home_exists:
                home.createDirectory()
            home = CalendarHomeFile(home.path)
    
            # Handle ACLs on calendar home
            if resetACLs or not home_exists:
                if item.acl:
                    home.setAccessControlList(item.acl.acl)
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
                                davxml.Principal(davxml.HRef.fromString(principalURL)),
                                davxml.Grant(
                                    davxml.Privilege(davxml.All()),
                                ),
                                TwistedACLInheritable(),
                            ),
                        )
                    )
            
            # Handle quota on calendar home
            home.setQuotaRoot(None, item.quota)
    
            # Save the calendar-home-set, schedule-inbox and schedule-outbox properties
            principal.writeDeadProperty(caldavxml.CalendarHomeSet(davxml.HRef.fromString(homeURL + "/")))
            principal.writeDeadProperty(caldavxml.ScheduleInboxURL(davxml.HRef.fromString(joinURL(homeURL, "inbox/"))))
            principal.writeDeadProperty(caldavxml.ScheduleOutboxURL(davxml.HRef.fromString(joinURL(homeURL, "outbox/"))))
            
            # Set ACLs on inbox and outbox
            if resetACLs or not home_exists:
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
                if item.autorespond:
                    inbox.writeDeadProperty(customxml.TwistedScheduleAutoRespond())
    
                outbox = home.getChild("outbox")
                if outbox.hasDeadProperty(davxml.ACL()):
                    outbox.removeDeadProperty(davxml.ACL())
    
            calendars = []
            for calendar in item.calendars:
                childURL = joinURL(homeURL, calendar)
                child = CalDAVFile(os.path.join(home.fp.path, calendar))
                child_exists = child.exists()
                if not child_exists:
                    c = child.createCalendarCollection()
                    assert c.called
                    c = c.result
                    
                calendars.append(childURL)
                if (resetACLs or not child_exists):
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

class ProvisionPrincipal (object):
    """
    Contains provision information for one user.
    """
    def __init__(self, uid, pswd, name, cuaddrs, cuhome, calendars, acl, quota, autorespond):
        """
        @param uid:           user id.
        @param pswd:          clear-text password for this user.
        @param name:          common name of user.
        @param cuaddr:        list of calendar user addresses.
        @param calendars:     list of calendars to auto-create.
        @param acl:           ACL to apply to calendar home
        @param quota:         quota allowed on user's calendar home C{int} size in bytes
            or C{None} if no quota
        @param autorespond    auto-respond to scheduling requests
        """
        
        self.uid = uid
        self.pswd = pswd
        self.name = name
        self.cuaddrs = cuaddrs
        self.cuhome = cuhome
        self.calendars = calendars
        self.acl = acl
        self.quota = quota
        self.autorespond = autorespond

    def repeat(self, ctr):
        """
        Create another object like this but with all text items having % substitution
        done on them with the numeric value provided.
        @param ctr: an integer to substitute into text.
        """
        
        if self.uid.find("%") != -1:
            uid = self.uid % ctr
        else:
            uid = self.uid
        if self.pswd.find("%") != -1:
            pswd = self.pswd % ctr
        else:
            pswd = self.pswd
        if self.name.find("%") != -1:
            name = self.name % ctr
        else:
            name = self.name
        cuaddrs = []
        for cuaddr in self.cuaddrs:
            if cuaddr.find("%") != -1:
                cuaddrs.append(cuaddr % ctr)
            else:
                cuaddrs.append(cuaddr)
        if self.cuhome.find("%") != -1:
            cuhome = self.cuhome % ctr
        else:
            cuhome = self.cuhome
        
        return ProvisionPrincipal(uid, pswd, name, cuaddrs, cuhome, self.calendars, self.acl, self.quota, self.autorespond)

    def parseXML( self, node ):
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_USERID:
                if child.firstChild is not None:
                   self.uid = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_PASSWORD:
                if child.firstChild is not None:
                    self.pswd = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_NAME:
                if child.firstChild is not None:
                   self.name = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_CUADDR:
                if child.firstChild is not None:
                   self.cuaddrs.append(child.firstChild.data.encode("utf-8"))
            elif child._get_localName() == ELEMENT_CUHOME:
                if child.firstChild is not None:
                   self.cuhome = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_CALENDAR:
                if child.firstChild is not None:
                   self.calendars.append(child.firstChild.data.encode("utf-8"))
            elif child._get_localName() == ELEMENT_QUOTA:
                if child.firstChild is not None:
                   self.quota = int(child.firstChild.data.encode("utf-8"))
            elif child._get_localName() == ELEMENT_ACL:
                self.acl = ACL()
                self.acl.parseXML(child)
            elif child._get_localName() == ELEMENT_AUTORESPOND:
                self.autorespond = True
            elif child._get_localName() == ELEMENT_CANPROXY:
                CalDAVResource.proxyUsers.add(self.uid)

class Authentication:
    """
    Parses authentication information  for XML file.
    """
    
    class AuthType:
        """
        Base class for authentication method behaviors.
        """
        
        def __init__(self, type):
            self.type = type
            self.enabled = False
            self.onlyssl = False
            if type == "kerberos":
                self.credentials = ATTRIBUTE_VALUE_KERBEROS
            else:
                self.credentials = ATTRIBUTE_VALUE_PROPERTY
            self.realm = ""
            self.service = ""
            
        def parseXML(self, node):
            if node.hasAttribute(ATTRIBUTE_ENABLE):
                self.enabled = node.getAttribute(ATTRIBUTE_ENABLE) == ATTRIBUTE_VALUE_YES
            if node.hasAttribute(ATTRIBUTE_ONLYSSL):
                self.onlyssl = node.getAttribute(ATTRIBUTE_ONLYSSL) == ATTRIBUTE_VALUE_YES
            if node.hasAttribute(ATTRIBUTE_CREDENTIALS):
                self.credentials = node.getAttribute(ATTRIBUTE_CREDENTIALS)
            for child in node._get_childNodes():
                if child._get_localName() == ELEMENT_REALM:
                    if child.firstChild is not None:
                       self.realm = child.firstChild.data.encode("utf-8")
                elif child._get_localName() == ELEMENT_SERVICE:
                    if child.firstChild is not None:
                       self.service = child.firstChild.data.encode("utf-8")
            
    def __init__(self):
        self.basic = Authentication.AuthType("basic")
        self.digest = Authentication.AuthType("digest")
        self.kerberos = Authentication.AuthType("kerberos")
    
    def getEnabledAuthenticator(self):
        if self.basic.enabled:
            return self.basic
        elif self.digest.enabled:
            return self.digest
        elif self.kerberos.enabled:
            return self.kerberos
        else:
            return None

    def parseXML(self, node):
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_BASIC:
                self.basic.parseXML(child)
            elif child._get_localName() == ELEMENT_DIGEST:
                self.digest.parseXML(child)
            elif child._get_localName() == ELEMENT_KERBEROS:
                self.kerberos.parseXML(child)
        
        # Sanity checks
        ctr = 0
        if self.basic.enabled:
            ctr += 1
        if self.digest.enabled:
            ctr += 1
        if self.kerberos.enabled:
            ctr += 1
        if ctr == 0:
            log.msg("One authentication method must be enabled.")
            raise ValueError, "One authentication method must be enabled."
        elif ctr > 1:
            log.msg("Only one authentication method allowed.")
            raise ValueError, "Only one authentication method allowed."
        
        # FIXME: currently we have no way to turn off an auth mechanism based on whether SSL is in use or not,
        # so the onlyssl attribute is meaning less for now.
#        if self.basic.enabled and not self.basic.onlyssl:
#            log.msg("IMPORTANT: plain text passwords are allowed without an encrypted/secure connection.")
        if self.basic.enabled:
            log.msg("IMPORTANT: plain text passwords are allowed without an encrypted/secure connection.")
