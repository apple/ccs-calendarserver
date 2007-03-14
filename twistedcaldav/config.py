##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
# DRI: David Reid, dreid@apple.com
##

import os
import copy

from twisted.python import log

from twistedcaldav.py.plistlib import readPlist

defaultConfigFile = "/etc/caldavd/caldavd.plist"

defaultConfig = {
    #
    # Public network address information
    #
    #    This is the server's public network address, which is provided to
    #    clients in URLs and the like.  It may or may not be the network
    #    address that the server is listening to directly, though it is by
    #    default.  For example, it may be the address of a load balancer or
    #    proxy which forwards connections to the server.
    #
    "ServerHostName": "localhost", # Network host name.
    "HTTPPort": -1,                # HTTP port (None to disable HTTP)
    "SSLPort" : -1,                # SSL port (None to disable HTTPS)

    # Note: we'd use None above, but that confuses the command-line parser.

    #
    # Network address configuration information
    #
    #    This configures the actual network address that the server binds to.
    #
    "BindAddresses": [],   # List of IP addresses to bind to [empty = all]
    "BindHTTPPorts": [],   # List of port numbers to bind to for HTTP [empty = same as "Port"]
    "BindSSLPorts" : [],   # List of port numbers to bind to for SSL [empty = same as "SSLPort"]

    #
    # Data store
    #
    "DocumentRoot": "/Library/CalendarServer/Documents",
    "UserQuota"            : 104857600, # User quota (in bytes)
    "MaximumAttachmentSize":   1048576, # Attachment size limit (in bytes)

    #
    # Directory service
    #
    #    A directory service provides information about principals (eg.
    #    users, groups, locations and resources) to the server.
    #
    "DirectoryService": {
#        "type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService",
#        "params": {
#            "node": "/Search",
#            "requireComputerRecord": True,
#        },
    },

    #
    # Special principals
    #
    "AdminPrincipals": [],                       # Principals with "DAV:all" access (relative URLs)
    "SudoersFile": "/etc/caldavd/sudoers.plist", # Principals that can pose as other principals
    "EnableProxyPrincipals": True,               # Create "proxy access" principals

    #
    # Authentication
    #
    "Authentication": {
        "Basic"   : { "Enabled": False },                     # Clear text; best avoided
        "Digest"  : { "Enabled": True,  "Algorithm": "md5" }, # Digest challenge/response
        "Kerberos": { "Enabled": False, "Realm": "" },        # Kerberos/SPNEGO
    },

    #
    # Logging
    #
    "Verbose": False,
    "AccessLogFile"  : "/var/log/caldavd/access.log",                   # Apache-style access log
    "ErrorLogFile"   : "/var/log/caldavd/error.log",                    # Server activity log
    "ServerStatsFile": "/Library/CalendarServer/Documents/stats.plist",
    "PIDFile"        : "/var/run/caldavd.pid",

    #
    # SSL/TLS
    #
    "SSLCertificate": "/etc/certificates/Default.crt", # Public key
    "SSLPrivateKey": "/etc/certificates/Default.key",  # Private key

    #
    # Process management
    #
    "UserName": "daemon",
    "GroupName": "daemon",
    "ProcessType": "Slave",
    "MultiProcess": {
        "ProcessCount": 4,
        "LoadBalancer": {
            "Enabled": True,
            "Scheduler": "LeastConnections",
        },
    },

    #
    # Service ACLs
    #
    "EnableSACLs": False,

    #
    # Non-standard CalDAV extensions
    #
    "EnableDropBox"      : False, # Calendar Drop Box
    "EnableNotifications": False, # Drop Box Notifications

    #
    # Implementation details
    #
    #    The following are specific to how the server is built, and useful
    #    for development, but shouldn't be needed by users.
    #

    # Twisted
    "Twisted": {
        "twistd": "/usr/share/caldavd/bin/twistd",
    },

    # Python Director
    "PythonDirector": {
        "pydir": "/usr/share/caldavd/bin/pydir.py",
        "ConfigFile": "/etc/caldavd/pydir.xml",
    },
}

def _mergeData(oldData, newData):
    for key, value in newData.iteritems():
        if isinstance(value, (dict,)):
            assert isinstance(oldData.get(key, {}), (dict,))
            oldData[key] = _mergeData(oldData.get(key, {}), value)
        else:
            oldData[key] = value

    return oldData

class Config (object):
    def __init__(self, defaults):
        self._defaults = defaults
        self._data = copy.deepcopy(defaults)
        self._configFile = None

    def __str__(self):
        return str(self._data)

    def update(self, items):
        self._data = _mergeData(self._data, items)

    def updateDefaults(self, items):
        self._defaults = _mergeData(self._defaults, items)
        self.update(items)

    def __getattr__(self, attr):
        if attr in self._data:
            return self._data[attr]

        raise AttributeError(attr)

    def reload(self):
        self._data = copy.deepcopy(self._defaults)
        self.loadConfig(self._configFile)

    def loadConfig(self, configFile):
        self._configFile = configFile

        if configFile and os.path.exists(configFile):
            configDict = readPlist(configFile)
            configDict = self.cleanup(configDict)
            configDict = self.cleanup(configDict)
            self.update(configDict)

    def cleanup(self, configDict):
        cleanDict = copy.deepcopy(configDict)

        def deprecated(oldKey, newKey):
            log.err("Configuration option %r is deprecated in favor of %r." % (oldKey, newKey))

        def renamed(oldKey, newKey):
            deprecated(oldKey, newKey)
            cleanDict[newKey] = configDict[oldKey]
            del cleanDict[oldKey]

        renamedOptions = {
            "BindAddress"                : "BindAddresses",
            "ServerLogFile"              : "AccessLogFile",
            "MaximumAttachmentSizeBytes" : "MaximumAttachmentSize",
            "UserQuotaBytes"             : "UserQuota",
            "DropBoxEnabled"             : "EnableDropBox",
            "NotificationsEnabled"       : "EnableNotifications",
            "CalendarUserProxyEnabled"   : "EnableProxyPrincipals",
            "SACLEnable"                 : "EnableSACLs",
            "ServerType"                 : "ProcessType",
        }

        for key in configDict:
            if key in defaultConfig:
                continue

            if key == "SSLOnly":
                deprecated(key, "HTTPPort")
                if configDict["SSLOnly"]:
                    cleanDict["HTTPPort"] = None
                del cleanDict["SSLOnly"]

            elif key == "SSLEnable":
                deprecated(key, "SSLPort")
                if not configDict["SSLEnable"]:
                    cleanDict["SSLPort"] = None
                del cleanDict["SSLEnable"]

            elif key == "Port":
                deprecated(key, "HTTPPort")
                if not configDict.get("SSLOnly", False):
                    cleanDict["HTTPPort"] = cleanDict["Port"]
                del cleanDict["Port"]

            elif key == "twistdLocation":
                deprecated(key, "Twisted -> twistd")
                if "Twisted" not in cleanDict:
                    cleanDict["Twisted"] = {}
                cleanDict["Twisted"]["twistd"] = cleanDict["twistdLocation"]
                del cleanDict["twistdLocation"]

            elif key == "pydirLocation":
                deprecated(key, "PythonDirector -> pydir")
                if "PythonDirector" not in cleanDict:
                    cleanDict["PythonDirector"] = {}
                cleanDict["PythonDirector"]["pydir"] = cleanDict["pydirLocation"]
                del cleanDict["pydirLocation"]

            elif key == "pydirConfig":
                deprecated(key, "PythonDirector -> pydir")
                if "PythonDirector" not in cleanDict:
                    cleanDict["PythonDirector"] = {}
                cleanDict["PythonDirector"]["ConfigFile"] = cleanDict["pydirConfig"]
                del cleanDict["pydirConfig"]

            elif key in renamedOptions:
                renamed(key, renamedOptions[key])

            elif key == "RunStandalone":
                log.err("Ignoring obsolete configuration option: %s" % (key,))
                del cleanDict[key]

            else:
                log.err("Ignoring unknown configuration option: %s" % (key,))
                del cleanDict[key]

        return cleanDict

class ConfigurationError (RuntimeError):
    """
    Invalid server configuration.
    """

config = Config(defaultConfig)

def parseConfig(configFile):
    config.loadConfig(configFile)
