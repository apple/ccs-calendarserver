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
"""

from twistedcaldav.log import Logger

log = Logger()

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
previousLogLevel = logtypes["debug"]

def toggle():
    """
    Toggle between normal mode and full debug mode.
    """

    global currentLogLevel
    global previousLogLevel
    tempLevel = currentLogLevel
    currentLogLevel = previousLogLevel
    previousLogLevel = tempLevel
    
    for key, value in logtypes.iteritems():
        if value == currentLogLevel:
            log.msg("Switching to log level: %s" % (key,))
            break
    else:
        log.msg("Switching to log level: %d" % (currentLogLevel,))
            

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
