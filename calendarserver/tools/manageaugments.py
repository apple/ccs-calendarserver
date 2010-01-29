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
from xml.etree.ElementTree import ElementTree, tostring, SubElement
from xml.parsers.expat import ExpatError
import sys
import os

def error(s):
    print s
    sys.exit(1)

def readXML(xmlfile):

    # Read in XML
    try:
        tree = ElementTree(file=xmlfile)
    except ExpatError, e:
        error("Unable to parse file '%s' because: %s" % (xmlfile, e,))

    # Verify that top-level element is correct
    augments_node = tree.getroot()
    if augments_node.tag != xmlaugmentsparser.ELEMENT_AUGMENTS:
        error("Ignoring file '%s' because it is not a augments file" % (xmlfile,))

    return augments_node

def writeXML(xmlfile, root):
    
    data = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE augments SYSTEM "augments.dtd">

""" + tostring(root)

    with open(xmlfile, "w") as f:
        f.write(data)

def addSubElement(parent, tag, text=None, indent=0):
    
    child = SubElement(parent, tag)
    child.text = text
    child.tail = "\n" + " " * indent
    return child

def changeSubElementText(parent, tag, text):
    
    child = parent.find(tag)
    child.text = text

def doAdd(xmlfile, guid, host, enable_calendar, auto_schedule):

    augments_node = readXML(xmlfile)

    # Make sure GUID is not already present
    for child in augments_node.getchildren():
        
        if child.tag != xmlaugmentsparser.ELEMENT_RECORD:
            error("Unknown augment type: '%s' in augment file: '%s'" % (child.tag, xmlfile,))

        for node in child.getchildren():
            
            if node.tag == xmlaugmentsparser.ELEMENT_GUID and node.text == guid:
                error("Cannot add guid '%s' because it already exists in augment file: '%s'" % (guid, xmlfile,))
    
    # Create new record
    augments_node.getchildren()[-1].tail = "\n  "
    record = addSubElement(augments_node, xmlaugmentsparser.ELEMENT_RECORD, "\n    ")
    addSubElement(record, xmlaugmentsparser.ELEMENT_GUID, guid, 4)
    addSubElement(record, xmlaugmentsparser.ELEMENT_ENABLE, "true", 4)
    addSubElement(record, xmlaugmentsparser.ELEMENT_HOSTEDAT, host, 4)
    addSubElement(record, xmlaugmentsparser.ELEMENT_ENABLECALENDAR, "true" if enable_calendar else "false", 4)
    addSubElement(record, xmlaugmentsparser.ELEMENT_AUTOSCHEDULE, "true" if auto_schedule else "false", 2)
    
    # Modify xmlfile
    writeXML(xmlfile, augments_node)
    print "Added guid '%s' in augment file: '%s'" % (guid, xmlfile,)
    
def doModify(xmlfile, guid, host, enable_calendar, auto_schedule):

    augments_node = readXML(xmlfile)

    # Make sure GUID is present
    for child in augments_node.getchildren():
        
        if child.tag != xmlaugmentsparser.ELEMENT_RECORD:
            error("Unknown augment type: '%s' in augment file: '%s'" % (child.tag, xmlfile,))

        for node in child.getchildren():
            
            if node.tag == xmlaugmentsparser.ELEMENT_GUID and node.text == guid:
                break
        else:
            continue
        break
    else:
        error("Cannot modify guid '%s' because it does not exist in augment file: '%s'" % (guid, xmlfile,))
    
    # Modify record
    if host is not None:
        child.find(xmlaugmentsparser.ELEMENT_HOSTEDAT).text = host
    child.find(xmlaugmentsparser.ELEMENT_ENABLECALENDAR).text = "true" if enable_calendar else "false"
    child.find(xmlaugmentsparser.ELEMENT_AUTOSCHEDULE).text = "true" if auto_schedule else "false"
    
    # Modify xmlfile
    writeXML(xmlfile, augments_node)
    print "Modified guid '%s' in augment file: '%s'" % (guid, xmlfile,)

def doRemove(xmlfile, guid):

    augments_node = readXML(xmlfile)

    # Make sure GUID is present
    for child in augments_node.getchildren():
        
        if child.tag != xmlaugmentsparser.ELEMENT_RECORD:
            error("Unknown augment type: '%s' in augment file: '%s'" % (child.tag, xmlfile,))

        for node in child.getchildren():
            
            if node.tag == xmlaugmentsparser.ELEMENT_GUID and node.text == guid:
                break
        else:
            continue
        augments_node.remove(child)
        break
    else:
        error("Cannot remove guid '%s' because it does not exist in augment file: '%s'" % (guid, xmlfile,))
    
    # Modify xmlfile
    writeXML(xmlfile, augments_node)
    print "Removed guid '%s' from augment file: '%s'" % (guid, xmlfile,)
    
def doPrint(xmlfile):

    # Read in XML
    augments_node = readXML(xmlfile)

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
    parser.add_option("-g", "--guid", dest="guid",
                      help="OD GUID to manipulate", metavar="GUID")
    parser.add_option("-h", "--guidfile", dest="guidfile",
                      help="File containing a list of GUIDs to manipulate", metavar="GUIDFILE")
    parser.add_option("-n", "--node", dest="node",
                      help="Partition node to assign to GUID", metavar="NODE")
    parser.add_option("-c", "--enable-calendar", action="store_true", dest="enable_calendar",
                      default=True, help="Enable calendaring for this GUID: %default")
    parser.add_option("-a", "--auto-schedule", action="store_true", dest="auto_schedule",
                      default=False, help="Enable auto-schedule for this GUID: %default")

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("incorrect number of arguments")

    guids = []
    if options.guid:
        guids.append(options.guid)
    elif options.guidfile:
        if not os.path.exists(options.guidfile):
            parser.error("File containing list of GUIDs does not exist")
        with open(options.guidfile) as f:
            for line in f:
                guids.append(line[:-1])
        
    if args[0] == "add":
        if not options.node:
            parser.error("Partition node must be specified when adding")
        for guid in guids:
            doAdd(options.xmlfilename, guid, options.node, options.enable_calendar, options.auto_schedule)
    elif args[0] == "modify":
        for guid in guids:
            doModify(options.xmlfilename, guid, options.node, options.enable_calendar, options.auto_schedule)
    elif args[0] == "remove":
        for guid in guids:
            doRemove(options.xmlfilename, guid)
    elif args[0] == "print":
        doPrint(options.xmlfilename)

if __name__ == '__main__':
    main()
