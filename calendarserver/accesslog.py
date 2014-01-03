##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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

import collections
import datetime
import json
import os
try:
    import psutil
except ImportError:
    psutil = None
from sys import platform
import time

from calendarserver.logAnalysis import getAdjustedMethodName, \
    getAdjustedClientName

from twext.python.log import Logger
from txweb2 import iweb
from txweb2.log import BaseCommonAccessLoggingObserver
from txweb2.log import LogWrapperResource

from twisted.internet import protocol, task
from twisted.protocols import amp

from twistedcaldav.config import config
from twistedcaldav.directory.directory import DirectoryService

from txdav.xml import element as davxml

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

        format = None
        formatArgs = None
        if eventDict.get("interface") is iweb.IRequest:

            request = eventDict["request"]
            response = eventDict["response"]
            loginfo = eventDict["loginfo"]

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
                        record = request.site.resource.getDirectory().recordWithUID(uid)
                        if record:
                            if record.recordType == DirectoryService.recordType_users:
                                return record.shortNames[0]
                            else:
                                return "(%s)%s" % (record.recordType, record.shortNames[0],)
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
            }

            # Add extended items to format and formatArgs
            if config.EnableExtendedAccessLog:
                format += ' i=%(serverInstance)s'
                formatArgs["serverInstance"] = config.LogID if config.LogID else "0"

                format += ' or=%(outstandingRequests)s'
                formatArgs["outstandingRequests"] = request.chanRequest.channel.factory.outstandingRequests

                # Tags for time stamps collected along the way - the first one in the list is the initial
                # time for request creation - we use that to track the entire request/response time
                nowtime = time.time()
                if config.EnableExtendedTimingAccessLog:
                    basetime = request.timeStamps[0][1]
                    request.timeStamps[0] = ("t", time.time(),)
                    for tag, timestamp in request.timeStamps:
                        format += " %s=%%(%s).1f" % (tag, tag,)
                        formatArgs[tag] = (timestamp - basetime) * 1000
                        if tag != "t":
                            basetime = timestamp
                    if len(request.timeStamps) > 1:
                        format += " t-log=%(t-log).1f"
                        formatArgs["t-log"] = (timestamp - basetime) * 1000
                else:
                    format += " t=%(t).1f"
                    formatArgs["t"] = (nowtime - request.timeStamps[0][1]) * 1000

                if hasattr(request, "extendedLogItems"):
                    for k, v in sorted(request.extendedLogItems.iteritems(), key=lambda x: x[0]):
                        k = str(k).replace('"', "%22")
                        v = str(v).replace('"', "%22")
                        if " " in v:
                            v = '"%s"' % (v,)
                        format += " %s=%%(%s)s" % (k, k,)
                        formatArgs[k] = v

                # Add the name of the XML error element for debugging purposes
                if hasattr(response, "error"):
                    format += " err=%(err)s"
                    formatArgs["err"] = response.error.qname()[1]

                fwdHeaders = request.headers.getRawHeaders("x-forwarded-for", "")
                if fwdHeaders:
                    # Limit each x-forwarded-header to 50 in case someone is
                    # trying to overwhelm the logs
                    forwardedFor = ",".join([hdr[:50] for hdr in fwdHeaders])
                    forwardedFor = forwardedFor.replace(" ", "")
                    format += " fwd=%(fwd)s"
                    formatArgs["fwd"] = forwardedFor

        elif "overloaded" in eventDict:
            overloaded = eventDict.get("overloaded")

            format = (
                '%(host)s - %(uid)s [%(date)s]'
                ' "%(method)s"'
                ' %(statusCode)s %(bytesSent)d'
                ' "%(referer)s" "%(userAgent)s"'
            )

            formatArgs = {
                "host"                : overloaded.transport.hostname,
                "uid"                 : "-",
                "date"                : self.logDateString(time.time()),
                "method"              : "???",
                "uri"                 : "",
                "protocolVersion"     : "",
                "statusCode"          : 503,
                "bytesSent"           : 0,
                "referer"             : "-",
                "userAgent"           : "-",
            }

            if config.EnableExtendedAccessLog:
                format += ' p=%(serverPort)s'
                formatArgs["serverPort"] = overloaded.transport.server.port

                format += ' or=%(outstandingRequests)s'
                formatArgs["outstandingRequests"] = overloaded.outstandingRequests

        # Write anything we got to the log and stats
        if format is not None:
            # sanitize output to mitigate log injection
            for k, v in formatArgs.items():
                if not isinstance(v, basestring):
                    continue
                v = v.replace("\r", "\\r")
                v = v.replace("\n", "\\n")
                v = v.replace("\"", "\\\"")
                formatArgs[k] = v

            formatArgs["type"] = "access-log"
            formatArgs["log-format"] = format
            self.logStats(formatArgs)



class RotatingFileAccessLoggingObserver(CommonAccessLoggingObserverExtensions):
    """
    Class to do "apache" style access logging to a rotating log file. The log
    file is rotated after midnight each day.

    This class also currently handles the collection of system and log statistics.
    """

    def __init__(self, logpath):
        self.logpath = logpath

        self.systemStats = None
        self.statsByMinute = []


    def accessLog(self, message, allowrotate=True):
        """
        Log a message to the file and possibly rotate if date has changed.

        @param message: C{str} for the message to log.
        @param allowrotate: C{True} if log rotate allowed, C{False} to log to current file
            without testing for rotation.
        """

        if self.shouldRotate() and allowrotate:
            self.flush()
            self.rotate()
        self.f.write(message + "\n")


    def start(self):
        """
        Start logging. Open the log file and log an "open" message.
        """

        super(RotatingFileAccessLoggingObserver, self).start()
        self._open()
        self.accessLog("Log opened - server start: [%s]." % (datetime.datetime.now().ctime(),))


    def stop(self):
        """
        Stop logging. Close the log file and log an "open" message.
        """

        self.accessLog("Log closed - server stop: [%s]." % (datetime.datetime.now().ctime(),), False)
        super(RotatingFileAccessLoggingObserver, self).stop()
        self._close()

        if self.systemStats is not None:
            self.systemStats.stop()


    def _open(self):
        """
        Open the log file.
        """

        self.f = open(self.logpath, "a", 1)
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
            return "_".join(map(str, tupledate))
        except:
            # try taking a float unixtime
            return "_".join(map(str, self.toDate(tupledate)))


    def rotate(self):
        """
        Rotate the file and create a new one.

        If it's not possible to open new logfile, this will fail silently,
        and continue logging to old logfile.
        """

        newpath = "%s.%s" % (self.logpath, self.suffix(self.lastDate))
        if os.path.exists(newpath):
            log.info("Cannot rotate log file to %s because it already exists." % (newpath,))
            return
        self.accessLog("Log closed - rotating: [%s]." % (datetime.datetime.now().ctime(),), False)
        log.info("Rotating log file to: %s" % (newpath,), system="Logging")
        self.f.close()
        os.rename(self.logpath, newpath)
        self._open()
        self.accessLog("Log opened - rotated: [%s]." % (datetime.datetime.now().ctime(),), False)


    def logStats(self, stats):
        """
        Update stats
        """

        if self.systemStats is None:
            self.systemStats = SystemMonitor()

        # Currently only storing stats for access log type
        if "type" not in stats or stats["type"] != "access-log":
            return

        currentStats = self.ensureSequentialStats()
        self.updateStats(currentStats, stats)

        if stats["type"] == "access-log":
            self.accessLog(stats["log-format"] % stats)


    def getStats(self):
        """
        Return the stats
        """

        if self.systemStats is None:
            self.systemStats = SystemMonitor()

        # The current stats
        currentStats = self.ensureSequentialStats()

        # Get previous minute details
        index = min(2, len(self.statsByMinute))
        if index > 0:
            previousMinute = self.statsByMinute[-index][1]
        else:
            previousMinute = self.initStats()

        # Do five minute aggregate
        fiveMinutes = self.initStats()
        index = min(6, len(self.statsByMinute))
        for i in range(-index, -1):
            stat = self.statsByMinute[i][1]
            self.mergeStats(fiveMinutes, stat)

        # Do one hour aggregate
        oneHour = self.initStats()
        index = min(61, len(self.statsByMinute))
        for i in range(-index, -1):
            stat = self.statsByMinute[i][1]
            self.mergeStats(oneHour, stat)

        printStats = {
            "System": self.systemStats.items,
            "Current": currentStats,
            "1 Minute": previousMinute,
            "5 Minutes": fiveMinutes,
            "1 Hour": oneHour,
        }
        return json.dumps(printStats)


    def ensureSequentialStats(self):
        """
        Make sure the list of timed stats is contiguous wrt time.
        """
        dtindex = int(time.time() / 60.0) * 60

        if len(self.statsByMinute) > 0:
            if self.statsByMinute[-1][0] != dtindex:
                oldindex = self.statsByMinute[-1][0]
                while oldindex != dtindex:
                    oldindex += 60
                    self.statsByMinute.append((oldindex, self.initStats(),))
        else:
            self.statsByMinute.append((dtindex, self.initStats(),))
        return self.statsByMinute[-1][1]


    def initStats(self):

        def initTimeHistogram():
            return {
                "<10ms": 0,
                "10ms<->100ms" : 0,
                "100ms<->1s"   : 0,
                "1s<->10s"     : 0,
                "10s<->30s"    : 0,
                "30s<->60s"    : 0,
                ">60s"         : 0,
                "Over 1s"      : 0,
                "Over 10s"     : 0,
            }

        return {
            "requests"   : 0,
            "method"     : collections.defaultdict(int),
            "method-t"   : collections.defaultdict(float),
            "uid"        : collections.defaultdict(int),
            "user-agent" : collections.defaultdict(int),
            "500"        : 0,
            "t"          : 0.0,
            "t-resp-wr"  : 0.0,
            "slots"      : 0,
            "T"          : initTimeHistogram(),
            "T-RESP-WR"  : initTimeHistogram(),
            "T-MAX"      : 0.0,
            "cpu"        : self.systemStats.items["cpu use"],
        }


    def updateStats(self, current, stats):
        # Gather specific information and aggregate into our persistent stats
        adjustedMethod = getAdjustedMethodName(stats)
        adjustedClient = getAdjustedClientName(stats)

        if current["requests"] == 0:
            current["cpu"] = 0.0
        current["requests"] += 1
        current["method"][adjustedMethod] += 1
        current["method-t"][adjustedMethod] += stats.get("t", 0.0)
        current["uid"][stats["uid"]] += 1
        current["user-agent"][adjustedClient] += 1
        if stats["statusCode"] >= 500:
            current["500"] += 1
        current["t"] += stats.get("t", 0.0)
        current["t-resp-wr"] += stats.get("t-resp-wr", 0.0)
        current["slots"] += stats.get("outstandingRequests", 0)
        current["cpu"] += self.systemStats.items["cpu use"]

        def histogramUpdate(t, key):
            if t >= 60000.0:
                current[key][">60s"] += 1
            elif t >= 30000.0:
                current[key]["30s<->60s"] += 1
            elif t >= 10000.0:
                current[key]["10s<->30s"] += 1
            elif t >= 1000.0:
                current[key]["1s<->10s"] += 1
            elif t >= 100.0:
                current[key]["100ms<->1s"] += 1
            elif t >= 10.0:
                current[key]["10ms<->100ms"] += 1
            else:
                current[key]["<10ms"] += 1
            if t >= 1000.0:
                current[key]["Over 1s"] += 1
            elif t >= 10000.0:
                current[key]["Over 10s"] += 1

        t = stats.get("t", None)
        if t is not None:
            histogramUpdate(t, "T")
        current["T-MAX"] = max(current["T-MAX"], t)
        t = stats.get("t-resp-wr", None)
        if t is not None:
            histogramUpdate(t, "T-RESP-WR")


    def mergeStats(self, current, stats):
        # Gather specific information and aggregate into our persistent stats
        if current["requests"] == 0:
            current["cpu"] = 0.0
        current["requests"] += stats["requests"]
        for method in stats["method"].keys():
            current["method"][method] += stats["method"][method]
        for method in stats["method-t"].keys():
            current["method-t"][method] += stats["method-t"][method]
        for uid in stats["uid"].keys():
            current["uid"][uid] += stats["uid"][uid]
        for ua in stats["user-agent"].keys():
            current["user-agent"][ua] += stats["user-agent"][ua]
        current["500"] += stats["500"]
        current["t"] += stats["t"]
        current["t-resp-wr"] += stats["t-resp-wr"]
        current["slots"] += stats["slots"]
        current["cpu"] += stats["cpu"]

        def histogramUpdate(t, key):
            if t >= 60000.0:
                current[key][">60s"] += 1
            elif t >= 30000.0:
                current[key]["30s<->60s"] += 1
            elif t >= 10000.0:
                current[key]["10s<->30s"] += 1
            elif t >= 1000.0:
                current[key]["1s<->10s"] += 1
            elif t >= 100.0:
                current[key]["100ms<->1s"] += 1
            elif t >= 10.0:
                current[key]["10ms<->100ms"] += 1
            else:
                current[key]["<10ms"] += 1
            if t >= 1000.0:
                current[key]["Over 1s"] += 1
            elif t >= 10000.0:
                current[key]["Over 10s"] += 1

        for bin in stats["T"].keys():
            current["T"][bin] += stats["T"][bin]
        current["T-MAX"] = max(current["T-MAX"], stats["T-MAX"])
        for bin in stats["T-RESP-WR"].keys():
            current["T-RESP-WR"][bin] += stats["T-RESP-WR"][bin]



class SystemMonitor(object):
    """
    Keeps track of system usage information. This installs a reactor task to
    run about once per second and track system use.
    """

    CPUStats = collections.namedtuple("CPUStats", ("total", "idle",))

    def __init__(self):
        self.items = {
            "cpu count"     : psutil.NUM_CPUS if psutil is not None else -1,
            "cpu use"       : 0.0,
            "memory used"   : 0,
            "memory percent": 0.0,
            "start time"    : time.time(),
        }

        if psutil is not None:
            times = psutil.cpu_times()
            self.previous_cpu = SystemMonitor.CPUStats(sum(times), times.idle,)
        else:
            self.previous_cpu = SystemMonitor.CPUStats(0, 0)

        self.task = task.LoopingCall(self.update)
        self.task.start(1.0)


    def stop(self):
        """
        Just stop the task
        """
        self.task.stop()


    def update(self):

        # CPU usage based on diff'ing CPU times
        if psutil is not None:
            times = psutil.cpu_times()
            cpu_now = SystemMonitor.CPUStats(sum(times), times.idle,)
            try:
                self.items["cpu use"] = 100.0 * (1.0 - (cpu_now.idle - self.previous_cpu.idle) / (cpu_now.total - self.previous_cpu.total))
            except ZeroDivisionError:
                self.items["cpu use"] = 0.0
            self.previous_cpu = cpu_now

        # Memory usage
        if psutil is not None and 'freebsd' not in platform:
            mem = psutil.virtual_memory()
            self.items["memory used"] = mem.used
            self.items["memory percent"] = mem.percent



class LogStats(amp.Command):
    arguments = [("message", amp.String())]



class AMPCommonAccessLoggingObserver(CommonAccessLoggingObserverExtensions):
    def __init__(self):
        self.protocol = None
        self._buffer = []


    def flushBuffer(self):
        if self._buffer:
            for msg in self._buffer:
                self.logStats(msg)


    def addClient(self, connectedClient):
        """
        An AMP client connected; hook it up to this observer.
        """
        self.protocol = connectedClient
        self.flushBuffer()


    def logStats(self, message):
        """
        Log server stats via the remote AMP Protocol
        """

        if self.protocol is not None:
            message = json.dumps(message)
            if isinstance(message, unicode):
                message = message.encode("utf-8")
            d = self.protocol.callRemote(LogStats, message=message)
            d.addErrback(log.error)
        else:
            self._buffer.append(message)



class AMPLoggingProtocol(amp.AMP):
    """
    A server side protocol for logging to the given observer.
    """

    def __init__(self, observer):
        self.observer = observer

        super(AMPLoggingProtocol, self).__init__()


    def logStats(self, message):
        stats = json.loads(message)
        self.observer.logStats(stats)
        return {}

    LogStats.responder(logStats)



class AMPLoggingFactory(protocol.ServerFactory):
    def __init__(self, observer):
        self.observer = observer


    def doStart(self):
        self.observer.start()


    def doStop(self):
        self.observer.stop()


    def buildProtocol(self, addr):
        return AMPLoggingProtocol(self.observer)
