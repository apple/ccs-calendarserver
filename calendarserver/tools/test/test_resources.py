##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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


try:
    from calendarserver.tools.resources import migrateResources
    from twisted.internet.defer import inlineCallbacks, succeed
    from twistedcaldav.directory.directory import DirectoryService
    from twistedcaldav.test.util import TestCase
    import dsattributes
    strGUID = dsattributes.kDS1AttrGeneratedUID
    strName = dsattributes.kDS1AttrDistinguishedName
    RUN_TESTS = True
except ImportError:
    RUN_TESTS = False



if RUN_TESTS:
    class StubDirectoryRecord(object):

        def __init__(self, recordType, guid=None, shortNames=None, fullName=None):
            self.recordType = recordType
            self.guid = guid
            self.shortNames = shortNames
            self.fullName = fullName


    class StubDirectoryService(object):

        def __init__(self, augmentService):
            self.records = {}
            self.augmentService = augmentService

        def recordWithGUID(self, guid):
            return None

        def createRecords(self, data):
            for recordType, recordData in data:
                guid = recordData["guid"]
                record = StubDirectoryRecord(recordType, guid=guid,
                    shortNames=recordData['shortNames'],
                    fullName=recordData['fullName'])
                self.records[guid] = record

        def updateRecord(self, recordType, guid=None, shortNames=None,
            fullName=None):
            pass


    class StubAugmentRecord(object):

        def __init__(self, guid=None):
            self.guid = guid
            self.autoSchedule = True


    class StubAugmentService(object):

        records = {}

        @classmethod
        def getAugmentRecord(cls, guid, recordType):
            if not cls.records.has_key(guid):
                record = StubAugmentRecord(guid=guid)
                cls.records[guid] = record
            return succeed(cls.records[guid])

        @classmethod
        def addAugmentRecords(cls, records):
            for record in records:
                cls.records[record.guid] = record
            return succeed(True)


    class MigrateResourcesTestCase(TestCase):

        @inlineCallbacks
        def test_migrateResources(self):

            data = {
                    dsattributes.kDSStdRecordTypeResources :
                    [
                        ['projector1', {
                            strGUID : '6C99E240-E915-4012-82FA-99E0F638D7EF',
                            strName : 'Projector 1'
                        }],
                        ['projector2', {
                            strGUID : '7C99E240-E915-4012-82FA-99E0F638D7EF',
                            strName : 'Projector 2'
                        }],
                    ],
                    dsattributes.kDSStdRecordTypePlaces :
                    [
                        ['office1', {
                            strGUID : '8C99E240-E915-4012-82FA-99E0F638D7EF',
                            strName : 'Office 1'
                        }],
                    ],
                }

            def queryMethod(sourceService, recordType, verbose=False):
                return data[recordType]

            directoryService = StubDirectoryService(StubAugmentService())
            yield migrateResources(None, directoryService, queryMethod=queryMethod)
            for guid, recordType in (
                ('6C99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_resources),
                ('7C99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_resources),
                ('8C99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_locations),
            ):
                self.assertTrue(guid in directoryService.records)
                record = directoryService.records[guid]
                self.assertEquals(record.recordType, recordType)

                self.assertTrue(guid in StubAugmentService.records)


            #
            # Add more to OD and re-migrate
            #

            data[dsattributes.kDSStdRecordTypeResources].append(
                ['projector3', {
                    strGUID : '9C99E240-E915-4012-82FA-99E0F638D7EF',
                    strName : 'Projector 3'
                }]
            )
            data[dsattributes.kDSStdRecordTypePlaces].append(
                ['office2', {
                    strGUID : 'AC99E240-E915-4012-82FA-99E0F638D7EF',
                    strName : 'Office 2'
                }]
            )

            yield migrateResources(None, directoryService, queryMethod=queryMethod)

            for guid, recordType in (
                ('6C99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_resources),
                ('7C99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_resources),
                ('9C99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_resources),
                ('8C99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_locations),
                ('AC99E240-E915-4012-82FA-99E0F638D7EF', DirectoryService.recordType_locations),
            ):
                self.assertTrue(guid in directoryService.records)
                record = directoryService.records[guid]
                self.assertEquals(record.recordType, recordType)

                self.assertTrue(guid in StubAugmentService.records)
