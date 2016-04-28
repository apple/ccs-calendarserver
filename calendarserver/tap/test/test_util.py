##
# Copyright (c) 2007-2016 Apple Inc. All rights reserved.
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

from calendarserver.tap.util import (
    MemoryLimitService, Stepper, verifyTLSCertificate, memoryForPID,
    AlertPoster, AMPAlertProtocol,
    AMPAlertSender
)

from twisted.internet.defer import succeed, inlineCallbacks
from twisted.internet.task import Clock
from twisted.protocols.amp import AMP
from twisted.python.filepath import FilePath
from twisted.test.testutils import returnConnected

from twistedcaldav.config import ConfigDict
from twistedcaldav.test.util import TestCase
from twistedcaldav.util import computeProcessCount

import os


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


    def test_memoryForPID(self):
        """
        Test that L{memoryForPID} returns a valid result.
        """

        memory = memoryForPID(os.getpid())
        self.assertNotEqual(memory, 0)



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



class PreFlightChecksTestCase(TestCase):
    """
    Verify that missing, empty, or bogus TLS Certificates are detected
    """

    def test_missingCertificate(self):
        success, _ignore_reason = verifyTLSCertificate(
            ConfigDict(
                {
                    "SSLCertificate": "missing",
                    "SSLKeychainIdentity": "missing",
                }
            )
        )
        self.assertFalse(success)


    def test_emptyCertificate(self):
        certFilePath = FilePath(self.mktemp())
        certFilePath.setContent("")
        success, _ignore_reason = verifyTLSCertificate(
            ConfigDict(
                {
                    "SSLCertificate": certFilePath.path,
                    "SSLKeychainIdentity": "missing",
                }
            )
        )
        self.assertFalse(success)


    def test_bogusCertificate(self):
        certFilePath = FilePath(self.mktemp())
        certFilePath.setContent("bogus")
        keyFilePath = FilePath(self.mktemp())
        keyFilePath.setContent("bogus")
        success, _ignore_reason = verifyTLSCertificate(
            ConfigDict(
                {
                    "SSLCertificate": certFilePath.path,
                    "SSLPrivateKey": keyFilePath.path,
                    "SSLAuthorityChain": "",
                    "SSLMethod": "SSLv3_METHOD",
                    "SSLCiphers": "ALL:!aNULL:!ADH:!eNULL:!LOW:!EXP:RC4+RSA:+HIGH:+MEDIUM",
                    "SSLKeychainIdentity": "missing",
                }
            )
        )
        self.assertFalse(success)



class AlertTestCase(TestCase):

    def test_secondsSinceLastPost(self):

        timestampsDir = self.mktemp()
        os.mkdir(timestampsDir)

        # Non existent timestamp file
        self.assertEquals(
            AlertPoster.secondsSinceLastPost("TestAlert", timestampsDirectory=timestampsDir, now=10),
            10
        )

        # Existing valid, past timestamp file
        AlertPoster.recordTimeStamp("TestAlert", timestampsDirectory=timestampsDir, now=5)
        self.assertEquals(
            AlertPoster.secondsSinceLastPost("TestAlert", timestampsDirectory=timestampsDir, now=12),
            7
        )

        # Existing valid, future timestamp file
        AlertPoster.recordTimeStamp("TestAlert", timestampsDirectory=timestampsDir, now=20)
        self.assertEquals(
            AlertPoster.secondsSinceLastPost("TestAlert", timestampsDirectory=timestampsDir, now=12),
            -8
        )

        # Existing invalid timestamp file
        dirFP = FilePath(timestampsDir)
        child = dirFP.child(".TestAlert.timestamp")
        child.setContent("not a number")
        self.assertEquals(
            AlertPoster.secondsSinceLastPost("TestAlert", timestampsDirectory=timestampsDir, now=12),
            12
        )


    def stubPostAlert(self, alertType, ignoreWithinSeconds, args):
        self.alertType = alertType
        self.ignoreWithinSeconds = ignoreWithinSeconds
        self.args = args


    def test_protocol(self):
        self.patch(AlertPoster, "postAlert", self.stubPostAlert)

        client = AMP()
        server = AMPAlertProtocol()
        pump = returnConnected(server, client)

        sender = AMPAlertSender(protocol=client)
        sender.sendAlert("alertType", ["arg1", "arg2"])
        pump.flush()

        self.assertEquals(self.alertType, "alertType")
        self.assertEquals(self.ignoreWithinSeconds, 0)
        self.assertEquals(self.args, ["arg1", "arg2"])
