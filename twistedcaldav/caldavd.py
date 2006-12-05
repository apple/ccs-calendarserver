#!/usr/bin/env python

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
# DRI: Cyrus Daboo, cdaboo@apple.com
##

import sys
import os
import getopt
import signal
from tempfile import mkstemp

try:
    #
    # plistlib is only included in Mac OS distributions of Python.
    # This may change in Python 2.6, see:
    #   https://sourceforge.net/tracker/?func=detail&atid=105470&aid=1555501&group_id=5470
    #
    from plistlib import readPlist
except ImportError:
    from twistedcaldav.py.plistlib import readPlist

sys.path.insert(0, "/usr/share/caldavd/lib/python")

"""
Parse the command line and read in a configuration file and then launch the server.
"""

DEFAULTS = {
    'CreateAccounts': False,
    'DirectoryService': {'params': {'node': '/Search'},
                         'type': 'OpenDirectoryService'},
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
    'SACLEnable': True,
    }

# FIXME: This doesn't actually work because the webserver runs in a different
# python process from the commandline util caldavd that actually parses the 
# plists the twistd plugin will fix this.
CONFIG = DEFAULTS.copy()


class caldavd(object):
    """
    Runs the caldav server.
    """
    
    def __init__(self):
        # Option defaults
        self.plistfile = "/etc/caldavd/caldavd.plist"

        self.config = CONFIG

        self.action = None
    
    def printit(self):
        """
        Print out details about the current configuration.
        """

        print "Current Configuration"
        print ""
        print "Configuration File:               %s" % (self.plistfile,)
        print ""
        print "Run as daemon:                    %s" % (self.config['RunStandalone'],)
        print "Document Root:                    %s" % (self.config['DocumentRoot'],)
        print "Repository Configuration:         %s" % (self.config['Repository'],)
        print "Generate Accounts in Repository:  %s" % (self.config['CreateAccounts'],)
        print "Reset ACLs on Generated Accounts: %s" % (self.config['ResetAccountACLs'],)
        print "Non-ssl Port:                     %s" % (self.config['Port'],)
        print "Use SSL:                          %s" % (self.config['SSLEnable'],)
        print "SSL Port:                         %s" % (self.config['SSLPort'],)
        print "Only Use SSL:                     %s" % (self.config['SSLOnly'],)
        print "SSL Private Key File:             %s" % (self.config['SSLPrivateKey'],)
        print "SSL Certificate File:             %s" % (self.config['SSLCertificate'],)
        print "Directory Service:                %s" % (self.config['DirectoryService']["type"],)
        print "Directory Service Parameters:     %r" % (self.config['DirectoryService']["params"],)
        print "Drop Box Enabled:                 %s" % (self.config['DropBoxEnabled'],)
        print "Drop Box Name:                    %s" % (self.config['DropBoxName'],)
        print "Drop Box ACLs are Inherited       %s" % (self.config['DropBoxInheritedACLs'],)
        print "Notifications Enabled:            %s" % (self.config['NotificationsEnabled'],)
        print "Notification Collection Name:     %s" % (self.config['NotificationCollectionName'],)
        print "Server Log File:                  %s" % (self.config['ServerLogFile'],)
        print "Error Log File:                   %s" % (self.config['ErrorLogFile'],)
        print "PID File:                         %s" % (self.config['PIDFile'],)
        print "twistd Location:                  %s" % (self.config['twistdLocation'],)
        print "Maximum Calendar Resource Size:   %d bytes" % (self.config['MaximumAttachmentSizeBytes'],)
        print "Global per-user quota limit:      %d bytes" % (self.config['UserQuotaBytes'],)

    def run(self):
        """
        Run the caldavd server using the provided options and configuration.

        @raise: C:{ValueError} if options or configuration are wrong.
        """

        # Parse command line options and config file
        self.commandLine()
        if self.action is None:
            return
        
        # Dispatch action
        {"start":   self.start,
         "stop":    self.stop,
         "restart": self.restart,
         "debug":   self.debug,  }[self.action]()

    def start(self):
        """
        Start the caldavd server.
        """
        
        print "Starting CalDAV Server",
        try:
            fd, tac = mkstemp(prefix="caldav")
            os.write(fd, self.generateTAC())
            os.close(fd)
        except Exception, e:
            print "        [Failed]"
            print "Unable to create temporary file for server configuration."
            print e
            sys.exit(1)
        
        # Create arguments for twistd
        args = [os.path.basename(sys.executable)]
        args.append(self.config['twistdLocation'])
        if not self.config['RunStandalone']:
            args.append("-n")
        args.append("--logfile=%s" % (self.config['ErrorLogFile'],))
        args.append("--pidfile=%s" % (self.config['PIDFile'],))
        args.append("-y")
        args.append(tac)

        # Create environment for twistd
        environment = dict(os.environ)
        environment["PYTHONPATH"] = ":".join(sys.path)

        # spawn the twistd python process
        try:
            os.spawnve(os.P_WAIT, sys.executable, args, environment)
        except OSError, why:
            print "        [Failed]"
            print "Error: %s" % (why[1],)
        
        # Get rid of temp file
        try:
            os.unlink(tac)
        except:
            pass
        print "        [Done]"
    
    def stop(self):
        """
        Stop the caldavd server.
        """
        
        if os.path.exists(self.config['PIDFile']):
            try:
                pid = int(open(self.config['PIDFile']).read())
            except ValueError:
                sys.exit("Pidfile %s contains non-numeric value" % self.config['PIDFile'])
            try:
                print "Stopping CalDAV Server",
                os.kill(pid, signal.SIGTERM)
                print "        [Done]"
            except OSError, why:
                print "        [Failed]"
                print "Error: %s" % (why[1],)
        else:
            print "CalDAV server is not running"
    
    def restart(self):
        """
        Restart the caldavd server.
        """
        self.stop()
        self.start()
        
    def debug(self):
        """
        Debug the caldavd server. This is the same as starting it except we do not
        spawn a seperate process - we run twistd directly so a debugger stays 'attached'.
        """
        
        print "Starting CalDAV Server",
        try:
            fd, tac = mkstemp(prefix="caldav")
            os.write(fd, self.generateTAC())
            os.close(fd)
        except Exception, e:
            print "        [Failed]"
            print "Unable to create temporary file for server configuration."
            print e
            sys.exit(1)
        
        # Create arguments for twistd
        args = []
        args.append(self.config['twistdLocation'])
        if not self.config['RunStandalone']:
            args.append("-n")
        args.append("--logfile=%s" % (self.config['ErrorLogFile'],))
        args.append("--pidfile=%s" % (self.config['PIDFile'],))
        args.append("-y")
        args.append(tac)

        # Create environment for twistd
        environment = dict(os.environ)
        environment["PYTHONPATH"] = ":".join(sys.path)

        # run the twistd python process directly
        try:
            sys.argv = args
            os.environ = environment
            from twisted.scripts.twistd import run
            run()
        except OSError, why:
            print "        [Failed]"
            print "Error: %s" % (why[1],)
        
        # Get rid of temp file
        try:
            os.unlink(tac)
        except:
            pass
        print "        [Done]"
    
    def commandLine(self):
        """
        Parse the command line options into the config object.
        
        @return: the C{str} for the requested action, or C{None} when
            immediate exit is called for.
        @raise: C{ValueError} when a problem occurs with the options.
        """
        options, args = getopt.getopt(sys.argv[1:], "hvf:XT:p")
        
        # Process the plist file first, then the options, so that command line
        # options get to override plist options
        pls = [p for p in options if p[0] == "-f"]
        if len(pls) == 1:
            self.plistfile = pls[0][1]
        if not os.path.exists(self.plistfile):
            print "Configuration file does not exist: %s" % (self.plistfile,)
            raise ValueError
        self.parsePlist()
    
        # Parse all the options
        do_print = False
        for option, value in options:
            if option == "-h":
                self.usage()
                return
            elif option == "-v":
                self.config['Verbose'] = True
            elif option == "-f":
                # We should have handled this already
                pass
            elif option == "-X":
                self.config['RunStandalone'] = False
            elif option == "-T":
                self.config['twistdLocation'] = value
            elif option == "-p":
                do_print = True
            else:
                print "Unrecognized option: %s" % (option,)
                self.usage()
                raise ValueError
        
        # Print out config if requested
        if do_print:
            self.printit()
            return
    
        # Process arguments
        if len(args) == 0:
            print "No arguments given. One of start, stop, restart or debug must be present."
            self.usage()
            raise ValueError
        elif len(args) > 1:
            print "Too many arguments given. Only one of start, stop, restart or debug must be present."
            self.usage()
            raise ValueError
        elif args[0] not in ("start", "stop", "restart", "debug",):
            print "Wrong arguments given: %s" % (args[0],)
            self.usage()
            raise ValueError
        
        # Verify that configuration is valid
        if not self.validate():
            raise ValueError
    
        self.action = args[0]
    
    def parsePlist(self):
        print "Reading configuration file %s." % (self.plistfile,)

        root = readPlist(self.plistfile)
        
        for k,v in root.items():
            if k in self.config:
                self.config[k] = v
            else:
                print "Unknown option: %s" % (k,)

        CONFIG = self.config

    def validate(self):
        
        result = True

        if not os.path.exists(self.config['DocumentRoot']):
            print "Document Root does not exist: %s" % (self.config['DocumentRoot'],)
            result = False

        if not os.path.exists(self.config['Repository']):
            print "Repository File does not exist: %s" % (self.config['Repository'],)
            result = False

        if self.config['SSLEnable'] and not os.path.exists(self.config['SSLPrivateKey']):
            print "SSL Private Key File does not exist: %s" % (self.config['SSLPrivateKey'],)
            result = False

        if self.config['SSLEnable'] and not os.path.exists(self.config['SSLCertificate']):
            print "SSL Certificate File does not exist: %s" % (self.config['SSLCertificate'],)
            result = False

        if not self.config['SSLEnable'] and self.config['SSLOnly']:
            self.config['SSLEnable'] = True

        if not self.config['RunStandalone']:
            self.config['ErrorLogFile'] = "-"

        if not os.path.exists(self.config['twistdLocation']):
            print "twistd does not exist: %s" % (self.config['twistdLocation'],)
            result = False
            
        return result

    def usage(self):
        default = caldavd()
        print """Usage: caldavd [options] start|stop|restart|debug
Options:
    -h          Print this help and exit
    -v          Be verbose
    -f config   Specify path to configuration file [""" + default.plistfile + """]
    -X          Do not daemonize
    -T twistd   Specify path to twistd [""" + default.twistd + """]
    -p          Print current configuration and exit
"""
    
    def generateTAC(self):
        return """
from twistedcaldav.repository import startServer

application, site = startServer(
    %(DocumentRoot)r,
    %(Repository)r,
    %(CreateAccounts)s,
    %(ResetAccountACLs)s,
    %(SSLEnable)s,
    %(SSLPrivateKey)r,
    %(SSLCertificate)r,
    %(SSLOnly)s,
    %(Port)d,
    %(SSLPort)d,
    %(MaximumAttachmentSizeBytes)d,
    %(UserQuotaBytes)d,
    %(ServerLogFile)r,
    %(DirectoryService)r,
    %(DropBoxEnabled)r,
    %(DropBoxName)r,
    %(DropBoxInheritedACLs)r,
    %(NotificationsEnabled)r,
    %(NotificationCollectionName)r,
    %(ManholePort)d,
)
""" % self.config


if __name__ == "__main__":
    try:
        caldavd().run()
    except Exception, e:
        sys.exit(str(e))
