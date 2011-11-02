##
# Copyright (c) 2007-2010 Apple Inc. All rights reserved.
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

from calendarserver.tap.util import computeProcessCount, directoryFromConfig
from twistedcaldav.test.util import TestCase
from twistedcaldav.config import config
from twistedcaldav.directory.augment import AugmentXMLDB

class ProcessCountTestCase(TestCase):

    def test_count(self):

        data = (
            # minimum, perCPU, perGB, cpu, memory (in GB), expected:
            (0, 1, 1, 0, 0, 0),
            (1, 2, 2, 0, 0, 1),
            (1, 2, 1, 1, 1, 1),
            (1, 2, 2, 1, 1, 2),
            (1, 2, 2, 2, 1, 2),
            (1, 2, 2, 1, 2, 2),
            (1, 2, 2, 2, 2, 4),
            (4, 1, 2, 8, 2, 4),
            (6, 2, 2, 2, 2, 6),
            (1, 2, 1, 4, 99, 8),

            (2, 1, 2, 2, 2, 2), # 2 cores, 2GB = 2
            (2, 1, 2, 2, 4, 2), # 2 cores, 4GB = 2
            (2, 1, 2, 8, 6, 8), # 8 cores, 6GB = 8
            (2, 1, 2, 8, 16, 8), # 8 cores, 16GB = 8
        )

        for min, perCPU, perGB, cpu, mem, expected in data:
            mem *= (1024 * 1024 * 1024)

            self.assertEquals(
                expected,
                computeProcessCount(min, perCPU, perGB, cpuCount=cpu, memSize=mem)
            )

class UtilTestCase(TestCase):

    def test_directoryFromConfig(self):
        """
        Ensure augments service is on by default
        """
        dir = directoryFromConfig(config)
        for service in dir._recordTypes.values():
            # all directory services belonging to the aggregate have
            # augmentService set to AugmentXMLDB
            if hasattr(service, "augmentService"):
                self.assertTrue(isinstance(service.augmentService, AugmentXMLDB))
