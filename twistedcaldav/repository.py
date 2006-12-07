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

import os

from xml.dom.minidom import Element
from xml.dom.minidom import Text
import xml.dom.minidom

from twisted.application.internet import SSLServer, TCPServer
from twisted.application.service import Application, IServiceCollection, MultiService
from twisted.cred.portal import Portal
from twisted.internet.ssl import DefaultOpenSSLContextFactory
from twisted.python import log
from twisted.python.reflect import namedObject
from twisted.web2.auth import basic, digest
from twisted.web2.channel.http import HTTPFactory
from twisted.web2.dav import auth, davxml
from twisted.web2.dav.element.base import PCDATAElement
from twisted.web2.dav.element.parser import lookupElement
from twisted.web2.dav.resource import TwistedACLInheritable
from twisted.web2.dav.util import joinURL
from twisted.web2.dav.idav import IDAVPrincipalCollectionResource
from twisted.web2.log import LogWrapperResource
from twisted.web2.server import Site

from twistedcaldav.dropbox import DropBox
from twistedcaldav import authkerb
from twistedcaldav.logging import RotatingFileAccessLoggingObserver
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.static import CalendarHomeFile

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

ATTRIBUTE_VALUE_DIRECTORY = "directory"
ATTRIBUTE_VALUE_KERBEROS = "kerberos"

def startServer(docroot, repo, dossl,
                keyfile, certfile, onlyssl, port, sslport, maxsize,
                quota, serverlogfile,
                directoryservice,
                dropbox, dropboxACLs,
                notifications,
                manhole):
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
    
    # Turn on drop box support before building the repository
    DropBox.enable(dropbox, dropboxACLs, notifications)

    dirname = directoryservice["type"]
    dirparams = directoryservice["params"]
    try:
        resource_class = namedObject(dirname)
    except:
        log.err("Unable to locate Python class %r" % (dirname,))
        raise
    try:
        directory = resource_class(**dirparams)
    except Exception:
        log.err("Unable to instantiate Python class %r with arguments %r" % (resource_class, dirparams))
        raise

    # Build the server
    builder = RepositoryBuilder(docroot,
                                maxsize=maxsize,
                                quota=quota)
    builder.buildFromFile(repo, directory)
    rootresource = builder.docRoot.collection.resource
    
    application = Application("CalDAVServer")
    parent      = IServiceCollection(application)
    web2        = Web2Service(RotatingFileAccessLoggingObserver(serverlogfile))
    web2.setServiceParent(parent)
    parent = web2
    
    # Configure appropriate authentication 
    authenticator = builder.authentication.getEnabledAuthenticator()
    
    portal = Portal(auth.DavRealm())
    if authenticator.credentials == ATTRIBUTE_VALUE_DIRECTORY:
        portal.registerChecker(directory)
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
    Builds a repository hierarchy at a supplied document root file system path.
    """
    
    def __init__(self, docroot, maxsize=None, quota=None):
        """
        @param docroot:    file system path to use as the root.
        @param maxsize:    maximum size in bytes for any calendar object resource, C{int} to set size,
            if <= 0, then no limit will be set.
        @param quota:    maximum quota size in bytes for a user's calendar home, C{int} to set size,
            if <= 0, then no limit will be set.
        """
        self.docRoot = DocRoot(docroot)
        self.authentication = Authentication()
        self.maxsize = maxsize
        self.quota = quota
        
        if self.maxsize <= 0:
            self.maxsized = None
        if self.quota <= 0:
            self.quota = None
        
    def buildFromFile(self, filename, directory):
        """
        Parse the required information from an XML file.
        @param file: the path of the XML file to parse.
        """
        # Read in XML
        fd = open(filename, "r")
        doc = xml.dom.minidom.parse( fd )
        fd.close()

        # Verify that top-level element is correct
        repository_node = doc._get_documentElement()
        if repository_node._get_localName() != ELEMENT_REPOSITORY:
            self.log("Ignoring file %r because it is not a repository builder file" % (filename,))
            return
        self.parseXML(repository_node)
        
        self.docRoot.build(directory)
            
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
        
    def parseXML(self, node):
        """
        Parse the XML collection nodes from the repository configuration document.
        @param node: the L{Node} to parse.
        """
        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_COLLECTION:
                self.collection = Collection()
                self.collection.parseXML(child, self)
                break

    def build(self, directory):
        """
        Build the entire repository starting at the root resource.
        """
        self.collection.build(self, self.path, "/", directory)
        
        # Cheat        
        self.collection.resource._principalCollections = self.principalCollections
            
class Collection (object):
    """
    Contains information about a collection in the repository.
    """
    def __init__(self):
        self.name = None
        self.pytype = None
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

    def build(self, docroot, mypath, urlroot, directory):
        """
        Create this collection, initialising any properties and then create any child
        collections.
        @param docroot: the file system path to create the collection in.
        @param urlroot: the URI path root to create the collection resource in.
        """
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
            ("path"     , mypath   ),
            ("url"      , myurl    ),
            ("directory", directory),
        ):
            if name in argnames:
                kwargs[name] = value
        if self.params:
            kwargs["params"] = self.params
        try:
            self.resource = resource_class(**kwargs)
        except Exception:
            log.err("Unable to instantiate Python class %r with arguments %r" % (resource_class, kwargs))
            raise

        self.uri = myurl
        
        # Set properties now
        for prop in self.properties:
            self.resource.writeDeadProperty(prop.prop)

        # Set ACL now
        if self.acl is not None:
            self.resource.setAccessControlList(self.acl.acl)
        
        for member in self.members:
            child = member.build(docroot, mypath, myurl, directory)
            # Only putChild if one does not already exists
            if self.resource.putChildren.get(member.name, None) is None:
                self.resource.putChild(member.name, child)

            if IDAVPrincipalCollectionResource.providedBy(child):
                docroot.principalCollections.append(child)
                
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
                self.credentials = ATTRIBUTE_VALUE_DIRECTORY
            self.realm = ""
            self.service = ""
            
        def parseXML(self, node):
            if node.hasAttribute(ATTRIBUTE_ENABLE):
                self.enabled = node.getAttribute(ATTRIBUTE_ENABLE) == ATTRIBUTE_VALUE_YES
            if node.hasAttribute(ATTRIBUTE_ONLYSSL):
                self.onlyssl = node.getAttribute(ATTRIBUTE_ONLYSSL) == ATTRIBUTE_VALUE_YES
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
