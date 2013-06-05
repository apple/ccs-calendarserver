# -*- test-case-name: twext.python.test.test_log-*-
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

    from twext.python.log import Logger

    class Foo(object):
        log = Logger()

        def oops(self):
            self.log.error("Oops!")

C{Logger}s have namespaces, for which logging can be configured independently.
Namespaces may be specified by passing in a C{namespace} argument to L{Logger}
when instantiating it, but if none is given, the logger will derive its own
namespace by using the module name of the callable that instantiated it, or, in
the case of a class, by using the fully qualified name of the class.

In the first example above, the namespace would be C{some.module}, and in the
second example, it would be C{some.module.Foo}.
"""

#
# TODO List:
#
# * Replace message argument with format argument
#

__all__ = [
    "InvalidLogLevelError",
    "LogLevel",
    "logLevelForNamespace",
    "setLogLevelForNamespace",
    "clearLogLevels",
    "Logger",
    "LegacyLogger",
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



#
# Log level definitions
#

class InvalidLogLevelError(RuntimeError):
    """
    Someone tried to use a L{LogLevel} that is unknown to the logging system.
    """
    def __init__(self, level):
        super(InvalidLogLevelError, self).__init__(str(level))
        self.level = level



class LogLevel(Names):
    """
    Constants denoting log levels.
    """
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



#
# Tools for managing log levels
#

def logLevelForNamespace(namespace):
    """
    @param namespace: a logging namespace, or C{None} for the default
        namespace.

    @return: the L{LogLevel} for the specified namespace.
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

    @param level: the L{LogLevel} for the given namespace.
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
    def __init__(self, namespace=None, source=None):
        """
        @param namespace: The namespace for this logger.  Uses a dotted
            notation, as used by python modules.  If not C{None}, then the name
            of the module of the caller is used.

        @param source: The object which is emitting messages to this logger;
            this is automatically set on instances of a class if this L{Logger}
            is an attribute of that class.
        """
        if namespace is None:
            currentFrame = inspect.currentframe()
            callerFrame  = currentFrame.f_back
            callerModule = callerFrame.f_globals["__name__"]

            namespace = callerModule

        self.namespace = namespace
        self.source = source


    def __get__(self, oself, type=None):
        """
        When used as a descriptor, i.e.::

            # athing.py
            class Something(object):
                log = Logger()
                def something(self):
                    self.log.info("Hello")

        a L{Logger}'s namespace will be set to the name of the class it is
        declared on, in this case, C{athing.Something}.
        """
        if oself is None:
            source = type
        else:
            source = oself

        return self.__class__(
            '.'.join([type.__module__, type.__name__]),
            source
        )


    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.namespace)


    def emit(self, level, message=None, **kwargs):
        """
        Emit a log message to all log observers at the given level.

        @param level: a L{LogLevel}

        @param message: a message

        @param kwargs: additional keyword parameters to include with the
            message.
        """
        if level not in LogLevel.iterconstants():
            raise InvalidLogLevelError(level)

        # FIXME: Filtering should be done by the log observer(s)
        if not self.willLogAtLevel(level):
            return

        kwargs.update(
            level = level, levelName = level.name,
            namespace = self.namespace, source = self.source,
        )

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


    def failure(self, failure=None, message=None, **kwargs):
        """
        Log a failure.

        @param failure: a L{Failure} to log.  If C{None}, a L{Failure} is
            created from the exception in flight.

        @param message: a message

        @param kwargs: additional keyword parameters to include with the
            message.
        """
        if failure is None:
            failure=Failure()

        self.emit(LogLevel.error, None, failure=failure, isError=1, why=message, **kwargs)


    def level(self):
        """
        @return: the log level for this logger's namespace.
        """
        return logLevelForNamespace(self.namespace)


    def setLevel(self, level):
        """
        Set the log level for this logger's namespace.

        @param level: a L{LogLevel}
        """
        setLogLevelForNamespace(self.namespace, level)


    def willLogAtLevel(self, level):
        """
        @param level: a L{LogLevel}

        @return: true if this logger will emit at the given log level,
            otherwise false.
        """
        return self.level() <= level



class LegacyLogger(Logger):
    """
    A L{Logger} that provides some compatibility with the L{twisted.python.log}
    module.
    """

    def msg(self, *message, **kwargs):
        """
        This method is API-compatible with L{twisted.python.log.msg} and exists
        for compatibility with that API.
        """
        if message:
            message = " ".join(map(safe_str, message))
        else:
            message = None
        return self.emit(LogLevel.info, message, **kwargs)


    def err(self, _stuff=None, _why=None, **kwargs):
        """
        This method is API-compatible with L{twisted.python.log.err} and exists
        for compatibility with that API.
        """
        if _stuff is None:
            _stuff = Failure()
        elif isinstance(_stuff, Exception):
            _stuff = Failure(_stuff)

        # FIXME: We are setting isError=0 below to work around
        # existing bugs, should be =1.

        if isinstance(_stuff, Failure):
            self.emit(LogLevel.error, failure=_stuff, why=_why, isError=1, **kwargs)
        else:
            # We got called with an invalid _stuff.
            self.emit(LogLevel.error, repr(_stuff), why=_why, isError=1, **kwargs)



def bindEmit(level):
    doc = """
    Emit a log message at log level L{%s}.

    @param message: a message

    @param kwargs: additional keyword parameters to include with the message.
    """ % (level.__class__.__name__,)

    #
    # Attach methods to Logger
    #
    def log_emit(self, message=None, **kwargs):
        self.emit(level, message, **kwargs)

    def will_emit(self):
        return self.willLogAtLevel(level)

    log_emit.__doc__ = doc

    setattr(Logger, level.name, log_emit)
    setattr(Logger, level.name + "_enabled", property(will_emit))

for level in LogLevel.iterconstants(): 
    bindEmit(level)

del level



#
# Observers
#

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
