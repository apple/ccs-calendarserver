# -*- test-case-name: twistedcaldav.test.test_stdconfig -*-
##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

from socket import getfqdn
from socket import gethostbyname
import copy
import os
import re

from twext.web2.dav import davxml
from twext.web2.dav.resource import TwistedACLInheritable

from twext.python.plistlib import PlistParser #@UnresolvedImport
from twext.python.log import Logger, InvalidLogLevelError
from twext.python.log import clearLogLevels, setLogLevelForNamespace

from twistedcaldav import caldavxml, customxml, carddavxml, mkcolxml
from twistedcaldav.config import ConfigProvider, ConfigurationError
from twistedcaldav.config import config, _mergeData, fullServerPath
from twistedcaldav.util import getPasswordFromKeychain
from twistedcaldav.util import KeychainAccessError, KeychainPasswordNotFound

from twisted.python.runtime import platform

from calendarserver.push.util import getAPNTopicFromCertificate

log = Logger()

if platform.isMacOSX():
    DEFAULT_CONFIG_FILE = "/Library/Server/Calendar and Contacts/Config/caldavd.plist"
else:
    DEFAULT_CONFIG_FILE = "/etc/caldavd/caldavd.plist"

DEFAULT_SERVICE_PARAMS = {
    "twistedcaldav.directory.xmlfile.XMLDirectoryService": {
        "xmlFile": "accounts.xml",
        "recordTypes": ("users", "groups"),
        "statSeconds" : 15,
    },
    "twistedcaldav.directory.appleopendirectory.OpenDirectoryService": {
        "node": "/Search",
        "cacheTimeout": 10, # Minutes
        "batchSize": 100, # for splitting up large queries
        "negativeCaching": False,
        "restrictEnabledRecords": False,
        "restrictToGroup": "",
        "recordTypes": ("users", "groups"),
    },
    "twistedcaldav.directory.ldapdirectory.LdapDirectoryService": {
        "cacheTimeout": 10, # Minutes
        "negativeCaching": False,
        "warningThresholdSeconds": 3,
        "batchSize": 500, # for splitting up large queries
        "queryLocationsImplicitly": True,
        "restrictEnabledRecords": False,
        "restrictToGroup": "",
        "recordTypes": ("users", "groups"),
        "uri": "ldap://localhost/",
        "tls": False,
        "tlsCACertFile": None,
        "tlsCACertDir": None,
        "tlsRequireCert": None, # never, allow, try, demand, hard
        "credentials": {
            "dn": None,
            "password": None,
        },
        "authMethod": "LDAP",
        "rdnSchema": {
            "base": "dc=example,dc=com",
            "guidAttr": None,
            "users": {
                "rdn": "ou=People",
                "attr": "uid", # used only to synthesize email address
                "emailSuffix": None, # used only to synthesize email address
                "filter": None, # additional filter for this type
                "loginEnabledAttr" : "", # attribute controlling login
                "loginEnabledValue" : "yes", # "True" value of above attribute
                "calendarEnabledAttr" : "", # attribute controlling enabledForCalendaring
                "calendarEnabledValue" : "yes", # "True" value of above attribute
                "mapping" : { # maps internal record names to LDAP
                    "recordName": "uid",
                    "fullName" : "cn",
                    "emailAddresses" : "mail",
                    "firstName" : "givenName",
                    "lastName" : "sn",
                },
            },
            "groups": {
                "rdn": "ou=Group",
                "attr": "cn", # used only to synthesize email address
                "emailSuffix": None, # used only to synthesize email address
                "filter": None, # additional filter for this type
                "mapping" : { # maps internal record names to LDAP
                    "recordName": "cn",
                    "fullName" : "cn",
                    "emailAddresses" : "mail",
                    "firstName" : "givenName",
                    "lastName" : "sn",
                },
            },
            "locations": {
                "rdn": "ou=Places",
                "attr": "cn", # used only to synthesize email address
                "emailSuffix": None, # used only to synthesize email address
                "filter": None, # additional filter for this type
                "calendarEnabledAttr" : "", # attribute controlling enabledForCalendaring
                "calendarEnabledValue" : "yes", # "True" value of above attribute
                "mapping" : { # maps internal record names to LDAP
                    "recordName": "cn",
                    "fullName" : "cn",
                    "emailAddresses" : "mail",
                    "firstName" : "givenName",
                    "lastName" : "sn",
                },
            },
            "resources": {
                "rdn": "ou=Resources",
                "attr": "cn", # used only to synthesize email address
                "emailSuffix": None, # used only to synthesize email address
                "filter": None, # additional filter for this type
                "calendarEnabledAttr" : "", # attribute controlling enabledForCalendaring
                "calendarEnabledValue" : "yes", # "True" value of above attribute
                "mapping" : { # maps internal record names to LDAP
                    "recordName": "cn",
                    "fullName" : "cn",
                    "emailAddresses" : "mail",
                    "firstName" : "givenName",
                    "lastName" : "sn",
                },
            },
        },
        "groupSchema": {
            "membersAttr": "member", # how members are specified
            "nestedGroupsAttr": None, # how nested groups are specified
            "memberIdAttr": None, # which attribute the above refer to
        },
        "resourceSchema": {
            "resourceInfoAttr": None, # contains location/resource info
        },
        "partitionSchema": {
            "serverIdAttr": None, # maps to augments server-id
            "partitionIdAttr": None, # maps to augments partition-id
        },
    },
}

DEFAULT_RESOURCE_PARAMS = {
    "twistedcaldav.directory.xmlfile.XMLDirectoryService": {
        "xmlFile": "resources.xml",
        "recordTypes" : ("locations", "resources"),
    },
    "twistedcaldav.directory.appleopendirectory.OpenDirectoryService": {
        "node": "/Search",
        "cacheTimeout": 1, # Minutes
        "negativeCaching": False,
        "restrictEnabledRecords": False,
        "restrictToGroup": "",
        "recordTypes" : ("locations", "resources"),
    },
}

DEFAULT_AUGMENT_PARAMS = {
    "twistedcaldav.directory.augment.AugmentXMLDB": {
        "xmlFiles": ["augments.xml",],
        "statSeconds" : 15,
    },
    "twistedcaldav.directory.augment.AugmentSqliteDB": {
        "dbpath": "augments.sqlite",
    },
    "twistedcaldav.directory.augment.AugmentPostgreSQLDB": {
        "host":     "localhost",
        "database": "augments",
        "user":     "",
        "password": "",
    },
}

DEFAULT_PROXYDB_PARAMS = {
    "twistedcaldav.directory.calendaruserproxy.ProxySqliteDB": {
        "dbpath": "proxies.sqlite",
    },
    "twistedcaldav.directory.calendaruserproxy.ProxyPostgreSQLDB": {
        "host":     "localhost",
        "database": "proxies",
        "user":     "",
        "password": "",
        "dbtype": "",
    },
}


directoryAddressBookBackingServiceDefaultParams = {
    "twistedcaldav.directory.xmlfile.XMLDirectoryService": {
        "xmlFile": "/etc/carddavd/accounts.xml",
    },
    "twistedcaldav.directory.opendirectorybacker.OpenDirectoryBackingService": {
        "queryPeopleRecords": True,
        "peopleNode": "/Search/Contacts",
        "queryUserRecords": True,
        "userNode": "/Search/Contacts",
        "maxDSQueryRecords":0,
        "queryDSLocal": False,
        "ignoreSystemRecords": True,
        "dsLocalCacheTimeout":30,
        "liveQuery": True,
        "fakeETag": True,
        "cacheQuery": False,
        "cacheTimeout": 30,
        "standardizeSyntheticUIDs": False,
        "addDSAttrXProperties": False,
        "appleInternalServer": False,
        "additionalAttributes" : [],
        "allowedAttributes" : [],
    },
}

DEFAULT_CONFIG = {
    # Note: Don't use None values below; that confuses the command-line parser.

    #
    # Public network address information
    #
    #    This is the server's public network address, which is provided to
    #    clients in URLs and the like.  It may or may not be the network
    #    address that the server is listening to directly, though it is by
    #    default.  For example, it may be the address of a load balancer or
    #    proxy which forwards connections to the server.
    #
    "ServerHostName": "",          # Network host name.
    "HTTPPort": 0,                 # HTTP port (0 to disable HTTP)
    "SSLPort" : 0,                 # SSL port (0 to disable HTTPS)
    "EnableSSL" : False,           # Whether to listen on SSL port(s)
    "RedirectHTTPToHTTPS" : False, # If True, all nonSSL requests redirected to an SSL Port
    "SSLMethod" : "SSLv3_METHOD",  # SSLv2_METHOD, SSLv3_METHOD, SSLv23_METHOD, TLSv1_METHOD
    "SSLCiphers" : "ALL:!aNULL:!ADH:!eNULL:!LOW:!EXP:RC4+RSA:+HIGH:+MEDIUM",

    #
    # Network address configuration information
    #
    #    This configures the actual network address that the server binds to.
    #
    "BindAddresses": [],   # List of IP addresses to bind to [empty = all]
    "BindHTTPPorts": [],   # List of port numbers to bind to for HTTP
                           # [empty = same as "Port"]
    "BindSSLPorts" : [],   # List of port numbers to bind to for SSL
                           # [empty = same as "SSLPort"]
    "InheritFDs"   : [],   # File descriptors to inherit for HTTP requests
                           # (empty = don't inherit)
    "InheritSSLFDs": [],   # File descriptors to inherit for HTTPS requests
                           # (empty = don't inherit)
    "MetaFD"       : 0,    # Inherited file descriptor to call recvmsg() on to
                           # receive sockets (none = don't inherit)

    "UseMetaFD"    : True, # Use a 'meta' FD, i.e. an FD to transmit other FDs
                           # to slave processes.

    "UseDatabase"  : True, # True: database; False: files

    "DBType"       : "",   # 2 possible values: empty, meaning 'spawn postgres
                           # yourself', or 'postgres', meaning 'connect to a
                           # postgres database as specified by the 'DSN'
                           # configuration key.  Will support more values in
                           # the future.

    "DSN"          : "",   # Data Source Name.  Used to connect to an external
                           # database if DBType is non-empty.  Format varies
                           # depending on database type.

    "DBAMPFD"      : 0,    # Internally used by database to tell slave
                           # processes to inherit a file descriptor and use it
                           # as an AMP connection over a UNIX socket; see
                           # twext.enterprise.adbapi2.ConnectionPoolConnection

    "SharedConnectionPool" : False, # Use a shared database connection pool in
                                    # the master process, rather than having
                                    # each client make its connections directly.

    #
    # Types of service provided
    #
    "EnableCalDAV"  : True,  # Enable CalDAV service
    "EnableCardDAV" : True,  # Enable CardDAV service

    #
    # Data store
    #
    "ServerRoot"              : "/var/db/caldavd",
    "DataRoot"                : "Data",
    "DatabaseRoot"            : "Database",
    "AttachmentsRoot"         : "Attachments",
    "DocumentRoot"            : "Documents",
    "ConfigRoot"              : "Config",
    "LogRoot"                 : "/var/log/caldavd",
    "RunRoot"                 : "/var/run/caldavd",
    "WebCalendarRoot"         : "/Applications/Server.app/Contents/ServerRoot/usr/share/collabd",
    
    #
    # Quotas
    #
    
    # Attachments
    "UserQuota"                 : 104857600, # User attachment quota (in bytes)
    
    # Resource data
    "MaxCollectionsPerHome"     :      50, # Maximum number of calendars/address books allowed in a home
    "MaxResourcesPerCollection" :   10000, # Maximum number of resources in a calendar/address book
    "MaxResourceSize"           : 1048576, # Maximum resource size (in bytes)
    "MaxAttendeesPerInstance"   :     100, # Maximum number of unique attendees
    "MaxAllowedInstances"       :    3000, # Maximum number of instances the server will index
    "MaxInstancesForRRULE"      :     400, # Maximum number of instances for an RRULE

    # Set to URL path of wiki authentication service, e.g. "/auth", in order
    # to use javascript authentication dialog.  Empty string indicates standard
    # browser authentication dialog should be used.
    "WebCalendarAuthPath"     : "",

    "Aliases": {},

    #
    # Directory service
    #
    #    A directory service provides information about principals (eg.
    #    users, groups, locations and resources) to the server.
    #
    "DirectoryService": {
        "type": "twistedcaldav.directory.xmlfile.XMLDirectoryService",
        "params": DEFAULT_SERVICE_PARAMS["twistedcaldav.directory.xmlfile.XMLDirectoryService"],
    },

    #
    # Locations and Resources service
    #
    #    Supplements the directory service with information about locations
    #    and resources.
    #
    "ResourceService": {
        "Enabled" : True,
        "type": "twistedcaldav.directory.xmlfile.XMLDirectoryService",
        "params": DEFAULT_RESOURCE_PARAMS["twistedcaldav.directory.xmlfile.XMLDirectoryService"],
    },

    #
    # Augment service
    #
    #    Augments for the directory service records to add calendar specific attributes.
    #
    "AugmentService": {
        "type": "twistedcaldav.directory.augment.AugmentXMLDB",
        "params" : DEFAULT_AUGMENT_PARAMS["twistedcaldav.directory.augment.AugmentXMLDB"],
    },

    #
    # Proxies
    #
    "ProxyDBService": {
        "type": "twistedcaldav.directory.calendaruserproxy.ProxySqliteDB",
        "params": DEFAULT_PROXYDB_PARAMS["twistedcaldav.directory.calendaruserproxy.ProxySqliteDB"],
    },
    "ProxyLoadFromFile": "",    # Allows for initialization of the proxy database from an XML file

    #
    # Special principals
    #
    "AdminPrincipals": [],                       # Principals with "DAV:all" access (relative URLs)
    "ReadPrincipals": [],                        # Principals with "DAV:read" access (relative URLs)
    "SudoersFile": "sudoers.plist",              # Principals that can pose as other principals
    "EnableProxyPrincipals": True,               # Create "proxy access" principals

    #
    # Permissions
    #
    "EnableAnonymousReadRoot": True,    # Allow unauthenticated read access to /
    "EnableAnonymousReadNav": False,    # Allow unauthenticated read access to hierarchy
    "EnablePrincipalListings": True,    # Allow listing of principal collections
    "EnableMonolithicCalendars": True,  # Render calendar collections as a monolithic iCalendar object

    #
    # Client controls
    #
    "RejectClients": [], # List of regexes for clients to disallow

    #
    # Authentication
    #
    "Authentication": {
        "Basic": { "Enabled": False },     # Clear text; best avoided
        "Digest": {                        # Digest challenge/response
            "Enabled": True,
            "Algorithm": "md5",
            "Qop": "",
        },
        "Kerberos": {                       # Kerberos/SPNEGO
            "Enabled": False,
            "ServicePrincipal": ""
        },
        "Wiki": {
            "Enabled": False,
            "Cookie": "apple_webauth_token",
            "URL": "http://127.0.0.1:8089/RPC2",
            "UserMethod": "userForSession",
            "WikiMethod": "accessLevelForUserWikiCalendar",
            "LionCompatibility": False,
            "CollabHost": "localhost",
            "CollabPort": 4444,
        },
    },

    #
    # Logging
    #
    "AccessLogFile"  : "access.log",  # Apache-style access log
    "ErrorLogFile"   : "error.log",   # Server activity log
    "ErrorLogEnabled"   : True,       # True = use log file, False = stdout
    "ErrorLogRotateMB"  : 10,         # Rotate error log after so many megabytes
    "ErrorLogMaxRotatedFiles"  : 5,   # Retain this many error log files
    "PIDFile"        : "caldavd.pid",
    "RotateAccessLog"   : False,
    "EnableExtendedAccessLog": True,
    "DefaultLogLevel"   : "",
    "LogLevels"         : {},
    "LogID"             : "",

    "AccountingCategories": {
        "iTIP": False,
    },
    "AccountingPrincipals": [],
    "AccountingLogRoot"   : "accounting",

    "GlobalStatsSocket"           : "caldavd-stats.sock", 
    "GlobalStatsLoggingPeriod"    : 60, 
    "GlobalStatsLoggingFrequency" : 12,
    
    "LogDatabase" : {
        "LabelsInSQL"   : False,
        "Statistics"    : False,
        "SQLStatements" : False,
    },

    #
    # SSL/TLS
    #
    "SSLCertificate"     : "",  # Public key
    "SSLPrivateKey"      : "",  # Private key
    "SSLAuthorityChain"  : "",  # Certificate Authority Chain
    "SSLPassPhraseDialog": "/etc/apache2/getsslpassphrase",
    "SSLCertAdmin"       : "/Applications/Server.app/Contents/ServerRoot/usr/sbin/certadmin",

    #
    # Process management
    #

    # Username and Groupname to drop privileges to, if empty privileges will
    # not be dropped.

    "UserName": "",
    "GroupName": "",
    "ProcessType": "Combined",
    "MultiProcess": {
        "ProcessCount": 0,
        "MinProcessCount": 2,
        "PerCPU": 1,
        "PerGB": 1,
        "StaggeredStartup": {
            "Enabled": False,
            "Interval": 15,
        },
    },

    #
    # Service ACLs
    #
    "EnableSACLs": False,

    "EnableReadOnlyServer": False, # Make all data read-only

    #
    # Standard (or draft) WebDAV extensions
    #
    "EnableAddMember"             : True,  # POST ;add-member extension
    "EnableSyncReport"            : True,  # REPORT collection-sync
    "EnableSyncReportHome"        : True,  # REPORT collection-sync on home collections
    "EnableWellKnown"             : True,  # /.well-known resource
    "EnableCalendarQueryExtended" : True,  # Extended calendar-query REPORT

    #
    # Non-standard CalDAV extensions
    #
    "EnableDropBox"           : False, # Calendar Drop Box
    "EnablePrivateEvents"     : False, # Private Events
    "EnableTimezoneService"   : False, # Old Timezone service
    
    "TimezoneService"         : {    # New standard timezone service
        "Enabled"       : False,     # Overall on/off switch
        "Mode"          : "primary", # Can be "primary" or "secondary"
        "BasePath"      : "",        # Path to zoneinfo - if None use default package path
                                     # secondary service MUST define its own writable path
        "XMLInfoPath"   : "",        # Path to db cache info - if None use default package path
                                     # secondary service MUST define its own writable path if
                                     # not None
        
        "SecondaryService" : {
            # Only one of these should be used when a secondary service is used
            "Host"                  : "",        # Domain/IP of secondary service to discover
            "URI"                   : "",        # HTTP(s) URI to secondary service

            "UpdateIntervalMinutes" : 24 * 60,
        }
    },
    
    "EnableTimezonesByReference" : False, # Strip out VTIMEZONES that are known

    "EnableBatchUpload"       : True,     # POST batch uploads
    "MaxResourcesBatchUpload" : 100,      # Maximum number of resources in a batch POST
    "MaxBytesBatchUpload"     : 10485760, # Maximum size of a batch POST (10 MB)
    
    "Sharing": {
        "Enabled"             : False, # Overall on/off switch
        "AllowExternalUsers"  : False, # External (non-principal) sharees allowed

        "Calendars" : {
            "Enabled"         : True,  # Calendar on/off switch
        },
        "AddressBooks" : {
            "Enabled"         : True,  # Address Books on/off switch
        }        
    },
    
    "RestrictCalendarsToOneComponentType" : True,  # Only allow calendars to be created with a single component type
                                                   # If this is on, it will also trigger an upgrade behavior that will
                                                   # split existing calendars into multiples based on component type.
                                                   # If on, it will also cause new accounts to provision with separate
                                                   # calendars for events and tasks.

    "ParallelUpgrades" : False,    # Perform upgrades - currently only the
                                   # database -> filesystem migration - but in
                                   # the future, hopefully all relevant
                                   # upgrades - in parallel in subprocesses.

    "MergeUpgrades": False, # During the upgrade phase of startup, rather than
                            # skipping homes found both on the filesystem and in
                            # the database, merge the data from the filesystem
                            # into the database homes.

    "EnableDefaultAlarms" : True, # Support for default alarms generated by the server

    # CardDAV Features
    "DirectoryAddressBook": {
        "Enabled": True,
        "type":    "twistedcaldav.directory.opendirectorybacker.OpenDirectoryBackingService",
        "params":  directoryAddressBookBackingServiceDefaultParams["twistedcaldav.directory.opendirectorybacker.OpenDirectoryBackingService"],
        "name":    "directory",
        "MaxQueryResults": 1000,
    },
    "EnableSearchAddressBook": False, # /directory resource exists
    "AnonymousDirectoryAddressBookAccess": False, # Anonymous users may access directory address book

    "GlobalAddressBook": {
        "Enabled":                   False,
        "Name":                      "global-addressbook",
        "EnableAnonymousReadAccess": False,
    },

    # /XXX CardDAV

    #
    # Web-based administration
    #
    "EnableWebAdmin"          : True,

    #
    # Scheduling related options
    #

    "Scheduling": {
        
        "CalDAV": {
            "EmailDomain"                : "",    # Domain for mailto calendar user addresses on this server
            "HTTPDomain"                 : "",    # Domain for http calendar user addresses on this server
            "AddressPatterns"            : [],    # Regex patterns to match local calendar user addresses
            "OldDraftCompatibility"      : True,  # Whether to maintain compatibility with non-implicit mode
            "ScheduleTagCompatibility"   : True,  # Whether to support older clients that do not use Schedule-Tag feature
            "EnablePrivateComments"      : True,  # Private comments from attendees to organizer
        },

        "iSchedule": {
            "Enabled"          : False, # iSchedule protocol
            "AddressPatterns"  : [],    # Reg-ex patterns to match iSchedule-able calendar user addresses
            "Servers"          : "servertoserver.xml",    # iSchedule server configurations
        },

        "iMIP": {
            "Enabled"          : False, # Server-to-iMIP protocol
            "MailGatewayServer" : "localhost",
            "MailGatewayPort"   : 62310,
            "Username"          : "com.apple.calendarserver", # For account injecting replies
            "Password"          : "",    # For account injecting replies
            "GUID"              : "B86ED9D3-49BD-44F8-8F5E-C89D08753DAC", # GUID for special internal user
            "Header"            : "x-calendarserver-internal", # HTTP header for internal authentication
            "Sending": {
                "Server"        : "",    # SMTP server to relay messages through
                "Port"          : 587,   # SMTP server port to relay messages through
                "Address"       : "",    # 'From' address for server
                "UseSSL"        : True,
                "Username"      : "",    # For account sending mail
                "Password"      : "",    # For account sending mail
                "SuppressionDays" : 7,   # Messages for events older than this may days are not sent
            },
            "Receiving": {
                "Server"        : "",    # Server to retrieve email messages from
                "Port"          : 0,     # Server port to retrieve email messages from
                "UseSSL"        : True,
                "Type"          : "",    # Type of message access server: 'pop' or 'imap'
                "PollingSeconds"    : 30,  # How often to fetch mail
                "Username"      : "",    # For account receiving mail
                "Password"      : "",    # For account receiving mail
            },
            "AddressPatterns"   : [],    # Regex patterns to match iMIP-able calendar user addresses
            "MailTemplatesDirectory": "/usr/share/caldavd/share/email_templates", # Directory containing HTML templates for email invitations (invite.html, cancel.html)
            "MailIconsDirectory": "/usr/share/caldavd/share/date_icons", # Directory containing language-specific subdirectories containing date-specific icons for email invitations
            "InvitationDaysToLive" : 90, # How many days invitations are valid
        },

        "Options" : {
            "AllowGroupAsOrganizer"               : False, # Allow groups to be Organizers
            "AllowLocationAsOrganizer"            : False, # Allow locations to be Organizers
            "AllowResourceAsOrganizer"            : False, # Allow resources to be Organizers
            "LimitFreeBusyAttendees"              :  30,    # Maximum number of attendees to request freebusy for
            "AttendeeRefreshBatch"                :   5,    # Number of attendees to do batched refreshes: 0 - no batching
            "AttendeeRefreshBatchDelaySeconds"    :   5,    # Time after an iTIP REPLY for first batched attendee refresh
            "AttendeeRefreshBatchIntervalSeconds" :   5,    # Time between attendee batch refreshes
            "UIDLockTimeoutSeconds"               :  60,    # Time for implicit UID lock timeout
            "UIDLockExpirySeconds"                : 300,    # Expiration time for UID lock,
            "V1Compatibility"                     : False,  # Allow /path-based CUAs in scheduling replies
            "PrincipalHostAliases"                : [],     # Hostnames matched in http(s) CUAs
            
            "AutoSchedule" : {
                "Enabled"                         : True,   # Auto-scheduling will never occur if set to False
                "Always"                          : False,  # Override augments setting and always auto-schedule
                "AllowUsers"                      : False,  # Allow auto-schedule for users
                "DefaultMode"                     : "automatic",   # Default mode for auto-schedule processing, one of:
                                                                   # "none"            - no auto-scheduling
                                                                   # "accept-always"   - always accept, ignore busy time
                                                                   # "decline-always"  - always decline, ignore free time
                                                                   # "accept-if-free"  - accept if free, do nothing if busy
                                                                   # "decline-if-busy" - decline if busy, do nothing if free
                                                                   # "automatic"       - accept if free, decline if busy
            }
        }
    },

    "FreeBusyURL": {
        "Enabled"          : False, # Per-user free-busy-url protocol
        "TimePeriod"       : 14,    # Number of days into the future to generate f-b data if no explicit time-range is specified
        "AnonymousAccess"  : False, # Allow anonymous read access to free-busy URL
    },

    #
    # Notifications
    #
    "Notifications" : {
        "Enabled": False,
        "CoalesceSeconds" : 3,
        "InternalNotificationHost" : "localhost",
        "InternalNotificationPort" : 62309,
        "BindAddress" : "127.0.0.1",

        "Services" : {
            "SimpleLineNotifier" : {
                "Service" : "twistedcaldav.notify.SimpleLineNotifierService",
                "Enabled" : False,
                "Port" : 62308,
            },
            "ApplePushNotifier" : {
                "Service" : "calendarserver.push.applepush.ApplePushNotifierService",
                "Enabled" : False,
                "SubscriptionURL" : "apns",
                "AuthMechanisms" : [],
                "DataHost" : "",
                "ProviderHost" : "gateway.push.apple.com",
                "ProviderPort" : 2195,
                "FeedbackHost" : "feedback.push.apple.com",
                "FeedbackPort" : 2196,
                "FeedbackUpdateSeconds" : 28800, # 8 hours
                "Environment" : "PRODUCTION",
                "CalDAV" : {
                    "CertificatePath" : "",
                    "PrivateKeyPath" : "",
                    "AuthorityChainPath" : "",
                    "Passphrase" : "",
                    "Topic" : "",
                },
                "CardDAV" : {
                    "CertificatePath" : "",
                    "PrivateKeyPath" : "",
                    "AuthorityChainPath" : "",
                    "Passphrase" : "",
                    "Topic" : "",
                },
            },
            "XMPPNotifier" : {
                "Service" : "twistedcaldav.notify.XMPPNotifierService",
                "Enabled" : False,
                "Host" : "", # "xmpp.host.name"
                "Port" : 5222,
                "JID" : "", # "jid@xmpp.host.name/resource"
                "Password" : "",
                "ServiceAddress" : "", # "pubsub.xmpp.host.name"
                "CalDAV" : {
                    "APSBundleID" : "",
                    "SubscriptionURL" : "",
                    "APSEnvironment" : "PRODUCTION",
                },
                "CardDAV" : {
                    "APSBundleID" : "",
                    "SubscriptionURL" : "",
                    "APSEnvironment" : "PRODUCTION",
                },
                "NodeConfiguration" : {
                    "pubsub#deliver_payloads" : "1",
                    "pubsub#persist_items" : "1",
                },
                "KeepAliveSeconds" : 120,
                "HeartbeatMinutes" : 30,
                "AllowedJIDs": [],
            },
        }
    },

    #
    # Support multiple hosts within a domain
    #
    "Servers" : {
        "Enabled": False,                          # Multiple servers/partitions enabled or not
        "ConfigFile": "servers.xml",               # File path for server information
        "MaxClients": 5,                           # Pool size for connections to each partition
    },
    "ServerPartitionID": "",                       # Unique ID for this server's partition instance.

    #
    # Performance tuning
    #

    # Set the maximum number of outstanding requests to this server.
    "MaxRequests": 3,
    "MaxAccepts": 1,

    "MaxDBConnectionsPerPool": 10, # The maximum number of outstanding database
                                   # connections per database connection pool.
                                   # When SharedConnectionPool (see above) is
                                   # set to True, this is the total number of
                                   # outgoing database connections allowed to
                                   # the entire server; when
                                   # SharedConnectionPool is False - this is the
                                   # default - this is the number of database
                                   # connections used per worker process.

    "ListenBacklog": 2024,
    "IdleConnectionTimeOut": 15,
    "UIDReservationTimeOut": 30 * 60,

    "MaxMultigetWithDataHrefs": 5000,
    "MaxQueryWithDataResults": 1000,

    #
    # Localization
    #
    "Localization" : {
        "TranslationsDirectory" : "/usr/share/caldavd/share/translations",
        "LocalesDirectory" : "/usr/share/caldavd/share/locales",
        "Language" : "en",
    },


    #
    # Implementation details
    #
    #    The following are specific to how the server is built, and useful
    #    for development, but shouldn't be needed by users.
    #

    # Twisted
    "Twisted": {
        "reactor": "select",
    },

    # Umask
    "umask": 0022,

    # A TCP port used for communication between the child and master
    # processes (bound to 127.0.0.1). Specify 0 to let OS assign a port.
    "ControlPort": 0,

    # A unix socket used for communication between the child and master
    # processes. If blank, then an AF_INET socket is used instead.
    "ControlSocket": "caldavd.sock",


    # Support for Content-Encoding compression options as specified in
    # RFC2616 Section 3.5
    "ResponseCompression": True,

    # The retry-after value (in seconds) to return with a 503 error
    "HTTPRetryAfter": 180,

    # Profiling options
    "Profiling": {
        "Enabled": False,
        "BaseDirectory": "/tmp/stats",
    },

    "Memcached": {
        "MaxClients": 5,
        "Pools": {
            "Default": {
                "ClientEnabled": True,
                "ServerEnabled": True,
                "BindAddress": "127.0.0.1",
                "Port": 11211,
                "HandleCacheTypes": [
                    "Default",
#                   "OpenDirectoryBacker",
#                   "ImplicitUIDLock",
#                   "RefreshUIDLock",
#                   "DIGESTCREDENTIALS",
#                   "resourceInfoDB",
#                   "pubsubnodes",
#                   "FBCache",
#                   "ScheduleAddressMapper",
#                   "SQL.props",
#                   "SQL.calhome",
#                   "SQL.adbkhome",
                ]
            },
#            "Shared": {
#                "ClientEnabled": True,
#                "ServerEnabled": True,
#                "BindAddress": "127.0.0.1",
#                "Port": 11211,
#                "HandleCacheTypes": [
#                    "ProxyDB",
#                    "PrincipalToken",
#                ]
#            },
        },
        "memcached": "memcached", # Find in PATH
        "MaxMemory": 0, # Megabytes
        "Options": [],
        "ProxyDBKeyNormalization": True,
    },

    "Postgres": {
        "DatabaseName": "caldav",
        "LogFile": "postgres.log",
        "ListenAddresses": [],
        "SharedBuffers": 30,
        "MaxConnections": 20,
        "Options": [
            "-c standard_conforming_strings=on",
        ],
    },

    "GroupCaching" : {
        "Enabled": True,
        "MemcachedPool" : "Default",
        "UpdateSeconds" : 300,
        "ExpireSeconds" : 3600,
        "LockSeconds" : 300,
        "EnableUpdater" : True,
        "UseExternalProxies" : False,
    },

    "EnableKeepAlive": True,

    "EnableResponseCache":  True,
    "ResponseCacheTimeout": 30, # Minutes

    "EnableFreeBusyCache":          True,
    "FreeBusyCacheDaysBack":        7,
    "FreeBusyCacheDaysForward":     12 * 7,

    "FreeBusyIndexExpandAheadDays": 365,
    "FreeBusyIndexExpandMaxDays":   5 * 365,
    "FreeBusyIndexDelayedExpand":   True,

    # Specify which opendirectory module to use:
    # "opendirectory" is PyOpenDirectory (the old one which uses
    # DirectoryService.framework)
    # "calendarserver.platform.darwin.od.opendirectory" is the new PyObjC
    # version which uses OpenDirectory.framework
    "OpenDirectoryModule": "opendirectory",

    # The RootResource uses a twext property store. Specify the class here
    "RootResourcePropStoreClass": "twext.web2.dav.xattrprops.xattrPropertyStore",

    # Used in the command line utilities to specify which service class to
    # use to carry out work.
    "UtilityServiceClass": "",

    "Includes": [],     # Other plists to parse after this one
}



class NoUnicodePlistParser(PlistParser):
    """
    A variant of L{PlistParser} which avoids exposing the 'unicode' data-type
    to application code when non-ASCII characters are found, instead
    consistently exposing UTF-8 encoded 'str' objects.
    """

    def getData(self):
        """
        Get the currently-parsed data as a 'str' object.
        """
        data = "".join(self.data).encode("utf-8")
        self.data = []
        return data



class PListConfigProvider(ConfigProvider):
    
    def loadConfig(self):
        configDict = {}
        if self._configFileName:
            configDict = self._parseConfigFromFile(self._configFileName)
        # Now check for Includes and parse and add each of those
        if "Includes" in configDict:
            configRoot = os.path.join(configDict.ServerRoot, configDict.ConfigRoot)
            for include in configDict.Includes:
                path = _expandPath(fullServerPath(configRoot, include))
                additionalDict = self._parseConfigFromFile(path)
                if additionalDict:
                    log.info("Adding configuration from file: '%s'" % (path,))
                    configDict.update(additionalDict)
        return configDict


    def _parseConfigFromFile(self, filename):
        parser = NoUnicodePlistParser()
        configDict = None
        try:
            configDict = parser.parse(open(filename))
        except (IOError, OSError):
            log.err("Configuration file does not exist or is inaccessible: %s" % (filename, ))
            raise ConfigurationError("Configuration file does not exist or is inaccessible: %s" % (filename, ))
        else:
            configDict = _cleanup(configDict, self._defaults)
        return configDict

def _expandPath(path):
    if '$' in path:
        return path.replace('$', getfqdn())
    elif '#' in path:
        return path.replace('#', gethostbyname(getfqdn()))
    else:
        return path

RELATIVE_PATHS = [
    ("ServerRoot", "DataRoot"),
    ("ServerRoot", "ConfigRoot"),
    ("ServerRoot", "LogRoot"),
    ("ServerRoot", "RunRoot"),
    ("DataRoot", "DocumentRoot"),
    ("DataRoot", "DatabaseRoot"),
    ("DataRoot", "AttachmentsRoot"),
    ("DataRoot", ("TimezoneService", "BasePath",)),
    ("ConfigRoot", "SudoersFile"),
    ("LogRoot", "AccessLogFile"),
    ("LogRoot", "ErrorLogFile"),
    ("LogRoot", ("Postgres", "LogFile",)),
    ("LogRoot", "AccountingLogRoot"),
    ("RunRoot", "PIDFile"),
    ("RunRoot", "GlobalStatsSocket"),
    ("RunRoot", "ControlSocket"),
]


def _updateDataStore(configDict):
    """
    Post-update configuration hook for making all configured paths relative to
    their respective root directories rather than the current working directory.
    """

    # Remove possible trailing slash from ServerRoot
    try:
        configDict["ServerRoot"] = configDict["ServerRoot"].rstrip("/")
    except KeyError:
        pass

    for root, relativePath in RELATIVE_PATHS:
        if root in configDict:
            if isinstance(relativePath, str):
                relativePath = (relativePath,)
            
            inDict = configDict
            for segment in relativePath[:-1]:
                if segment not in inDict:
                    inDict = None
                    break
                inDict = inDict[segment]
            lastPath = relativePath[-1]
            relativePath = ".".join(relativePath)
            if inDict and lastPath in inDict:
                previousAbsoluteName = ".absolute." + relativePath
                previousRelativeName = ".relative." + relativePath
    
                # If we previously made the name absolute, and the name in the
                # config is still the same absolute name that we made it, let's
                # change it to be the relative name again.  (This is necessary
                # because the config data is actually updated several times before
                # the config *file* has been read, so these keys will be made
                # absolute based on default values, and need to be made relative to
                # non-default values later.)  -glyph
                if previousAbsoluteName in configDict and (
                        configDict[previousAbsoluteName] == inDict[lastPath]
                    ):
                    userSpecifiedPath = configDict[previousRelativeName]
                else:
                    userSpecifiedPath = inDict[lastPath]
                    configDict[previousRelativeName] = inDict[lastPath]
                newAbsolutePath = fullServerPath(configDict[root],
                                                 userSpecifiedPath)
                inDict[lastPath] = newAbsolutePath
                configDict[previousAbsoluteName] = newAbsolutePath


def _updateHostName(configDict):
    if not configDict.ServerHostName:
        hostname = getfqdn()
        if not hostname:
            hostname = "localhost"
        configDict.ServerHostName = hostname

def _preUpdateDirectoryService(configDict, items):
    # Special handling for directory services configs
    dsType = items.get("DirectoryService", {}).get("type", None)
    if dsType is None:
        dsType = configDict.DirectoryService.type
    else:
        if dsType == configDict.DirectoryService.type:
            oldParams = configDict.DirectoryService.params
            newParams = items.DirectoryService.get("params", {})
            _mergeData(oldParams, newParams)
        else:
            if dsType in DEFAULT_SERVICE_PARAMS:
                configDict.DirectoryService.params = copy.deepcopy(DEFAULT_SERVICE_PARAMS[dsType])
            else:
                configDict.DirectoryService.params = {}

    for param in items.get("DirectoryService", {}).get("params", {}):
        if dsType in DEFAULT_SERVICE_PARAMS and param not in DEFAULT_SERVICE_PARAMS[dsType]:
            log.warn("Parameter %s is not supported by service %s" % (param, dsType))
            
def _postUpdateDirectoryService(configDict):
    if configDict.DirectoryService.type in DEFAULT_SERVICE_PARAMS:
        for param in tuple(configDict.DirectoryService.params):
            if param not in DEFAULT_SERVICE_PARAMS[configDict.DirectoryService.type]:
                del configDict.DirectoryService.params[param]

def _preUpdateResourceService(configDict, items):
    # Special handling for directory services configs
    dsType = items.get("ResourceService", {}).get("type", None)
    if dsType is None:
        dsType = configDict.ResourceService.type
    else:
        if dsType == configDict.ResourceService.type:
            oldParams = configDict.ResourceService.params
            newParams = items.ResourceService.get("params", {})
            _mergeData(oldParams, newParams)
        else:
            if dsType in DEFAULT_RESOURCE_PARAMS:
                configDict.ResourceService.params = copy.deepcopy(DEFAULT_RESOURCE_PARAMS[dsType])
            else:
                configDict.ResourceService.params = {}

    for param in items.get("ResourceService", {}).get("params", {}):
        if dsType in DEFAULT_RESOURCE_PARAMS and param not in DEFAULT_RESOURCE_PARAMS[dsType]:
            log.warn("Parameter %s is not supported by service %s" % (param, dsType))
            
def _postUpdateResourceService(configDict):
    if configDict.ResourceService.type in DEFAULT_RESOURCE_PARAMS:
        for param in tuple(configDict.ResourceService.params):
            if param not in DEFAULT_RESOURCE_PARAMS[configDict.ResourceService.type]:
                del configDict.ResourceService.params[param]


def _preUpdateDirectoryAddressBookBackingDirectoryService(configDict, items):
    #
    # Special handling for directory address book configs
    #
    dsType = items.get("DirectoryAddressBook", {}).get("type", None)
    if dsType is None:
        dsType = configDict.DirectoryAddressBook.type
    else:
        if dsType == configDict.DirectoryAddressBook.type:
            oldParams = configDict.DirectoryAddressBook.params
            newParams = items["DirectoryAddressBook"].get("params", {})
            _mergeData(oldParams, newParams)
        else:
            if dsType in directoryAddressBookBackingServiceDefaultParams:
                configDict.DirectoryAddressBook.params = copy.deepcopy(directoryAddressBookBackingServiceDefaultParams[dsType])
            else:
                configDict.DirectoryAddressBook.params = {}

    for param in items.get("DirectoryAddressBook", {}).get("params", {}):
        if param not in directoryAddressBookBackingServiceDefaultParams[dsType]:
            raise ConfigurationError("Parameter %s is not supported by service %s" % (param, dsType))

    _mergeData(configDict, items)

    for param in tuple(configDict.DirectoryAddressBook.params):
        if param not in directoryAddressBookBackingServiceDefaultParams[configDict.DirectoryAddressBook.type]:
            del configDict.DirectoryAddressBook.params[param]

def _postUpdateAugmentService(configDict):
    if configDict.AugmentService.type in DEFAULT_AUGMENT_PARAMS:
        for param in tuple(configDict.AugmentService.params):
            if param not in DEFAULT_AUGMENT_PARAMS[configDict.AugmentService.type]:
                log.warn("Parameter %s is not supported by service %s" % (param, configDict.AugmentService.type))
                del configDict.AugmentService.params[param]

def _postUpdateProxyDBService(configDict):
    if configDict.ProxyDBService.type in DEFAULT_PROXYDB_PARAMS:
        for param in tuple(configDict.ProxyDBService.params):
            if param not in DEFAULT_PROXYDB_PARAMS[configDict.ProxyDBService.type]:
                log.warn("Parameter %s is not supported by service %s" % (param, configDict.ProxyDBService.type))
                del configDict.ProxyDBService.params[param]

def _updateACLs(configDict):
    #
    # Base resource ACLs
    #
    def readOnlyACE(allowAnonymous):
        if allowAnonymous:
            reader = davxml.All()
        else:
            reader = davxml.Authenticated()

        return davxml.ACE(
            davxml.Principal(reader),
            davxml.Grant(
                davxml.Privilege(davxml.Read()),
                davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
            ),
            davxml.Protected(),
        )

    configDict.AdminACEs = tuple(
        davxml.ACE(
            davxml.Principal(davxml.HRef(principal)),
            davxml.Grant(davxml.Privilege(davxml.All())),
            davxml.Protected(),
            TwistedACLInheritable(),
        )
        for principal in configDict.AdminPrincipals
    )

    configDict.ReadACEs = tuple(
        davxml.ACE(
            davxml.Principal(davxml.HRef(principal)),
            davxml.Grant(
                davxml.Privilege(davxml.Read()),
                davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
            ),
            davxml.Protected(),
            TwistedACLInheritable(),
        )
        for principal in configDict.ReadPrincipals
    )

    configDict.RootResourceACL = davxml.ACL(
        # Read-only for anon or authenticated, depending on config
        readOnlyACE(configDict.EnableAnonymousReadRoot),

        # Add inheritable all access for admins
        *configDict.AdminACEs
    )

    log.debug("Root ACL: %s" % (configDict.RootResourceACL.toxml(),))

    configDict.ProvisioningResourceACL = davxml.ACL(
        # Read-only for anon or authenticated, depending on config
        readOnlyACE(configDict.EnableAnonymousReadNav),

        # Add read and read-acl access for admins
        *[
            davxml.ACE(
                davxml.Principal(davxml.HRef(principal)),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                    davxml.Privilege(davxml.ReadACL()),
                    davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                ),
                davxml.Protected(),
            )
            for principal in configDict.AdminPrincipals
        ]
    )

    log.debug("Nav ACL: %s" % (configDict.ProvisioningResourceACL.toxml(),))

    def principalObjects(urls):
        for principalURL in urls:
            yield davxml.Principal(davxml.HRef(principalURL))

    # Should be sets, except WebDAVElement isn't hashable.
    a = configDict.AdminPrincipalObjects = list(
        principalObjects(configDict.AdminPrincipals))
    b = configDict.ReadPrincipalObjects = list(
        principalObjects(configDict.ReadPrincipals))
    configDict.AllAdminPrincipalObjects = a + b



def _updateRejectClients(configDict):
    #
    # Compile RejectClients expressions for speed
    #
    try:
        configDict.RejectClients = [re.compile(x) for x in configDict.RejectClients if x]
    except re.error, e:
        raise ConfigurationError("Invalid regular expression in RejectClients: %s" % (e,))

def _updateLogLevels(configDict):
    clearLogLevels()

    try:
        if "DefaultLogLevel" in configDict:
            level = configDict["DefaultLogLevel"]
            if level:
                setLogLevelForNamespace(None, level)

        if "LogLevels" in configDict:
            for namespace in configDict["LogLevels"]:
                setLogLevelForNamespace(namespace, configDict["LogLevels"][namespace])

    except InvalidLogLevelError, e:
        raise ConfigurationError("Invalid log level: %s" % (e.level))

def _updateNotifications(configDict):
    # Reloading not supported -- requires process running as root
    if getattr(configDict, "_reloading", False):
        return

    for key, service in configDict.Notifications["Services"].iteritems():
        if service["Enabled"]:
            configDict.Notifications["Enabled"] = True
            break
    else:
        configDict.Notifications["Enabled"] = False

    for key, service in configDict.Notifications["Services"].iteritems():

        if (
            service["Service"] == "calendarserver.push.applepush.ApplePushNotifierService" and
            service["Enabled"]
        ):
            # The default for apple push DataHost is ServerHostName
            if service["DataHost"] == "":
                service["DataHost"] = configDict.ServerHostName

            # Advertise Basic and/or Digest on subscription resource
            if not service["AuthMechanisms"]:
                authMechanisms = []
                if configDict.Authentication.Basic.Enabled:
                    authMechanisms.append("basic")
                if configDict.Authentication.Digest.Enabled:
                    authMechanisms.append("digest")
                if not authMechanisms:
                    raise ConfigurationError("Must have either 'basic' or 'digest' enabled for Apple Push Notifications.")
                service["AuthMechanisms"] = authMechanisms

            # Retrieve APN topics from certificates if not explicitly set
            for protocol, accountName in (
                ("CalDAV", "apns:com.apple.calendar"),
                ("CardDAV", "apns:com.apple.contact"),
            ):
                if not service[protocol]["Topic"]:
                    certPath = service[protocol]["CertificatePath"]
                    if certPath and os.path.exists(certPath):
                        topic = getAPNTopicFromCertificate(certPath)
                        service[protocol]["Topic"] = topic

                # If we already have the cert passphrase, don't fetch it again
                if service[protocol]["Passphrase"]:
                    continue

                # Get passphrase from keychain.  If not there, fall back to what
                # is in the plist.
                try:
                    passphrase = getPasswordFromKeychain(accountName)
                    service[protocol]["Passphrase"] = passphrase
                    log.info("%s APN certificate passphrase retreived from keychain" % (protocol,))
                except KeychainAccessError:
                    # The system doesn't support keychain
                    pass
                except KeychainPasswordNotFound:
                    # The password doesn't exist in the keychain.
                    log.info("%s APN certificate passphrase not found in keychain" % (protocol,))


        if (
            service["Service"] == "twistedcaldav.notify.XMPPNotifierService" and
            service["Enabled"]
        ):
            # If we already have the password, don't fetch it again
            if service["Password"]:
                continue

            # Get password from keychain.  If not there, fall back to what
            # is in the plist.
            try:
                password = getPasswordFromKeychain(service["JID"])
                service["Password"] = password
                log.info("XMPP password retreived from keychain")
            except KeychainAccessError:
                # The system doesn't support keychain
                pass
            except KeychainPasswordNotFound:
                # The password doesn't exist in the keychain.
                log.info("XMPP password not found in keychain")

            # Check for empty fields
            for key, value in service.iteritems():
                if not value and key not in (
                    "AllowedJIDs", "HeartbeatMinutes", "Password",
                    "SubscriptionURL", "APSBundleID"
                ):
                    raise ConfigurationError("Invalid %s for XMPPNotifierService: %r"
                                             % (key, value))



def _updateScheduling(configDict):
    #
    # Scheduling
    #

    # Reloading not supported -- requires process running as root
    if getattr(configDict, "_reloading", False):
        return

    service = configDict.Scheduling["iMIP"]

    if service["Enabled"]:

        # If we already have the password, don't fetch it again
        if service["Password"]:
            return

        # Get password for the user that is allowed to inject iMIP replies
        # to the server's /inbox; if not available, fall back to plist
        if service["Username"]:
            try:
                service["Password"] = getPasswordFromKeychain(service["Username"])
            except KeychainAccessError:
                # The system doesn't support keychain
                pass
            except KeychainPasswordNotFound:
                # The password doesn't exist in the keychain.
                log.info("iMIP injecting password not found in keychain")

        for direction in ("Sending", "Receiving"):
            if service[direction].Username:
                # Get password from keychain.  If not there, fall back to
                # what is in the plist.
                try:
                    account = "%s@%s" % (
                        service[direction].Username,
                        service[direction].Server
                    )
                    password = getPasswordFromKeychain(account)
                    service[direction]["Password"] = password
                    log.info("iMIP %s password successfully retreived from keychain" % (direction,))
                except KeychainAccessError:
                    # The system doesn't support keychain
                    pass
                except KeychainPasswordNotFound:
                    # The password doesn't exist in the keychain.
                    log.info("iMIP %s password not found in keychain" %
                        (direction,))

def _updateServers(configDict):
    import servers
    if configDict.Servers.Enabled:
        servers.Servers.load()
        servers.Servers.getThisServer().installReverseProxies(
            configDict.ServerPartitionID,
            configDict.Servers.MaxClients,
        )
    else:
        servers.Servers.clear()

def _updateCompliance(configDict):

    if configDict.EnableCalDAV:
        if configDict.Scheduling.CalDAV.OldDraftCompatibility:
            compliance = caldavxml.caldav_full_compliance
        else:
            compliance = caldavxml.caldav_implicit_compliance
        if configDict.EnableProxyPrincipals:
            compliance += customxml.calendarserver_proxy_compliance
        if configDict.EnablePrivateEvents:
            compliance += customxml.calendarserver_private_events_compliance
        if configDict.Scheduling.CalDAV.EnablePrivateComments:
            compliance += customxml.calendarserver_private_comments_compliance
        if config.Sharing.Enabled:
            compliance += customxml.calendarserver_sharing_compliance
            # TODO: This is only needed whilst we do not support scheduling in shared calendars
            compliance += customxml.calendarserver_sharing_no_scheduling_compliance
        if configDict.EnableCalendarQueryExtended:
            compliance += caldavxml.caldav_query_extended_compliance
        if configDict.EnableDefaultAlarms:
            compliance += caldavxml.caldav_default_alarms_compliance
    else:
        compliance = ()

    if configDict.EnableCardDAV:
        compliance += carddavxml.carddav_compliance

    if configDict.EnableCalDAV or configDict.EnableCardDAV:
        compliance += mkcolxml.mkcol_compliance

    # Principal property search is always enabled
    compliance += customxml.calendarserver_principal_property_search_compliance

    configDict.CalDAVComplianceClasses = compliance


PRE_UPDATE_HOOKS = (
    _preUpdateDirectoryService,
    _preUpdateResourceService,
    _preUpdateDirectoryAddressBookBackingDirectoryService,
    )
POST_UPDATE_HOOKS = (
    _updateDataStore,
    _updateHostName,
    _postUpdateDirectoryService,
    _postUpdateResourceService,
    _postUpdateAugmentService,
    _postUpdateProxyDBService,
    _updateACLs,
    _updateRejectClients,
    _updateLogLevels,
    _updateNotifications,
    _updateScheduling,
    _updateServers,
    _updateCompliance,
    )
    
def _cleanup(configDict, defaultDict):
    cleanDict = copy.deepcopy(configDict)

    def unknown(key):
        config_key = "CALENDARSERVER_CONFIG_VALIDATION"
        config_key_value = "loose"
        if config_key in os.environ and os.environ[config_key] == config_key_value:
            pass
        else:
            log.err("Ignoring unknown configuration option: %r" % (key,))
            del cleanDict[key]

    def deprecated(oldKey, newKey):
        log.err("Configuration option %r is deprecated in favor of %r." % (oldKey, newKey))
        if oldKey in configDict and newKey in configDict:
            raise ConfigurationError(
                "Both %r and %r options are specified; use the %r option only."
                % (oldKey, newKey, newKey)
            )

    def renamed(oldKey, newKey):
        deprecated(oldKey, newKey)
        cleanDict[newKey] = configDict[oldKey]
        del cleanDict[oldKey]

    renamedOptions = {
#       "BindAddress": "BindAddresses",
    }

    for key in configDict:
        if key in defaultDict:
            continue

        elif key in renamedOptions:
            renamed(key, renamedOptions[key])

        else:
            unknown(key,)

    return cleanDict

config.setProvider(PListConfigProvider(DEFAULT_CONFIG))
config.addPreUpdateHooks(PRE_UPDATE_HOOKS)
config.addPostUpdateHooks(POST_UPDATE_HOOKS)


def _preserveConfig(configDict):
    """
    Preserve certain config keys across reset( ) because these can't be
    re-fetched after the process has shed privileges
    """
    iMIP = configDict.Scheduling.iMIP
    XMPP = configDict.Notifications.Services.XMPPNotifier
    preserved = {
        "iMIPPassword" : iMIP.Password,
        "MailSendingPassword" : iMIP.Sending.Password,
        "MailReceivingPassword" : iMIP.Receiving.Password,
        "XMPPPassword" : XMPP.Password,
    }
    return preserved

def _restoreConfig(configDict, preserved):
    """
    Restore certain config keys across reset( ) because these can't be
    re-fetched after the process has shed privileges
    """
    iMIP = configDict.Scheduling.iMIP
    XMPP = configDict.Notifications.Services.XMPPNotifier
    iMIP.Password = preserved["iMIPPassword"]
    iMIP.Sending.Password = preserved["MailSendingPassword"]
    iMIP.Receiving.Password = preserved["MailReceivingPassword"]
    XMPP.Password = preserved["XMPPPassword"]


config.addResetHooks(_preserveConfig, _restoreConfig)
