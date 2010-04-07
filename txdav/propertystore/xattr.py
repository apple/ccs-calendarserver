##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Property store using filesystem extended attributes.
"""

from __future__ import absolute_import

__all__ = [
    "PropertyStore",
]

import sys
import errno
import urllib
from zlib import compress, decompress, error as ZlibError
from cPickle import UnpicklingError, loads as unpickle
from xattr import xattr

from twext.web2.dav.davxml import WebDAVDocument

from txdav.propertystore.base import AbstractPropertyStore, PropertyName, validKey
from txdav.idav import PropertyStoreError


#
# RFC 2518 Section 12.13.1 says that removal of non-existing property
# is not an error.  python-xattr on Linux fails with ENODATA in this
# case.  On OS X, the xattr library fails with ENOATTR, which CPython
# does not expose.  Its value is 93.
#
if sys.platform is "darwin":
    if hasattr(errno, "ENOATTR"):
        _ERRNO_NO_ATTR = errno.ENOATTR
    else:
        _ERRNO_NO_ATTR = 93
else:
    _ERRNO_NO_ATTR = errno.ENODATA


class PropertyStore(AbstractPropertyStore):
    """
    Property store using filesystem extended attributes.

    This implementation uses Bob Ippolito's xattr package, available from::

        http://undefined.org/python/#xattr
    """
    #
    # Dead properties are stored as extended attributes on disk.  In order to
    # avoid conflicts with other attributes, prefix dead property names.
    #
    deadPropertyXattrPrefix = "WebDAV:"

    # Linux seems to require that attribute names use a "user." prefix.
    if sys.platform == "linux2":
        deadPropertyXattrPrefix = "user.%s" % (deadPropertyXattrPrefix,)

    @classmethod
    def _encodeKey(cls, name):
        result = urllib.quote(name.toString(), safe="{}:")
        r = cls.deadPropertyXattrPrefix + result
        return r

    @classmethod
    def _decodeKey(cls, name):
        return PropertyName.fromString(
            urllib.unquote(name[len(cls.deadPropertyXattrPrefix):])
        )

    def __init__(self, path):
        self.path = path
        self.attrs = xattr(path.path)
        self.removed = set()
        self.modified = {}

    def __str__(self):
        return "<%s %s>" % (self.__class__.__name__, self.path.path)

    #
    # Accessors
    #

    def __delitem__(self, key):
        validKey(key)

        if key in self.modified:
            del self.modified[key]
        elif self._encodeKey(key) not in self.attrs:
            raise KeyError(key)

        self.removed.add(key)

    def __getitem__(self, key):
        validKey(key)

        if key in self.modified:
            return self.modified[key]

        if key in self.removed:
            raise KeyError(key)

        try:
            data = self.attrs[self._encodeKey(key)]
        except IOError, e:
            if e.errno in _ERRNO_NO_ATTR:
                raise KeyError(key)
            raise PropertyStoreError(e)

        #
        # Unserialize XML data from an xattr.  The storage format has changed
        # over time:
        #
        #  1- Started with XML
        #  2- Started compressing the XML due to limits on xattr size
        #  3- Switched to pickle which is faster, still compressing
        #  4- Back to compressed XML for interoperability, size
        #
        # We only write the current format, but we also read the old
        # ones for compatibility.
        #
        legacy = False

        try:
            data = decompress(data)
        except ZlibError:
            legacy = True

        try:
            doc = WebDAVDocument.fromString(data)
        except ValueError:
            try:
                doc = unpickle(data)
            except UnpicklingError:
                msg = "Invalid property value stored on server: %s %s" % (
                    key.toString(), data
                )
                self.log_error(msg)
                raise PropertyStoreError(msg)
            else:
                legacy = True

        if legacy:
            self.set(doc.root_element)

        return doc.root_element

    def __contains__(self, key):
        validKey(key)

        if key in self.modified:
            return True
        if key in self.removed:
            return False
        return self._encodeKey(key) in self.attrs

    def __setitem__(self, key, value):
        validKey(key)

        if key in self.removed:
            self.removed.remove(key)
        self.modified[key] = value

    def __iter__(self):
        seen = set()

        for key in self.attrs:
            key = self._decodeKey(key)
            if key not in self.removed:
                seen.add(key)
                yield key

        for key in self.modified:
            if key not in seen:
                yield key

    def __len__(self):
        keys = (
            set(self.attrs.keys()) |
            set(self._encodeKey(key) for key in self.modified)
        )
        return len(keys)

    #
    # I/O
    #

    def flush(self):
        attrs    = self.attrs
        removed  = self.removed
        modified = self.modified

        for key in removed:
            assert key not in modified
            del attrs[self._encodeKey(key)]

        for key in modified:
            assert key not in removed
            value = modified[key]
            attrs[self._encodeKey(key)] = compress(value.toxml())

    def abort(self):
        self.removed.clear()
        self.modified.clear()
