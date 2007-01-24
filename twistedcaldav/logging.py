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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Classes and functions to do better logging.
"""

import datetime
import os
import time

from twisted.python import log
from twisted.web2 import iweb
from twisted.web2.dav import davxml
from twisted.web2.log import BaseCommonAccessLoggingObserver

#
# Logging levels:
#  0 - no logging
#  1 - errors only
#  2 - errors and warnings only
#  3 - errors, warnings and info
#  4 - errors, warnings, info and debug
#

logtypes = {"none": 0, "error": 1, "warning": 2, "info": 3, "debug": 4}

currentLogLevel = logtypes["error"]

def canLog(type):
    """
    Determine whether a particular log level type is current active.
    
    @param type: a string with one of the types above.
    @return:     True if the log level is currently active.
    """
    
    return currentLogLevel >= logtypes.get(type, 1)

def info(message, **kwargs):
    """
    Log a message at the "info" level.
    
    @param message:  message to log.
    @param **kwargs: additional log arguments.
    """
    
    if canLog("info"):
        log.msg(message, **kwargs)

def warn(message, **kwargs):
    """
    Log a message at the "warning" level.
    
    @param message:  message to log.
    @param **kwargs: additional log arguments.
    """
    
    if canLog("warning"):
        log.msg(message, **kwargs)

def err(message, **kwargs):
    """
    Log a message at the "error" level.
    
    @param message:  message to log.
    @param **kwargs: additional log arguments.
    """
    
    if canLog("error"):
        log.msg(message, **kwargs)

def debug(message, **kwargs):
    """
    Log a message at the "debug" level.
    
    @param message:  message to log.
    @param **kwargs: additional log arguments.
    """
    
    if canLog("debug"):
        log.msg(message, debug=True, **kwargs)

class RotatingFileAccessLoggingObserver(BaseCommonAccessLoggingObserver):
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

    def emit(self, eventDict):
        if eventDict.get('interface') is not iweb.IRequest:
            return

        request = eventDict['request']
        response = eventDict['response']
        loginfo = eventDict['loginfo']
        firstLine = '%s %s HTTP/%s' %(
            request.method,
            request.uri,
            '.'.join([str(x) for x in request.clientproto]))
        
        # Try to determine authentication and authorization identifiers
        uid = "-"
        if hasattr(request, "authnUser"):
            if isinstance(request.authnUser.children[0], davxml.HRef):
                uid = str(request.authnUser.children[0])
                if hasattr(request, "authzUser") and str(request.authzUser.children[0]) != uid:
                    uid = '"%s as %s"' % (uid, str(request.authzUser.children[0]),)
        

        self.logMessage(
            '%s - %s [%s] "%s" %s %d "%s" "%s"' %(
                request.remoteAddr.host,
                uid,
                self.logDateString(
                    response.headers.getHeader('date', 0)),
                firstLine,
                response.code,
                loginfo.bytesSent,
                request.headers.getHeader('referer', '-'),
                request.headers.getHeader('user-agent', '-')
                )
            )

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

        return self.toDate() > self.lastDate

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
        info("Rotating log file to: %s" % (newpath,), system="Logging")
        self.f.close()
        os.rename(self.logpath, newpath)
        self._open()
        self.logMessage("Log opened - rotated: [%s]." % (datetime.datetime.now().ctime(),), False)

