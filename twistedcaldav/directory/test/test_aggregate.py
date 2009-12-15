##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.aggregate import AggregateDirectoryService

from twistedcaldav.directory.test.test_xmlfile import xmlFile

from twistedcaldav.directory.test.util import DirectoryTestCase
from twistedcaldav.directory.test.test_xmlfile import XMLFile

node1_prefix = "node1:"
node2_prefix = "node2:"


class XMLFile2(object):
    """
    Dummy values for accounts2.xml
    """
    recordTypes = set((
        DirectoryService.recordType_users,
        DirectoryService.recordType_groups,
        DirectoryService.recordType_locations,
        DirectoryService.recordType_resources
    ))

    users = {
        "wsanchez": { "password": "foo",  "guid": None, "addresses": () },
        "cdaboo"  : { "password": "bar",  "guid": None, "addresses": () },
        "dreid"   : { "password": "baz",  "guid": None, "addresses": () },
        "lecroy"  : { "password": "quux", "guid": None, "addresses": () },
    }
    users = {}    # XXX: fix accounts2.xml to match the above values


    groups = {
        "managers"   : { "guid": None, "addresses": (), "members": ((DirectoryService.recordType_users, "lecroy"),)                                        },
        "grunts"     : { "guid": None, "addresses": (), "members": ((DirectoryService.recordType_users, "wsanchez"),
                                                                    (DirectoryService.recordType_users, "cdaboo"),
                                                                    (DirectoryService.recordType_users, "dreid")) },
        "right_coast": { "guid": None, "addresses": (), "members": ((DirectoryService.recordType_users, "cdaboo"),)                                        },
        "left_coast" : { "guid": None, "addresses": (), "members": ((DirectoryService.recordType_users, "wsanchez"),
                                                                    (DirectoryService.recordType_users, "dreid"),
                                                                    (DirectoryService.recordType_users, "lecroy")) },
    }
    groups = {}   # XXX: fix accounts2.xml to match the above values

    locations = {}
    resources = {}


testServices = (
    (node1_prefix, XMLFile),
    (node2_prefix, XMLFile2)
)

class AggregatedDirectories(DirectoryTestCase):
    def _recordTypes(self):
        recordTypes = set()
        for prefix, testClass in testServices:
            for recordType in testClass.recordTypes:
                recordTypes.add(prefix + recordType)
        return recordTypes

    def _records(key):
        def get(self):
            records = {}
            for prefix, testClass in testServices:
                for record, info in getattr(testClass, key).iteritems():
                    info = dict(info)
                    info["prefix"] = prefix
                    info["members"] = tuple(
                        (t, prefix + s) for t, s in info.get("members", {})
                    )
                    records[prefix + record] = info
            return records
        return get

    recordTypes = property(_recordTypes)
    users = property(_records("users"))
    groups = property(_records("groups"))
    locations = property(_records("locations"))
    resources = property(_records("resources"))

    recordTypePrefixes = tuple(s[0] for s in testServices)

    def service(self):
        """
        Returns an IDirectoryService.
        """

        node1Service = XMLDirectoryService({'xmlFile' : xmlFile})
        node1Service.recordTypePrefix = node1_prefix

        fn, ext = xmlFile.basename().split(".")
        otherFile = xmlFile.sibling(fn+'2.'+ext)
        node2Service = XMLDirectoryService({'xmlFile': otherFile})
        node2Service.recordTypePrefix = node2_prefix

        return AggregateDirectoryService((node1Service, node2Service))

del DirectoryTestCase           # DirectoryTestCase is a bad test-citizen and
                                # subclasses TestCase even though it does not
                                # want to be discovered as such.
