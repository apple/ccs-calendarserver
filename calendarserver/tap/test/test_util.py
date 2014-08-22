##
# Copyright (c) 2007-2014 Apple Inc. All rights reserved.
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

import OpenSSL
from calendarserver.tap.util import (
    MemoryLimitService, Stepper, PreFlightChecksStep
)
from twistedcaldav.util import computeProcessCount
from twistedcaldav.test.util import TestCase
from twisted.internet.task import Clock
from twisted.internet.defer import succeed, inlineCallbacks
from twisted.python.filepath import FilePath
from twistedcaldav.config import ConfigDict, ConfigurationError


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

            (2, 1, 2, 2, 2, 2),   # 2 cores, 2GB = 2
            (2, 1, 2, 2, 4, 2),   # 2 cores, 4GB = 2
            (2, 1, 2, 8, 6, 8),   # 8 cores, 6GB = 8
            (2, 1, 2, 8, 16, 8),  # 8 cores, 16GB = 8
        )

        for min, perCPU, perGB, cpu, mem, expected in data:
            mem *= (1024 * 1024 * 1024)

            self.assertEquals(
                expected,
                computeProcessCount(min, perCPU, perGB, cpuCount=cpu, memSize=mem)
            )



# Stub classes for MemoryLimitServiceTestCase

class StubProtocol(object):
    def __init__(self, transport):
        self.transport = transport



class StubProcess(object):
    def __init__(self, pid):
        self.pid = pid



class StubProcessMonitor(object):
    def __init__(self, processes, protocols):
        self.processes = processes
        self.protocols = protocols
        self.history = []


    def stopProcess(self, name):
        self.history.append(name)



class MemoryLimitServiceTestCase(TestCase):

    def test_checkMemory(self):
        """
        Set up stub objects to verify MemoryLimitService.checkMemory( )
        only stops the processes whose memory usage exceeds the configured
        limit, and skips memcached
        """
        data = {
            # PID : (name, resident memory-in-bytes, virtual memory-in-bytes)
            101: ("process #1", 10, 1010),
            102: ("process #2", 30, 1030),
            103: ("process #3", 50, 1050),
            99: ("memcached-Default", 10, 1010),
        }

        processes = []
        protocols = {}
        for pid, (name, _ignore_resident, _ignore_virtual) in data.iteritems():
            protocols[name] = StubProtocol(StubProcess(pid))
            processes.append(name)
        processMonitor = StubProcessMonitor(processes, protocols)
        clock = Clock()
        service = MemoryLimitService(processMonitor, 10, 15, True, reactor=clock)

        # For testing, use a stub implementation of memory-usage lookup
        def testMemoryForPID(pid, residentOnly):
            return data[pid][1 if residentOnly else 2]
        service._memoryForPID = testMemoryForPID

        # After 5 seconds, nothing should have happened, since the interval is 10 seconds
        service.startService()
        clock.advance(5)
        self.assertEquals(processMonitor.history, [])

        # After 7 more seconds, processes 2 and 3 should have been stopped since their
        # memory usage exceeds 10 bytes
        clock.advance(7)
        self.assertEquals(processMonitor.history, ['process #2', 'process #3'])

        # Now switch to looking at virtual memory, in which case all 3 processes
        # should be stopped
        service._residentOnly = False
        processMonitor.history = []
        clock.advance(10)
        self.assertEquals(processMonitor.history, ['process #1', 'process #2', 'process #3'])



#
# Tests for Stepper
#

class Step(object):

    def __init__(self, recordCallback, shouldFail):
        self._recordCallback = recordCallback
        self._shouldFail = shouldFail


    def stepWithResult(self, result):
        self._recordCallback(self.successValue, None)
        if self._shouldFail:
            1 / 0
        return succeed(result)


    def stepWithFailure(self, failure):
        self._recordCallback(self.errorValue, failure)
        if self._shouldFail:
            return failure



class StepOne(Step):
    successValue = "one success"
    errorValue = "one failure"



class StepTwo(Step):
    successValue = "two success"
    errorValue = "two failure"



class StepThree(Step):
    successValue = "three success"
    errorValue = "three failure"



class StepFour(Step):
    successValue = "four success"
    errorValue = "four failure"



class StepperTestCase(TestCase):

    def setUp(self):
        self.history = []
        self.stepper = Stepper()


    def _record(self, value, failure):
        self.history.append(value)


    @inlineCallbacks
    def test_allSuccess(self):
        self.stepper.addStep(
            StepOne(self._record, False)
        ).addStep(
            StepTwo(self._record, False)
        ).addStep(
            StepThree(self._record, False)
        ).addStep(
            StepFour(self._record, False)
        )
        result = (yield self.stepper.start("abc"))
        self.assertEquals(result, "abc")  # original result passed through
        self.assertEquals(
            self.history,
            ['one success', 'two success', 'three success', 'four success'])


    def test_allFailure(self):
        self.stepper.addStep(StepOne(self._record, True))
        self.stepper.addStep(StepTwo(self._record, True))
        self.stepper.addStep(StepThree(self._record, True))
        self.stepper.addStep(StepFour(self._record, True))
        self.failUnlessFailure(self.stepper.start(), ZeroDivisionError)
        self.assertEquals(
            self.history,
            ['one success', 'two failure', 'three failure', 'four failure'])


    @inlineCallbacks
    def test_partialFailure(self):
        self.stepper.addStep(StepOne(self._record, True))
        self.stepper.addStep(StepTwo(self._record, False))
        self.stepper.addStep(StepThree(self._record, True))
        self.stepper.addStep(StepFour(self._record, False))
        result = (yield self.stepper.start("abc"))
        self.assertEquals(result, None)  # original result is gone
        self.assertEquals(
            self.history,
            ['one success', 'two failure', 'three success', 'four failure'])


class PreFlightChecksStepTestCase(TestCase):
    """
    Verify that missing, empty, or bogus TLS Certificates are detected
    """

    @inlineCallbacks
    def test_missingCertificate(self):
        step = PreFlightChecksStep(
            ConfigDict(
                {
                    "SSLCertificate": "missing",
                }
            )
        )
        try:
            yield step.stepWithResult(None)
        except ConfigurationError as e:
            self.assertTrue("Missing" in str(e))
        else:
            self.fail("Did not raise ConfigurationError")


    @inlineCallbacks
    def test_emptyCertificate(self):
        certFilePath = FilePath(self.mktemp())
        certFilePath.setContent("")
        step = PreFlightChecksStep(
            ConfigDict(
                {
                    "SSLCertificate": certFilePath.path,
                }
            )
        )
        try:
            yield step.stepWithResult(None)
        except ConfigurationError as e:
            self.assertTrue("Empty" in str(e))
        else:
            self.fail("Did not raise ConfigurationError")


    @inlineCallbacks
    def test_bogusCertificate(self):
        certFilePath = FilePath(self.mktemp())
        certFilePath.setContent("bogus")
        keyFilePath = FilePath(self.mktemp())
        keyFilePath.setContent("bogus")
        step = PreFlightChecksStep(
            ConfigDict(
                {
                    "SSLCertificate": certFilePath.path,
                    "SSLPrivateKey": keyFilePath.path,
                    "SSLAuthorityChain": "",
                    "SSLMethod": "SSLv3_METHOD",
                    "SSLCiphers": "ALL:!aNULL:!ADH:!eNULL:!LOW:!EXP:RC4+RSA:+HIGH:+MEDIUM",
                }
            )
        )
        try:
            yield step.stepWithResult(None)
        except OpenSSL.SSL.Error:
            pass
        else:
            self.fail("Did not raise OpenSSL.SSL.Error")
