##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

from __future__ import print_function

__all__ = [
    "checkSACL"
]

from cffi import FFI, VerificationError

ffi = FFI()

definitions = """
    typedef unsigned char uuid_t[16];
    int mbr_check_service_membership(const uuid_t user, const char* servicename, int* ismember);
    int mbr_user_name_to_uuid(const char* name, uuid_t uu);
    int mbr_group_name_to_uuid(const char* name, uuid_t uu);
"""

ffi.cdef(definitions)

try:
    lib = ffi.verify(definitions, libraries=[])
except VerificationError as ve:
    raise ImportError(ve)



def checkSACL(userOrGroupName, serviceName):
    """
    Check to see if a given user or group is a member of an OS X Server
    service's access group.  If userOrGroupName is an empty string, we
    want to know if unauthenticated access is allowed for the given service.

    @param userOrGroupName: the name of the user or group
    @type userOrGroupName: C{unicode}

    @param serviceName: the name of the service (e.g. calendar, addressbook)
    @type serviceName: C{str}

    @return: True if the user or group is allowed access to service
    @rtype: C{bool}
    """

    userOrGroupName = userOrGroupName.encode("utf-8")
    prefix = "com.apple.access_"
    uu = ffi.new("uuid_t")

    # See if the access group exists.  If it does not, then there are no
    # restrictions
    groupName = prefix + serviceName
    groupMissing = lib.mbr_group_name_to_uuid(groupName, uu)
    if groupMissing:
        return True

    # See if userOrGroupName matches a user
    result = lib.mbr_user_name_to_uuid(userOrGroupName, uu)
    if result:
        # Not a user, try looking up a group of that name
        result = lib.mbr_group_name_to_uuid(userOrGroupName, uu)

    if result:
        # Neither a user nor a group matches the name
        return False

    # See if the uuid is a member of the service access group
    isMember = ffi.new("int *")
    result = lib.mbr_check_service_membership(uu, serviceName, isMember)
    if not result and isMember[0]:
        return True

    return False
