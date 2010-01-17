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
Access logs.
"""

__all__ = [
    "DirectoryLogWrapperResource",
    "RotatingFileAccessLoggingObserver",
    "AMPCommonAccessLoggingObserver",
    "AMPLoggingFactory",
]

import datetime
import os
import time

from twisted.internet import protocol

from twisted.web2 import iweb
from twisted.web2.dav import davxml
from twisted.web2.log import BaseCommonAccessLoggingObserver
from twisted.web2.log import LogWrapperResource

from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.log import Logger

log = Logger()

class DirectoryLogWrapperResource(LogWrapperResource):
    
    def __init__(self, resource, directory):
        super(DirectoryLogWrapperResource, self).__init__(resource)
        
        self.directory = directory
        
    def getDirectory(self):
        return self.directory

class CommonAccessLoggingObserverExtensions(BaseCommonAccessLoggingObserver):
    """
    A base class for our extension to the L{BaseCommonAccessLoggingObserver}
    """

    def emit(self, eventDict):

        if eventDict.get('interface') is iweb.IRequest:

            request = eventDict['request']
            response = eventDict['response']
            loginfo = eventDict['loginfo']

            channel = request.chanRequest.channel
            if channel._inspection:
                channel._inspection.add("access_log")
    
            # Try to determine authentication and authorization identifiers
            uid = "-"
            if hasattr(request, "authnUser"):
                if isinstance(request.authnUser.children[0], davxml.HRef):
                    uidn = str(request.authnUser.children[0])
                    uidz = None
                    if hasattr(request, "authzUser") and str(request.authzUser.children[0]) != uidn:
                        uidz = str(request.authzUser.children[0])
                        
                    def convertUIDtoShortName(uid):
                        uid = uid.rstrip("/")
                        uid = uid[uid.rfind("/") + 1:]
                        record = request.site.resource.getDirectory().recordWithGUID(uid)
                        if record:
                            if record.recordType == DirectoryService.recordType_users:
                                return record.shortName
                            else:
                                return "(%s)%s" % (record.recordType, record.shortName,)
                        else:
                            return uid
                        
                    uidn = convertUIDtoShortName(uidn)
                    if uidz:
                        uidz = convertUIDtoShortName(uidz)
                        
                    if uidn and uidz:
                        uid = '"%s as %s"' % (uidn, uidz,)
                    else:
                        uid = uidn
    
            #
            # For some methods which basically allow you to tunnel a
            # custom request (eg. REPORT, POST), the method name
            # itself doesn't tell you much about what action is being
            # requested.  This allows a method to tack a submethod
            # attribute to the request, so we can provide a little
            # more detail here.
            #
            if config.EnableExtendedAccessLog and hasattr(request, "submethod"):
                method = "%s(%s)" % (request.method, request.submethod)
            else:
                method = request.method

            # Standard Apache access log fields
            format = (
                '%(host)s - %(uid)s [%(date)s]'
                ' "%(method)s %(uri)s HTTP/%(protocolVersion)s"'
                ' %(statusCode)s %(bytesSent)d'
                ' "%(referer)s" "%(userAgent)s"'
            )

            try:
                if config.EnableConnectionInheriting:
                    serverInstance = config.LogID
                else:
                    serverInstance = request.chanRequest.transport.server.port
            except AttributeError:
                serverInstance = "Unknown"
            if config.EnableExtendedAccessLog:
                
                formats = [
                    format,
                    # Performance monitoring extensions
                    'i=%(serverInstance)s t=%(timeSpent).1f or=%(outstandingRequests)s',
                ]
                if hasattr(request, "extendedLogItems"):
                    for k, v in request.extendedLogItems.iteritems():
                        k = str(k).replace('"', "%22")
                        v = str(v).replace('"', "%22")
                        if " " in v:
                            v = '"%s"' % (v,)
                        formats.append("%s=%s" % (k, v))

                fwdHeaders = request.headers.getRawHeaders("x-forwarded-for", "")
                if fwdHeaders:
                    forwardedFor = ",".join(fwdHeaders)
                    forwardedFor = forwardedFor.replace(" ", "")
                    formats.append("fwd=%(fwd)s")
                else:
                    forwardedFor = ""

                format = " ".join(formats)

            formatArgs = {
                "host"                : request.remoteAddr.host,
                "uid"                 : uid,
                "date"                : self.logDateString(response.headers.getHeader("date", 0)),
                "method"              : method,
                "uri"                 : request.uri.replace('"', "%22"),
                "protocolVersion"     : ".".join(str(x) for x in request.clientproto),
                "statusCode"          : response.code,
                "bytesSent"           : loginfo.bytesSent,
                "referer"             : request.headers.getHeader("referer", "-"),
                "userAgent"           : request.headers.getHeader("user-agent", "-"),
                "serverInstance"      : serverInstance,
                "timeSpent"           : (time.time() - request.initTime) * 1000,
                "outstandingRequests" : request.chanRequest.channel.factory.outstandingRequests,
                "outstandingRequests" : request.chanRequest.channel.factory.outstandingRequests,
                "fwd"                 : forwardedFor,
            }
            self.logMessage(format % formatArgs)

        elif "overloaded" in eventDict:
            overloaded = eventDict.get("overloaded")
            format = '%(host)s - - [%(date)s] "???" 503 0 "-" "-"'
            formatArgs = {
                "host": overloaded.transport.hostname,
                "date": self.logDateString(time.time()),
            }
            if config.EnableExtendedAccessLog:
                format += " i=%(serverInstance)s t=0.0 or=%(outstandingRequests)s"
                formatArgs["serverInstance"] = overloaded.transport.server.port
                formatArgs["outstandingRequests"] = overloaded.outstandingRequests
            self.logMessage(format % formatArgs)

class RotatingFileAccessLoggingObserver(CommonAccessLoggingObserverExtensions):
    """
    Class to do 'apache' style access logging to a rotating log file. The log
    file is rotated after midnight each day.
    """

    def __init__(self, logpath):
        self.logpath = logpath

    def logMessage(self, message, allowrotate=True):
        """
        Log a message to the file and possibly rotate if date has changed.

        @param message: C{str} for the message to log.
        @param allowrotate: C{True} if log rotate allowed, C{False} to log to current file
            without testing for rotation.
        """

        if self.shouldRotate() and allowrotate:
            self.flush()
            self.rotate()
        self.f.write(message + '\n')

    def start(self):
        """
        Start logging. Open the log file and log an 'open' message.
        """

        super(RotatingFileAccessLoggingObserver, self).start()
        self._open()
        self.logMessage("Log opened - server start: [%s]." % (datetime.datetime.now().ctime(),))

    def stop(self):
        """
        Stop logging. Close the log file and log an 'open' message.
        """

        self.logMessage("Log closed - server stop: [%s]." % (datetime.datetime.now().ctime(),), False)
        super(RotatingFileAccessLoggingObserver, self).stop()
        self._close()

    def _open(self):
        """
        Open the log file.
        """

        self.f = open(self.logpath, 'a', 1)
        self.lastDate = self.toDate(os.stat(self.logpath)[8])

    def _close(self):
        """
        Close the log file.
        """

        self.f.close()

    def flush(self):
        """
        Flush the log file.
        """

        self.f.flush()

    def shouldRotate(self):
        """
        Rotate when the date has changed since last write
        """

        if config.RotateAccessLog:
            return self.toDate() > self.lastDate
        else:
            return False

    def toDate(self, *args):
        """
        Convert a unixtime to (year, month, day) localtime tuple,
        or return the current (year, month, day) localtime tuple.

        This function primarily exists so you may overload it with
        gmtime, or some cruft to make unit testing possible.
        """

        # primarily so this can be unit tested easily
        return time.localtime(*args)[:3]

    def suffix(self, tupledate):
        """
        Return the suffix given a (year, month, day) tuple or unixtime
        """

        try:
            return '_'.join(map(str, tupledate))
        except:
            # try taking a float unixtime
            return '_'.join(map(str, self.toDate(tupledate)))

    def rotate(self):
        """
        Rotate the file and create a new one.

        If it's not possible to open new logfile, this will fail silently,
        and continue logging to old logfile.
        """

        newpath = "%s.%s" % (self.logpath, self.suffix(self.lastDate))
        if os.path.exists(newpath):
            log.msg("Cannot rotate log file to %s because it already exists." % (newpath,))
            return
        self.logMessage("Log closed - rotating: [%s]." % (datetime.datetime.now().ctime(),), False)
        log.msg("Rotating log file to: %s" % (newpath,), system="Logging")
        self.f.close()
        os.rename(self.logpath, newpath)
        self._open()
        self.logMessage("Log opened - rotated: [%s]." % (datetime.datetime.now().ctime(),), False)


from twisted.protocols import amp


class LogMessage(amp.Command):
    arguments = [('message', amp.String())]


class AMPCommonAccessLoggingObserver(CommonAccessLoggingObserverExtensions):
    def __init__(self, socket):
        self.socket = socket
        self.protocol = None
        self._buffer = []

    def flushBuffer(self):
        if self._buffer:
            for msg in self._buffer:
                self.logMessage(msg)

    def start(self):
        super(AMPCommonAccessLoggingObserver, self).start()

        from twisted.internet import reactor

        def _gotProtocol(proto):
            self.protocol = proto
            self.flushBuffer()

        self.client = protocol.ClientCreator(reactor, amp.AMP)
        d = self.client.connectUNIX(self.socket)
        d.addCallback(_gotProtocol)

    def stop(self):
        super(AMPCommonAccessLoggingObserver, self).stop()
        self.client.disconnect()

    def logMessage(self, message):
        """
        Log a message to the remote AMP Protocol
        """
        if self.protocol is not None:
            # XXX: Yeah we're not waiting for anything to happen here.
            #      but we will log an error.
            d = self.protocol.callRemote(LogMessage, message=message)
            d.addErrback(log.err)
        else:
            self._buffer.append(message)


class AMPLoggingProtocol(amp.AMP):
    """
    A server side protocol for logging to the given observer.
    """

    def __init__(self, observer):
        self.observer = observer

        super(AMPLoggingProtocol, self).__init__()

    def logMessage(self, message):
        self.observer.logMessage(message)
        return {}

    LogMessage.responder(logMessage)


class AMPLoggingFactory(protocol.ServerFactory):
    def __init__(self, observer):
        self.observer = observer

    def doStart(self):
        self.observer.start()

    def doStop(self):
        self.observer.stop()

    def buildProtocol(self, addr):
        return AMPLoggingProtocol(self.observer)
