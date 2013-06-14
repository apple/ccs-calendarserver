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

"""
Classes and functions to do granular logging.

Example usage in a module::

    from twext.python.log import Logger
    log = Logger()

    ...

    log.debug("Got data: {data}.", data=data)

Or in a class::

    from twext.python.log import Logger

    class Foo(object):
        log = Logger()

        def oops(self, data):
            self.log.error("Oops! Invalid data from server: {data}", data=data)

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
# * Expose the default log observer (TheLogPublisher)
#  * Specifically, expose addObserver and removeObserver so one can register other observers
# * Change the default log observer to something non-legacy
#  * Register a legacy observer with Twisted's logging that forwards to this module
#  * Monkey patch logging in Twisted to use our LegacyLogger to sprinkle betterness everywhere
# * Move namespace settings to Filter class
#

__all__ = [
    "InvalidLogLevelError",
    "LogLevel",
    "logLevelForNamespace",
    "setLogLevelForNamespace",
    "clearLogLevels",
    "formatEvent",
    "Logger",
    "LegacyLogger",
    "ILogObserver",
    "ILegacyLogObserver",
    "LogPublisher",
    "PredicateResult",
    "ILogFilterPredicate",
    "FilteringLogObserver",
    "LogLevelFilterPredicate",
    "LegacyLogObserver",
    #"StandardIOObserver",
]

from sys import stdout, stderr
from string import Formatter
import inspect
import logging
import time

from zope.interface import Interface, implementer
from twisted.python.constants import NamedConstant, Names
from twisted.python.failure import Failure
from twisted.python.reflect import safe_str
from twisted.python.log import msg as twistedLogMessage
from twisted.python.log import addObserver, removeObserver
from twisted.python.log import ILogObserver as ILegacyLogObserver



#
# Log level definitions
#

class InvalidLogLevelError(Exception):
    """
    Someone tried to use a L{LogLevel} that is unknown to the logging system.
    """
    def __init__(self, level):
        """
        @param level: a L{LogLevel}
        """
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
        """
        @param name: the name of a L{LogLevel}

        @return: the L{LogLevel} with the specified C{name}
        """
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
    Sets the global log level for a logging namespace.

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
    Clears all global log levels to the default.
    """
    logLevelsByNamespace.clear()
    logLevelsByNamespace[None] = LogLevel.warn  # Default log level


logLevelsByNamespace = {}
clearLogLevels()



##
# Loggers
##

def formatEvent(event):
    """
    Formats an event as a L{unicode}, using the format in
    C{event["log_format"]}.  This implementation should never
    raise an exception; if the formatting cannot be done, the
    returned string will describe the event so that a useful
    message is emitted regardless.

    @param event: a logging event

    @return: a L{unicode}
    """
    try:
        format = event.get("log_format", None)

        if format is None:
            raise ValueError("No log format provided")

        # Make sure format is unicode.
        if type(format) is bytes:
            # If we get bytes, assume it's UTF-8 bytes
            format = format.decode("utf-8")
        else:
            # For anything else, assume we can just convert to unicode
            format = unicode(format)

        return formatWithCall(format, event)

    except BaseException as e:
        try:
            return formatUnformattableEvent(event, e)
        except:
            return u"MESSAGE LOST"


def formatUnformattableEvent(event, error):
    """
    Formats an event as a L{unicode} that describes the event
    generically and a formatting error.

    @param event: a logging event

    @param error: the formatting error

    @return: a L{unicode}
    """
    try:
        return (
            u"Unable to format event {event}: {error}"
            .format(event=event, error=error)
        )
    except BaseException as error:
        #
        # Yikes, something really nasty happened.
        #
        # Try to recover as much formattable data as possible;
        # hopefully at least the namespace is sane, which will
        # help you find the offending logger.
        #
        try:
            items = []

            for key, value in event.items():
                try:
                    items.append(u"{key} = ".format(key=key))
                except:
                    items.append(u"<UNFORMATTABLE KEY> = ")
                try:
                    items.append(u"{value}".format(value=value))
                except:
                    items.append(u"<UNFORMATTABLE VALUE>")

            text = ", ".join(items)
        except:
            text = ""

        return (
            u"MESSAGE LOST: Unformattable object logged: {error}\n"
            u"Recoverable data: {text}"
            .format(text=text)
        )



class Logger(object):
    """
    Logging object.
    """
    def __init__(self, namespace=None, source=None):
        """
        @param namespace: The namespace for this logger.  Uses a dotted
            notation, as used by python modules.  If not C{None}, then the name
            of the module of the caller is used.

        @param source: The object which is emitting events to this
            logger; this is automatically set on instances of a class
            if this L{Logger} is an attribute of that class.
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


    def emit(self, level, format=None, **kwargs):
        """
        Emit a log event to all log observers at the given level.

        @param level: a L{LogLevel}

        @param format: a message format using new-style (PEP 3101)
            formatting.  The logging event (which is a L{dict}) is
            used to render this format string.

        @param kwargs: additional keyword parameters to include with
            the event.
        """
        if level not in LogLevel.iterconstants(): # FIXME: Updated Twisted supports 'in' on constants container
            self.failure(
                "Got invalid log {invalidLevel} level in {logger}.emit().",
                Failure(InvalidLogLevelError(level)),
                invalidLevel = level,
                logger = self,
            )
            #level = LogLevel.error
            # FIXME: continue to emit?
            return

        event = kwargs
        event.update(
            log_logger    = self,
            log_level     = level,
            log_namespace = self.namespace,
            log_source    = self.source,
            log_format    = format,
            log_time      = time.time(),
        )

        self.publisher(event)


    def failure(self, format, failure=None, level=LogLevel.error, **kwargs):
        """
        Log an failure and emit a traceback.

        For example::

            try:
                frob(knob)
            except Exception:
                log.failure("While frobbing {knob}", knob=knob)

        or::

            d = deferred_frob(knob)
            d.addErrback(lambda f: log.failure, "While frobbing {knob}", f, knob=knob)

        @param format: a message format using new-style (PEP 3101)
            formatting.  The logging event (which is a L{dict}) is
            used to render this format string.

        @param failure: a L{Failure} to log.  If C{None}, a L{Failure} is
            created from the exception in flight.

        @param level: a L{LogLevel} to use.

        @param kwargs: additional keyword parameters to include with the
            event.
        """
        if failure is None:
            failure=Failure()

        self.emit(level, format, log_failure=failure, **kwargs)


    def level(self):
        """
        @return: the global log level for this logger's namespace.
        """
        return logLevelForNamespace(self.namespace)


    def setLevel(self, level):
        """
        Set the global log level for this logger's namespace.

        @param level: a L{LogLevel}
        """
        setLogLevelForNamespace(self.namespace, level)



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

        if isinstance(_stuff, Failure):
            self.emit(LogLevel.error, failure=_stuff, why=_why, isError=1, **kwargs)
        else:
            # We got called with an invalid _stuff.
            self.emit(LogLevel.error, repr(_stuff), why=_why, isError=1, **kwargs)



def bindEmit(level):
    doc = """
    Emit a log event at log level L{{{level}}}.

    @param format: a message format using new-style (PEP 3101)
        formatting.  The logging event (which is a L{{dict}}) is used to
        render this format string.

    @param kwargs: additional keyword parameters to include with the
        event.
    """.format(level=level.name)

    #
    # Attach methods to Logger
    #
    def log_emit(self, format=None, **kwargs):
        self.emit(level, format, **kwargs)

    log_emit.__doc__ = doc

    setattr(Logger, level.name, log_emit)

for level in LogLevel.iterconstants(): 
    bindEmit(level)

del level



#
# Observers
#

class ILogObserver(Interface):
    """
    An observer which can handle log events.
    """

    def __call__(event):
        """
        Log an event.

        @type event: C{dict} with C{str} keys.

        @param event: A dictionary with arbitrary keys as defined by
            the application emitting logging events, as well as keys
            added by the logging system, with are:
            ...
        """



@implementer(ILogObserver)
class LogPublisher(object):
    """
    I{ILogObserver} that fans out events to other observers.

    Keeps track of a set of L{ILogObserver} objects and forwards
    events to each.
    """
    log = Logger()

    def __init__(self, *observers):
        self._observers = set(observers)


    @property
    def observers(self):
        return frozenset(self._observers)


    def addObserver(self, observer):
        """
        Registers an observer with this publisher.

        @param observer: An L{ILogObserver} to add.
        """
        self._observers.add(observer)


    def removeObserver(self, observer):
        """
        Unregisters an observer with this publisher.

        @param observer: An L{ILogObserver} to remove.
        """
        self._observers.remove(observer)


    def __call__(self, event): 
        for observer in self.observers:
            try:
                observer(event)
            except:
                #
                # We have to remove the offending observer because
                # we're going to badmouth it to all of its friends
                # (other observers) and it might get offended and
                # raise again, causing an infinite loop.
                #
                self.removeObserver(observer)
                try:
                    self.log.failure("Observer {observer} raised an exception; removing.")
                    Failure().printTraceback()
                except:
                    pass
                finally:
                    self.addObserver(observer)



class PredicateResult(Names):
    """
    Predicate results.
    """
    yes   = NamedConstant() # Log this
    no    = NamedConstant() # Don't log this
    maybe = NamedConstant() # No opinion



class ILogFilterPredicate(Interface):
    """
    A predicate that determined whether an event should be logged.
    """

    def __call__(event):
        """
        Determine whether an event should be logged.

        @returns: a L{PredicateResult}.
        """



@implementer(ILogObserver)
class FilteringLogObserver(object):
    """
    L{ILogObserver} that wraps another L{ILogObserver}, but filters
    out events based on applying a series of L{ILogFilterPredicate}s.
    """

    def __init__(self, observer, predicates):
        """
        @param observer: an L{ILogObserver} to which this observer
            will forward events.

        @param predicates: an ordered iterable of predicates to apply
            to events before forwarding to the wrapped observer.
        """
        self.observer   = observer
        self.predicates = list(predicates)


    def shouldLogEvent(self, event):
        """
        Determine whether an event should be logged, based
        C{self.predicates}.

        @param event: an event
        """
        for predicate in self.predicates:
            result = predicate(event)
            if result == PredicateResult.yes:
                return True
            if result == PredicateResult.no:
                return False
            if result == PredicateResult.maybe:
                continue
            raise AssertionError("Unknown predicate result: {0!r}".format(result))
        return True


    def __call__(self, event):
        if self.shouldLogEvent(event):
            self.observer(event)



@implementer(ILogFilterPredicate)
class LogLevelFilterPredicate(object):
    """
    L{ILogFilterPredicate} that filters out events with a log level
    lower than the log level for the event's namespace.
    """

    def __call__(self, event):
        level     = event["log_level"]
        namespace = event["log_namespace"]

        if level < logLevelForNamespace(namespace):
            return PredicateResult.no

        return PredicateResult.maybe



@implementer(ILogObserver)
class LegacyLogObserver(object):
    """
    L{ILogObserver} that wraps an L{ILegacyLogObserver}.
    """

    def __init__(self, legacyObserver):
        """
        @param legacyObserver: an L{ILegacyLogObserver} to which this
            observer will forward events.
        """
        self.legacyObserver = legacyObserver

    
    def __call__(self, event): 
        prefix = "[{log_namespace}#{log_level.name}] ".format(**event)

        level = event["log_level"]

        #
        # Twisted's logging supports indicating a python log level, so let's
        # provide the equivalent to our logging levels.
        #
        if level in pythonLogLevelMapping:
            event["logLevel"] = pythonLogLevelMapping[level]

        # Format new style -> old style
        if event["log_format"]:
            #
            # Create an object that implements __str__() in order to
            # defer the work of formatting until it's needed by a
            # legacy log observer.
            #
            class LegacyFormatStub(object):
                def __str__(oself):
                    return formatEvent(event).encode("utf-8")

            event["format"] = prefix + "%(log_legacy)s"
            event["log_legacy"] = LegacyFormatStub()

        # log.failure() -> isError blah blah
        if "log_failure" in event:
            event["failure"] = event["log_failure"]
            event["isError"] = 1
            event["why"] = "{prefix}{message}".format(prefix=prefix, message=formatEvent(event))

        self.legacyObserver(**event)



#
# Utilities
#

class CallMapping(object):
    def __init__(self, submapping):
        self._submapping = submapping

    def __getitem__(self, key):
        callit = key.endswith(u"()")
        realKey = key[:-2] if callit else key
        value = self._submapping[realKey]
        if callit:
            value = value()
        return value


def formatWithCall(formatString, mapping):
    """
    Format a string like L{unicode.format}, but:

        - taking only a name mapping; no positional arguments

        - with the additional syntax that an empty set of parentheses
          correspond to a formatting item that should be called, and its result
          C{str}'d, rather than calling C{str} on the element directly as
          normal.

    For example::

        >>> formatWithCall("{string}, {function()}.",
        ...                dict(string="just a string",
        ...                     function=lambda: "a function"))
        'just a string, a function.'

    @param formatString: A PEP-3101 format string.
    @type formatString: L{unicode}

    @param mapping: A L{dict}-like object to format.

    @return: The string with formatted values interpolated.
    @rtype: L{unicode}
    """
    return unicode(
        formatter.vformat(formatString, (), CallMapping(mapping))
    )

formatter = Formatter()



#
# Default observers
# FIXME: ...
#
theLegacyLogObserver = LegacyLogObserver(twistedLogMessage)
theFilteredLogPublisher = LogPublisher(theLegacyLogObserver) # Add post-filtering observers here
theFilteringLogObserver = FilteringLogObserver(theFilteredLogPublisher, (LogLevelFilterPredicate(),))
Logger.publisher = LogPublisher(theFilteringLogObserver) # Add pre-filtering observers here



######################################################################
# FIXME: This may not be needed; look into removing it.

class StandardIOObserver(object):
    """
    (Legacy) log observer that writes to standard I/O.
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
