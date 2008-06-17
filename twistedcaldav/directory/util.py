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

import errno
import time
from twisted.python.filepath import FilePath

class NotFilePath(FilePath):
    """
    Dummy placeholder for FilePath for when we don't actually want a file.
    Pretends to be an empty file or directory.
    """
    def __init__(self, isfile=False, isdir=False, islink=False):
        assert isfile or isdir or islink

        self._isfile = isfile
        self._isdir  = isdir
        self._islink = islink

        self._time = time.time()

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return cmp(
            ( self.isdir(),  self.isfile(),  self.islink()),
            (other.isdir(), other.isfile(), other.islink()),
        )

    def __repr__(self):
        types = []
        if self.isdir():
            types.append("dir")
        if self.isfile():
            types.append("file")
        if self.islink():
            types.append("link")
        if types:
            return "<%s (%s)>" % (self.__class__.__name__, ",".join(types))
        else:
            return "<%s>" % (self.__class__.__name__,)

    def _unimplemented(self, *args):
        try:
            raise NotImplementedError("NotFilePath isn't really a FilePath: psych!")
        except NotImplementedError:
            from twisted.python.failure import Failure
            Failure().printTraceback()
            raise

    child                  = _unimplemented
    preauthChild           = _unimplemented
    siblingExtensionSearch = _unimplemented
    siblingExtension       = _unimplemented
    open                   = _unimplemented
    clonePath              = _unimplemented # Cuz I think it's dumb

    def childSearchPreauth(self, *paths):
        return ()

    def splitext(self):
        return ("", "")

    def basename(self):
        return ""

    def dirname(self):
        return ""

    def restat(self, reraise=True):
        pass

    def getsize(self):
        return 0

    def _time(self):
        return self._time

    # FIXME: Maybe we should have separate ctime, mtime, atime. Meh.
    getModificationTime = _time
    getStatusChangeTime = _time
    getAccessTime       = _time

    def exists(self):
        return True

    def isdir(self):
        return self._isdir

    def isfile(self):
        return self._isfile

    def islink(self):
        return self._islink

    def isabs(self):
        return True

    def listdir(self):
        return ()

    def touch(self):
        self._time = time.time()

    def _notAllowed(self):
        raise OSError(errno.EACCES, "Permission denied")

    remove     = _notAllowed
    setContent = _notAllowed

    def globChildren(self, pattern):
        return ()

    def parent(self):
        return self.__class__(isdir=True)

    def createDirectory(self):
        if self.isdir():
            raise OSError(errno.EEXIST, "File exists")
        else:
            return self._notAllowed

    makedirs = createDirectory

    def create(self):
        if self.isfile():
            raise OSError(errno.EEXIST, "File exists")
        else:
            return self._notAllowed

    def temporarySibling(self):
        return self.__class__(isfile=True)

    def copyTo(self, destination):
        if self.isdir():
            if not destination.isdir():
                destination.createDirectory()
        elif self.isfile():
            destination.open("w").close()
        else:
            raise NotImplementedError()

    moveTo = _notAllowed
