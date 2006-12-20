##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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

"""
Examples:

  caladmin users

  caladmin purge

  caladmin backup

  caladmin restore
"""

import sys, os

from twisted.python import usage
from twisted.python import filepath

from twistedcaldav.admin import options
from twistedcaldav.admin import formatters

from twistedcaldav.config import defaultConfigFile, config, parseConfig

class AdminOptions(usage.Options):
    recursing = 0
    params = ()

    optParameters = [
        ['config', 'c', defaultConfigFile, "Path to the caldavd.plist"],
        ['format', 'f', 'plain', ("Select an appropriate output formatter: "
                                  "%s" % (formatters.listFormatters(),))]
    ]

    def __init__(self):
        usage.Options.__init__(self)

        self.config = None
        self.format_options = {}

    def opt_option(self, option):
        if '=' in option:
            k,v = option.split('=', 1)
        
            self.format_options[k] = v
        else:
            self.format_options[option] = True

    opt_o = opt_option

    def parseArgs(self, *rest):
        self.params += rest

    def parseOptions(self, opts=None):
        if not opts:
            opts = ['--help']

        if opts == ['--help']:
            self.subCommands = options.genSubCommandsDef()

        usage.Options.parseOptions(self, opts)
    
    def postOptions(self):
        if self.recursing:
            return

        if self['config']:
            self['config'] = os.path.abspath(self['config'])
            if os.path.exists(self['config']):
                parseConfig(self['config'])

        self.root = filepath.FilePath(config.DocumentRoot)
        self.calendarCollection = self.root.child('calendars')
        self.principalCollection = self.root.child('principals')

        if self['format'] in sorted(formatters.listFormatters()):
            self.formatter = formatters.getFormatter(self['format'])
            self.formatter = self.formatter(options=self.format_options)
        else:
            raise usage.UsageError("Please specify a valid formatter")
        
        self.subCommands = options.genSubCommandsDef()
        self.recursing = 1
        self.parseOptions(self.params)
        
        sc = options.listCommands()

        if self.subCommand not in sc:
            raise usage.UsageError("Please select one of: %s" % (', '.join(sorted(sc))))

    
def run():
    adminOptions = AdminOptions()

    try:
        adminOptions.parseOptions(sys.argv[1:])

    except usage.UsageError, ue:
        print adminOptions
        if len(sys.argv) > 1:
            cmd = sys.argv[1]
        else:
            cmd = sys.argv[0]

        print "%s: %s" % (cmd, ue)


    except KeyboardInterrupt:
        sys.exit(1)
