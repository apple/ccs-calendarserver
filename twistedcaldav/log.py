##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
Classes and functions to do better logging.

Example usage in a module:

    from twistedcaldav.log import Logger
    log = Logger()

    log.info("Blah blah")

Or in a class:

    from twistedcaldav.log import LoggingMixIn

    class Foo (object, LoggingMixIn):
        def oops(self):
            self.log_error("Oops!")
"""

__all__ = [
    "logLevels",
    "logLevelForNamespace",
    "setLogLevelForNamespace",
    "clearLogLevels",
    "Logger",
    "LoggingMixIn",
]

import inspect

from twisted.python import log

logLevels = (
    "debug",
    "info",
    "warn",
    "error",
)

logLevelIndexes = dict(zip(logLevels, xrange(0, len(logLevels))))

##
# Tools for manageing log levels
##

defaultLogLevel = "info"

logLevelsByNamespace = {}

def logLevelForNamespace(namespace):
    """
    @param namespace: a logging namespace
    @return: the log level for the given namespace.
    """
    if namespace in logLevelsByNamespace:
        return logLevelsByNamespace[namespace]

    segments = namespace.split(".")
    index = len(segments) - 1

    while index > 0:
        namespace = ".".join(segments[:index])
        if namespace in logLevelsByNamespace:
            return logLevelsByNamespace[namespace]
        index -= 1

    return defaultLogLevel

def setLogLevelForNamespace(namespace, level):
    """
    Sets the log level for a logging namespace.
    @param namespace: a logging namespace
    @param level: the log level for the given namespace.
    """
    assert level in logLevels
    logLevelsByNamespace[namespace] = level

def clearLogLevels():
    """
    Clears all log levels to the default.
    """
    logLevelsByNamespace.clear()

##
# Loggers
##

class Logger (object):
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

    def emit(self, level, message, **kwargs):
        """
        Called internally to emit log messages at a given log level.
        """
        assert level in logLevels
        log.msg(
            str(message),
            isError = (logLevelIndexes[level] >= logLevelIndexes["error"]),
            level = level,
            namespace = self.namespace,
            **kwargs
        )

class LoggingMixIn (object):
    """
    Mix-in class for logging methods.
    """
    def _getLogger(self):
        try:
            return self._logger
        except AttributeError:
            namespace = repr(self.__class__)[8:-2]

            assert repr(self.__class__)[:8] == "<class '"
            assert repr(self.__class__)[-2:] == "'>"
            assert namespace.find("'") == -1

            self._logger = Logger(namespace)

        return self._logger

    def _setLogger(self, value):
        self._logger = value

    logger = property(_getLogger, _setLogger)

for level in logLevels:
    doc = """
    Emit a log message at log level C{%s}.
    @param message: The message to emit.
    """ % (level,)

    #
    # Attach methods to Logger
    #
    def log_level(self, message, level=level, **kwargs):
        self.emit(level, message, **kwargs)

    log_level.__doc__ = doc

    setattr(Logger, level, log_level)

    #
    # Attach methods to LoggingMixIn
    #
    def log_level(self, message, level=level, **kwargs):
        self.logger.emit(level, message, **kwargs)

    log_level.__doc__ = doc

    setattr(LoggingMixIn, "log_%s" % (level,), log_level)

del level, log_level

# Add some compatibility with twisted's log module
Logger.msg = Logger.info
Logger.err = Logger.error
