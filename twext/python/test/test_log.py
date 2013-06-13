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

from twisted.python import log as twistedLogging
from twisted.python.failure import Failure

from twext.python.log import LogLevel, InvalidLogLevelError
from twext.python.log import logLevelsByNamespace, logLevelForNamespace
from twext.python.log import setLogLevelForNamespace, clearLogLevels
from twext.python.log import pythonLogLevelMapping
from twext.python.log import Logger, LegacyLogger

from twistedcaldav.test.util import TestCase



defaultLogLevel = logLevelsByNamespace[None]



class TestLoggerMixIn(object):
    def emit(self, level, format=None, **kwargs):
        if False:
            print "*"*60
            print "level =", level
            print "format =", format
            for key, value in kwargs.items():
                print key, "=", value
            print "*"*60

        def observer(event):
            self.event = event

        twistedLogging.addObserver(observer)
        try:
            Logger.emit(self, level, format, **kwargs)
        finally:
            twistedLogging.removeObserver(observer)

        self.emitted = {
            "level" : level,
            "format": format,
            "kwargs": kwargs,
        }



class TestLogger(TestLoggerMixIn, Logger):
    pass



class TestLegacyLogger(TestLoggerMixIn, LegacyLogger):
    pass



class LogComposedObject(object):
    """
    Just a regular object.
    """
    log = TestLogger()

    def __init__(self, state=None):
        self.state = state


    def __str__(self):
        return "<LogComposedObject {state}>".format(state=self.state)



class Logging(TestCase):
    def setUp(self):
        super(Logging, self).setUp()
        clearLogLevels()


    def tearDown(self):
        super(Logging, self).tearDown()
        clearLogLevels()


    def test_repr(self):
        """
        repr() on Logger
        """
        namespace = "bleargh"
        log = Logger(namespace)
        self.assertEquals(repr(log), "<Logger {0}>".format(repr(namespace)))


    def test_namespace_default(self):
        """
        Default namespace is module name.
        """
        log = Logger()
        self.assertEquals(log.namespace, __name__)


    def test_namespace_attribute(self):
        """
        Default namespace for classes using L{Logger} as a descriptor is the
        class name they were retrieved from.
        """
        obj = LogComposedObject()
        self.assertEquals(obj.log.namespace,
                          "twext.python.test.test_log.LogComposedObject")
        self.assertEquals(LogComposedObject.log.namespace,
                          "twext.python.test.test_log.LogComposedObject")
        self.assertIdentical(LogComposedObject.log.source, LogComposedObject)
        self.assertIdentical(obj.log.source, obj)
        self.assertIdentical(Logger().source, None)


    def test_sourceAvailableForFormatting(self):
        """
        On instances that have a L{Logger} class attribute, the C{log_source} key
        is available to format strings.
        """
        obj = LogComposedObject("hello")
        log = obj.log
        log.error("Hello, {log_source}.")

        self.assertIn("log_source", log.event)
        self.assertEquals(log.event["log_source"], obj)

        stuff = log.formatEvent(log.event)
        self.assertIn("Hello, <LogComposedObject hello>.", stuff)


    def test_basic_Logger(self):
        """
        Test that log levels and messages are emitted correctly for
        Logger.
        """
        # FIXME:Need a basic test like this for logger attached to a class.
        # At least: source should not be None in that case.

        for level in LogLevel.iterconstants():
            format = "This is a {level_name} message"
            message = format.format(level_name=level.name)

            log = TestLogger()
            method = getattr(log, level.name)
            method(format, junk=message, level_name=level.name)

            # Ensure that test_emit got called with expected arguments
            self.assertEquals(log.emitted["level"], level)
            self.assertEquals(log.emitted["format"], format)
            self.assertEquals(log.emitted["kwargs"]["junk"], message)

            if level >= log.level():
                self.assertEquals(log.event["log_format"], format)
                self.assertEquals(log.event["log_level"], level)
                self.assertEquals(log.event["log_namespace"], __name__)
                self.assertEquals(log.event["log_source"], None)

                self.assertEquals(log.event["logLevel"], pythonLogLevelMapping[level])

                self.assertEquals(log.event["junk"], message)

                # FIXME: this checks the end of message because we do formatting in emit()
                self.assertEquals(
                    log.formatEvent(log.event),
                    message
                )
            else:
                self.assertFalse(hasattr(log, "event"))


    def test_defaultFailure(self):
        """
        Test that log.failure() emits the right data.
        """
        log = TestLogger()
        try:
            raise RuntimeError("baloney!")
        except RuntimeError:
            log.failure("Whoops")

        #
        # log.failure() will cause trial to complain, so here we check that
        # trial saw the correct error and remove it from the list of things to
        # complain about.
        #
        errors = self.flushLoggedErrors(RuntimeError)
        self.assertEquals(len(errors), 1)

        self.assertEquals(log.emitted["level"], LogLevel.error)
        self.assertEquals(log.emitted["format"], "Whoops")


    def test_conflicting_kwargs(self):
        """
        Make sure that kwargs conflicting with args don't pass through.
        """
        log = TestLogger()

        log.warn(
            "*",
            log_format = "#",
            log_level = LogLevel.error,
            log_namespace = "*namespace*",
            log_source = "*source*",
        )

        # FIXME: Should conflicts log errors?

        self.assertEquals(log.event["log_format"], "*")
        self.assertEquals(log.event["log_level"], LogLevel.warn)
        self.assertEquals(log.event["log_namespace"], log.namespace)
        self.assertEquals(log.event["log_source"], None)


    def test_defaultLogLevel(self):
        """
        Default log level is used.
        """
        self.failUnless(logLevelForNamespace(None), defaultLogLevel)
        self.failUnless(logLevelForNamespace(""), defaultLogLevel)
        self.failUnless(logLevelForNamespace("rocker.cool.namespace"), defaultLogLevel)


    def test_logLevelWithName(self):
        """
        Look up log level by name.
        """
        for level in LogLevel.iterconstants():
            self.assertIdentical(LogLevel.levelWithName(level.name), level)


    def test_logLevelWithInvalidName(self):
        """
        You can't make up log level names.
        """
        bogus = "*bogus*"
        try:
            LogLevel.levelWithName(bogus)
        except InvalidLogLevelError as e:
            self.assertIdentical(e.level, bogus)
        else:
            self.fail("Expected InvalidLogLevelError.")


    def test_setLogLevel(self):
        """
        Setting and retrieving log levels.
        """
        setLogLevelForNamespace(None, LogLevel.error)
        setLogLevelForNamespace("twext.web2", LogLevel.debug)
        setLogLevelForNamespace("twext.web2.dav", LogLevel.warn)

        self.assertEquals(logLevelForNamespace(None                        ), LogLevel.error)
        self.assertEquals(logLevelForNamespace("twisted"                   ), LogLevel.error)
        self.assertEquals(logLevelForNamespace("twext.web2"                ), LogLevel.debug)
        self.assertEquals(logLevelForNamespace("twext.web2.dav"            ), LogLevel.warn)
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test"       ), LogLevel.warn)
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test1.test2"), LogLevel.warn)


    def test_setInvalidLogLevel(self):
        """
        Can't pass invalid log levels to setLogLevelForNamespace().
        """
        self.assertRaises(InvalidLogLevelError, setLogLevelForNamespace, "twext.web2", object())

        # Level must be a constant, not the name of a constant
        self.assertRaises(InvalidLogLevelError, setLogLevelForNamespace, "twext.web2", "debug")


    def test_clearLogLevel(self):
        """
        Clearing log levels.
        """
        setLogLevelForNamespace("twext.web2", LogLevel.debug)
        setLogLevelForNamespace("twext.web2.dav", LogLevel.error)

        clearLogLevels()

        self.assertEquals(logLevelForNamespace("twisted"                   ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2"                ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2.dav"            ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test"       ), defaultLogLevel)
        self.assertEquals(logLevelForNamespace("twext.web2.dav.test1.test2"), defaultLogLevel)


    def test_setLevelOnLogger(self):
        """
        Set level on the logger directly.
        """
        log = Logger()

        for level in (LogLevel.error, LogLevel.info):
            log.setLevel(level)
            self.assertIdentical(level, log.level())
            self.assertIdentical(level, logLevelForNamespace(log.namespace))


    def test_logInvalidLogLevel(self):
        """
        Test passing in a bogus log level to C{emit()}.
        """
        log = TestLogger()

        log.emit("*bogus*")

        errors = self.flushLoggedErrors(InvalidLogLevelError)
        self.assertEquals(len(errors), 1)


    def test_formatEvent(self):
        """
        Test formatting.
        """
        def formatEvent(log_format, **event):
            event["log_format"] = log_format
            result = Logger.formatEvent(event)
            self.assertIdentical(type(result), unicode) # Always returns unicode
            return result

        self.assertEquals("", formatEvent(""))
        self.assertEquals("abc", formatEvent("{x}", x="abc"))
        self.assertEquals(u'S\xe1nchez', formatEvent("S\xc3\xa1nchez")) # bytes->unicode
        self.assertIn("Unable to format event", formatEvent("S\xe1nchez")) # Non-UTF-8 bytes


    def test_legacy_msg(self):
        """
        Test LegacyLogger's log.msg()
        """
        log = TestLegacyLogger()

        message = "Hi, there."
        kwargs = { "foo": "bar", "obj": object() }

        log.msg(message, **kwargs)

        self.assertIdentical(log.emitted["level"], LogLevel.info)
        self.assertEquals(log.emitted["format"], message)

        for key, value in kwargs.items():
            self.assertIdentical(log.emitted["kwargs"][key], value)

        log.msg(foo="")

        self.assertIdentical(log.emitted["level"], LogLevel.info)
        self.assertIdentical(log.emitted["format"], None)


    def test_legacy_err_implicit(self):
        """
        Test LegacyLogger's log.err() capturing the in-flight exception.
        """
        log = TestLegacyLogger()

        exception = RuntimeError("Oh me, oh my.")
        kwargs = { "foo": "bar", "obj": object() }

        try:
            raise exception
        except RuntimeError:
            log.err(**kwargs)

        self.legacy_err(log, kwargs, None, exception)


    def test_legacy_err_exception(self):
        """
        Test LegacyLogger's log.err() with a given exception.
        """
        log = TestLegacyLogger()

        exception = RuntimeError("Oh me, oh my.")
        kwargs = { "foo": "bar", "obj": object() }
        why = "Because I said so."

        try:
            raise exception
        except RuntimeError as e:
            log.err(e, why, **kwargs)

        self.legacy_err(log, kwargs, why, exception)


    def test_legacy_err_failure(self):
        """
        Test LegacyLogger's log.err() with a given L{Failure}.
        """
        log = TestLegacyLogger()

        exception = RuntimeError("Oh me, oh my.")
        kwargs = { "foo": "bar", "obj": object() }
        why = "Because I said so."

        try:
            raise exception
        except RuntimeError:
            log.err(Failure(), why, **kwargs)

        self.legacy_err(log, kwargs, why, exception)


    def test_legacy_err_bogus(self):
        """
        Test LegacyLogger's log.err() with a bogus argument.
        """
        log = TestLegacyLogger()

        exception = RuntimeError("Oh me, oh my.")
        kwargs = { "foo": "bar", "obj": object() }
        why = "Because I said so."
        bogus = object()

        try:
            raise exception
        except RuntimeError:
            log.err(bogus, why, **kwargs)

        errors = self.flushLoggedErrors(exception.__class__)
        self.assertEquals(len(errors), 0)

        self.assertIdentical(log.emitted["level"], LogLevel.error)
        self.assertEquals(log.emitted["format"], repr(bogus))
        self.assertIdentical(log.emitted["kwargs"]["why"], why)

        for key, value in kwargs.items():
            self.assertIdentical(log.emitted["kwargs"][key], value)


    def legacy_err(self, log, kwargs, why, exception):
        #
        # log.failure() will cause trial to complain, so here we check that
        # trial saw the correct error and remove it from the list of things to
        # complain about.
        #
        errors = self.flushLoggedErrors(exception.__class__)
        self.assertEquals(len(errors), 1)

        self.assertIdentical(log.emitted["level"], LogLevel.error)
        self.assertEquals(log.emitted["format"], None)
        self.assertIdentical(log.emitted["kwargs"]["failure"].__class__, Failure)
        self.assertIdentical(log.emitted["kwargs"]["failure"].value, exception)
        self.assertIdentical(log.emitted["kwargs"]["why"], why)

        for key, value in kwargs.items():
            self.assertIdentical(log.emitted["kwargs"][key], value)
