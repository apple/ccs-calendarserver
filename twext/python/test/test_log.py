##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

import logging

from twisted.python import log as twistedLogging

from twext.python.log import logLevelsByNamespace, logLevelForNamespace
from twext.python.log import setLogLevelForNamespace, clearLogLevels
from twext.python.log import logLevels, cmpLogLevels
from twext.python.log import pythonLogLevelForLevel, InvalidLogLevelError
from twext.python.log import Logger, LoggingMixIn

from twistedcaldav.test.util import TestCase

defaultLogLevel = logLevelsByNamespace[None]


class TestLogger (Logger):
    def __init__(self, namespace=None):
        super(TestLogger, self).__init__(namespace)

    def emit(self, level, message, **kwargs):
        def observer(eventDict):
            self.eventDict = eventDict

        twistedLogging.addObserver(observer)

        super(TestLogger, self).emit(level, message, **kwargs)

        twistedLogging.removeObserver(observer)

        self.emitted = {
            "level"  : level,
            "message": message,
            "kwargs" : kwargs,
        }

class LoggingEnabledObject (LoggingMixIn):
    pass

class Logging (TestCase):
    def setUp(self):
        super(Logging, self).setUp()
        clearLogLevels()

    def tearDown(self):
        super(Logging, self).tearDown()
        clearLogLevels()

    def test_cmpLogLevels(self):
        self.assertEquals(cmpLogLevels("info" , "error"), -1)
        self.assertEquals(cmpLogLevels("debug", "debug"),  0)
        self.assertEquals(cmpLogLevels("warn" , "debug"),  1)

    def test_pythonLogLevel(self):
        self.assertEquals(pythonLogLevelForLevel("debug"), logging.DEBUG)
        self.assertEquals(pythonLogLevelForLevel("info"), logging.INFO)
        self.assertEquals(pythonLogLevelForLevel("warn"), logging.WARNING)
        self.assertEquals(pythonLogLevelForLevel("error"), logging.ERROR)
        #self.assertEquals(pythonLogLevelForLevel("critical"), logging.CRITICAL)
        self.assertRaises(InvalidLogLevelError, pythonLogLevelForLevel, "-not-a-log-level-")

    def test_namespace_default(self):
        """
        Default namespace is module name.
        """
        log = Logger()
        self.assertEquals(log.namespace, __name__)

    def test_namespace_mixin(self):
        """
        Default namespace for classes using L{LoggingMixIn} is the class name.
        """
        object = LoggingEnabledObject()
        self.assertEquals(object.logger.namespace, "twext.python.test.test_log.LoggingEnabledObject")

    def test_basic_Logger(self):
        """
        Test that log levels and messages are emitted correctly for
        Logger.
        """
        for level in logLevels:
            message = "This is a %s message" % (level,)

            log = TestLogger()
            method = getattr(log, level)
            method(message, junk=message)

            # Ensure that test_emit got called with expected arguments
            self.assertEquals(log.emitted["level"], level)
            self.assertEquals(log.emitted["message"], message)
            self.assertEquals(log.emitted["kwargs"]["junk"], message)

            if log.willLogAtLevel(level):
                self.assertEquals(log.eventDict["level"], level)
                self.assertEquals(log.eventDict["logLevel"], pythonLogLevelForLevel(level))
                # FIXME: this checks the end of message because we do formatting in emit()
                self.assertEquals(log.eventDict["message"][0][-len(message):], message)
                self.assertEquals(log.eventDict["junk"], message)
            else:
                self.assertFalse(hasattr(log, "eventDict"))

    def test_basic_LoggingMixIn(self):
        """
        Test that log levels and messages are emitted correctly for
        LoggingMixIn.
        """
        for level in logLevels:
            message = "This is a %s message" % (level,)

            object = LoggingEnabledObject()
            object.logger = TestLogger()

            method = getattr(object, "log_" + level)
            method(message, junk=message)

            # Ensure that test_emit got called with expected arguments
            self.assertEquals(object.logger.emitted["level"], level)
            self.assertEquals(object.logger.emitted["message"], message)
            self.assertEquals(object.logger.emitted["kwargs"]["junk"], message)

            if object.logger.willLogAtLevel(level):
                self.assertEquals(object.logger.eventDict["level"], level)
                self.assertEquals(object.logger.eventDict["logLevel"], pythonLogLevelForLevel(level))
                # FIXME: this checks the end of message because we do formatting in emit()
                self.assertEquals(object.logger.eventDict["message"][0][-len(message):], message)
                self.assertEquals(object.logger.eventDict["junk"], message)
            else:
                self.assertFalse(hasattr(object.logger, "eventDict"))

    def test_conflicting_kwargs(self):
        """
        Make sure that conflicting kwargs don't pass through.
        """
        log = TestLogger()

        log.error("*", logLevel="*", namespace="boogers")
        self.assertEquals(log.eventDict["logLevel"], logging.ERROR)
        self.assertEquals(log.eventDict["namespace"], log.namespace)

    def test_defaultLogLevel(self):
        """
        Default log level is used.
        """
        self.failUnless(logLevelForNamespace("rocker.cool.namespace"), defaultLogLevel)

    def test_logLevel(self):
        """
        Setting and retrieving log levels.
        """
        setLogLevelForNamespace("twext.web2", "debug")
        setLogLevelForNamespace("twext.web2.dav", "error")

        self.assertEquals(logLevelForNamespace("twisted"                     ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2"                ), "debug")
        self.assertEquals(logLevelForNamespace("twext.web2.dav"            ), "error")
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test"       ), "error")
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test1.test2"), "error")

    def test_clearLogLevel(self):
        """
        Clearing log levels.
        """
        setLogLevelForNamespace("twext.web2", "debug")
        setLogLevelForNamespace("twext.web2.dav", "error")

        clearLogLevels()

        self.assertEquals(logLevelForNamespace("twisted"                     ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2"                ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2.dav"            ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test"       ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test1.test2"), defaultLogLevel)

    def test_willLogAtLevel(self):
        """
        willLogAtLevel()
        """
        log = Logger()

        for level in logLevels:
            if cmpLogLevels(level, log.level()) < 0:
                self.assertFalse(log.willLogAtLevel(level))
            else:
                self.assertTrue(log.willLogAtLevel(level))

    def test_logMethodTruthiness_Logger(self):
        """
        Logger's log level functions/methods have true/false
        value based on whether they will log.
        """
        log = Logger()

        for level in logLevels:
            enabled = getattr(log, level + "_enabled")
            if enabled:
                self.assertTrue(log.willLogAtLevel(level))
            else:
                self.assertFalse(log.willLogAtLevel(level))

    def test_logMethodTruthiness_LoggingMixIn(self):
        """
        LoggingMixIn's log level functions/methods have true/false
        value based on whether they will log.
        """
        object = LoggingEnabledObject()

        for level in logLevels:
            enabled = getattr(object, "log_" + level + "_enabled")
            if enabled:
                self.assertTrue(object.logger.willLogAtLevel(level))
            else:
                self.assertFalse(object.logger.willLogAtLevel(level))
