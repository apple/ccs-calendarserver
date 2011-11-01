##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

import twistedcaldav.test.util
from contrib.migration.calendarmigrator import (
    mergePlist, examinePreviousSystem, relocateData, relativize
)
import contrib.migration.calendarmigrator

class FakeUser(object):
    pw_uid = 6543


class FakeGroup(object):
    gr_gid = 7654


class FakePwd(object):
    def getpwnam(self, nam):
        if nam != 'calendar':
            raise RuntimeError("Only 'calendar' user supported for testing.")
        return FakeUser()


class FakeGrp(object):
    def getgrnam(self, nam):
        if nam != 'calendar':
            raise RuntimeError("Only 'calendar' group supported for testing.")
        return FakeGroup()


DEFAULT_AUGMENT_SERVICE = {
    "params" : {
        "xmlFiles" : ["augments.xml"],
    },
    "type" : "twistedcaldav.directory.augment.AugmentXMLDB",
}

class MigrationTests(twistedcaldav.test.util.TestCase):
    """
    Calendar Server Migration Tests
    """

    def setUp(self):
        # Disable logging during tests

        self.patch(contrib.migration.calendarmigrator, "log", lambda _: None)
        self.patch(contrib.migration.calendarmigrator, "pwd", FakePwd())
        self.patch(contrib.migration.calendarmigrator, "grp", FakeGrp())


    def test_mergeSSL(self):

        # SSL on for both services
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8843,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # SSL off for both services
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # SSL on for only caldav
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # SSL on for only carddav
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 0,
            "SSLPrivateKey": "",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8843,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # Non standard ports
        oldCalDAV = {
            "BindHTTPPorts": [1111, 2222],
            "BindSSLPorts": [3333],
            "HTTPPort": 8888,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 9999,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        oldCardDAV = {
            "BindHTTPPorts": [4444, 5555],
            "BindSSLPorts": [6666],
            "HTTPPort": 7777,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 11111,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        expected = {
            "BindHTTPPorts": [1111, 2222, 4444, 5555, 7777, 8888],
            "BindSSLPorts": [3333, 6666, 9999, 11111],
            "EnableSSL" : True,
            "HTTPPort": 8888,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 9999,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)


        # Never had SSL enabled, so missing SSLPort
        oldCalDAV = {
            "BindHTTPPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPrivateKey": "",
        }
        oldCardDAV = {
            "BindHTTPPorts": [],
            "HTTPPort": 8800,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPrivateKey": "",
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # Only CalDAV (Lion -> Lion)
        oldCalDAV = {
            "BindHTTPPorts": [],
            "BindSSLPorts": [],
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        oldCardDAV = {
        }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)


        # All settings missing!
        oldCalDAV = { }
        oldCardDAV = { }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)


    def test_mergeDirectoryService(self):

        # Ensure caldavd DirectoryService config is carried over, except
        # for requireComputerRecord which was is obsolete.

        oldCalDAV = {
            "DirectoryService": {
                "type" : "twistedcaldav.directory.appleopendirectory.OpenDirectoryService",
                "params" : {
                    "node" : "/Search",
                    "cacheTimeout" : 15,
                    "restrictToGroup" : "test-group",
                    "restrictEnabledRecords" : True,
                    "negativeCaching" : False,
                    "requireComputerRecord" : True,
                },
            },
        }
        oldCardDAV = { "Is this ignored?" : True }
        expected = {
            "DirectoryService": {
                "type" : "twistedcaldav.directory.appleopendirectory.OpenDirectoryService",
                "params" : {
                    "node" : "/Search",
                    "cacheTimeout" : 15,
                    "restrictToGroup" : "test-group",
                    "restrictEnabledRecords" : True,
                    "negativeCaching" : False,
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)


    def test_mergeAuthentication(self):

        # Ensure caldavd Authentication config for wiki gets reset because
        # the port number has changed for the wiki rpc url

        oldCalDAV = {
            "Authentication": {
                "Wiki" : {
                    "UseSSL" : False,
                    "Enabled" : True,
                    "Hostname" : "127.0.0.1",
                    "URL" : "http://127.0.0.1/RPC2",
                },
            },
        }
        oldCardDAV = { "Is this ignored?" : True }
        expected = {
            "Authentication": {
                "Wiki" : {
                    "Enabled" : True,
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)

        # If the port is :8089, leave the wiki config as is, since it's
        # already set for Lio

        oldCalDAV = {
            "Authentication": {
                "Wiki" : {
                    "UseSSL" : False,
                    "Enabled" : True,
                    "Hostname" : "127.0.0.1",
                    "URL" : "http://127.0.0.1:8089/RPC2",
                },
            },
        }
        oldCardDAV = { "Is this ignored?" : True }
        expected = {
            "Authentication": {
                "Wiki" : {
                    "UseSSL" : False,
                    "Enabled" : True,
                    "Hostname" : "127.0.0.1",
                    "URL" : "http://127.0.0.1:8089/RPC2",
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
            "AugmentService" : DEFAULT_AUGMENT_SERVICE,
        }
        newCombined = { }
        mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(newCombined, expected)


    def test_examinePreviousSystem(self):
        """
        Set up a virtual system in various configurations, then ensure the
        examinePreviousSystem( ) method detects/returns the expected values.

        'info' is an array of tuples, each tuple containing:
            - Description of configuration
            - Layout of disk as a dictionary of paths plus file contents
            - Expected return values
        """

        info = [

        (
            "Snow -> Lion Migration, all in default locations",
            ("/Volumes/old", "/"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/old/Library/CalendarServer/Documents/calendars/" : True,
                "/Volumes/old/Library/CalendarServer/Data/" : True,
                "/Volumes/old/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/Library/AddressBookServer/Data/" : True,
            },
            (
                None, # Old ServerRoot value
                "/Library/CalendarServer/Documents", # Old Cal DocRoot value
                "/Library/CalendarServer/Data", # Old Cal DataRoot value
                "/Library/AddressBookServer/Documents", # Old AB DocRoot value
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),

        (
            "Snow -> Lion Migration, all in default locations, non-/ target",
            ("/Volumes/old", "/Volumes/new"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/old/Library/CalendarServer/Documents/calendars/" : True,
                "/Volumes/old/Library/CalendarServer/Data/" : True,
                "/Volumes/old/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/Library/AddressBookServer/Data/" : True,
            },
            (
                None, # Old ServerRoot value
                "/Library/CalendarServer/Documents", # Old Cal DocRoot value
                "/Library/CalendarServer/Data", # Old Cal DataRoot value
                "/Library/AddressBookServer/Documents", # Old AB DocRoot value
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),

        (
            "Snow -> Lion Migration, not in default locations",
            ("/Volumes/old", "/"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/NonStandard/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/NonStandard/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/NonStandard/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/NonStandard/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/old/NonStandard/CalendarServer/Documents/calendars/" : True,
                "/Volumes/old/NonStandard/CalendarServer/Data/" : True,
                "/Volumes/old/NonStandard/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/NonStandard/AddressBookServer/Data/" : True,
            },
            (
                None, # Old ServerRoot value
                "/NonStandard/CalendarServer/Documents", # Old Cal DocRoot Value
                "/NonStandard/CalendarServer/Data", # Old Cal DataRoot Value
                "/NonStandard/AddressBookServer/Documents", # Old AB DocRoot Value
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),

        (
            "Snow -> Lion Migration, in internal/external locations",
            ("/Volumes/old", "/"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Volumes/External/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Volumes/External/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/External/CalendarServer/Documents/calendars/" : True,
                "/Volumes/External/CalendarServer/Data/" : True,
                "/Volumes/old/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/Library/AddressBookServer/Data/" : True,
            },
            (
                None, # Old ServerRoot value
                "/Volumes/External/CalendarServer/Documents", # Old Cal DocRoot Value
                "/Volumes/External/CalendarServer/Data", # Old Cal DataRoot Value
                "/Library/AddressBookServer/Documents", # Old AB DocRoot Value
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),


        (
            "Snow -> Lion Migration, only AddressBook data",
            ("/Volumes/old", "/"),
            {
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/old/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/Library/AddressBookServer/Data/" : True,
            },
            (
                None, # Old ServerRoot value
                None, # Old Cal DocRoot value
                None, # Old Cal DataRoot value
                "/Library/AddressBookServer/Documents", # Old AB DocRoot value
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),

        (
            "Lion -> Lion Migration, all in default locations",
            ("/Volumes/old", "/"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Volumes/old/Library/Server/Calendar and Contacts/Data/" : True,
            },
            (
                "/Library/Server/Calendar and Contacts", # Old ServerRoot value
                "Documents", # Old Cal DocRoot value
                "Data", # Old Cal DataRoot value
                None, # Old AB Docs
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),

        (
            "Lion -> Lion Migration, not in default locations",
            ("/Volumes/old", "/"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/NonStandard/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>/Volumes/External/Calendar/Documents</string>
                        <key>DataRoot</key>
                        <string>/Volumes/External/Calendar/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/NonStandard/Calendar and Contacts/Documents/" : True,
                "/Volumes/old/NonStandard/Calendar and Contacts/Data/" : True,
            },
            (
                "/NonStandard/Calendar and Contacts", # Old ServerRoot value
                "/Volumes/External/Calendar/Documents", # Old Cal DocRoot value
                "/Volumes/External/Calendar/Data", # Old Cal DataRoot value
                None, # Old AB Docs
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),

        (
            "Lion -> Lion Migration, non-/ targetRoot",
            ("/Volumes/old", "/Volumes/new"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Volumes/old/Library/Server/Calendar and Contacts/Data/" : True,
            },
            (
                "/Library/Server/Calendar and Contacts", # Old ServerRoot value
                "Documents", # Old Cal DocRoot value
                "Data", # Old Cal DocRoot value
                None, # Old AB Docs
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),

        (
            "Lion -> Lion Migration, external ServerRoot with absolute external DocumentRoot and internal DataRoot",
            ("/Volumes/old", "/Volumes/new"),
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Volumes/External/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>/Volumes/External/CalendarDocuments/</string>
                        <key>DataRoot</key>
                        <string>/CalendarData</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/External/Library/Server/Calendar and Contacts/" : True,
                "/Volumes/External/CalendarDocuments/" : True,
                "/Volumes/old/CalendarData" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/" : True,
            },
            (
                "/Volumes/External/Server/Calendar and Contacts", # Old ServerRoot value
                "/Volumes/External/CalendarDocuments/", # Old Cal DocRoot value
                "/CalendarData", # Old Cal DocRoot value
                None, # Old AB Docs
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            )
        ),



        (
            "Empty migration, nothing exists",
            ("/Volumes/old", "/Volumes/new"),
            {
            },
            (
                None, # Old ServerRoot value
                None, # Old Cal DocRoot value
                None, # Old Cal DocRoot value
                None, # Old AB Docs
                -1, -1, # user id, group id
            )
        ),


        ]

        for description, (source, target), paths, expected in info:
            # print "-=-=-=- %s -=-=-=-" % (description,)
            accessor = StubDiskAccessor(paths)
            actual = examinePreviousSystem(source, target, diskAccessor=accessor)
            self.assertEquals(expected, actual)


    def test_relocateData(self):

        info = [

        (
            "Snow -> Lion Migration, all in default locations",
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/old/Library/CalendarServer/Documents/calendars/" : True,
                "/Volumes/old/Library/CalendarServer/Data/" : True,
                "/Volumes/old/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/Library/AddressBookServer/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts" : True,
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                None, # oldServerRootValue
                "/Library/CalendarServer/Documents", # oldCalDocumentRootValue
                "/Library/CalendarServer/Data", # oldCalDataRootValue
                "/Library/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Documents",
                "Data"
            ),
            [   # expected DiskAccessor history
                ('ditto', '/Volumes/old/Library/CalendarServer/Documents', '/Volumes/new/Library/Server/Calendar and Contacts/Documents'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Documents', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/old/Library/CalendarServer/Data', '/Volumes/new/Library/Server/Calendar and Contacts/Data'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Data', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/old/Library/AddressBookServer/Documents/addressbooks', '/Volumes/new/Library/Server/Calendar and Contacts/Documents/addressbooks'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Documents/addressbooks', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Snow -> Lion Migration, external DocumentRoot",
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Volumes/External/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Volumes/External/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/External/CalendarServer/Documents/calendars/" : True,
                "/Volumes/External/CalendarServer/Calendar and Contacts/" : True,
                "/Volumes/old/Library/CalendarServer/Data/" : True,
                "/Volumes/External/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/Library/AddressBookServer/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts" : True,
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                None, # oldServerRootValue
                "/Volumes/External/CalendarServer/Documents", # oldCalDocumentRootValue
                "/Library/CalendarServer/Data", # oldCalDataRootValue
                "/Volumes/External/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/External/CalendarServer/Calendar and Contacts",
                "/Volumes/External/CalendarServer/Calendar and Contacts",
                "Documents",
                "Data"
            ),
            [   # expected DiskAccessor history
                ('rename', '/Volumes/External/CalendarServer/Calendar and Contacts', '/Volumes/External/CalendarServer/Calendar and Contacts.bak'),
                ('mkdir', '/Volumes/External/CalendarServer/Calendar and Contacts'),
                ('rename', '/Volumes/External/CalendarServer/Documents', '/Volumes/External/CalendarServer/Calendar and Contacts/Documents'),
                ('ditto', '/Volumes/old/Library/CalendarServer/Data', '/Volumes/External/CalendarServer/Calendar and Contacts/Data'),
                ('chown-recursive', '/Volumes/External/CalendarServer/Calendar and Contacts/Data', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/External/AddressBookServer/Documents/addressbooks', '/Volumes/External/CalendarServer/Calendar and Contacts/Documents/addressbooks'),
                ('chown-recursive', '/Volumes/External/CalendarServer/Calendar and Contacts/Documents/addressbooks', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Snow -> Lion Migration, in non-standard locations",
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/NonStandard/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/NonStandard/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/NonStandard/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/NonStandard/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/old/NonStandard/CalendarServer/Documents/calendars/" : True,
                "/Volumes/old/NonStandard/CalendarServer/Data/" : True,
                "/Volumes/old/NonStandard/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/NonStandard/AddressBookServer/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts" : True,
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                None, # oldServerRootValue
                "/NonStandard/CalendarServer/Documents", # oldCalDocumentRootValue
                "/NonStandard/CalendarServer/Data", # oldCalDataRootValue
                "/NonStandard/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Documents",
                "Data"
            ),
            [
                ('ditto', '/Volumes/old/NonStandard/CalendarServer/Documents', '/Volumes/new/Library/Server/Calendar and Contacts/Documents'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Documents', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/old/NonStandard/CalendarServer/Data', '/Volumes/new/Library/Server/Calendar and Contacts/Data'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Data', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/old/NonStandard/AddressBookServer/Documents/addressbooks', '/Volumes/new/Library/Server/Calendar and Contacts/Documents/addressbooks'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Documents/addressbooks', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Snow -> Lion Migration, internal AB, external Cal",
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Volumes/External/CalendarServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Volumes/External/CalendarServer/Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/old/private/etc/carddavd/carddavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>DocumentRoot</key>
                        <string>/Library/AddressBookServer/Documents</string>
                        <key>DataRoot</key>
                        <string>/Library/AddressBookServer/Data</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/External/CalendarServer/Documents" : True,
                "/Volumes/External/CalendarServer/Data" : True,
                "/Volumes/old/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Volumes/old/Library/AddressBookServer/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts" : True,
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                None, # oldServerRootValue
                "/Volumes/External/CalendarServer/Documents", # oldCalDocumentRootValue
                "/Volumes/External/CalendarServer/Data", # oldCalDataRootValue
                "/Library/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/External/CalendarServer/Calendar and Contacts",
                "/Volumes/External/CalendarServer/Calendar and Contacts",
                "Documents",
                "Data"
            ),
            [
                ('mkdir', '/Volumes/External/CalendarServer/Calendar and Contacts'),
                ('rename', '/Volumes/External/CalendarServer/Documents', '/Volumes/External/CalendarServer/Calendar and Contacts/Documents'),
                ('ditto', '/Volumes/External/CalendarServer/Data', '/Volumes/External/CalendarServer/Calendar and Contacts/Data'),
                ('chown-recursive', '/Volumes/External/CalendarServer/Calendar and Contacts/Data', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/old/Library/AddressBookServer/Documents/addressbooks', '/Volumes/External/CalendarServer/Calendar and Contacts/Documents/addressbooks'),
                ('chown-recursive', '/Volumes/External/CalendarServer/Calendar and Contacts/Documents/addressbooks', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Lion -> Lion Migration, all in default locations",
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/old/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Volumes/old/Library/Server/Calendar and Contacts/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/" : True,
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                "/Library/Server/Calendar and Contacts", # oldServerRootValue
                "Documents", # oldCalDocumentRootValue
                "Data", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Documents",
                "Data"
            ),
            [
                ('ditto', '/Volumes/old/Library/Server/Calendar and Contacts/Documents', '/Volumes/new/Library/Server/Calendar and Contacts/Documents'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Documents', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/old/Library/Server/Calendar and Contacts/Data', '/Volumes/new/Library/Server/Calendar and Contacts/Data'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts/Data', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Lion -> Lion Migration, external ServerRoot with relative DocumentRoot and DataRoot",
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Volumes/External/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/External/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Volumes/External/Library/Server/Calendar and Contacts/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/" : True,
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                "/Volumes/External/Library/Server/Calendar and Contacts", # oldServerRootValue
                "Documents", # oldCalDocumentRootValue
                "Data", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/External/Library/Server/Calendar and Contacts",
                "/Volumes/External/Library/Server/Calendar and Contacts",
                "Documents",
                "Data"
            ),
            [
            ]
        ),


        (
            "Lion -> Lion Migration, external ServerRoot with absolute external DocumentRoot and internal DataRoot",
            {
                "/Volumes/old/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Volumes/External/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>/Volumes/External/CalendarDocuments/</string>
                        <key>DataRoot</key>
                        <string>/CalendarData</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,
                "/Volumes/new/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/Server/Calendar and Contacts</string>
                        <key>DocumentRoot</key>
                        <string>Documents</string>
                        <key>DataRoot</key>
                        <string>Data</string>
                        <key>UserName</key>
                        <string>calendar</string>
                        <key>GroupName</key>
                        <string>calendar</string>
                    </dict>
                    </plist>
                """,

                "/Volumes/External/Library/Server/Calendar and Contacts/" : True,
                "/Volumes/External/CalendarDocuments/" : True,
                "/Volumes/old/CalendarData" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/" : True,
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                "/Volumes/External/Library/Server/Calendar and Contacts", # oldServerRootValue
                "/Volumes/External/CalendarDocuments/", # oldCalDocumentRootValue
                "/CalendarData", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/External/Library/Server/Calendar and Contacts",
                "/Volumes/External/Library/Server/Calendar and Contacts",
                "/Volumes/External/CalendarDocuments",
                "Data" # Note that DataRoot was copied over to external volume
            ),
            [
                ('ditto', '/Volumes/old/CalendarData', '/Volumes/External/Library/Server/Calendar and Contacts/Data'),
                ('chown-recursive', '/Volumes/External/Library/Server/Calendar and Contacts/Data', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Empty migration",
            {   # no files
            },
            (   # args
                "/Volumes/old", # sourceRoot
                "/Volumes/new", # targetRoot
                None, # oldServerRootValue
                None, # oldCalDocumentRootValue
                None, # oldCalDataRootValue
                None, # oldABDocumentRootValue
                -1, -1, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Documents",
                "Data"
            ),
            [   # no history
            ]
        ),

        ]

        for description, paths, args, expected, history in info:
            accessor = StubDiskAccessor(paths)
            actual = relocateData(*args, diskAccessor=accessor)
            self.assertEquals(expected, actual)
            self.assertEquals(history, accessor.history)


    def test_stubDiskAccessor(self):

        paths = {
            "/a/b/c/d" : "foo",
            "/a/b/c/e" : "bar",
            "/x/y/z/" : True,
        }
        accessor = StubDiskAccessor(paths)

        shouldExist = ["/a", "/a/", "/a/b", "/a/b/", "/a/b/c/d", "/x/y/z"]
        shouldNotExist = ["/b", "/x/y/z/Z"]

        for path in shouldExist:
            self.assertTrue(accessor.exists(path))
        for path in shouldNotExist:
            self.assertFalse(accessor.exists(path))

        for key, value in paths.iteritems():
            if value is not True:
                self.assertEquals(accessor.readFile(key), value)


    def test_relativize(self):
        """
        Make sure child paths are made relative to their parent
        """
        info = [
            (("/abc/", "/abc/def"), ("/abc", "def")),
            (("/abc", "/abc/def"), ("/abc", "def")),
            (("/abc", "/def"), ("/abc", "/def")),
        ]
        for args, expected in info:
            self.assertEquals(expected, relativize(*args))


class StubDiskAccessor(object):
    """
    A stub which allows testing without actually having real files
    """

    def __init__(self, paths):
        self.paths = paths
        self._fillInDirectories()

        self.reset()

    def _fillInDirectories(self):
        for key in self.paths.keys():
            parts = key.split("/")
            for i in xrange(len(parts)):
                path = "/".join(parts[:i])
                self.paths[path] = True

    def addPath(self, path, value):
        self.paths[path] = value
        self._fillInDirectories()

    def reset(self):
        self.history = []

    def exists(self, path):
        return self.paths.has_key(path.rstrip("/"))

    def readFile(self, path):
        return self.paths[path]

    def mkdir(self, path):
        self.history.append(("mkdir", path))
        self.addPath(path, True)

    def rename(self, before, after):
        self.history.append(("rename", before, after))

    def isfile(self, path):
        # FIXME: probably want a better way to denote a directory than "True"
        return self.exists(path) and self.paths[path] is not True

    def symlink(self, orig, link):
        self.history.append(("symlink", orig, link))

    def chown(self, path, uid, gid, recursive=False):
        self.history.append(("chown-recursive" if recursive else "chown", path, uid, gid))

    def walk(self, path, followlinks=True):
        yield [], [], []

    def listdir(self, path):
        return []

    def ditto(self, src, dest):
        self.history.append(("ditto", src, dest))
        self.addPath(dest, True)

