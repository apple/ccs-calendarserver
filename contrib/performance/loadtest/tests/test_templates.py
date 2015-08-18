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


class TemplateTests(TestCase):
    def assertVCalendar(self, vcal):
        self.assertEqual(vcal.name(), 'VCALENDAR')
        self.assertEqual(vcal.propertyValue('VERSION'), '2.0')

    def test_eventTemplate(self):
        self.assertVCalendar(eventTemplate)
        vevent = eventTemplate.mainComponent()
        self.assertEqual(vevent.name(), 'VEVENT')

    def test_taskTemplate(self):
        self.assertVCalendar(taskTemplate)
        vtodo = taskTemplate.mainComponent()
        self.assertEqual(vtodo.name(), 'VTODO')

    def test_alarmTemplate(self):
        self.assertVCalendar(alarmTemplate)
        valarm = alarmTemplate.mainComponent()
        self.assertEqual(valarm.name(), 'VALARM')
        self.assertTrue(valarm.hasProperty('ACTION'))
        self.assertTrue(valarm.hasProperty('TRIGGER'))
