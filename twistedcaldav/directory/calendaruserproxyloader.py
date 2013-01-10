##
# Copyright (c) 2009-2013 Apple Inc. All rights reserved.
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
XML based calendar user proxy loader.
"""

__all__ = [
    "XMLCalendarUserProxyLoader",
]

import types

from twisted.internet.defer import inlineCallbacks

from twext.python.log import Logger

from twistedcaldav.config import config, fullServerPath
from twistedcaldav.directory import calendaruserproxy
from twistedcaldav.xmlutil import readXML

log = Logger()

ELEMENT_PROXIES           = "proxies"
ELEMENT_RECORD            = "record"

ELEMENT_GUID              = "guid"
ELEMENT_PROXIES           = "proxies"
ELEMENT_READ_ONLY_PROXIES = "read-only-proxies"
ELEMENT_MEMBER            = "member"

ATTRIBUTE_REPEAT          = "repeat"

class XMLCalendarUserProxyLoader(object):
    """
    XML calendar user proxy configuration file parser and loader.
    """
    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.xmlFile)

    def __init__(self, xmlFile):

        self.items = []
        self.xmlFile = fullServerPath(config.DataRoot, xmlFile)

        # Read in XML
        try:
            _ignore_tree, proxies_node = readXML(self.xmlFile, ELEMENT_PROXIES)
        except ValueError, e:
            log.error("XML parse error for '%s' because: %s" % (self.xmlFile, e,), raiseException=RuntimeError)

        self._parseXML(proxies_node)

    def _parseXML(self, rootnode):
        """
        Parse the XML root node from the augments configuration document.
        @param rootnode: the L{Element} to parse.
        """
        for child in rootnode.getchildren():
            
            if child.tag != ELEMENT_RECORD:
                log.error("Unknown augment type: '%s' in augment file: '%s'" % (child.tag, self.xmlFile,), raiseException=RuntimeError)

            repeat = int(child.get(ATTRIBUTE_REPEAT, "1"))

            guid = None
            write_proxies = set()
            read_proxies = set()
            for node in child.getchildren():
                
                if node.tag == ELEMENT_GUID:
                    guid = node.text

                elif node.tag in (
                    ELEMENT_PROXIES,
                    ELEMENT_READ_ONLY_PROXIES,
                ):
                    self._parseMembers(node, write_proxies if node.tag == ELEMENT_PROXIES else read_proxies)
                else:
                    log.error("Invalid element '%s' in proxies file: '%s'" % (node.tag, self.xmlFile,), raiseException=RuntimeError)
                    
            # Must have at least a guid
            if not guid:
                log.error("Invalid record '%s' without a guid in proxies file: '%s'" % (child, self.xmlFile,), raiseException=RuntimeError)
                
            if repeat > 1:
                for i in xrange(1, repeat+1):
                    self._buildRecord(guid, write_proxies, read_proxies, i)
            else:
                self._buildRecord(guid, write_proxies, read_proxies)

    def _parseMembers(self, node, addto):
        for child in node.getchildren():
            if child.tag == ELEMENT_MEMBER:
                addto.add(child.text)
    
    def _buildRecord(self, guid, write_proxies, read_proxies, count=None):

        def expandCount(value, count):
            
            if type(value) in types.StringTypes:
                return value % (count,) if count and "%" in value else value
            else:
                return value
        
        guid = expandCount(guid, count)
        write_proxies = set([expandCount(member, count) for member in write_proxies])
        read_proxies = set([expandCount(member, count) for member in read_proxies])
            
        self.items.append((guid, write_proxies, read_proxies,))

    @inlineCallbacks
    def updateProxyDB(self):
        
        db = calendaruserproxy.ProxyDBService
        for item in self.items:
            guid, write_proxies, read_proxies = item
            yield db.setGroupMembers("%s#%s" % (guid, "calendar-proxy-write"), write_proxies)
            yield db.setGroupMembers("%s#%s" % (guid, "calendar-proxy-read"), read_proxies)
