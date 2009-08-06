#!/usr/bin/env python

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

from getopt import getopt, GetoptError
from subprocess import Popen, PIPE, STDOUT
import datetime
import hashlib
import operator
import os
import plistlib
import random
import shutil
import sys
import tempfile
import urllib
import uuid
import vobject
import xattr
import zlib

COPY_CAL_XATTRS = (
    'WebDAV:{DAV:}resourcetype',
    'WebDAV:{urn:ietf:params:xml:ns:caldav}calendar-timezone',
    'WebDAV:{http:%2F%2Fapple.com%2Fns%2Fical%2F}calendar-color',
    'WebDAV:{http:%2F%2Fapple.com%2Fns%2Fical%2F}calendar-order',
)
COPY_EVENT_XATTRS = ('WebDAV:{DAV:}getcontenttype',)


def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] source destination" % (name,)
    print ""
    print "  Anonymizes calendar data"
    print ""
    print "  source and destination should refer to document root directories"
    print ""
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -n --node <node>: Directory node (defaults to /Search)"
    print ""

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def main():

    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hn:", [
                "help",
                "node=",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    directoryNode = "/Search"
    sourceDirectory = None
    destDirectory = None

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-n", "--node"):
            directoryNode = arg

    if len(args) != 2:
        usage("Source and destination directories must be specified.")

    sourceDirectory, destDirectory = args

    directoryMap = DirectoryMap(directoryNode)

    anonymizeRoot(directoryMap, sourceDirectory, destDirectory)

    directoryMap.printStats()


def anonymizeRoot(directoryMap, sourceDirectory, destDirectory):
    # sourceDirectory and destDirectory are DocumentRoots

    print "Anonymizing calendar data from %s into %s" % (sourceDirectory, destDirectory)

    homes = 0
    calendars = 0
    resources = 0

    if not os.path.exists(sourceDirectory):
        print "Can't find source: %s" % (sourceDirectory,)
        sys.exit(1)

    if not os.path.exists(destDirectory):
        os.makedirs(destDirectory)

    sourceCalRoot = os.path.join(sourceDirectory, "calendars")

    destCalRoot = os.path.join(destDirectory, "calendars")
    if not os.path.exists(destCalRoot):
        os.makedirs(destCalRoot)

    sourceUidHomes = os.path.join(sourceCalRoot, "__uids__")
    if os.path.exists(sourceUidHomes):

        destUidHomes = os.path.join(destCalRoot, "__uids__")
        if not os.path.exists(destUidHomes):
            os.makedirs(destUidHomes)

        homeNames = os.listdir(sourceUidHomes)
        totalHomes = len(homeNames)
        print "Processing %d calendar homes..." % (totalHomes,)

        for home in homeNames:
            quotaUsed = 0

            if len(home) <= 2:
                continue
            sourceHome = os.path.join(sourceUidHomes, home)
            if not os.path.isdir(sourceHome):
                continue

            record = directoryMap.lookupCUA(home)
            if not record:
                print "Couldn't find %s, skipping." % (home,)
                continue

            destHome = os.path.join(destUidHomes, record['guid'])
            if not os.path.exists(destHome):
                os.makedirs(destHome)

            homes += 1

            # Iterate calendars
            freeBusies = []
            for cal in os.listdir(sourceHome):

                # Skip these:
                if cal in ("dropbox", "notifications"):
                    continue

                # Don't include these in freebusy list
                if cal not in ("inbox", "outbox"):
                    freeBusies.append(cal)

                sourceCal = os.path.join(sourceHome, cal)
                destCal = os.path.join(destHome, cal)
                if not os.path.exists(destCal):
                    os.makedirs(destCal)
                calendars += 1

                # Copy calendar xattrs
                for attr, value in xattr.xattr(sourceCal).iteritems():
                    if attr in COPY_CAL_XATTRS:
                        xattr.setxattr(destCal, attr, value)

                # Copy index
                sourceIndex = os.path.join(sourceCal, ".db.sqlite")
                destIndex = os.path.join(destCal, ".db.sqlite")
                if os.path.exists(sourceIndex):
                    shutil.copyfile(sourceIndex, destIndex)

                # Iterate resources
                for resource in os.listdir(sourceCal):

                    if resource.startswith("."):
                        continue

                    sourceResource = os.path.join(sourceCal, resource)

                    # Skip directories
                    if os.path.isdir(sourceResource):
                        continue

                    with open(sourceResource) as res:
                        data = res.read()

                    data = anonymizeData(directoryMap, data)

                    destResource = os.path.join(destCal, resource)
                    with open(destResource, "w") as res:
                        res.write(data)

                    quotaUsed += len(data)

                    for attr, value in xattr.xattr(sourceResource).iteritems():
                        if attr in COPY_EVENT_XATTRS:
                            xattr.setxattr(destResource, attr, value)

                    # Set new etag
                    xml = "<?xml version='1.0' encoding='UTF-8'?>\r\n<getcontentmd5 xmlns='http://twistedmatrix.com/xml_namespace/dav/'>%s</getcontentmd5>\r\n" % (hashlib.md5(data).hexdigest(),)
                    xattr.setxattr(destResource, "WebDAV:{http:%2F%2Ftwistedmatrix.com%2Fxml_namespace%2Fdav%2F}getcontentmd5", zlib.compress(xml))

                    resources += 1


                # Store new ctag on calendar
                xml = "<?xml version='1.0' encoding='UTF-8'?>\r\n<getctag xmlns='http://calendarserver.org/ns/'>%s</getctag>\r\n" % (str(datetime.datetime.now()),)
                xattr.setxattr(destCal, "WebDAV:{http:%2F%2Fcalendarserver.org%2Fns%2F}getctag", zlib.compress(xml))


            # Calendar home quota
            xml = "<?xml version='1.0' encoding='UTF-8'?>\r\n<quota-used xmlns='http://twistedmatrix.com/xml_namespace/dav/private/'>%d</quota-used>\r\n" % (quotaUsed,)
            xattr.setxattr(destHome, "WebDAV:{http:%2F%2Ftwistedmatrix.com%2Fxml_namespace%2Fdav%2Fprivate%2F}quota-used", zlib.compress(xml))

            # Inbox free busy calendars list
            destInbox = os.path.join(destHome, "inbox")
            if not os.path.exists(destInbox):
                os.makedirs(destInbox)
            xml = "<?xml version='1.0' encoding='UTF-8'?><calendar-free-busy-set xmlns='urn:ietf:params:xml:ns:caldav'>\n"
            for freeBusy in freeBusies:
                xml += "<href xmlns='DAV:'>/calendars/__uids__/%s/%s/</href>\n" % (record['guid'], freeBusy)
            xml += "</calendar-free-busy-set>\n"
            xattr.setxattr(destInbox,
                "WebDAV:{urn:ietf:params:xml:ns:caldav}calendar-free-busy-set",
                zlib.compress(xml)
            )

            if not (homes % 100):
                print " %d..." % (homes,)

    print "Done."
    print ""

    print "Calendar totals:"
    print " Calendar homes: %d" % (homes,)
    print " Calendars: %d" % (calendars,)
    print " Events: %d" % (resources,)
    print ""


def anonymizeData(directoryMap, data):
    vobj = vobject.readComponents(data).next()

    # Delete property from the top level
    try:
        for prop in vobj.contents['x-wr-calname']:
            prop.value = anonymize(prop.value)
    except KeyError:
        pass

    for comp in vobj.components():

        # Replace with anonymized CUAs:
        for propName in ('organizer', 'attendee'):
            try:
                for prop in list(comp.contents[propName]):
                    cua = prop.value
                    record = directoryMap.lookupCUA(cua)
                    if record is None:
                        # print "Can't find record for", cua
                        record = directoryMap.addRecord(cua=cua)
                        if record is None:
                            comp.remove(prop)
                            continue
                    prop.value = "urn:uuid:%s" % (record['guid'],)
                    if prop.params.has_key('X-CALENDARSERVER-EMAIL'):
                        prop.params['X-CALENDARSERVER-EMAIL'] = (record['email'],)
                    if prop.params.has_key('EMAIL'):
                        prop.params['EMAIL'] = (record['email'],)
                    prop.params['CN'] = (record['name'],)
            except KeyError:
                pass

        # Replace with anonymized text:
        for propName in ('summary', 'location', 'description'):
            try:
                for prop in comp.contents[propName]:
                    prop.value = anonymize(prop.value)
            except KeyError:
                pass

        # Replace with anonymized URL:
        try:
            for prop in comp.contents['url']:
                prop.value = "http://example.com/%s/" % (anonymize(prop.value),)
        except KeyError:
            pass

        # Remove properties:
        for propName in ('x-apple-dropbox', 'attach'):
            try:
                for prop in list(comp.contents[propName]):
                    comp.remove(prop)
            except KeyError:
                pass

    return vobj.serialize()


class DirectoryMap(object):

    def __init__(self, node):

        self.map = { }
        self.counts = {
            'users' : 0,
            'groups' : 0,
            'locations' : 0,
            'resources' : 0,
            'unknown' : 0,
        }

        self.strings = {
            'users' : ('Users', 'User'),
            'groups' : ('Groups', 'Group'),
            'locations' : ('Places', 'Place'),
            'resources' : ('Resources', 'Resource'),
        }

        print "Fetching records from directory: %s" % (node,)

        for internalType, (recordType, friendlyType) in self.strings.iteritems():
            print " %s..." % (internalType,)
            child = Popen(
                args = [
                    "/usr/bin/dscl", "-plist", node, "-readall",
                    "/%s" % (recordType,),
                    "GeneratedUID", "RecordName", "EMailAddress",
                ],
                stdout=PIPE, stderr=STDOUT,
            )
            output, error = child.communicate()

            if child.returncode:
                raise DirectoryError(error)
            else:
                records = plistlib.readPlistFromString(output)
                random.shuffle(records) # so we don't go alphabetically

                for record in records:
                    origGUID = record.get('dsAttrTypeStandard:GeneratedUID', [None])[0]
                    if not origGUID:
                        continue
                    origRecordNames = record['dsAttrTypeStandard:RecordName']
                    origEmails = record.get('dsAttrTypeStandard:EMailAddress', [])
                    self.addRecord(internalType=internalType, guid=origGUID,
                        names=origRecordNames, emails=origEmails)

        print "Done."
        print ""

    def addRecord(self, internalType="users", guid=None, names=None,
        emails=None, cua=None):

        if cua:
            keys = [self.cua2key(cua)]
            self.counts['unknown'] += 1
        else:
            keys = self.getKeys(guid, names, emails)

        if keys:
            self.counts[internalType] += 1
            count = self.counts[internalType]

            record = {
                'guid' : str(uuid.uuid4()),
                'name' : "%s %d" % (self.strings[internalType][1], count,),
                'recordName' : "%s%d" % (self.strings[internalType][1], count,),
                'email' : ("%s%d@example.com" % (internalType, count,)),
                'type' : self.strings[internalType][0],
                'cua' : cua,
            }
            for key in keys:
                self.map[key] = record
            return record
        else:
            return None


    def getKeys(self, guid, names, emails):
        keys = []
        if guid:
            keys.append(guid.lower())
        if names:
            for name in names:
                try:
                    name = name.encode('utf-8')
                    name = urllib.quote(name).lower()
                    keys.append(name)
                except:
                    # print "Failed to urllib.quote( ) %s. Skipping." % (name,)
                    pass
        if emails:
            for email in emails:
                email = email.lower()
                keys.append(email)
        return keys

    def cua2key(self, cua):
        key = cua.lower()

        if key.startswith("mailto:"):
            key = key[7:]

        elif key.startswith("urn:uuid:"):
            key = key[9:]

        elif (key.startswith("/") or key.startswith("http")):
            key = key.rstrip("/")
            key = key.split("/")[-1]

        return key

    def lookupCUA(self, cua):
        key = self.cua2key(cua)

        if key and self.map.has_key(key):
            return self.map[key]
        else:
            return None


    def printStats(self):
        print "Directory totals:"
        for internalType, (recordType, ignore) in self.strings.iteritems():
            print " %s: %d" % (recordType, self.counts[internalType])

        unknown = self.counts['unknown']
        if unknown:
            print " Principals not found in directory: %d" % (unknown,)


class DirectoryError(Exception):
    """
    Error trying to access dscl
    """

class DatabaseError(Exception):
    """
    Error trying to access sqlite3
    """





def anonymize(text):
    """
    Return a string whose value is the hex digest of text, repeated as needed
    to create a string of the same length as text.

    Useful for anonymizing strings in a deterministic manner.
    """
    if isinstance(text, unicode):
        try:
            text = text.encode('utf-8')
        except UnicodeEncodeError:
            print "Failed to anonymize:", text
            text = "Anonymize me!"
    h = hashlib.md5(text)
    h = h.hexdigest()
    l = len(text)
    return (h*((l/32)+1))[:-(32-(l%32))]



if __name__ == "__main__":
    main()
