##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

__all__ = [
    "defaultConfigFile",
    "defaultConfig",
    "ConfigDict",
    "Config",
    "ConfigurationError",
    "config",
]

import os
import copy
import re

from twisted.web2.dav import davxml
from twisted.web2.dav.resource import TwistedACLInheritable

from twext.python.plistlib import readPlist

from twistedcaldav.log import Logger
from twistedcaldav.log import clearLogLevels, setLogLevelForNamespace, InvalidLogLevelError
from twistedcaldav.util import (
    KeychainAccessError, KeychainPasswordNotFound, getPasswordFromKeychain
)

log = Logger()

class ConfigDict (dict):
    def __init__(self, mapping=None):
        if mapping is not None:
            for key, value in mapping.iteritems():
                self[key] = value

    def __repr__(self):
        return "*" + dict.__repr__(self)

    def __setitem__(self, key, value):
        if isinstance(value, dict) and not isinstance(value, self.__class__):
            dict.__setitem__(self, key, self.__class__(value))
        else:
            dict.__setitem__(self, key, value)

    def __setattr__(self, attr, value):
        if attr[0] == "_":
            dict.__setattr__(self, attr, value)
        else:
            self[attr] = value

    def __getattr__(self, attr):
        if attr in self:
            return self[attr]
        else:
            return dict.__getattr__(self, attr)

defaultConfigFile = "/etc/caldavd/caldavd.plist"

serviceDefaultParams = {
    "twistedcaldav.directory.xmlfile.XMLDirectoryService": {
        "xmlFile": "/etc/caldavd/accounts.xml",
    },
    "twistedcaldav.directory.appleopendirectory.OpenDirectoryService": {
        "node": "/Search",
        "restrictEnabledRecords": False,
        "restrictToGroup": "",
        "cacheTimeout": 30,
    },
}

defaultConfig = {
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
    "ServerHostName": "", # Network host name.
    "HTTPPort": 0,        # HTTP port (0 to disable HTTP)
    "SSLPort" : 0,        # SSL port (0 to disable HTTPS)
    "RedirectHTTPToHTTPS" : False, # If True, all nonSSL requests redirected to an SSL Port
    "SSLMethod" : "SSLv3_METHOD", # SSLv2_METHOD, SSLv3_METHOD, SSLv23_METHOD, TLSv1_METHOD

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
    "DataRoot"                : "/Library/CalendarServer/Data",
    "DocumentRoot"            : "/Library/CalendarServer/Documents",
    "UserQuota"               : 104857600, # User quota (in bytes)
    "MaximumAttachmentSize"   :   1048576, # Attachment size limit (in bytes)
    "MaxAttendeesPerInstance" :       100, # Maximum number of unique attendees
    "MaxInstancesForRRULE"    :       400, # Maximum number of instances for an RRULE
    "WebCalendarRoot"         : "/usr/share/collaboration",

    "Aliases": {},

    #
    # Directory service
    #
    #    A directory service provides information about principals (eg.
    #    users, groups, locations and resources) to the server.
    #
    "DirectoryService": {
        "type": "twistedcaldav.directory.xmlfile.XMLDirectoryService",
        "params": serviceDefaultParams["twistedcaldav.directory.xmlfile.XMLDirectoryService"],
    },

    #
    # Special principals
    #
    "AdminPrincipals": [],                       # Principals with "DAV:all" access (relative URLs)
    "ReadPrincipals": [],                        # Principals with "DAV:read" access (relative URLs)
    "SudoersFile": "/etc/caldavd/sudoers.plist", # Principals that can pose as other principals
    "EnableProxyPrincipals": True,               # Create "proxy access" principals

    #
    # Permissions
    #
    "EnableAnonymousReadRoot": True,    # Allow unauthenticated read access to /
    "EnableAnonymousReadNav": False,    # Allow unauthenticated read access to hierachcy
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
            "Cookie": "sessionID",
            "URL": "http://127.0.0.1:8086/RPC2",
            "UserMethod": "userForSession",
            "WikiMethod": "accessLevelForUserWikiCalendar",
        },
    },

    #
    # Logging
    #
    "AccessLogFile"  : "/var/log/caldavd/access.log",  # Apache-style access log
    "ErrorLogFile"   : "/var/log/caldavd/error.log",   # Server activity log
    "ServerStatsFile": "/var/run/caldavd/stats.plist",
    "PIDFile"        : "/var/run/caldavd.pid",
    "RotateAccessLog"   : False,
    "MoreAccessLogData" : True,
    "DefaultLogLevel"   : "",
    "LogLevels"         : {},

    "AccountingCategories": {
        "iTIP": False,
    },
    "AccountingPrincipals": [],
    "AccountingLogRoot"   : "/var/log/caldavd/accounting",

    "GlobalStatsSocket"           : "/var/run/caldavd-stats.sock", 
    "GlobalStatsLoggingPeriod"    : 60, 
    "GlobalStatsLoggingFrequency" : 12, 

    #
    # SSL/TLS
    #
    "SSLCertificate"     : "",  # Public key
    "SSLPrivateKey"      : "",  # Private key
    "SSLAuthorityChain"  : "",  # Certificate Authority Chain
    "SSLPassPhraseDialog": "/etc/apache2/getsslpassphrase",
    "SSLCertAdmin"       : "/usr/sbin/certadmin",

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
        "MinProcessCount": 4,
        "LoadBalancer": {
            "Enabled": True,
            "Scheduler": "LeastConnections",
        },
        "StaggeredStartup": {
            "Enabled": False,
            "Interval": 15,
        },
    },

    #
    # Service ACLs
    #
    "EnableSACLs": False,

    #
    # Non-standard CalDAV extensions
    #
    "EnableDropBox"           : False, # Calendar Drop Box
    "EnablePrivateEvents"     : False, # Private Events
    "EnableTimezoneService"   : False, # Timezone service

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
            "AddressPatterns"            : [],    # Reg-ex patterns to match local calendar user addresses
            "OldDraftCompatibility"      : True,  # Whether to maintain compatibility with non-implicit mode
            "ScheduleTagCompatibility"   : True,  # Whether to support older clients that do not use Schedule-Tag feature
            "EnablePrivateComments"      : True,  # Private comments from attendees to organizer
        },

        "iSchedule": {
            "Enabled"          : False, # iSchedule protocol
            "AddressPatterns"  : [],    # Reg-ex patterns to match iSchedule-able calendar user addresses
            "Servers"          : "/etc/caldavd/servertoserver.xml",    # iSchedule server configurations
        },

        "iMIP": {
            "Enabled"          : False, # Server-to-iMIP protocol
            "MailGatewayServer" : "localhost",
            "MailGatewayPort"   : 62310,
            "Username"          : "com.apple.calendarserver", # For account injecting replies
            "Password"          : "",    # For account injecting replies
            "Sending": {
                "Server"        : "",    # SMTP server to relay messages through
                "Port"          : 587,   # SMTP server port to relay messages through
                "Address"       : "",    # 'From' address for server
                "UseSSL"        : True,
                "Username"      : "",    # For account sending mail
                "Password"      : "",    # For account sending mail
            },
            "Receiving": {
                "Server"        : "",    # Server to retrieve email messages from
                "Port"          : 0,     # Server port to retrieve email messages from
                "UseSSL"        : True,
                "Type"          : "",    # Type of message access server: 'pop' or 'imap'
                "PollingSeconds"    : 30,  # How often to fetch mail
                "Username"      : "",    # For account receving mail
                "Password"      : "",    # For account receving mail
            },
            "AddressPatterns"   : [],    # Reg-ex patterns to match iMIP-able calendar user addresses
            "MailTemplatesDirectory": "/usr/share/caldavd/share/email_templates", # Directory containing HTML templates for email invitations (invite.html, cancel.html)
            "MailIconsDirectory": "/usr/share/caldavd/share/date_icons", # Directory containing language-specific subdirectories containing date-specific icons for email invitations
            "InvitationDaysToLive" : 90, # How many days invitations are valid
        },

        "Options" : {
            "AllowGroupAsOrganizer"      : False, # Allow groups to be Organizers
            "AllowLocationAsOrganizer"   : False, # Allow locations to be Organizers
            "AllowResourceAsOrganizer"   : False, # Allow resources to be Organizers
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
            "XMPPNotifier" : {
                "Service" : "twistedcaldav.notify.XMPPNotifierService",
                "Enabled" : False,
                "Host" : "", # "xmpp.host.name"
                "Port" : 5222,
                "JID" : "", # "jid@xmpp.host.name/resource"
                "Password" : "",
                "ServiceAddress" : "", # "pubsub.xmpp.host.name"
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
    # Performance tuning
    #

    # Set the maximum number of outstanding requests to this server.
    "MaxRequests": 600,

    "ListenBacklog": 50,
    "IdleConnectionTimeOut": 15,
    "UIDReservationTimeOut": 30 * 60,


    #
    # Localization
    #
    "Localization" : {
        "TranslationsDirectory" : "/usr/share/caldavd/share/translations",
        "LocalesDirectory" : "/usr/share/caldavd/share/locales",
        "Language" : "English",
    },


    #
    # Implementation details
    #
    #    The following are specific to how the server is built, and useful
    #    for development, but shouldn't be needed by users.
    #

    # Twisted
    "Twisted": {
        "twistd": "/usr/share/caldavd/bin/twistd",
        "reactor": "select",
    },

    # Python Director
    "PythonDirector": {
        "pydir": "/usr/share/caldavd/bin/pydir.py",
        "ConfigFile": "/etc/caldavd/pydir.xml",
        "ControlSocket": "/var/run/caldavd-pydir.sock",
    },

    # Umask
    "umask": 0027,

    # A TCP port used for communication between the child and master
    # processes (bound to 127.0.0.1). Specify 0 to let OS assign a port.
    "ControlPort": 0,

    # A unix socket used for communication between the child and master
    # processes. If blank, then an AF_INET socket is used instead.
    "ControlSocket": "/var/run/caldavd.sock",


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
        "ClientEnabled": True,
        "ServerEnabled": True,
        "BindAddress": "127.0.0.1",
        "Port": 11211,
        "memcached": "memcached", # Find in PATH
        "MaxMemory": 0, # Megabytes
        "Options": [],
    },

    "EnableKeepAlive": True,

    "ResponseCacheTimeout": 30, # Minutes
}

class Config (object):
    """
    @DynamicAttrs
    """
    def __init__(self, defaults):
        if not isinstance(defaults, ConfigDict):
            defaults = ConfigDict(defaults)

        self.setDefaults(defaults)
        self._data = copy.deepcopy(defaults)
        self._configFile = None
        self._hooks = [
            self.updateHostName,
            self.updateDirectoryService,
            self.updateACLs,
            self.updateRejectClients,
            self.updateDropBox,
            self.updateLogLevels,
            self.updateNotifications,
            self.updateScheduling,
        ]

    def __str__(self):
        return str(self._data)

    def addHook(self, hook):
        self._hooks.append(hook)

    def update(self, items):
        if not isinstance(items, ConfigDict):
            items = ConfigDict(items)

        #
        # Call hooks
        #
        for hook in self._hooks:
            hook(self, items)

    @staticmethod
    def updateHostName(self, items):
        if not self.ServerHostName:
            from socket import getfqdn
            hostname = getfqdn()
            if not hostname:
                hostname = "localhost"
            self.ServerHostName = hostname

    @staticmethod
    def updateDirectoryService(self, items):
        #
        # Special handling for directory services configs
        #
        dsType = items.get("DirectoryService", {}).get("type", None)
        if dsType is None:
            dsType = self._data.DirectoryService.type
        else:
            if dsType == self._data.DirectoryService.type:
                oldParams = self._data.DirectoryService.params
                newParams = items.DirectoryService.get("params", {})
                _mergeData(oldParams, newParams)
            else:
                if dsType in serviceDefaultParams:
                    self._data.DirectoryService.params = copy.deepcopy(serviceDefaultParams[dsType])
                else:
                    self._data.DirectoryService.params = {}

        for param in items.get("DirectoryService", {}).get("params", {}):
            if dsType in serviceDefaultParams and param not in serviceDefaultParams[dsType]:
                log.warn("Parameter %s is not supported by service %s" % (param, dsType))

        _mergeData(self._data, items)

        if self._data.DirectoryService.type in serviceDefaultParams:
            for param in tuple(self._data.DirectoryService.params):
                if param not in serviceDefaultParams[self._data.DirectoryService.type]:
                    del self._data.DirectoryService.params[param]

    @staticmethod
    def updateACLs(self, items):
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

        self.AdminACEs = tuple(
            davxml.ACE(
                davxml.Principal(davxml.HRef(principal)),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected(),
                TwistedACLInheritable(),
            )
            for principal in config.AdminPrincipals
        )

        self.ReadACEs = tuple(
            davxml.ACE(
                davxml.Principal(davxml.HRef(principal)),
                davxml.Grant(
                    davxml.Privilege(davxml.Read()),
                    davxml.Privilege(davxml.ReadCurrentUserPrivilegeSet()),
                ),
                davxml.Protected(),
                TwistedACLInheritable(),
            )
            for principal in config.ReadPrincipals
        )

        self.RootResourceACL = davxml.ACL(
            # Read-only for anon or authenticated, depending on config
            readOnlyACE(self.EnableAnonymousReadRoot),

            # Add inheritable all access for admins
            *self.AdminACEs
        )

        log.debug("Root ACL: %s" % (self.RootResourceACL.toxml(),))

        self.ProvisioningResourceACL = davxml.ACL(
            # Read-only for anon or authenticated, depending on config
            readOnlyACE(self.EnableAnonymousReadNav),

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
                for principal in config.AdminPrincipals
            ]
        )

        log.debug("Nav ACL: %s" % (self.ProvisioningResourceACL.toxml(),))

    @staticmethod
    def updateRejectClients(self, items):
        #
        # Compile RejectClients expressions for speed
        #
        try:
            self.RejectClients = [re.compile(x) for x in self.RejectClients if x]
        except re.error, e:
            raise ConfigurationError("Invalid regular expression in RejectClients: %s" % (e,))

    @staticmethod
    def updateDropBox(self, items):
        #
        # FIXME: Use the config object instead of doing this here
        #
        from twistedcaldav.resource import CalendarPrincipalResource
        CalendarPrincipalResource.enableDropBox(self.EnableDropBox)

    @staticmethod
    def updateLogLevels(self, items):
        clearLogLevels()

        try:
            if "DefaultLogLevel" in self._data:
                level = self._data["DefaultLogLevel"]
                if not level:
                    level = "warn"
                setLogLevelForNamespace(None, level)

            if "LogLevels" in self._data:
                for namespace in self._data["LogLevels"]:
                    setLogLevelForNamespace(namespace, self._data["LogLevels"][namespace])

        except InvalidLogLevelError, e:
            raise ConfigurationError("Invalid log level: %s" % (e.level))

    def updateDefaults(self, items):
        _mergeData(self._defaults, items)
        self.update(items)

    def setDefaults(self, defaults):
        if not isinstance(defaults, ConfigDict):
            defaults = ConfigDict(defaults)
        self._defaults = copy.deepcopy(defaults)

    def __setattr__(self, attr, value):
        if "_data" in self.__dict__ and attr in self.__dict__["_data"]:
            self._data[attr] = value
        else:
            self.__dict__[attr] = value

    def __getattr__(self, attr):
        if attr in self._data:
            return self._data[attr]

        raise AttributeError(attr)

    def reload(self):
        log.info("Reloading configuration from file: %s" % (self._configFile,))
        self._data = copy.deepcopy(self._defaults)
        self.loadConfig(self._configFile)

    def loadConfig(self, configFile):
        self._configFile = configFile

        if configFile:
            try:
                configDict = readPlist(configFile)
            except (IOError, OSError):
                log.error("Unable to open config file: %s" % (configFile,))
            else:
                configDict = _cleanup(configDict)
                self.update(ConfigDict(configDict))

    @staticmethod
    def updateNotifications(self, items):
        #
        # Notifications
        #
        for key, service in self.Notifications["Services"].iteritems():
            if service["Enabled"]:
                self.Notifications["Enabled"] = True
                break
        else:
            self.Notifications["Enabled"] = False

        for key, service in self.Notifications["Services"].iteritems():
            if (
                service["Service"] == "twistedcaldav.notify.XMPPNotifierService" and
                service["Enabled"]
            ):
                # Get password from keychain.  If not there, fall back to what
                # is in the plist.
                try:
                    password = getPasswordFromKeychain(service["JID"])
                    service["Password"] = password
                    log.info("XMPP password successfully retreived from keychain")
                except KeychainAccessError:
                    # The system doesn't support keychain
                    pass
                except KeychainPasswordNotFound:
                    # The password doesn't exist in the keychain.
                    log.error("XMPP password not found in keychain")

                # Check for empty fields
                for key, value in service.iteritems():
                    if not value and key not in ("AllowedJIDs", "HeartbeatMinutes", "Password"):
                        raise ConfigurationError("Invalid %s for XMPPNotifierService: %r"
                                                 % (key, value))

    @staticmethod
    def updateScheduling(self, items):
        #
        # Scheduling
        #
        service = self.Scheduling["iMIP"]

        if service["Enabled"]:

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


def _mergeData(oldData, newData):
    for key, value in newData.iteritems():
        if isinstance(value, (dict,)):
            if key in oldData:
                assert isinstance(oldData[key], ConfigDict), "%r in %r is not a ConfigDict" % (oldData[key], oldData)
            else:
                oldData[key] = {}
            _mergeData(oldData[key], value)
        else:
            oldData[key] = value

def _cleanup(configDict):
    cleanDict = copy.deepcopy(configDict)

    def unknown(key):
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
        if key in defaultConfig:
            continue

        elif key in renamedOptions:
            renamed(key, renamedOptions[key])

#       elif key == "pydirConfig":
#           deprecated(key, "PythonDirector -> pydir")
#           if "PythonDirector" not in cleanDict:
#               cleanDict["PythonDirector"] = {}
#           cleanDict["PythonDirector"]["ConfigFile"] = cleanDict["pydirConfig"]
#           del cleanDict["pydirConfig"]

        else:
            unknown(key,)

    return cleanDict

class ConfigurationError (RuntimeError):
    """
    Invalid server configuration.
    """

config = Config(defaultConfig)
