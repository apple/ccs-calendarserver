##
# Copyright (c) 2009-2010 Apple Inc. All rights reserved.
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

from twext.python.log import Logger
from twext.python.plistlib import readPlist

from twistedcaldav.client.pool import installPool

"""
Collection of classes for managing partition information for a group of servers.
"""

log = Logger()

class Partitions(object):

    def __init__(self):
        
        self.clear()

    def clear(self):
        self.partitions = {}
        self.ownUID = ""
        self.maxClients = 5

    def readConfig(self, plistpath):
        try:
            dataDict = readPlist(plistpath)
        except (IOError, OSError):                                    
            log.error("Configuration file does not exist or is inaccessible: %s" % (self._configFileName,))
            return
        
        for partition in dataDict.get("partitions", ()):
            uid = partition.get("uid", None)
            url = partition.get("url", None)
            if uid and url:
                self.partitions[uid] = url

    def setSelfPartition(self, uid):
        self.ownUID = uid

    def setMaxClients(self, maxClients):
        self.maxClients = maxClients

    def getPartitionURL(self, uid):
        # When the UID matches this server return an empty string
        return self.partitions.get(uid, None) if uid != self.ownUID else ""

    def installReverseProxies(self):
        
        for partition, url in self.partitions.iteritems():
            if partition != self.ownUID:
                installPool(
                    partition,
                    url,
                    self.maxClients,
                )

partitions = Partitions()
