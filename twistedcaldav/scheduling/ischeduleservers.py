##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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

from twext.python.filepath import CachingFilePath as FilePath

from twext.python.log import Logger

from twistedcaldav.config import config, fullServerPath
from twistedcaldav.scheduling.delivery import DeliveryService

import xml.dom.minidom

"""
XML based iSchedule configuration file handling.
"""

__all__ = [
    "IScheduleServers",
]

log = Logger()

class IScheduleServers(object):
    
    _fileInfo = None
    _xmlFile = None
    _servers = None
    _domainMap = None
    
    def __init__(self):
        
        self._loadConfig()

    def _loadConfig(self):
        if IScheduleServers._servers is None:
            IScheduleServers._xmlFile = FilePath(
                fullServerPath(
                    config.ConfigRoot,
                    config.Scheduling[DeliveryService.serviceType_ischedule]["Servers"]
                )
            )
        IScheduleServers._xmlFile.restat()
        fileInfo = (IScheduleServers._xmlFile.getmtime(), IScheduleServers._xmlFile.getsize())
        if fileInfo != IScheduleServers._fileInfo:
            parser = IScheduleServersParser(IScheduleServers._xmlFile)
            IScheduleServers._servers = parser.servers
            self._mapDomains()
            IScheduleServers._fileInfo = fileInfo
        
    def _mapDomains(self):
        IScheduleServers._domainMap = {}
        for server in IScheduleServers._servers:
            for domain in server.domains:
                IScheduleServers._domainMap[domain] = server
    
    def mapDomain(self, domain):
        """
        Map a calendar user address domain to a suitable server that can
        handle server-to-server requests for that user.
        """
        return IScheduleServers._domainMap.get(domain)

ELEMENT_SERVERS                 = "servers"
ELEMENT_SERVER                  = "server"
ELEMENT_URI                     = "uri"
ELEMENT_AUTHENTICATION          = "authentication"
ATTRIBUTE_TYPE                  = "type"
ATTRIBUTE_BASICAUTH             = "basic"
ELEMENT_USER                    = "user"
ELEMENT_PASSWORD                = "password"
ELEMENT_ALLOW_REQUESTS_FROM     = "allow-requests-from"
ELEMENT_ALLOW_REQUESTS_TO       = "allow-requests-to"
ELEMENT_DOMAINS                 = "domains"
ELEMENT_DOMAIN                  = "domain"
ELEMENT_CLIENT_HOSTS            = "hosts"
ELEMENT_HOST                    = "host"

class IScheduleServersParser(object):
    """
    Server-to-server configuration file parser.
    """
    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.xmlFile)

    def __init__(self, xmlFile):

        self.servers = []
        
        # Read in XML
        fd = open(xmlFile.path, "r")
        doc = xml.dom.minidom.parse(fd)
        fd.close()

        # Verify that top-level element is correct
        servers_node = doc._get_documentElement()
        if servers_node._get_localName() != ELEMENT_SERVERS:
            log.error("Ignoring file %r because it is not a server-to-server config file" % (self.xmlFile,))
            return
        self._parseXML(servers_node)
        
    def _parseXML(self, node):
        """
        Parse the XML root node from the server-to-server configuration document.
        @param node: the L{Node} to parse.
        """

        for child in node._get_childNodes():
            child_name = child._get_localName()
            if child_name is None:
                continue
            elif child_name == ELEMENT_SERVER:
                self.servers.append(IScheduleServerRecord())
                self.servers[-1].parseXML(child)
                
class IScheduleServerRecord (object):
    """
    Contains server-to-server details.
    """
    def __init__(self, uri=None):
        """
        @param recordType: record type for directory entry.
        """
        self.uri = ""
        self.authentication = None
        self.allow_from = False
        self.allow_to = True
        self.domains = []
        self.client_hosts = []
        self.unNormalizeAddresses = True
        self.moreHeaders = []
        
        if uri:
            self.uri = uri
            self._parseDetails()

    def parseXML(self, node):
        for child in node._get_childNodes():
            child_name = child._get_localName()
            if child_name is None:
                continue
            elif child_name == ELEMENT_URI:
                if child.firstChild is not None:
                    self.uri = child.firstChild.data.encode("utf-8")
            elif child_name == ELEMENT_AUTHENTICATION:
                self._parseAuthentication(child)
            elif child_name == ELEMENT_ALLOW_REQUESTS_FROM:
                self.allow_from = True
            elif child_name == ELEMENT_ALLOW_REQUESTS_TO:
                self.allow_to = True
            elif child_name == ELEMENT_DOMAINS:
                self._parseList(child, ELEMENT_DOMAIN, self.domains)
            elif child_name == ELEMENT_CLIENT_HOSTS:
                self._parseList(child, ELEMENT_HOST, self.client_hosts)
            else:
                raise RuntimeError("[%s] Unknown attribute: %s" % (self.__class__, child_name,))
        
        self._parseDetails()

    def _parseList(self, node, element_name, appendto):
        for child in node._get_childNodes():
            if child._get_localName() == element_name:
                if child.firstChild is not None:
                    appendto.append(child.firstChild.data.encode("utf-8"))

    def _parseAuthentication(self, node):
        if node.hasAttribute(ATTRIBUTE_TYPE):
            atype = node.getAttribute(ATTRIBUTE_TYPE).encode("utf-8")
            if atype != ATTRIBUTE_BASICAUTH:
                return
        else:
            return

        for child in node._get_childNodes():
            if child._get_localName() == ELEMENT_USER:
                if child.firstChild is not None:
                    user = child.firstChild.data.encode("utf-8")
            elif child._get_localName() == ELEMENT_PASSWORD:
                if child.firstChild is not None:
                    password = child.firstChild.data.encode("utf-8")
        
        self.authentication = ("basic", user, password,)

    def _parseDetails(self):
        # Extract scheme, host, port and path
        if self.uri.startswith("http://"):
            self.ssl = False
            rest = self.uri[7:]
        elif self.uri.startswith("https://"):
            self.ssl = True
            rest = self.uri[8:]
        
        splits = rest.split("/", 1)
        hostport = splits[0].split(":")
        self.host = hostport[0]
        if len(hostport) > 1:
            self.port = int(hostport[1])
        else:
            self.port = {False:80, True:443}[self.ssl]
        self.path = "/"
        if len(splits) > 1:
            self.path += splits[1]
