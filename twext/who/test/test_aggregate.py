##
# Copyright (c) 2013-2014 Apple Inc. All rights reserved.
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
Aggregate directory service tests.
"""

from twisted.python.components import proxyForInterface
from twisted.trial import unittest

from twext.who.idirectory import IDirectoryService, DirectoryConfigurationError
from twext.who.aggregate import DirectoryService
from twext.who.util import ConstantsContainer

from twext.who.test import test_directory, test_xml
from twext.who.test.test_xml import QueryMixIn, xmlService
from twext.who.test.test_xml import TestService as XMLTestService



class BaseTest(object):
    def service(self, services=None):
        if services is None:
            services = (self.xmlService(),)

        #
        # Make sure aggregate DirectoryService isn't making
        # implementation assumptions about the IDirectoryService
        # objects it gets.
        #
        services = tuple((
            proxyForInterface(IDirectoryService)(s)
            for s in services
        ))

        class TestService(DirectoryService, QueryMixIn):
            pass

        return TestService("xyzzy", services)


    def xmlService(self, xmlData=None, serviceClass=None):
        return xmlService(self.mktemp(), xmlData, serviceClass)



class DirectoryServiceBaseTest(BaseTest, test_xml.DirectoryServiceBaseTest):
    def test_repr(self):
        service = self.service()
        self.assertEquals(repr(service), "<TestService 'xyzzy'>")



class DirectoryServiceQueryTest(BaseTest, test_xml.DirectoryServiceQueryTest):
    pass



class DirectoryServiceImmutableTest(
    BaseTest,
    test_directory.BaseDirectoryServiceImmutableTest,
):
    pass



class AggregatedBaseTest(BaseTest):
    def service(self):
        class UsersDirectoryService(XMLTestService):
            recordType = ConstantsContainer((XMLTestService.recordType.user,))

        class GroupsDirectoryService(XMLTestService):
            recordType = ConstantsContainer((XMLTestService.recordType.group,))

        usersService = self.xmlService(
            testXMLConfigUsers,
            UsersDirectoryService
        )
        groupsService = self.xmlService(
            testXMLConfigGroups,
            GroupsDirectoryService
        )

        return BaseTest.service(self, (usersService, groupsService))



class DirectoryServiceAggregatedBaseTest(
    AggregatedBaseTest,
    DirectoryServiceBaseTest,
):
    pass



class DirectoryServiceAggregatedQueryTest(
    AggregatedBaseTest,
    test_xml.DirectoryServiceQueryTest,
):
    pass



class DirectoryServiceAggregatedImmutableTest(
    AggregatedBaseTest,
    test_directory.BaseDirectoryServiceImmutableTest,
):
    pass



class DirectoryServiceTests(BaseTest, unittest.TestCase):
    def test_conflictingRecordTypes(self):
        self.assertRaises(
            DirectoryConfigurationError,
            BaseTest.service, self,
            (self.xmlService(), self.xmlService(testXMLConfigUsers)),
        )



testXMLConfigUsers = """<?xml version="1.0" encoding="utf-8"?>

<directory realm="Users Realm">

  <record type="user">
    <uid>__wsanchez__</uid>
    <short-name>wsanchez</short-name>
    <short-name>wilfredo_sanchez</short-name>
    <full-name>Wilfredo Sanchez</full-name>
    <password>zehcnasw</password>
    <email>wsanchez@bitbucket.calendarserver.org</email>
    <email>wsanchez@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__glyph__</uid>
    <short-name>glyph</short-name>
    <full-name>Glyph Lefkowitz</full-name>
    <password>hpylg</password>
    <email>glyph@bitbucket.calendarserver.org</email>
    <email>glyph@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__sagen__</uid>
    <short-name>sagen</short-name>
    <full-name>Morgen Sagen</full-name>
    <password>negas</password>
    <email>sagen@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="user">
    <uid>__cdaboo__</uid>
    <short-name>cdaboo</short-name>
    <full-name>Cyrus Daboo</full-name>
    <password>suryc</password>
    <email>cdaboo@bitbucket.calendarserver.org</email>
  </record>

  <record type="user">
    <uid>__dre__</uid>
    <short-name>dre</short-name>
    <full-name>Andre LaBranche</full-name>
    <password>erd</password>
    <email>dre@bitbucket.calendarserver.org</email>
    <email>shared@example.com</email>
  </record>

  <record type="user">
    <uid>__exarkun__</uid>
    <short-name>exarkun</short-name>
    <full-name>Jean-Paul Calderone</full-name>
    <password>nucraxe</password>
    <email>exarkun@devnull.twistedmatrix.com</email>
  </record>

  <record type="user">
    <uid>__dreid__</uid>
    <short-name>dreid</short-name>
    <full-name>David Reid</full-name>
    <password>dierd</password>
    <email>dreid@devnull.twistedmatrix.com</email>
  </record>

  <record> <!-- type defaults to "user" -->
    <uid>__joe__</uid>
    <short-name>joe</short-name>
    <full-name>Joe Schmoe</full-name>
    <password>eoj</password>
    <email>joe@example.com</email>
  </record>

  <record> <!-- type defaults to "user" -->
    <uid>__alyssa__</uid>
    <short-name>alyssa</short-name>
    <full-name>Alyssa P. Hacker</full-name>
    <password>assyla</password>
    <email>alyssa@example.com</email>
  </record>

</directory>
"""


testXMLConfigGroups = """<?xml version="1.0" encoding="utf-8"?>

<directory realm="Groups Realm">

  <record type="group">
    <uid>__calendar-dev__</uid>
    <short-name>calendar-dev</short-name>
    <full-name>Calendar Server developers</full-name>
    <email>dev@bitbucket.calendarserver.org</email>
    <member-uid>__wsanchez__</member-uid>
    <member-uid>__glyph__</member-uid>
    <member-uid>__sagen__</member-uid>
    <member-uid>__cdaboo__</member-uid>
    <member-uid>__dre__</member-uid>
  </record>

  <record type="group">
    <uid>__twisted__</uid>
    <short-name>twisted</short-name>
    <full-name>Twisted Matrix Laboratories</full-name>
    <email>hack@devnull.twistedmatrix.com</email>
    <member-uid>__wsanchez__</member-uid>
    <member-uid>__glyph__</member-uid>
    <member-uid>__exarkun__</member-uid>
    <member-uid>__dreid__</member-uid>
    <member-uid>__dre__</member-uid>
  </record>

  <record type="group">
    <uid>__developers__</uid>
    <short-name>developers</short-name>
    <full-name>All Developers</full-name>
    <member-uid>__calendar-dev__</member-uid>
    <member-uid>__twisted__</member-uid>
    <member-uid>__alyssa__</member-uid>
  </record>

</directory>
"""
