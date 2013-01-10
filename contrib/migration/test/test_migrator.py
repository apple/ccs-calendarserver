##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
    mergePlist, examinePreviousSystem, relocateData, relativize, isServiceDisabled,
    ServiceStateError, nextAvailable
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : True,
            "HTTPPort": 8888,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 9999,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : True,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": True,
            "SSLAuthorityChain": "/etc/certificates/test.chain.pem",
            "SSLCertificate": "/etc/certificates/test.cert.pem",
            "SSLPort": 8443,
            "SSLPrivateKey": "/etc/certificates/test.key.pem",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
        self.assertEquals(newCombined, expected)


        # All settings missing!
        oldCalDAV = { }
        oldCardDAV = { }
        expected = {
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
        oldCardDAV = { }
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
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
        oldCardDAV = { }
        expected = {
            "Authentication": {
                "Wiki" : {
                    "Enabled" : True,
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
        self.assertEquals(newCombined, expected)


    def test_disableXMPPNotifier(self):

        # Ensure XMPPNotifier is disabled

        # Both CalDAV and CardDAV push enabled:
        oldCalDAV = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : True,
                        "CalDAV" : {
                            "APSBundleID" : "com.apple.calendar.XServer",
                        },
                        "CardDAV" : {
                            "APSBundleID" : "com.apple.contact.XServer",
                        },
                    },
                },
            },
        }
        oldCardDAV = { }
        expected = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : False,
                        "CalDAV" : {
                            "APSBundleID" : "com.apple.calendar.XServer",
                        },
                        "CardDAV" : {
                            "APSBundleID" : "com.apple.contact.XServer",
                        },
                    },
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [["EnableAPNS", "yes"]])
        self.assertEquals(newCombined, expected)

        # Only with CalDAV push enabled:
        oldCalDAV = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : True,
                        "CalDAV" : {
                            "APSBundleID" : "com.apple.calendar.XServer",
                        },
                    },
                },
            },
        }
        oldCardDAV = { }
        expected = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : False,
                        "CalDAV" : {
                            "APSBundleID" : "com.apple.calendar.XServer",
                        },
                    },
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [["EnableAPNS", "yes"]])
        self.assertEquals(newCombined, expected)

        # Only with CardDAV push enabled:
        oldCalDAV = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : True,
                        "CardDAV" : {
                            "APSBundleID" : "com.apple.contact.XServer",
                        },
                    },
                },
            },
        }
        oldCardDAV = { }
        expected = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : False,
                        "CardDAV" : {
                            "APSBundleID" : "com.apple.contact.XServer",
                        },
                    },
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [["EnableAPNS", "yes"]])
        self.assertEquals(newCombined, expected)

        # APNS push was not previously enabled:
        oldCalDAV = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : True,
                    },
                },
            },
        }
        oldCardDAV = { }
        expected = {
            "Notifications": {
                "Services" : {
                    "XMPPNotifier" : {
                        "Enabled" : False,
                    },
                },
            },
            "BindHTTPPorts": [8008, 8800],
            "BindSSLPorts": [8443, 8843],
            "ConfigRoot" : "Config",
            "DSN" : "",
            "DBType" : "",
            "DBImportFile" : "/Library/Server/Calendar and Contacts/DataDump.sql",
            "EnableSSL" : False,
            "HTTPPort": 8008,
            "RedirectHTTPToHTTPS": False,
            "SSLAuthorityChain": "",
            "SSLCertificate": "",
            "SSLPort": 8443,
            "SSLPrivateKey": "",
        }
        newCombined = { }
        adminChanges = mergePlist(oldCalDAV, oldCardDAV, newCombined)
        self.assertEquals(adminChanges, [])
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
            "Snow -> Mountain Lion Migration, all in default locations",
            ("/Library/Server/Previous", "/"),
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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

                "/Library/Server/Previous/Library/CalendarServer/Documents/calendars/" : True,
                "/Library/Server/Previous/Library/CalendarServer/Data/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Data/" : True,
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
            "Snow -> Mountain Lion Migration, all in default locations, non-/ target",
            ("/Library/Server/Previous", "/Volumes/new"),
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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

                "/Library/Server/Previous/Library/CalendarServer/Documents/calendars/" : True,
                "/Library/Server/Previous/Library/CalendarServer/Data/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Data/" : True,
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
            "Snow -> Mountain Lion Migration, not in default locations",
            ("/Library/Server/Previous", "/"),
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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

                "/Library/Server/Previous/NonStandard/CalendarServer/Documents/calendars/" : True,
                "/Library/Server/Previous/NonStandard/CalendarServer/Data/" : True,
                "/Library/Server/Previous/NonStandard/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/NonStandard/AddressBookServer/Data/" : True,
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
            "Snow -> Mountain Lion Migration, in internal/external locations",
            ("/Library/Server/Previous", "/"),
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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
                "/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Data/" : True,
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
            "Snow -> Mountain Lion Migration, only AddressBook data",
            ("/Library/Server/Previous", "/"),
            {
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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

                "/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Data/" : True,
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
            "Lion -> Mountain Lion Migration, all in default locations",
            ("/Library/Server/Previous", "/"),
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Data/" : True,
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
            "Lion -> Mountain Lion Migration, not in default locations",
            ("/Library/Server/Previous", "/"),
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/NonStandard/Calendar and Contacts/Documents/" : True,
                "/Library/Server/Previous/NonStandard/Calendar and Contacts/Data/" : True,
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
            "Lion -> Mountain Lion Migration, non-/ targetRoot",
            ("/Library/Server/Previous", "/Volumes/new"),
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Data/" : True,
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
            "Empty migration, nothing exists",
            ("/Library/Server/Previous", "/Volumes/new"),
            {
            },
            (
                None, # Old ServerRoot value
                None, # Old Cal DocRoot value
                None, # Old Cal DocRoot value
                None, # Old AB Docs
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
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
            "Snow -> Mountain Lion Migration, all in default locations",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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

                "/Library/Server/Previous/Library/CalendarServer/Documents/calendars/" : True,
                "/Library/Server/Previous/Library/CalendarServer/Data/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Data/" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.6.8", # sourceVersion
                None, # oldServerRootValue
                "/Library/CalendarServer/Documents", # oldCalDocumentRootValue
                "/Library/CalendarServer/Data", # oldCalDataRootValue
                "/Library/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Data"
            ),
            [   # expected DiskAccessor history
                ('ditto', '/Library/Server/Previous/Library/CalendarServer/Data', '/Volumes/new/Library/Server/Calendar and Contacts/Data'),
                ('ditto', '/Library/Server/Previous/Library/CalendarServer/Documents', '/Volumes/new/Library/Server/Calendar and Contacts/Data/Documents'),
                ('ditto', '/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks', '/Volumes/new/Library/Server/Calendar and Contacts/Data/Documents/addressbooks'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Snow -> Mountain Lion Migration, external DocumentRoot",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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
                "/Volumes/External/CalendarServer/Calendar and Contacts Data/" : True,
                "/Volumes/External/CalendarServer/Calendar and Contacts Data.bak/" : True,
                "/Volumes/External/CalendarServer/Calendar and Contacts Data.1.bak/" : True,
                "/Volumes/External/CalendarServer/Calendar and Contacts Data.2.bak/" : True,
                "/Library/Server/Previous/Library/CalendarServer/Data/" : True,
                "/Volumes/External/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Data/" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.6.8", # sourceVersion
                None, # oldServerRootValue
                "/Volumes/External/CalendarServer/Documents", # oldCalDocumentRootValue
                "/Library/CalendarServer/Data", # oldCalDataRootValue
                "/Volumes/External/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "/Volumes/External/CalendarServer/Calendar and Contacts Data",
            ),
            [   # expected DiskAccessor history
                ('rename',
                 '/Volumes/External/CalendarServer/Calendar and Contacts Data',
                 '/Volumes/External/CalendarServer/Calendar and Contacts Data.3.bak'),
                ('ditto', '/Library/Server/Previous/Library/CalendarServer/Data', '/Volumes/External/CalendarServer/Calendar and Contacts Data'),
                ('rename', '/Volumes/External/CalendarServer/Documents', '/Volumes/External/CalendarServer/Calendar and Contacts Data/Documents'),
                ('chown-recursive', '/Volumes/External/CalendarServer/Calendar and Contacts Data', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Volumes/External/AddressBookServer/Documents/addressbooks', '/Volumes/External/CalendarServer/Calendar and Contacts Data/Documents/addressbooks'),
                ('mkdir', '/Volumes/new/Library/Server/Calendar and Contacts'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Snow -> Mountain Lion Migration, in non-standard locations",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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

                "/Library/Server/Previous/NonStandard/CalendarServer/Documents/calendars/" : True,
                "/Library/Server/Previous/NonStandard/CalendarServer/Data/" : True,
                "/Library/Server/Previous/NonStandard/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/NonStandard/AddressBookServer/Data/" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.6.8", # sourceVersion
                None, # oldServerRootValue
                "/NonStandard/CalendarServer/Documents", # oldCalDocumentRootValue
                "/NonStandard/CalendarServer/Data", # oldCalDataRootValue
                "/NonStandard/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Data"
            ),
            [
                ('ditto', '/Library/Server/Previous/NonStandard/CalendarServer/Data', '/Volumes/new/Library/Server/Calendar and Contacts/Data'),
                ('ditto', '/Library/Server/Previous/NonStandard/CalendarServer/Documents', '/Volumes/new/Library/Server/Calendar and Contacts/Data/Documents'),
                ('ditto', '/Library/Server/Previous/NonStandard/AddressBookServer/Documents/addressbooks', '/Volumes/new/Library/Server/Calendar and Contacts/Data/Documents/addressbooks'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Snow -> Mountain Lion Migration, internal AB, external Cal",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
                "/Library/Server/Previous/private/etc/carddavd/carddavd.plist" : """
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
                "/Library/Server/Previous/Library/CalendarServer/Data/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks/" : True,
                "/Library/Server/Previous/Library/AddressBookServer/Data/" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.6.8", # sourceVersion
                None, # oldServerRootValue
                "/Volumes/External/CalendarServer/Documents", # oldCalDocumentRootValue
                "/Library/CalendarServer/Data", # oldCalDataRootValue
                "/Library/AddressBookServer/Documents", # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "/Volumes/External/CalendarServer/Calendar and Contacts Data",
            ),
            [
                ('ditto',
                 '/Library/Server/Previous/Library/CalendarServer/Data',
                 '/Volumes/External/CalendarServer/Calendar and Contacts Data'),
                ('rename', '/Volumes/External/CalendarServer/Documents', '/Volumes/External/CalendarServer/Calendar and Contacts Data/Documents'),
                ('chown-recursive', '/Volumes/External/CalendarServer/Calendar and Contacts Data', FakeUser.pw_uid, FakeGroup.gr_gid),
                ('ditto', '/Library/Server/Previous/Library/AddressBookServer/Documents/addressbooks', '/Volumes/External/CalendarServer/Calendar and Contacts Data/Documents/addressbooks'),
                ('mkdir', '/Volumes/new/Library/Server/Calendar and Contacts'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Lion -> Mountain Lion Migration, all in default locations",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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

                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/Data" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/Documents" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.7.3", # sourceVersion
                "/Library/Server/Calendar and Contacts", # oldServerRootValue
                "Documents", # oldCalDocumentRootValue
                "Data", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Data"
            ),
            [
                ('ditto', '/Library/Server/Previous/Library/Server/Calendar and Contacts', '/Volumes/new/Library/Server/Calendar and Contacts'),
                ('rename', '/Volumes/new/Library/Server/Calendar and Contacts/Documents', '/Volumes/new/Library/Server/Calendar and Contacts/Data/Documents'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Lion -> Mountain Lion Migration, all in default locations, with existing Data/Documents",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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

                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Data/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/Data" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/Data/Documents" : True,
                "/Volumes/new/Library/Server/Calendar and Contacts/Documents" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.7.3", # sourceVersion
                "/Library/Server/Calendar and Contacts", # oldServerRootValue
                "Documents", # oldCalDocumentRootValue
                "Data", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Data"
            ),
            [
                ('ditto', '/Library/Server/Previous/Library/Server/Calendar and Contacts', '/Volumes/new/Library/Server/Calendar and Contacts'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),


        (
            "Lion -> Mountain Lion Migration, external ServerRoot",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.7.3", # sourceVersion
                "/Volumes/External/Library/Server/Calendar and Contacts", # oldServerRootValue
                "Documents", # oldCalDocumentRootValue
                "Data", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "/Volumes/External/Library/Server/Calendar and Contacts/Data",
            ),
            [
            ('rename',
              '/Volumes/External/Library/Server/Calendar and Contacts/Documents',
              '/Volumes/External/Library/Server/Calendar and Contacts/Data/Documents'),
            ('mkdir', '/Volumes/new/Library/Server/Calendar and Contacts'),
            ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Lion -> Mountain Lion Migration, ServerRoot is non-standard but also not on an external volume, e.g. /Library/CalendarServer/Documents",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
                    <plist version="1.0">
                    <dict>
                        <key>ServerRoot</key>
                        <string>/Library/CalendarServer/Documents</string>
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

                "/Library/Server/Previous/Library/CalendarServer/Documents/" : True,
                "/Library/Server/Previous/Library/CalendarServer/Documents/Documents/" : True,
                "/Library/Server/Previous/Library/CalendarServer/Documents/Data/" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.7.4", # sourceVersion
                "/Library/CalendarServer/Documents", # oldServerRootValue
                "Documents", # oldCalDocumentRootValue
                "Data", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Data",
            ),
            [
                ('ditto', '/Library/Server/Previous/Library/CalendarServer/Documents', '/Volumes/new/Library/Server/Calendar and Contacts'),
                ('mkdir', '/Volumes/new/Library/Server/Calendar and Contacts/Data'),
                ('mkdir', '/Volumes/new/Library/Server/Calendar and Contacts/Data/Documents'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Mountain Lion -> Mountain Lion Migration, all in default locations",
            {
                "/Library/Server/Previous/private/etc/caldavd/caldavd.plist" : """
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

                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Documents/" : True,
                "/Library/Server/Previous/Library/Server/Calendar and Contacts/Data/" : True,
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.8", # sourceVersion
                "/Library/Server/Calendar and Contacts", # oldServerRootValue
                "Documents", # oldCalDocumentRootValue
                "Data", # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Data"
            ),
            [
                ('ditto', '/Library/Server/Previous/Library/Server/Calendar and Contacts', '/Volumes/new/Library/Server/Calendar and Contacts'),
                ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', FakeUser.pw_uid, FakeGroup.gr_gid),
            ]
        ),

        (
            "Empty migration",
            {   # no files
            },
            (   # args
                "/Library/Server/Previous", # sourceRoot
                "/Volumes/new", # targetRoot
                "10.6.8", # sourceVersion
                None, # oldServerRootValue
                None, # oldCalDocumentRootValue
                None, # oldCalDataRootValue
                None, # oldABDocumentRootValue
                FakeUser.pw_uid, FakeGroup.gr_gid, # user id, group id
            ),
            (   # expected return values
                "/Volumes/new/Library/Server/Calendar and Contacts",
                "/Library/Server/Calendar and Contacts",
                "Data"
            ),
            [
             ('mkdir', '/Volumes/new/Library/Server/Calendar and Contacts'),
             ('chown-recursive', '/Volumes/new/Library/Server/Calendar and Contacts', 6543, 7654)
            ]
        ),

        ]

        for description, paths, args, expected, history in info:
            accessor = StubDiskAccessor(paths)
            actual = relocateData(*args, diskAccessor=accessor)
            self.assertEquals(expected, actual)
            self.assertEquals(history, accessor.history)


    def test_nextAvailable(self):
        data = [
            ( { }, "a.bak" ),
            ( { "a.bak": True }, "a.1.bak" ),
            ( { "a.bak": True, "a.1.bak" : True }, "a.2.bak" ),
        ]
        for paths, expected in data:
            accessor = StubDiskAccessor(paths)
            actual = nextAvailable("a", "bak", diskAccessor=accessor)
            self.assertEquals(actual, expected)


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


    def test_createExistingDirectory(self):
        import os
        t = self.mktemp()
        os.mkdir(t)
        da = contrib.migration.calendarmigrator.DiskAccessor()
        self.assertEquals(da.mkdir(t), None)


    def test_createDirectory(self):
        t = self.mktemp()
        da = contrib.migration.calendarmigrator.DiskAccessor()
        self.assertEquals(da.mkdir(t), None)


    def test_isServiceDisabledTrue(self):
        CONTENTS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>foo</key>
        <dict>
                <key>Disabled</key>
                <true/>
        </dict>
</dict>
</plist>
"""
        t = self.mktemp()
        f = open(t, "w")
        f.write(CONTENTS)
        f.close()
        self.assertTrue(isServiceDisabled("", "foo", t))

    def test_isServiceDisabledFalse(self):
        CONTENTS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>foo</key>
        <dict>
                <key>Disabled</key>
                <false/>
        </dict>
</dict>
</plist>
"""
        t = self.mktemp()
        f = open(t, "w")
        f.write(CONTENTS)
        f.close()
        self.assertFalse(isServiceDisabled("", "foo", t))

    def test_isServiceDisabledError(self):
        CONTENTS = """This is not a plist """
        t = self.mktemp()
        f = open(t, "w")
        f.write(CONTENTS)
        f.close()
        try:
            isServiceDisabled("", "foo", t)
        except ServiceStateError:
            pass
        else:
            self.fail(msg="Didn't raise ServiceStateError")


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

