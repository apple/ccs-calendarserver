##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Empty DAV property store.

This API is considered private to static.py and is therefore subject to
change.
"""

__all__ = ["NonePropertyStore"]

from txweb2 import responsecode
from txweb2.http import HTTPError, StatusResponse
from txdav.xml.base import encodeXMLName


class NonePropertyStore (object):
    """
    DAV property store which contains no properties and does not allow
    properties to be set.
    """
    __singleton = None

    def __new__(clazz, resource):
        if NonePropertyStore.__singleton is None:
            NonePropertyStore.__singleton = object.__new__(clazz)
        return NonePropertyStore.__singleton

    def __init__(self, resource):
        pass

    def get(self, qname, uid=None):
        raise HTTPError(StatusResponse(
            responsecode.NOT_FOUND,
            "No such property: %s" % (encodeXMLName(*qname),)
        ))

    def set(self, property, uid=None):
        raise HTTPError(StatusResponse(
            responsecode.FORBIDDEN,
            "Permission denied for setting property: %s" % (property,)
        ))

    def delete(self, qname, uid=None):
        # RFC 2518 Section 12.13.1 says that removal of
        # non-existing property is not an error.
        pass

    def contains(self, qname, uid=None):
        return False

    def list(self, uid=None):
        return ()
