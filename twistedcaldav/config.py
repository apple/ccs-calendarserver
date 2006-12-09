##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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

defaults = {
    'CreateAccounts': False,
    'DirectoryService': {
        'params': {'node': '/Search'},
        'type': 'twistedcaldav.directory.appleopendirectory.OpenDirectoryService'
    },
    'DocumentRoot': '/Library/CalendarServer/Documents',
    'DropBoxEnabled': True,
    'DropBoxInheritedACLs': True,
    'DropBoxName': 'dropbox',
    'ErrorLogFile': '/var/log/caldavd/error.log',
    'ManholePort': 0,
    'MaximumAttachmentSizeBytes': 1048576,
    'NotificationCollectionName': 'notifications',
    'NotificationsEnabled': False,
    'PIDFile': '/var/run/caldavd.pid',
    'Port': 8008,
    'Repository': '/etc/caldavd/repository.xml',
    'ResetAccountACLs': False,
    'RunStandalone': True,
    'SSLCertificate': '/etc/certificates/Default.crt',
    'SSLEnable': False,
    'SSLOnly': False,
    'SSLPort': 8443,
    'SSLPrivateKey': '/etc/certificates/Default.key',
    'ServerLogFile': '/var/log/caldavd/server.log',
    'ServerStatsFile': '/Library/CalendarServer/Documents/stats.plist',
    'UserQuotaBytes': 104857600,
    'Verbose': False,
    'twistdLocation': '/usr/share/caldavd/bin/twistd',
    'SACLEnable': False,
    'AuthSchemes': ['Basic'],
    'AdminPrincipals': ['/principal/users/admin']
}

config = dict(defaults)

def parseConfig(configFile):
    if os.path.exists(configFile):
        plist = readPlist(configFile)
        config.update(plist)
