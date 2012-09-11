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
from twistedcaldav import xmlutil

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

ELEMENT_SERVERS = "servers"
ELEMENT_SERVER = "server"
ELEMENT_URI = "uri"
ELEMENT_AUTHENTICATION = "authentication"
ATTRIBUTE_TYPE = "type"
ATTRIBUTE_BASICAUTH = "basic"
ELEMENT_USER = "user"
ELEMENT_PASSWORD = "password"
ELEMENT_ALLOW_REQUESTS_FROM = "allow-requests-from"
ELEMENT_ALLOW_REQUESTS_TO = "allow-requests-to"
ELEMENT_DOMAINS = "domains"
ELEMENT_DOMAIN = "domain"
ELEMENT_CLIENT_HOSTS = "hosts"
ELEMENT_HOST = "host"



class IScheduleServersParser(object):
    """
    Server-to-server configuration file parser.
    """
    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.xmlFile)


    def __init__(self, xmlFile):

        self.servers = []

        # Read in XML
        _ignore_etree, servers_node = xmlutil.readXML(xmlFile.path, ELEMENT_SERVERS)
        self._parseXML(servers_node)


    def _parseXML(self, node):
        """
        Parse the XML root node from the server-to-server configuration document.
        @param node: the L{Node} to parse.
        """

        for child in node.getchildren():
            if child.tag == ELEMENT_SERVER:
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
        for child in node.getchildren():
            if child.tag == ELEMENT_URI:
                self.uri = child.text
            elif child.tag == ELEMENT_AUTHENTICATION:
                self._parseAuthentication(child)
            elif child.tag == ELEMENT_ALLOW_REQUESTS_FROM:
                self.allow_from = True
            elif child.tag == ELEMENT_ALLOW_REQUESTS_TO:
                self.allow_to = True
            elif child.tag == ELEMENT_DOMAINS:
                self._parseList(child, ELEMENT_DOMAIN, self.domains)
            elif child.tag == ELEMENT_CLIENT_HOSTS:
                self._parseList(child, ELEMENT_HOST, self.client_hosts)
            else:
                raise RuntimeError("[%s] Unknown attribute: %s" % (self.__class__, child.tag,))

        self._parseDetails()


    def _parseList(self, node, element_name, appendto):
        for child in node.getchildren():
            if child.tag == element_name:
                appendto.append(child.text)


    def _parseAuthentication(self, node):
        if node.get(ATTRIBUTE_TYPE) != ATTRIBUTE_BASICAUTH:
            return

        for child in node.getchildren():
            if child.tag == ELEMENT_USER:
                user = child.text
            elif child.tag == ELEMENT_PASSWORD:
                password = child.text

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
            self.port = {False: 80, True: 443}[self.ssl]
        self.path = "/"
        if len(splits) > 1:
            self.path += splits[1]
