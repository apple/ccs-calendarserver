# -*- test-case-name: contrib.performance.loadtest.test_templates -*-
##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
#
##
"""
Tests for loadtest.templates
"""

from twisted.trial.unittest import TestCase

from contrib.performance.loadtest.templates import eventTemplate, alarmTemplate, taskTemplate

"""
ensure they're all comps
and that they are all vcalendars
with the right prodid and calscale and version
and that they have the corresponding component
and that each comp has its required properties
and that they are all v***

"""

class TemplateTests(TestCase):


    def assertTemplateIs(self, component, ):
        pass

    def test_components(self):


    def test_eventTemplate(self):
        runTests(eventTemplate, component_name="VEVENT", required="")
