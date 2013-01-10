#!/usr/bin/env python
#
##
# Copyright (c) 2007-2013 Apple Inc. All rights reserved.
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
#
# ...
#


import getopt
import os
import sys

def usage():
    print """Usage: directorysetup [options] init|addUser|disableUser|removeUser <<user>>
Options:
    -h       Print this help and exit
    -n node  OpenDirectory node to target (/LDAPv3/127.0.0.1)
    -u uid   OpenDirectory Admin user id
    -p pswd  OpenDirectory Admin user password
    -c cname OpenDirectory /Computers record name for the calendar server
    
Description:
This is a little command line utility to setup a directory server with records
conforming to the new schema used by the calendar server. It has several "actions":

"init" - this action will modify the computer record for the host calendar server to
add the new "com.apple.macosxserver.virtualhosts" entry.

"addUser" - modifies a user record to enable use of the calendar server.

"disableUser" - modifies a user record to disable use of the calendar server.

"removeUser" - modifies a user record to prevent use of the calendar server by
 removing any reference to the service.

"""

def initComputerRecord(admin_user, admin_pswd, node, recordname):
    plistdefault = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>ReplicaName</key>
        <string>Master</string>
        <key>com.apple.od.role</key>
        <string>master</string>
</dict>
</plist>
"""
    plistdefault = plistdefault.replace('"', '\\"')
    plistdefault = plistdefault.replace('\n', '')

    plist_good = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>
            
            <key>C18C34AC-3D9E-403C-8A33-BFC303F3840E</key>
            <dict>
                <key>hostname</key>
                <string>calendar.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>8800</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>8843</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>calendar</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>calendar</key>
                    <dict>
                        <key>templates</key>
                        <dict>
                            <key>principalPath</key>
                            <string>/principals/%(type)s/%(name)s</string>
                            <key>calendarUserAddresses</key>
                            <array>
                                <string>%(scheme)s://%(hostname)s:%(port)s/principals/%(type)s/%(name)s</string>
                                <string>mailto:%(email)s</string>
                                <string>urn:uuid:%(guid)s</string>
                            </array>
                        </dict>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

    plist_good = plist_good.replace('"', '\\"')
    plist_good = plist_good.replace('\n', '')
    cmd = "dscl -u %s -P %s %s -create /Computers/%s \"dsAttrTypeStandard:XMLPlist\" \"%s\"" % (admin_user, admin_pswd, node, recordname, plist_good,)
    print cmd
    os.system(cmd)

def getComputerRecordGUID(admin_user, admin_pswd, node, computername):
    # First get the generatedGUID for this computer
    cmd = "dscl -u %s -P %s %s -read /Computers/%s \"dsAttrTypeStandard:GeneratedUID\"" % (admin_user, admin_pswd, node, computername,)
    print cmd
    result = os.popen(cmd, "r")
    for line in result:
        return line[len("GeneratedUID: "):-1]

def addUser(admin_user, admin_pswd, node, computername, username):

    uid = getComputerRecordGUID(admin_user, admin_pswd, node, computername)
    servicetag = "%s:%s:calendar" % (uid, "C18C34AC-3D9E-403C-8A33-BFC303F3840E")

    cmd = "dscl -u %s -P %s %s -create /Users/%s \"dsAttrTypeStandard:ServicesLocator\" \"%s\"" % (admin_user, admin_pswd, node, username, servicetag,)
    print cmd
    os.system(cmd)

def disableUser(admin_user, admin_pswd, node, computername, username):

    uid = getComputerRecordGUID(admin_user, admin_pswd, node, computername)
    servicetag = "%s:%s:calendar:disabled" % (uid, "C18C34AC-3D9E-403C-8A33-BFC303F3840E")

    cmd = "dscl -u %s -P %s %s -create /Users/%s \"dsAttrTypeStandard:ServicesLocator\" \"%s\"" % (admin_user, admin_pswd, node, username, servicetag,)
    print cmd
    os.system(cmd)

def removeUser(admin_user, admin_pswd, node, computername, username):
    cmd = "dscl -u %s -P %s %s -delete /Users/%s \"dsAttrTypeStandard:ServicesLocator\"" % (admin_user, admin_pswd, node, username,)
    print cmd
    os.system(cmd)

if __name__ == "__main__":

    try:
        options, args = getopt.getopt(sys.argv[1:], "hc:n:p:u:")

        node = "/LDAPv3/127.0.0.1"
        admin_user = None
        admin_pswd = None
        computername = None

        for option, value in options:
            if option == "-h":
                usage()
                sys.exit(0)
            elif option == "-n":
                node = value
            elif option == "-u":
                admin_user = value
            elif option == "-p":
                admin_pswd = value
            elif option == "-c":
                computername = value
            else:
                print "Unrecognized option: %s" % (option,)
                usage()
                raise ValueError

        # Some options are required
        if not admin_user:
            print "A user name must be specified with the -u option"
        if not admin_pswd:
            print "A password must be specified with the -p option"
        if not computername:
            print "A computer record name must be specified with the -c option"
        if not admin_user or not admin_pswd or not computername:
            usage()
            raise ValueError
            
        # Process arguments
        if len(args) == 0:
            print "No arguments given. One of 'init', 'addUser', 'disableUser', 'removeUser' must be present."
            usage()
            raise ValueError
        elif args[0] not in ("init", "addUser", "disableUser", "removeUser"):
            print "Wrong arguments given: %s" % (args[0],)
            usage()
            raise ValueError
        
        if args[0] == "init":
            if len(args) > 1:
                print "Too many arguments given to 'init'"
                usage()
                raise ValueError
            initComputerRecord(admin_user, admin_pswd, node, computername)
        elif args[0] == "addUser":
            if len(args) > 2:
                print "Too many arguments given to 'addUser'"
                usage()
                raise ValueError
            elif len(args) != 2:
                print "'addUser' must have one argument - the user name"
                usage()
                raise ValueError
            addUser(admin_user, admin_pswd, node, computername, args[1])
        elif args[0] == "disableUser":
            if len(args) > 2:
                print "Too many arguments given to 'disableUser'"
                usage()
                raise ValueError
            elif len(args) != 2:
                print "'disableUser' must have one argument - the user name"
                usage()
                raise ValueError
            disableUser(admin_user, admin_pswd, node, computername, args[1])
        elif args[0] == "removeUser":
            if len(args) > 2:
                print "Too many arguments given to 'removeUser'"
                usage()
                raise ValueError
            elif len(args) != 2:
                print "'removeUser' must have one argument - the user name"
                usage()
                raise ValueError
            removeUser(admin_user, admin_pswd, node, computername, args[1])

    except Exception, e:
        sys.exit(str(e))
