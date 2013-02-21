##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Aggregate directory service tests
"""

from twext.who.aggregate import DirectoryService

#from twext.who.test import test_directory
from twext.who.test.test_xml import xmlService



class BaseTest(object):
    def service(self, subservices=()):
        return DirectoryService("xyzzy", subservices)

    def xmlService(self, xmlData=None):
        return xmlService(self.mktemp(), xmlData)



#class DirectoryServiceTest(BaseTest, test_directory.DirectoryServiceTest):
#    pass
