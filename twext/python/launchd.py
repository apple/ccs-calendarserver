# -*- test-case-name: twext.python.test.test_launchd -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
CFFI bindings for launchd check-in API.
"""

from __future__ import print_function

import sys

from cffi import FFI

ffi = FFI()

ffi.cdef("""

static const char* LAUNCH_KEY_CHECKIN;
static const char* LAUNCH_JOBKEY_LABEL;
static const char* LAUNCH_JOBKEY_SOCKETS;

typedef enum {
    LAUNCH_DATA_DICTIONARY = 1,
    LAUNCH_DATA_ARRAY,
    LAUNCH_DATA_FD,
    LAUNCH_DATA_INTEGER,
    LAUNCH_DATA_REAL,
    LAUNCH_DATA_BOOL,
    LAUNCH_DATA_STRING,
    LAUNCH_DATA_OPAQUE,
    LAUNCH_DATA_ERRNO,
    LAUNCH_DATA_MACHPORT,
} launch_data_type_t;

typedef struct _launch_data *launch_data_t;

bool launch_data_dict_insert(launch_data_t, const launch_data_t, const char *);

launch_data_t launch_data_alloc(launch_data_type_t);
launch_data_t launch_data_new_string(const char *);
launch_data_t launch_data_new_integer(long long);

launch_data_t launch_msg(const launch_data_t);

launch_data_type_t launch_data_get_type(const launch_data_t);

launch_data_t launch_data_dict_lookup(const launch_data_t, const char *);
size_t launch_data_dict_get_count(const launch_data_t);
long long launch_data_get_integer(const launch_data_t);
void launch_data_dict_iterate(
    const launch_data_t,
    void (*)(const launch_data_t, const char *, void *),
    void *);

const char * launch_data_get_string(const launch_data_t);

size_t launch_data_array_get_count(const launch_data_t);
launch_data_t launch_data_array_get_index(const launch_data_t, size_t);
bool launch_data_array_set_index(launch_data_t, const launch_data_t, size_t);

void launch_data_free(launch_data_t);
""")

lib = ffi.verify("""
#include <launch.h>
""")

class NullPointerException(Exception):
    """
    Python doesn't have one of these.
    """


class LaunchArray(object):
    def __init__(self, launchdata):
        self.launchdata = launchdata


    def __len__(self):
        return lib.launch_data_array_get_count(self.launchdata)


    def __getitem__(self, index):
        if index >= len(self):
            raise IndexError(index)
        return _launchify(
            lib.launch_data_array_get_index(self.launchdata, index)
        )



class LaunchDictionary(object):
    def __init__(self, launchdata):
        self.launchdata = launchdata


    def keys(self):
        """
        Return keys in the dictionary.
        """
        keys = []
        @ffi.callback("void (*)(const launch_data_t, const char *, void *)")
        def icb(v, k, n):
            keys.append(ffi.string(k))
        lib.launch_data_dict_iterate(self.launchdata, icb, ffi.NULL)
        return keys


    def values(self):
        """
        Return values in the dictionary.
        """
        values = []
        @ffi.callback("void (*)(const launch_data_t, const char *, void *)")
        def icb(v, k, n):
            values.append(_launchify(v))
        lib.launch_data_dict_iterate(self.launchdata, icb, ffi.NULL)
        return values


    def items(self):
        """
        Return items in the dictionary.
        """
        values = []
        @ffi.callback("void (*)(const launch_data_t, const char *, void *)")
        def icb(v, k, n):
            values.append((ffi.string(k), _launchify(v)))
        lib.launch_data_dict_iterate(self.launchdata, icb, ffi.NULL)
        return values


    def __getitem__(self, key):
        launchvalue = lib.launch_data_dict_lookup(self.launchdata, key)
        try:
            return _launchify(launchvalue)
        except LaunchErrno:
            raise KeyError(key)


    def __len__(self):
        return lib.launch_data_dict_get_count(self.launchdata)



class LaunchErrno(Exception):
    """
    Error from launchd.
    """



def _launchify(launchvalue):
    if launchvalue == ffi.NULL:
        return None
    dtype = lib.launch_data_get_type(launchvalue)

    if dtype == lib.LAUNCH_DATA_DICTIONARY:
        return LaunchDictionary(launchvalue)
    elif dtype == lib.LAUNCH_DATA_ARRAY:
        return LaunchArray(launchvalue)
    elif dtype == lib.LAUNCH_DATA_FD:
        return lib.launch_data_get_fd(launchvalue)
    elif dtype == lib.LAUNCH_DATA_INTEGER:
        return lib.launch_data_get_integer(launchvalue)
    elif dtype == lib.LAUNCH_DATA_REAL:
        raise TypeError("REALs unsupported.")
    elif dtype == lib.LAUNCH_DATA_BOOL:
        return lib.launch_data_get_bool(launchvalue)
    elif dtype == lib.LAUNCH_DATA_STRING:
        cvalue = lib.launch_data_get_string(launchvalue)
        if cvalue == ffi.NULL:
            return None
        return ffi.string(cvalue)
    elif dtype == lib.LAUNCH_DATA_OPAQUE:
        return launchvalue
    elif dtype == lib.LAUNCH_DATA_ERRNO:
        raise LaunchErrno(launchvalue)
    elif dtype == lib.LAUNCH_DATA_MACHPORT:
        return lib.launch_data_get_machport(launchvalue)
    else:
        raise TypeError("Unknown Launch Data Type", dtype)



def checkin():
    """
    Perform a launchd checkin, returning a Pythonic wrapped data structure
    representing the retrieved check-in plist.
    """

def getLaunchDSocketFDs():
    result = {}
    req = lib.launch_data_new_string(lib.LAUNCH_KEY_CHECKIN)
    if req == ffi.NULL:
        # Good luck reproducing this case.
        raise NullPointerException()
    response = lib.launch_msg(req)
    if response == ffi.NULL:
        raise NullPointerException()
    if lib.launch_data_get_type(response) == lib.LAUNCH_DATA_ERRNO:
        raise NullPointerException()
    response = LaunchDictionary(response)
    label = response[lib.LAUNCH_JOBKEY_LABEL]
    skts = response[lib.LAUNCH_JOBKEY_SOCKETS]
    result['label'] = label
    result['sockets'] = list(skts['TestSocket'])
    return result

if __name__ == '__main__':
    # Unit tests :-(
    import traceback
    try:
        print(getLaunchDSocketFDs())
    except:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
