##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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

