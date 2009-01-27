##
# Copyright (c) 2007 Apple Inc. All rights reserved.
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

import os
import re
import sys
from subprocess import Popen, PIPE, STDOUT

##
# getNCPU
##

try:
    from ctypes import *
    import ctypes.util
    hasCtypes = True
except ImportError:
    hasCtypes = False

if sys.platform == "darwin" and hasCtypes:
    libc = cdll.LoadLibrary(ctypes.util.find_library("libc"))

    def getNCPU():
        ncpu = c_int(0)
        size = c_size_t(sizeof(ncpu))

        libc.sysctlbyname.argtypes = [
            c_char_p, c_void_p, c_void_p, c_void_p, c_ulong
        ]
        libc.sysctlbyname(
            "hw.ncpu",
            c_voidp(addressof(ncpu)),
            c_voidp(addressof(size)),
            None,
            0
        )

        return int(ncpu.value)

elif sys.platform == "linux2" and hasCtypes:
    libc = cdll.LoadLibrary(ctypes.util.find_library("libc"))

    def getNCPU():
        return libc.get_nprocs()

else:
    def getNCPU():
        if not hasCtypes:
            msg = " without ctypes"
        else:
            msg = ""

        raise NotImplementedError("getNCPU not supported on %s%s" % (sys.platform, msg))

##
# Module management
##

def submodule(module, name):
    fullname = module.__name__ + "." + name

    try:
        submodule = __import__(fullname)
    except ImportError, e:
        raise ImportError("Unable to import submodule %s from module %s: %s" % (name, module, e))

    for m in fullname.split(".")[1:]:
        submodule = getattr(submodule, m)

    return submodule

##
# Tracebacks
##

from twisted.python.failure import Failure

def printTracebacks(f):
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except:
            Failure().printTraceback()
            raise
    return wrapper

##
# Helpers
##

class Alternator (object):
    """
    Object that alternates between True and False states.
    """
    def __init__(self, state=False):
        self._state = bool(state)

    def state(self):
        """
        @return: the current state
        """
        state = self._state
        self._state = not state
        return state

def utf8String(s):
    if isinstance(s, unicode):
        s = s.encode("utf-8")
    return s

##
# Keychain access
##

class KeychainPasswordNotFound(Exception):
    """
    Exception raised when the password does not exist
    """

class KeychainAccessError(Exception):
    """
    Exception raised when not able to access keychain
    """

passwordRegExp = re.compile(r'password: "(.*)"')

def getPasswordFromKeychain(label):
    if os.path.isfile("/usr/bin/security"):
        child = Popen(
            args=[
                "/usr/bin/security", "find-generic-password",
                "-l", label, "-g",
            ],
            stdout=PIPE, stderr=STDOUT,
        )
        output, error = child.communicate()

        if child.returncode:
            raise KeychainPasswordNotFound(error)
        else:
            match = passwordRegExp.search(output)
            if not match:
                error = "Password for %s not found in keychain" % (label,)
                raise KeychainPasswordNotFound(error)
            else:
                return match.group(1)

    else:
        error = "Keychain access utility ('security') not found"
        raise KeychainAccessError(error)
