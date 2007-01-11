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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Utilities.
"""

__all__ = [
    "uuidFromName",
]

from sha import sha

def uuidFromName(namespace, name):
    """
    Generate a version 5 (SHA-1) UUID from a namespace UUID and a name.
    See http://www.ietf.org/rfc/rfc4122.txt, section 4.3.
    @param namespace: a UUID denoting the namespace of the generated UUID.
    @param name: a byte string to generate the UUID from.
    """
    # Logic distilled from http://zesty.ca/python/uuid.py
    # by Ka-Ping Yee <ping@zesty.ca>
    
    # Convert from string representation to 16 bytes
    namespace = long(namespace.replace("-", ""), 16)
    bytes = ""
    for shift in xrange(0, 128, 8):
        bytes = chr((namespace >> shift) & 0xff) + bytes
    namespace = bytes

    # We don't want Unicode here; convert to UTF-8
    if type(name) is unicode:
        name = name.encode("utf-8")

    # Start with a SHA-1 hash of the namespace and name
    uuid = sha(namespace + name).digest()[:16]

    # Convert from hexadecimal to long integer
    uuid = long("%02x"*16 % tuple(map(ord, uuid)), 16)

    # Set the variant to RFC 4122.
    uuid &= ~(0xc000 << 48L)
    uuid |= 0x8000 << 48L
    
    # Set to version 5.
    uuid &= ~(0xf000 << 64L)
    uuid |= 5 << 76L

    # Convert from long integer to string representation
    uuid = "%032x" % (uuid,)
    return "%s-%s-%s-%s-%s" % (uuid[:8], uuid[8:12], uuid[12:16], uuid[16:20], uuid[20:])
