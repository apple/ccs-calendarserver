# Copyright (c) 2009 Twisted Matrix Laboratories.
# See LICENSE for details.

##
# Copyright (c) 2005-2012 Apple Computer, Inc. All rights reserved.
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
##

"""
WebDAV XML support.

This module provides XML utilities for use with WebDAV.

See RFC 2518: http://www.ietf.org/rfc/rfc2518.txt (WebDAV)
See RFC 3253: http://www.ietf.org/rfc/rfc3253.txt (WebDAV + Versioning)
See RFC 3744: http://www.ietf.org/rfc/rfc3744.txt (WebDAV ACLs)
See RFC 4331: http://www.ietf.org/rfc/rfc4331.txt (WebDAV Quota)
See RFC 5842: http://www.ietf.org/rfc/rfc5842.txt (WebDAV Bind)
"""

__all__ = [
    "base",
    "element",
    "parser",
]

import txdav.xml.rfc2518
import txdav.xml.rfc3253
import txdav.xml.rfc3744
import txdav.xml.rfc4331
import txdav.xml.rfc5842
import txdav.xml.rfc5397
import txdav.xml.rfc5995
import txdav.xml.draft_sync
import txdav.xml.extensions

txdav # Shhh pyflakes
