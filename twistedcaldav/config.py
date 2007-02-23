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

from twistedcaldav.py.plistlib import readPlist

defaultConfigFile = "/etc/caldavd/caldavd.plist"

defaultConfig = {
    # Public network address
    "ServerHostName": "localhost",
    "Port": 8008,
    "SSLPort": 8443,

    # Network configuration
    "BindAddress": [],
    "InstancePort": 0,
    "InstanceSSLPort": 0,
    "ManholePort": 0,

    # Data store
    "DocumentRoot": "/Library/CalendarServer/Documents",
    "UserQuotaBytes": 104857600,
    "MaximumAttachmentSizeBytes": 1048576,

    # Directory service
    "DirectoryService": {
        "params": {
            "node": "/Search",
            "useFullSchema": True,
        },
        "type": "twistedcaldav.directory.appleopendirectory.OpenDirectoryService"
    },

    # Special principals
    "AdminPrincipals": [],
    "SudoersFile": "/etc/caldavd/sudoers.plist",
    "CalendarUserProxyEnabled": True,

    # Authentication
    "Authentication": {
        "Basic": {
            "Enabled": False,
        },
        "Digest": {
            "Enabled": True,
            "Algorithm": "md5",
        },
        "Kerberos": {
            "Enabled": False,
            "Realm": "",
        },
    },

    # Logging
    "Verbose": False,
    "ServerLogFile": "/var/log/caldavd/access.log",
    "ErrorLogFile": "/var/log/caldavd/error.log",
    "ServerStatsFile": "/Library/CalendarServer/Documents/stats.plist",
    "PIDFile": "/var/run/caldavd.pid",

    # SSL
    "SSLOnly": True,
    "SSLEnable": True,
    "SSLCertificate": "/etc/certificates/Default.crt",
    "SSLPrivateKey": "/etc/certificates/Default.key",

    # Process management
    "RunStandalone": True,
    "Username": "daemon",
    "Groupname": "daemon",
    "ServerType": "singleprocess",
    "MultiProcess": {
        "NumProcesses": 10,
        "LoadBalancer": {
            "Enabled": True,
            "Scheduler": "leastconns",
        },
    },

    # Service ACLs
    "SACLEnable": False,

    # Non-standard CalDAV extensions
    "DropBoxEnabled": False,
    "NotificationsEnabled": False,

    # Twistd
    "twistdLocation": "/usr/share/caldavd/bin/twistd",

    # Python director
    "pydirLocation": "/usr/share/caldavd/bin/pydir++.py",
    "pydirConfig"  : "/etc/caldavd/pydir.xml",
}

class Config (object):
    def __init__(self, defaults):
        self.update(defaults)

    def update(self, items):
        items = items.iteritems()
        for key, value in items:
            setattr(self, key, value)

class ConfigurationError (RuntimeError):
    """
    Invalid server configuration.
    """

config = Config(defaultConfig)

def parseConfig(configFile):
    if os.path.exists(configFile):
        plist = readPlist(configFile)
        config.update(plist)
