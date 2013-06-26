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
Tests for L{twext.python.launchd}.
"""

from twext.python.launchd import lib, ffi, LaunchDictionary

from twisted.trial.unittest import TestCase

alloc = lib.launch_data_alloc



class WrapperTests(TestCase):
    """
    Tests for all wrapper objects.
    """

    def setUp(self):
        """
        Assemble some test data structures.
        """
        self.testDict = ffi.gc(
            lib.launch_data_alloc(lib.LAUNCH_DATA_DICTIONARY),
            lib.launch_data_free
        )
        key1 = ffi.new("char[]", "alpha")
        val1 = lib.launch_data_new_string("alpha-value")
        key2 = ffi.new("char[]", "beta")
        val2 = lib.launch_data_new_string("beta-value")
        lib.launch_data_dict_insert(self.testDict, val1, key1)
        lib.launch_data_dict_insert(self.testDict, val2, key2)
        self.assertEquals(lib.launch_data_dict_get_count(self.testDict), 2) 


    def test_launchDictionaryKeys(self):
        """
        L{LaunchDictionary.keys} returns a key.
        """
        dictionary = LaunchDictionary(self.testDict)
        self.assertEquals(dictionary.keys(), [u"alpha", u"beta"])



