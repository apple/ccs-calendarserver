# Copyright (c) 2009 Twisted Matrix Laboratories.
# See LICENSE for details.

##
# Copyright (c) 2005 Apple Computer, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
##

"""
DAV Property store using file system extended attributes.

This API is considered private to static.py and is therefore subject to
change.
"""

__all__ = ["xattrPropertyStore"]

import urllib
import sys
import zlib
import errno

from operator import setitem
from zlib import compress, decompress
from cPickle import UnpicklingError, loads as unpickle

import xattr

if getattr(xattr, 'xattr', None) is None:
    raise ImportError("wrong xattr package imported")

from twisted.python.util import untilConcludes
from twisted.python.failure import Failure
from twisted.python.log import err
from twext.web2 import responsecode
from twext.web2.http import HTTPError, StatusResponse
from twext.web2.dav import davxml
from twext.web2.dav.http import statusForFailure

# RFC 2518 Section 12.13.1 says that removal of non-existing property
# is not an error.  python-xattr on Linux fails with ENODATA in this
# case.  On OS X, the xattr library fails with ENOATTR, which CPython
# does not expose.  Its value is 93.
_ATTR_MISSING = (errno.ENODATA, 93)


class xattrPropertyStore (object):
    """

    This implementation uses Bob Ippolito's xattr package, available from::

        http://undefined.org/python/#xattr

    Note that the Bob's xattr package is specific to Linux and Darwin, at least
    presently.
    """
    #
    # Dead properties are stored as extended attributes on disk.  In order to
    # avoid conflicts with other attributes, prefix dead property names.
    #
    deadPropertyXattrPrefix = "WebDAV:"

    # Linux seems to require that attribute names use a "user." prefix.
    # FIXME: Is is a system-wide thing, or a per-filesystem thing?
    #   If the latter, how to we detect the file system?
    if sys.platform == "linux2":
        deadPropertyXattrPrefix = "user."

    def _encode(clazz, name):
        result = urllib.quote("{%s}%s" % name, safe='{}:')
        r = clazz.deadPropertyXattrPrefix + result
        return r

    def _decode(clazz, name):
        name = urllib.unquote(name[len(clazz.deadPropertyXattrPrefix):])

        index = name.find("}")

        if (index is -1 or not len(name) > index or not name[0] == "{"):
            raise ValueError("Invalid encoded name: %r" % (name,))

        return (name[1:index], name[index+1:])

    _encode = classmethod(_encode)
    _decode = classmethod(_decode)

    def __init__(self, resource):
        self.resource = resource
        self.attrs = xattr.xattr(self.resource.fp.path)


    def get(self, qname):
        """
        Retrieve the value of a property stored as an extended attribute on the
        wrapped path.

        @param qname: The property to retrieve as a two-tuple of namespace URI
            and local name.

        @raise HTTPError: If there is no value associated with the given
            property.

        @return: A L{WebDAVDocument} representing the value associated with the
            given property.
        """
        try:
            data = self.attrs.get(self._encode(qname))
        except KeyError:
            raise HTTPError(StatusResponse(
                    responsecode.NOT_FOUND,
                    "No such property: {%s}%s" % qname))
        except IOError, e:
            if e.errno in _ATTR_MISSING:
                raise HTTPError(StatusResponse(
                        responsecode.NOT_FOUND,
                        "No such property: {%s}%s" % qname))
            else:
                raise HTTPError(StatusResponse(
                        statusForFailure(Failure()),
                        "Unable to read property: {%s}%s" % qname))

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
        except zlib.error:
            legacy = True

        try:
            doc = davxml.WebDAVDocument.fromString(data)
        except ValueError:
            try:
                doc = unpickle(data)
            except UnpicklingError:
                format = "Invalid property value stored on server: {%s}%s %s"
                msg = format % (qname[0], qname[1], data)
                err(None, msg)
                raise HTTPError(
                    StatusResponse(responsecode.INTERNAL_SERVER_ERROR, msg))
            else:
                legacy = True

        if legacy:
            self.set(doc.root_element)

        return doc.root_element


    def set(self, property):
        """
        Store the given property as an extended attribute on the wrapped path.

        @param property: A L{WebDAVElement} to store.
        """
        key = self._encode(property.qname())
        value = compress(property.toxml())
        untilConcludes(setitem, self.attrs, key, value)

        # Update the resource because we've modified it
        self.resource.fp.restat()


    def delete(self, qname):
        """
        Remove the extended attribute from the wrapped path which stores the
        property given by C{qname}.

        @param qname: The property to delete as a two-tuple of namespace URI
            and local name.
        """
        key = self._encode(qname)
        try:
            try:
                self.attrs.remove(key)
            except KeyError:
                pass
            except IOError, e:
                if e.errno not in _ATTR_MISSING:
                    raise
        except:
            raise HTTPError(
                StatusResponse(
                    statusForFailure(Failure()),
                    "Unable to delete property: " + key))


    def contains(self, qname):
        """
        Determine whether the property given by C{qname} is stored in an
        extended attribute of the wrapped path.

        @param qname: The property to look up as a two-tuple of namespace URI
            and local name.

        @return: C{True} if the property exists, C{False} otherwise.
        """
        key = self._encode(qname)
        try:
            self.attrs.get(key)
        except KeyError:
            return False
        except IOError, e:
            if e.errno in _ATTR_MISSING or e.errno == errno.ENOENT:
                return False
            raise HTTPError(
                StatusResponse(
                    statusForFailure(Failure()),
                    "Unable to read property: " + key))
        else:
            return True


    def list(self):
        """
        Enumerate the property names stored in extended attributes of the
        wrapped path.

        @return: A C{list} of property names as two-tuples of namespace URI and
            local name.
        """
        prefix = self.deadPropertyXattrPrefix
        try:
            attrs = iter(self.attrs)
        except IOError:
            raise HTTPError(
                StatusResponse(
                    statusForFailure(Failure()),
                    "Unable to list properties: " + self.resource.fp.path))
        else:
            return [
                self._decode(name)
                for name
                in attrs
                if name.startswith(prefix)]
