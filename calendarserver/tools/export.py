#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_export -*-
##
# Copyright (c) 2006-2009 Apple Inc. All rights reserved.
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
This tool reads calendar data from a series of inputs and generates a
single iCalendar file which can be opened in many calendar
applications.

This can be used to quickly create an iCalendar file from a user's
calendars.

This tool requires access to the calendar server's configuration and
data storage; it does not operate by talking to the server via the
network.  It therefore does not apply any of the access restrictions
that the server would.  As such, one should be midful that data
exported via this tool may be sensitive.

Please also note that this is not an appropriate tool for backups, as there is
data associated with users and calendars beyond the iCalendar as visible to the
owner of that calendar, including DAV properties, information about sharing, and
per-user data such as alarms.
"""

import sys
import itertools

from getopt import getopt, GetoptError
from os.path import dirname, abspath

from twisted.python.usage import Options
from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav.config import ConfigurationError
from twistedcaldav.ical import Component

from twistedcaldav.resource import isCalendarCollectionResource,\
    CalendarHomeResource
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.stdconfig import DEFAULT_CARDDAV_CONFIG_FILE
from calendarserver.tools.cmdline import utilityMain
from twisted.application.service import Service
from calendarserver.tap.util import directoryFromConfig

from calendarserver.tools.util import (loadConfig, getDirectory)

def usage(e=None):
    if e:
        print e
        print ""
    try:
        ExportOptions().opt_help()
    except SystemExit:
        pass
    if e:
        sys.exit(64)
    else:
        sys.exit(0)



class ExportOptions(Options):
    """
    Command-line options for 'calendarserver_export'

    @ivar exporters: a list of L{HomeExporter} objects which can identify the
        calendars to export, given a directory service.  This list is built by
        parsing --record and --collection options.
    """

    optParameters = [['config', 'c', DEFAULT_CARDDAV_CONFIG_FILE,
                      "Specify caldavd.plist configuration path."]]

    def __init__(self):
        super(ExportOptions, self).__init__()
        self.exporters = []
        self.outputName = '-'


    def opt_record(self, recordName):
        """
        Add a directory record's calendar home (format: 'recordType:shortName').
        """
        recordType, shortName = recordName.split(":", 1)
        self.exporters.append(HomeExporter(recordType, shortName))

    opt_r = opt_record


    def opt_collection(self, collectionName):
        """
        Add a calendar collection.  This option must be passed after --record
        (or a synonym, like --user).  for example, to export user1's calendars
        called 'meetings' and 'team', invoke 'calendarserver_export --user=user1
        --collection=meetings --collection=team'.
        """
        self.exporters[-1].collections.append(collectionName)

    opt_c = opt_collection


    def opt_output(self, filename):
        """
        Specify output file path (default: '-', meaning stdout).
        """
        self.outputName = filename

    opt_o = opt_output


    def opt_user(self, user):
        """
        Add a user's calendar home (shorthand for '-r users:shortName').
        """
        self.opt_record("users:" + user)

    opt_u = opt_user


    def openOutput(self):
        """
        Open the appropriate output file based on the '--output' option.
        """
        if self.outputName == '-':
            return sys.stdout
        else:
            return open(self.outputName, 'wb')



class HomeExporter(object):
    """
    An exporter that constructs a list of calendars based on the UID or
    directory services record ID of the home.

    @ivar collections: A list of the names of collections that this exporter
        should enumerate.

    @type collections: C{list} of C{str}

    @ivar recordType: The directory record type to export.  For example:
        'users'.

    @type recordType: C{str}

    @ivar shortName: The shortName of the directory record to export, according
        to C{recordType}.
    """

    def __init__(self, recordType, shortName):
        self.collections = []
        self.recordType = recordType
        self.shortName = shortName


    @inlineCallbacks
    def listCalendars(self, txn, exportService):
        directory = exportService.directoryService()
        record = directory.recordWithShortName(self.recordType, self.shortName)
        home = yield txn.calendarHomeWithUID(record.guid)
        if self.collections:
            result = []
            for collection in self.collections:
                result.append((yield home.calendarWithName(collection)))
        else:
            result = yield home.calendars()
        returnValue(result)



@inlineCallbacks
def exportToFile(calendars, fileobj):
    """
    Export some calendars to a file as a particular UID.

    @param calendars: an iterable of L{ICalendar} providers (or L{Deferred}s of
        same).

    @param fileobj: an object with a C{write} method that will accept some
        iCalendar data.

    @return: a L{Deferred} which fires when the export is complete.  (Note that
        the file will not be closed.)
    @rtype: L{Deferred} that fires with C{None}
    """
    comp = Component.newCalendar()
    for calendar in calendars:
        calendar = yield calendar
        for obj in (yield calendar.calendarObjects()):
            evt = yield obj.filteredComponent(
                calendar.ownerCalendarHome().uid(), True)
            for sub in evt.subcomponents():
                if sub.name() != 'VTIMEZONE':
                    # Omit all VTIMEZONE components, since PyCalendar will
                    # helpfully re-include all necessary VTIMEZONEs when we call
                    # __str__; see pycalendar.calendar.PyCalendar.generate() and
                    # .includeTimezones().
                    comp.addComponent(sub)

    fileobj.write(str(comp))



def oldmain():
    # quiet pyflakes while I'm working on this.
    from stopbotheringme import CalDAVFile
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hf:o:c:H:r:u:", [
                "help",
                "config=",
                "output=",
                "collection=", "home=", "record=", "user=",
            ],
        )
    except GetoptError, e:
        usage(e)

    configFileName = None

    collections = set()
    calendarHomes = set()
    records = set()

    def checkExists(resource):
        if not resource.exists():
            sys.stderr.write("No such file: %s\n" % (resource.fp.path,))
            sys.exit(1)

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("-c", "--collection"):
            path = abspath(arg)
            collection = CalDAVFile(path)
            checkExists(collection)
            if not isCalendarCollectionResource(collection):
                sys.stderr.write("Not a calendar collection: %s\n" % (path,))
                sys.exit(1)
            collections.add(collection)

        elif opt in ("-H", "--home"):
            path = abspath(arg)
            parent = CalDAVFile(dirname(abspath(path)))
            calendarHome = CalendarHomeResource(arg, parent, None)
            checkExists(calendarHome)
            calendarHomes.add(calendarHome)

        elif opt in ("-r", "--record"):
            try:
                recordType, shortName = arg.split(":", 1)
                if not recordType or not shortName:
                    raise ValueError()
            except ValueError:
                sys.stderr.write("Invalid record identifier: %r\n" % (arg,))
                sys.exit(1)

            records.add((recordType, shortName))

        elif opt in ("-u", "--user"):
            records.add((DirectoryService.recordType_users, arg))

    if args:
        usage("Too many arguments: %s" % (" ".join(args),))

    if records:
        try:
            config = loadConfig(configFileName)
            config.directory = getDirectory()
        except ConfigurationError, e:
            sys.stdout.write("%s\n" % (e,))
            sys.exit(1)

    for record in records:
        recordType, shortName = record
        calendarHome = config.directory.calendarHomeForShortName(recordType, shortName)
        if not calendarHome:
            sys.stderr.write("No calendar home found for record: (%s)%s\n" % (recordType, shortName))
            sys.exit(1)
        calendarHomes.add(calendarHome)

    for calendarHome in calendarHomes:
        for childName in calendarHome.listChildren():
            child = calendarHome.getChild(childName)
            if isCalendarCollectionResource(child):
                collections.add(child)

    calendar = Component.newCalendar()

    uids  = set()

    for collection in collections:
        for name, uid, type in collection.index().indexedSearch(None):
            child = collection.getChild(name)

            if uid in uids:
                sys.stderr.write("Skipping duplicate event UID %r from %s\n" % (uid, collection.fp.path))
                continue
            else:
                uids.add(uid)

    calendarData = str(calendar)
    output = sys.stdout
    output.write(calendarData)



class ExporterService(Service, object):
    """
    Service which runs, exports the appropriate records, then stops the reactor.
    """

    def __init__(self, store, options, output, reactor, config):
        super(ExporterService, self).__init__()
        self.store   = store
        self.options = options
        self.output  = output
        self.reactor = reactor
        self.config = config
        self._directory = None


    def startService(self):
        """
        Start the service.
        """
        super(ExporterService, self).startService()
        self.doExport()


    @inlineCallbacks
    def doExport(self):
        """
        Do the export, stopping the reactor when done.
        """
        txn = self.store.newTransaction()
        try:
            allCalendars = itertools.chain(
                *[(yield exporter.listCalendars(txn, self)) for exporter in
                  self.options.exporters]
            )
            yield exportToFile(allCalendars, self.output)
        except:
            log.err()

        yield txn.commit()
        # TODO: should be read-only, so commit/abort shouldn't make a
        # difference.  commit() for now, in case any transparent cache / update
        # stuff needed to happen, don't want to undo it.
        self.output.close()
        self.reactor.stop()


    def directoryService(self):
        """
        Get an appropriate directory service for this L{ExporterService}'s
        configuration, creating one first if necessary.
        """
        if self._directory is None:
            self._directory = directoryFromConfig(self.config)
        return self._directory


    def stopService(self):
        """
        Stop the service.  Nothing to do; everything should be finished by this
        time.
        """
        # TODO: stopping this service mid-export should really stop the export
        # loop, but this is not implemented because nothing will actually do it
        # except hitting ^C (which also calls reactor.stop(), so that will exit
        # anyway).



def main(argv=sys.argv, stderr=sys.stderr, reactor=None):
    """
    Do the export.
    """
    if reactor is None:
        from twisted.internet import reactor
    options = ExportOptions()
    options.parseOptions(argv[1:])
    try:
        output = options.openOutput()
    except IOError, e:
        stderr.write("Unable to open output file for writing: %s\n" %
                     (e))
        sys.exit(1)
    def makeService(store):
        from twistedcaldav.config import config
        return ExporterService(store, options, output, reactor, config)
    utilityMain(options['config'], makeService, reactor)


