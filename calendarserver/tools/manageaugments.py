#!/usr/bin/env python
##
# Copyright (c) 2009-2010 Apple Inc. All rights reserved.
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

from optparse import OptionParser
from twistedcaldav.directory import xmlaugmentsparser
from xml.etree.ElementTree import tostring
import sys
import os
from twistedcaldav.xmlutil import readXML, addSubElement, writeXML

def error(s):
    print s
    sys.exit(1)

def doAdd(xmlfile, uid, host, enable_calendar, auto_schedule):

    try:
        _ignore_etree, augments_node = readXML(xmlfile)
    except ValueError, e:
        error("Could not read XML file: %s" % (e,))

    # Make sure UID is not already present
    for child in augments_node.getchildren():
        
        if child.tag != xmlaugmentsparser.ELEMENT_RECORD:
            error("Unknown augment type: '%s' in augment file: '%s'" % (child.tag, xmlfile,))

        for node in child.getchildren():
            
            if node.tag == xmlaugmentsparser.ELEMENT_UID and node.text == uid:
                error("Cannot add uid '%s' because it already exists in augment file: '%s'" % (uid, xmlfile,))
    
    # Create new record
    if len(augments_node.getchildren()):
        augments_node.getchildren()[-1].tail = "\n  "
    record = addSubElement(augments_node, xmlaugmentsparser.ELEMENT_RECORD)
    addSubElement(record, xmlaugmentsparser.ELEMENT_UID, uid)
    addSubElement(record, xmlaugmentsparser.ELEMENT_ENABLE, "true")
    addSubElement(record, xmlaugmentsparser.ELEMENT_HOSTEDAT, host)
    addSubElement(record, xmlaugmentsparser.ELEMENT_ENABLECALENDAR, "true" if enable_calendar else "false")
    addSubElement(record, xmlaugmentsparser.ELEMENT_AUTOSCHEDULE, "true" if auto_schedule else "false")
    
    # Modify xmlfile
    writeXML(xmlfile, augments_node)
    print "Added uid '%s' in augment file: '%s'" % (uid, xmlfile,)
    
def doModify(xmlfile, uid, host, enable_calendar, auto_schedule):

    try:
        _ignore_etree, augments_node = readXML(xmlfile)
    except ValueError, e:
        error("Could not read XML file: %s" % (e,))

    # Make sure UID is present
    for child in augments_node.getchildren():
        
        if child.tag != xmlaugmentsparser.ELEMENT_RECORD:
            error("Unknown augment type: '%s' in augment file: '%s'" % (child.tag, xmlfile,))

        for node in child.getchildren():
            
            if node.tag == xmlaugmentsparser.ELEMENT_UID and node.text == uid:
                break
        else:
            continue
        break
    else:
        error("Cannot modify uid '%s' because it does not exist in augment file: '%s'" % (uid, xmlfile,))
    
    # Modify record
    if host is not None:
        child.find(xmlaugmentsparser.ELEMENT_HOSTEDAT).text = host
    child.find(xmlaugmentsparser.ELEMENT_ENABLECALENDAR).text = "true" if enable_calendar else "false"
    child.find(xmlaugmentsparser.ELEMENT_AUTOSCHEDULE).text = "true" if auto_schedule else "false"
    
    # Modify xmlfile
    writeXML(xmlfile, augments_node)
    print "Modified uid '%s' in augment file: '%s'" % (uid, xmlfile,)

def doRemove(xmlfile, uid):

    try:
        _ignore_etree, augments_node = readXML(xmlfile)
    except ValueError, e:
        error("Could not read XML file: %s" % (e,))

    # Make sure UID is present
    for child in augments_node.getchildren():
        
        if child.tag != xmlaugmentsparser.ELEMENT_RECORD:
            error("Unknown augment type: '%s' in augment file: '%s'" % (child.tag, xmlfile,))

        for node in child.getchildren():
            
            if node.tag == xmlaugmentsparser.ELEMENT_UID and node.text == uid:
                break
        else:
            continue
        augments_node.remove(child)
        break
    else:
        error("Cannot remove uid '%s' because it does not exist in augment file: '%s'" % (uid, xmlfile,))
    
    # Modify xmlfile
    writeXML(xmlfile, augments_node)
    print "Removed uid '%s' from augment file: '%s'" % (uid, xmlfile,)
    
def doPrint(xmlfile):

    # Read in XML
    try:
        _ignore_etree, augments_node = readXML(xmlfile)
    except ValueError, e:
        error("Could not read XML file: %s" % (e,))

    print tostring(augments_node)

def main():

    usage = "%prog [options] ACTION"
    epilog = """
ACTION is one of add|modify|remove|print

  add:    add a user record
  modify: modify a user record
  remove: remove a user record
  print:  print all user records
"""
    description = "Tool to manipulate CalendarServer augments XML file"
    version = "%prog v1.0"
    parser = OptionParser(usage=usage, description=description, version=version)
    parser.epilog = epilog
    parser.format_epilog = lambda _:epilog

    parser.add_option("-f", "--file", dest="xmlfilename",
                      help="XML augment file to manipulate", metavar="FILE")
    parser.add_option("-u", "--uid", dest="uid",
                      help="OD GUID to manipulate", metavar="UID")
    parser.add_option("-i", "--uidfile", dest="uidfile",
                      help="File containing a list of GUIDs to manipulate", metavar="UIDFILE")
    parser.add_option("-n", "--node", dest="node",
                      help="Partition node to assign to UID", metavar="NODE")
    parser.add_option("-c", "--enable-calendar", action="store_true", dest="enable_calendar",
                      default=True, help="Enable calendaring for this UID: %default")
    parser.add_option("-a", "--auto-schedule", action="store_true", dest="auto_schedule",
                      default=False, help="Enable auto-schedule for this UID: %default")

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("incorrect number of arguments")

    uids = []
    if options.uid:
        uids.append(options.uid)
    elif options.uidfile:
        if not os.path.exists(options.uidfile):
            parser.error("File containing list of UIDs does not exist")
        with open(options.uidfile) as f:
            for line in f:
                uids.append(line[:-1])
        
    if args[0] == "add":
        if not options.node:
            parser.error("Partition node must be specified when adding")
        for uid in uids:
            doAdd(options.xmlfilename, uid, options.node, options.enable_calendar, options.auto_schedule)
    elif args[0] == "modify":
        for uid in uids:
            doModify(options.xmlfilename, uid, options.node, options.enable_calendar, options.auto_schedule)
    elif args[0] == "remove":
        for uid in uids:
            doRemove(options.xmlfilename, uid)
    elif args[0] == "print":
        doPrint(options.xmlfilename)
    else:
        parser.error("Unknown argument")

if __name__ == '__main__':
    main()
