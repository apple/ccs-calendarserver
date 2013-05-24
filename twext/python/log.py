##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
from __future__ import print_function

"""
Classes and functions to do granular logging.

Example usage in a module:

    from twext.python.log import Logger
    log = Logger()

    log.info("Blah blah")

Or in a class:

    from twext.python.log import LoggingMixIn

    class Foo(LoggingMixIn):
        def oops(self):
            self.log_error("Oops!")

C{Logger}s have namespaces, for which logging can be configured independently.
Namespaces may be specified by passing in a C{namespace} argument to L{Logger}
when instantiating it, but if none is given, the logger will derive its own
namespace by using the module name of the callable that instantiated it, or, in
the case of a class using L{LoggingMixIn}, by using the fully qualified name of
the class.

In the first example above, the namespace would be C{some.module}, and in the
second example, it would be C{some.module.Foo}.
"""

#
# TODO List:
#
# * TwistedCompatibleLogger.err is setting isError=0 until we fix our callers
#
# * Get rid of LoggingMixIn
#
# * Replace method argument with format argument
#

__all__ = [
    "LogLevel",
    "logLevelForNamespace",
    "setLogLevelForNamespace",
    "clearLogLevels",
    "logLevelsByNamespace",
    "Logger",
    "LoggingMixIn",
    "InvalidLogLevelError",
    "StandardIOObserver",
]

from sys import stdout, stderr

import inspect
import logging

from twisted.python.constants import NamedConstant, Names
from twisted.python.failure import Failure
from twisted.python.reflect import safe_str
from twisted.python.log import msg as twistedLogMessage
from twisted.python.log import addObserver, removeObserver



class LogLevel(Names):
    debug = NamedConstant()
    info  = NamedConstant()
    warn  = NamedConstant()
    error = NamedConstant()

    @classmethod
    def levelWithName(cls, name):
        try:
            return cls.lookupByName(name)
        except ValueError:
            raise InvalidLogLevelError(name)



#
# Mappings to Python's logging module
#
pythonLogLevelMapping = {
    LogLevel.debug   : logging.DEBUG,
    LogLevel.info    : logging.INFO,
    LogLevel.warn    : logging.WARNING,
    LogLevel.error   : logging.ERROR,
   #LogLevel.critical: logging.CRITICAL,
}



##
# Tools for managing log levels
##

def logLevelForNamespace(namespace):
    """
    @param namespace: a logging namespace, or C{None} to set the
        default log level.
    @return: the log level for the given namespace.
    """
    if not namespace:
        return logLevelsByNamespace[None]

    if namespace in logLevelsByNamespace:
        return logLevelsByNamespace[namespace]

    segments = namespace.split(".")
    index = len(segments) - 1

    while index > 0:
        namespace = ".".join(segments[:index])
        if namespace in logLevelsByNamespace:
            return logLevelsByNamespace[namespace]
        index -= 1

    return logLevelsByNamespace[None]


def setLogLevelForNamespace(namespace, level):
    """
    Sets the log level for a logging namespace.
    @param namespace: a logging namespace
    @param level: the log level for the given namespace.
    """
    if level not in LogLevel.iterconstants():
        raise InvalidLogLevelError(level)

    if namespace:
        logLevelsByNamespace[namespace] = level
    else:
        logLevelsByNamespace[None] = level


def clearLogLevels():
    """
    Clears all log levels to the default.
    """
    logLevelsByNamespace.clear()
    logLevelsByNamespace[None] = LogLevel.warn  # Default log level


logLevelsByNamespace = {}
clearLogLevels()



##
# Loggers
##

class Logger(object):
    """
    Logging object.
    """
    def __init__(self, namespace=None):
        """
        @param namespace: The namespace for this logger.  Uses a
            dotted notation, as used by python modules.  If not
            C{None}, then the name of the module of the caller
            is used.
        """
        if namespace is None:
            currentFrame = inspect.currentframe()
            callerFrame  = currentFrame.f_back
            callerModule = callerFrame.f_globals["__name__"]

            namespace = callerModule

        self.namespace = namespace


    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.namespace)


    def emit(self, level, message=None, **kwargs):
        """
        Called internally to emit log messages at a given log level.
        """
        assert level in LogLevel.iterconstants(), "Unknown log level: %r" % (level,)

        # FIXME: Filtering should be done by the log observer(s)
        if not self.willLogAtLevel(level):
            return

        kwargs["level"] = level
        kwargs["levelName"] = level.name
        kwargs["namespace"] = self.namespace

        #
        # Twisted's logging supports indicating a python log level, so let's
        # use the equivalent to our logging level.
        #
        if level in pythonLogLevelMapping:
            kwargs["logLevel"] = pythonLogLevelMapping[level]

        if message:
            kwargs["legacyMessage"] = message
            kwargs["format"] = "%(legacyMessage)s"

        prefix = "[%(namespace)s#%(levelName)s] "

        if "failure" in kwargs:
            # Handle unfortunate logic in twisted.log.textFromEventDict()
            # in which format is ignored if we have a failure and no why.
            why = kwargs.get("why", None)
            if not why:
                why = "Unhandled Error"
            kwargs["why"] = "%s%s" % (prefix % kwargs, why)

        if "format" in kwargs:
            kwargs["format"] = "%s%s" % (prefix, kwargs["format"])

        twistedLogMessage(**kwargs)


    def failure(self, failure=None, **kwargs):
        """
        Log a Failure.
        """
        if failure is None:
            failure=Failure()

        self.emit(LogLevel.error, failure=failure, isError=1, **kwargs)


    def level(self):
        """
        @return: the logging level for this logger's namespace.
        """
        return logLevelForNamespace(self.namespace)


    def setLevel(self, level):
        """
        Set the logging level for this logger's namespace.
        @param level: a logging level
        """
        setLogLevelForNamespace(self.namespace, level)


    def willLogAtLevel(self, level):
        """
        @param level: a logging level
        @return: C{True} if this logger will log at the given logging
            level.
        """
        return self.level() <= level



class TwistedCompatibleLogger(Logger):
    def msg(self, *message, **kwargs):
        if message:
            message = " ".join(map(safe_str, message))
        else:
            message = None
        return self.emit(LogLevel.info, message, **kwargs)


    def err(self, _stuff=None, _why=None, **kwargs):
        if _stuff is None:
            _stuff = Failure()
        elif isinstance(_stuff, Exception):
            _stuff = Failure(_stuff)

        # FIXME: We are setting isError=0 below to work around
        # existing bugs, should be =1.

        if isinstance(_stuff, Failure):
            self.emit(LogLevel.error, failure=_stuff, why=_why, isError=0, **kwargs)
        else:
            # We got called with an invalid _stuff.
            self.emit(LogLevel.error, repr(_stuff), why=_why, isError=0, **kwargs)



class LoggingMixIn(object):
    """
    Mix-in class for logging methods.
    """
    def _getLogger(self):
        try:
            return self._logger
        except AttributeError:
            self._logger = Logger(
                "%s.%s" % (
                    self.__class__.__module__,
                    self.__class__.__name__,
                )
            )

        return self._logger


    def _setLogger(self, value):
        self._logger = value

    logger = property(_getLogger, _setLogger)



def bindEmit(level):
    doc = """
    Emit a log message at log level C{%s}.
    @param message: The message to emit.
    """ % (level,)

    #
    # Attach methods to Logger
    #
    def log_emit(self, message=None, raiseException=None, **kwargs):
        self.emit(level, message, **kwargs)
        if raiseException:
            raise raiseException(message)

    def will_emit(self):
        return self.willLogAtLevel(level)

    log_emit.__doc__ = doc

    setattr(Logger, level.name, log_emit)
    setattr(Logger, level.name + "_enabled", property(will_emit))

    #
    # Attach methods to LoggingMixIn
    #
    def log_emit(self, message=None, raiseException=None, **kwargs):
        self.logger.emit(level, message, **kwargs)
        if raiseException:
            raise raiseException(message)

    def will_emit(self=log_emit):
        return self.logger.willLogAtLevel(level)

    log_emit.__doc__ = doc
    log_emit.enabled = will_emit

    setattr(LoggingMixIn, "log_" + level.name, log_emit)
    setattr(LoggingMixIn, "log_" + level.name + "_enabled", property(will_emit))


for level in LogLevel.iterconstants(): 
    bindEmit(level)
del level


##
# Errors
##

class InvalidLogLevelError(RuntimeError):
    def __init__(self, level):
        super(InvalidLogLevelError, self).__init__(str(level))
        self.level = level



##
# Observers
##

class StandardIOObserver(object):
    """
    Log observer that writes to standard I/O.
    """
    def emit(self, eventDict):
        text = None

        if eventDict["isError"]:
            output = stderr
            if "failure" in eventDict:
                text = eventDict["failure"].getTraceback()
        else:
            output = stdout

        if not text:
            text = " ".join([str(m) for m in eventDict["message"]]) + "\n"

        output.write(text)
        output.flush()


    def start(self):
        addObserver(self.emit)


    def stop(self):
        removeObserver(self.emit)
