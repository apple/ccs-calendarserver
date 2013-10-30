#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_upgrade -*-
##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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

"""
This tool allows any necessary upgrade to complete, then exits.
"""

from __future__ import print_function
import os
import sys
import time

from twisted.python.text import wordWrap
from twisted.python.usage import Options, UsageError

from twext.python.log import Logger, LogLevel, formatEvent, addObserver

from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE
from twisted.application.service import Service

from calendarserver.tools.cmdline import utilityMain
from calendarserver.tap.caldav import CalDAVServiceMaker

log = Logger()



def usage(e=None):
    if e:
        print(e)
        print("")
    try:
        UpgradeOptions().opt_help()
    except SystemExit:
        pass
    if e:
        sys.exit(64)
    else:
        sys.exit(0)


description = '\n'.join(
    wordWrap(
        """
        Usage: calendarserver_upgrade [options] [input specifiers]\n
        """ + __doc__,
        int(os.environ.get('COLUMNS', '80'))
    )
)

class UpgradeOptions(Options):
    """
    Command-line options for 'calendarserver_upgrade'

    @ivar upgraders: a list of L{DirectoryUpgradeer} objects which can identify the
        calendars to upgrade, given a directory service.  This list is built by
        parsing --record and --collection options.
    """

    synopsis = description

    optFlags = [
        ['status', 's', "Check database status and exit."],
        ['postprocess', 'p', "Perform post-database-import processing."],
        ['debug', 'D', "Debug logging."],
    ]

    optParameters = [
        ['config', 'f', DEFAULT_CONFIG_FILE, "Specify caldavd.plist configuration path."],
    ]

    def __init__(self):
        super(UpgradeOptions, self).__init__()
        self.upgradeers = []
        self.outputName = '-'
        self.merge = False


    def opt_output(self, filename):
        """
        Specify output file path (default: '-', meaning stdout).
        """
        self.outputName = filename

    opt_o = opt_output


    def opt_merge(self):
        """
        Rather than skipping homes that exist on the filesystem but not in the
        database, merge their data into the existing homes.
        """
        self.merge = True

    opt_m = opt_merge


    def openOutput(self):
        """
        Open the appropriate output file based on the '--output' option.
        """
        if self.outputName == '-':
            return sys.stdout
        else:
            return open(self.outputName, 'wb')



class UpgraderService(Service, object):
    """
    Service which runs, exports the appropriate records, then stops the reactor.
    """

    started = False

    def __init__(self, store, options, output, reactor, config):
        super(UpgraderService, self).__init__()
        self.store = store
        self.options = options
        self.output = output
        self.reactor = reactor
        self.config = config
        self._directory = None


    def startService(self):
        """
        Immediately stop.  The upgrade will have been run before this.
        """
        if self.store is None:
            if self.options["status"]:
                self.output.write("Upgrade needed.\n")
            else:
                self.output.write("Upgrade failed.\n")
        else:
            # If we get this far the database is OK
            if self.options["status"]:
                self.output.write("Database OK.\n")
            else:
                self.output.write("Upgrade complete, shutting down.\n")
        UpgraderService.started = True

        from twisted.internet import reactor
        from twisted.internet.error import ReactorNotRunning
        try:
            reactor.stop()
        except ReactorNotRunning:
            # I don't care.
            pass


    def stopService(self):
        """
        Stop the service.  Nothing to do; everything should be finished by this
        time.
        """



def main(argv=sys.argv, stderr=sys.stderr, reactor=None):
    """
    Do the export.
    """
    from twistedcaldav.config import config
    if reactor is None:
        from twisted.internet import reactor

    options = UpgradeOptions()
    try:
        options.parseOptions(argv[1:])
    except UsageError, e:
        usage(e)

    try:
        output = options.openOutput()
    except IOError, e:
        stderr.write("Unable to open output file for writing: %s\n" % (e))
        sys.exit(1)

    if options.merge:
        def setMerge(data):
            data.MergeUpgrades = True
        config.addPostUpdateHooks([setMerge])

    def makeService(store):
        return UpgraderService(store, options, output, reactor, config)

    def onlyUpgradeEvents(eventDict):
        text = formatEvent(eventDict)
        output.write(logDateString() + " " + text + "\n")
        output.flush()

    if not options["status"]:
        log.publisher.levels.setLogLevelForNamespace(None, LogLevel.debug)
        addObserver(onlyUpgradeEvents)

    def customServiceMaker():
        customService = CalDAVServiceMaker()
        customService.doPostImport = options["postprocess"]
        return customService

    def _patchConfig(config):
        config.FailIfUpgradeNeeded = options["status"]

    def _onShutdown():
        if not UpgraderService.started:
            print("Failed to start service.")

    utilityMain(options["config"], makeService, reactor, customServiceMaker, patchConfig=_patchConfig, onShutdown=_onShutdown, verbose=options["debug"])



def logDateString():
    logtime = time.localtime()
    Y, M, D, h, m, s = logtime[:6]
    tz = computeTimezoneForLog(time.timezone)

    return '%02d-%02d-%02d %02d:%02d:%02d%s' % (Y, M, D, h, m, s, tz)



def computeTimezoneForLog(tz):
    if tz > 0:
        neg = 1
    else:
        neg = 0
        tz = -tz
    h, rem = divmod(tz, 3600)
    m, rem = divmod(rem, 60)
    if neg:
        return '-%02d%02d' % (h, m)
    else:
        return '+%02d%02d' % (h, m)

if __name__ == '__main__':
    main()
