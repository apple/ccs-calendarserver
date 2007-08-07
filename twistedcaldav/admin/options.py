##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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

""" "pluggable" subcommands for the caladmin script
"""

from twisted.python import usage

COMMANDS = {}

def registerCommand(command):
    COMMANDS[command.name] = command

def listCommands():
    return COMMANDS.keys()

def genSubCommandsDef():
    for name in sorted(listCommands()):
        command = COMMANDS[name]
        yield [command.name, command.shortcut, command, command.help]


from twisted.python import reflect

class SubCommand(usage.Options):
    name = None
    shortcut = None
    help = "FIXME"
    action = None

    params = ()

    def parseArgs(self, *rest):
        self.params += rest

    def postOptions(self):
        
        report = reflect.namedAny(self.action)(self).run()
        if report:
            self.parent.formatter.config = self
            self.parent.formatter.printReport(report)


PARAM_HUMAN = ['human', 'h', 'Display byte values in a human readable form.']
PARAM_MEGA = ['megabytes', 'm', 'Display byte values in megabytes']
PARAM_KILO = ['kilobytes', 'k', 'Display byte values in kilobytes']
PARAM_GIGA = ['gigabytes', 'g', 'Display byte values in gigabytes']


class PurgeOptions(SubCommand):
    name = 'purge'
    help = ('Keep your store from becoming unnecessarily large by purging '
            'old events.')
    action = 'twistedcaldav.admin.purge.PurgeAction'

    optParameters = [
        ['days', 'n', 30, 'Age threshold for purging events.'],
        ]

registerCommand(PurgeOptions)


class StatsOptions(SubCommand):
    name = 'stats'
    help = ('Overall usage statistics.')
    action = 'twistedcaldav.admin.stats.StatsAction'

    optFlags = [
        PARAM_HUMAN,
        PARAM_KILO,
        PARAM_MEGA,
        PARAM_GIGA,
        ]

registerCommand(StatsOptions)


from twisted.python import filepath
from twistedcaldav.config import config

class LogOptions(SubCommand):
    name = 'logs'
    help = ('Gather and report useful information from the logfiles.')
    action = 'twistedcaldav.admin.logs.LogAction'

    optFlags = [
        ['nooutput', 'n', 'Do not output anything to stdout'],
        ['readonly', 'r', 'Just read the current stats in the statistics file'],
        PARAM_HUMAN,
        PARAM_KILO,
        PARAM_MEGA,
        PARAM_GIGA,
        ]

    optParameters = [
        ['days', 'd', 30, 'Age threshold for log analysis.'],
        ]
    
    def __init__(self):
        SubCommand.__init__(self)

        self['logfile'] = None
        self['statsfile'] = None

    def opt_logfile(self, path):
        """Path to input logfile
        """

        self['logfile'] = path

    def opt_statsfile(self, path):
        """Path to destination statistics plist
        """
        self['statsfile'] = path

    def postOptions(self):
        if not self['logfile']:
            self['logfile'] = filepath.FilePath(
                config.AccessLogFile)
        else:
            self['logfile'] = filepath.FilePath(self['logfile'])

        if not self['statsfile']:
            self['statsfile'] = filepath.FilePath(
                config.ServerStatsFile)
        else:
            self['statsfile'] = filepath.FilePath(self['statsfile'])

        SubCommand.postOptions(self)

registerCommand(LogOptions)


class PrincipalOptions(SubCommand):
    name = None
    help = ("Gather statistics and act on %s")
    action = 'twistedcaldav.admin.principals.PrincipalAction'

    optFlags = [
        ['list', '1', 'List principal names'],
        ['disabled', 'd', 'List disabled principals'],
        PARAM_HUMAN,
        PARAM_KILO,
        PARAM_MEGA,
        PARAM_GIGA,
        ]

    def __init__(self):
        SubCommand.__init__(self)
        self['quota'] = config.UserQuota

    def postOptions(self):
        report = reflect.namedAny(self.action)(self, self.name).run()
        self.parent.formatter.printReport(report)

from twistedcaldav.directory.directory import DirectoryService

class UserOptions(PrincipalOptions):
    name = DirectoryService.recordType_users
    help = PrincipalOptions.help % (name,)

registerCommand(UserOptions)


class GroupOptions(PrincipalOptions):
    name = DirectoryService.recordType_groups
    help = PrincipalOptions.help % (name,)

registerCommand(GroupOptions)


class LocationOptions(PrincipalOptions):
    name = DirectoryService.recordType_locations
    help = PrincipalOptions.help % (name,)

registerCommand(LocationOptions)


class ResourceOptions(PrincipalOptions):
    name = DirectoryService.recordType_resources
    help = PrincipalOptions.help % (name,)

registerCommand(ResourceOptions)

    
