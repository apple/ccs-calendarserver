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

import sys

try:
    from ctypes import *
    import ctypes.util
    hasCtypes = True
except ImportError:
    hasCtypes = False

if sys.platform == 'darwin' and hasCtypes:
    from ctypes import *
    import ctypes.util

    libc = cdll.LoadLibrary(ctypes.util.find_library('libc'))

    def getNCPU():
        ncpu = c_int(0)

        size = c_int(sizeof(ncpu))

        libc.sysctlbyname('hw.ncpu',
                          c_voidp(addressof(ncpu)),
                          addressof(size),
                          None, 0)

        return int(ncpu.value)

elif sys.platform == 'linux2' and hasCtypes:
    from ctypes import *
    import ctypes.util

    libc = cdll.LoadLibrary(ctypes.util.find_library('libc'))

    def getNCPU():
        return libc.get_nprocs()

else:
    def getNCPU():
        if not hasCtypes:
            msg = "without ctypes"
        else:
            msg = ""

        raise NotImplementedError(
            "getNCPU not supported on %s %s" % (sys.platform, msg))
