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

    class Foo (LoggingMixIn):
        def oops(self):
            self.log_error("Oops!")

C{Logger}s have namespaces, for which logging can be configured
independently.  Namespaces may be specified by passing in a
C{namespace} argument to L{Logger} when instantiating it, but if none
is given, the logger will derive its own namespace by using the module
name of the callable that instantiating it, or, in the case of a
L{LoggingMixIn}, by using the fully qualified name of the class.

In the first example above, the namespace would be C{some.module}, and
in the second example, it would be C{some.module.Foo}.
"""

__all__ = [
    "logLevels",
    "cmpLogLevels",
    "lowestLogLevel",
    "highestLogLevel",
    "logLevelForNamespace",
    "setLogLevelForNamespace",
    "clearLogLevels",
    "logLevelsByNamespace",
    "Logger",
    "LoggingMixIn",
    "InvalidLogLevelError",
]

import inspect

from twisted.python import log

from StringIO import StringIO

from twisted.internet.defer import succeed

from twisted.web2 import responsecode
from twisted.web2.dav.util import allDataFromStream
from twisted.web2.stream import MemoryStream

logLevels = (
    "debug",
    "info",
    "warn",
    "error",
)

logLevelIndexes = dict(zip(logLevels, xrange(0, len(logLevels))))

def cmpLogLevels(a, b):
    return cmp(logLevelIndexes[a], logLevelIndexes[b])

def lowestLogLevel(*levels):
    return sorted(levels, cmpLogLevels)[0]

def highestLogLevel(*levels):
    return sorted(levels, cmpLogLevels, reverse=True)[0]

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
    if level not in logLevels:
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
    logLevelsByNamespace[None] = "info"

logLevelsByNamespace = {}
clearLogLevels()

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

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.namespace)

    def emit(self, level, message, **kwargs):
        """
        Called internally to emit log messages at a given log level.
        """
        assert level in logLevels

        # FIXME: Filtering should be done by the log observer(s)
        if self.willLogAtLevel(level):
            log.msg(
                # FIXME: This formatting should be done by the log observer(s)
                "[%s#%s] %s" % (self.namespace, level, message),
                isError = (cmpLogLevels(level, "error") >= 0),
                level = level,
                namespace = self.namespace,
                **kwargs
            )

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
        return cmpLogLevels(self.level(), level) <= 0

    def logRequest(self, level, message, request, **kwargs):
        """
        Log an HTTP request.
        """

        assert level in logLevels

        if self.willLogAtLevel(level):
            iostr = StringIO()
            iostr.write("%s\n" % (message,))
            if hasattr(request, "clientproto"):
                protocol = "HTTP/%d.%d" % (request.clientproto[0], request.clientproto[1],)
            else:
                protocol = "HTTP/1.1"
            iostr.write("%s %s %s\n" % (request.method, request.uri, protocol,))
            for name, valuelist in request.headers.getAllRawHeaders():
                for value in valuelist:
                    # Do not log authorization details
                    if name not in ("Authorization",):
                        iostr.write("%s: %s\n" % (name, value))
                    else:
                        iostr.write("%s: xxxxxxxxx\n" % (name,))
            iostr.write("\n")
            
            # We need to play a trick with the request stream as we can only read it once. So we
            # read it, store the value in a MemoryStream, and replace the request's stream with that,
            # so the data can be read again.
            def _gotData(data):
                iostr.write(data)
                
                request.stream = MemoryStream(data)
                request.stream.doStartReading = None
            
                self.emit(level, iostr.getvalue(), **kwargs)

            d = allDataFromStream(request.stream)
            d.addCallback(_gotData)
            return d
        
        else:
            return succeed(None)
    
    def logResponse(self, level, message, response, **kwargs):
        """
        Log an HTTP request.
        """

        assert level in logLevels

        if self.willLogAtLevel(level):
            iostr = StringIO()
            iostr.write("%s\n" % (message,))
            code_message = responsecode.RESPONSES.get(response.code, "Unknown Status")
            iostr.write("HTTP/1.1 %s %s\n" % (response.code, code_message,))
            for name, valuelist in response.headers.getAllRawHeaders():
                for value in valuelist:
                    # Do not log authorization details
                    if name not in ("WWW-Authenticate",):
                        iostr.write("%s: %s\n" % (name, value))
                    else:
                        iostr.write("%s: xxxxxxxxx\n" % (name,))
            iostr.write("\n")
            
            # We need to play a trick with the response stream to ensure we don't mess it up. So we
            # read it, store the value in a MemoryStream, and replace the response's stream with that,
            # so the data can be read again.
            def _gotData(data):
                iostr.write(data)
                
                response.stream = MemoryStream(data)
                response.stream.doStartReading = None
            
                self.emit(level, iostr.getvalue(), **kwargs)
                
            d = allDataFromStream(response.stream)
            d.addCallback(_gotData)
            return d

class LoggingMixIn (object):
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

for level in logLevels:
    doc = """
    Emit a log message at log level C{%s}.
    @param message: The message to emit.
    """ % (level,)

    #
    # Attach methods to Logger
    #
    def log_emit(self, message, level=level, **kwargs):
        self.emit(level, message, **kwargs)

    log_emit.__doc__ = doc

    setattr(Logger, level, log_emit)

    del log_emit

    #
    # Attach methods to LoggingMixIn
    #
    def log_emit(self, message, level=level, **kwargs):
        self.logger.emit(level, message, **kwargs)

    log_emit.__doc__ = doc

    setattr(LoggingMixIn, "log_%s" % (level,), log_emit)

    del log_emit

del level

# Add some compatibility with twisted's log module
Logger.msg = Logger.info
Logger.err = Logger.error

##
# Errors
##

class InvalidLogLevelError (RuntimeError):
    def __init__(self, level):
        super(InvalidLogLevelError, self).__init__(str(level))
        self.level = level
