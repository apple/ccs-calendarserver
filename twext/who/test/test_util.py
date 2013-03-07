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
Directory service utility tests.
"""

from twisted.trial import unittest
from twisted.python.constants import Names, NamedConstant
from twisted.python.constants import Flags, FlagConstant

from twext.who.idirectory import DirectoryServiceError
from twext.who.util import ConstantsContainer
from twext.who.util import uniqueResult, describe



class Tools(Names):
    hammer      = NamedConstant()
    screwdriver = NamedConstant()

    hammer.description      = "nail pounder"
    screwdriver.description = "screw twister"



class Instruments(Names):
    hammer = NamedConstant()
    chisel = NamedConstant()



class Switches(Flags):
    r = FlagConstant()
    g = FlagConstant()
    b = FlagConstant()

    r.description = "red"
    g.description = "green"
    b.description = "blue"

    black = FlagConstant()



class ConstantsContainerTest(unittest.TestCase):
    def test_conflict(self):
        constants = set((Tools.hammer, Instruments.hammer))
        self.assertRaises(ValueError, ConstantsContainer, constants)


    def test_attrs(self):
        constants = set((Tools.hammer, Tools.screwdriver, Instruments.chisel))
        container = ConstantsContainer(constants)

        self.assertEquals(container.hammer, Tools.hammer)
        self.assertEquals(container.screwdriver, Tools.screwdriver)
        self.assertEquals(container.chisel, Instruments.chisel)
        self.assertRaises(AttributeError, lambda: container.plugh)


    def test_iterconstants(self):
        constants = set((Tools.hammer, Tools.screwdriver, Instruments.chisel))
        container = ConstantsContainer(constants)

        self.assertEquals(
            set(container.iterconstants()),
            constants,
        )

    def test_lookupByName(self):
        constants = set((Instruments.hammer, Tools.screwdriver, Instruments.chisel))
        container = ConstantsContainer(constants)

        self.assertEquals(
            container.lookupByName("hammer"),
            Instruments.hammer,
        )
        self.assertEquals(
            container.lookupByName("screwdriver"),
            Tools.screwdriver,
        )
        self.assertEquals(
            container.lookupByName("chisel"),
            Instruments.chisel,
        )

        self.assertRaises(
            ValueError,
            container.lookupByName, "plugh",
        )



class UtilTest(unittest.TestCase):
    def test_uniqueResult(self):
        self.assertEquals(1, uniqueResult((1,)))
        self.assertRaises(DirectoryServiceError, uniqueResult, (1,2,3))

    def test_describe(self):
        self.assertEquals("nail pounder", describe(Tools.hammer))
        self.assertEquals("hammer", describe(Instruments.hammer))

    def test_describeFlags(self):
        self.assertEquals("blue", describe(Switches.b))
        self.assertEquals("red|green", describe(Switches.r|Switches.g))
        self.assertEquals("blue|black", describe(Switches.b|Switches.black))
