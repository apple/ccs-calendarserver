##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Logging levels:
    
    0    - no logging
    1    - errors only
    2    - errors and warnings only
    3    - errors, warnings and debug
"""

from twisted.python import log

logtypes = {"none": 0, "info": 1, "warning": 2, "error": 3, "debug": 4}

currentLogLevel = 1

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

