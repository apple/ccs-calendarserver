##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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


class BaseResultsObserver(object):
    """
    A base class for an observer that gets passed results of tests.

    Supported messages:

    trace - tracing tool activity
    begin - beginning
    load - loading a test
    start - starting tests
    testFile - add a test file
    testSuite - add a test suite
    testResult - add a test result
    finish - tests completed
    """

    def __init__(self, manager):
        self.updateCalls()
        self.manager = manager


    def updateCalls(self):
        self._calls = {}


    def message(self, message, *args, **kwargs):

        callit = self._calls.get(message)

        if callit is not None:
            callit(*args, **kwargs)
