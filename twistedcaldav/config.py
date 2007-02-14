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

defaultConfigFile = '/etc/caldavd/caldavd.plist'

defaultConfig = {
    'BindAddress': [],
    'CalendarUserProxyEnabled': True,
    'DirectoryService': {
        'params': {'node': '/Search'},
        'type': 'twistedcaldav.directory.appleopendirectory.OpenDirectoryService'
    },
    'DocumentRoot': '/Library/CalendarServer/Documents',
    'DropBoxEnabled': False,
    'ErrorLogFile': '/var/log/caldavd/error.log',
    'ManholePort': 0,
    'MaximumAttachmentSizeBytes': 1048576,
    'NotificationsEnabled': False,
    'PIDFile': '/var/run/caldavd.pid',
    'ServerHostName': 'localhost',
    'Port': 8008,
    'RunStandalone': True,
    'SSLCertificate': '/etc/certificates/Default.crt',
    'SSLEnable': True,
    'SSLOnly': True,
    'SSLPort': 8443,
    'SSLPrivateKey': '/etc/certificates/Default.key',
    'ServerLogFile': '/var/log/caldavd/server.log',
    'ServerStatsFile': '/Library/CalendarServer/Documents/stats.plist',
    'UserQuotaBytes': 104857600,
    'Verbose': False,
    'ServerHostName': 'localhost',
    'SACLEnable': False,
    'Authentication': {
        'Basic': {
            'Enabled': False,
            },
        'Digest': {
            'Enabled': True,
            'Algorithm': 'md5',
            },
        'Kerberos': {
            'Enabled': False,
            'Realm': '',
            },
        },

    'AdminPrincipals': [],
    'SudoersFile': '/etc/caldavd/sudoers.plist',

    'twistdLocation': '/usr/share/caldavd/bin/twistd',
    'pydirLocation': '/usr/share/caldavd/bin/pydir++.py',
    'pydirConfig': '/etc/caldavd/pydir.xml',

    'ServerType': 'singleprocess',

    'Username': 'daemon',
    'Groupname': 'daemon',

    'MultiProcess': {
        'NumProcesses': 10,
        'LoadBalancer': {
            'Enabled': True,
            'Scheduler': 'leastconns',
            },
        },
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
