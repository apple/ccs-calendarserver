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
WebDAV XML Support.

This module provides XML utilities for use with WebDAV.

This API is considered private to static.py and is therefore subject to
change.

See RFC 2518: http://www.ietf.org/rfc/rfc2518.txt (WebDAV)
See RFC 3253: http://www.ietf.org/rfc/rfc3253.txt (WebDAV + Versioning)
See RFC 3744: http://www.ietf.org/rfc/rfc3744.txt (WebDAV ACLs)
"""

#
# Import all XML element definitions
#

from txdav.xml.base    import *
from txdav.xml.parser  import *
from txdav.xml.rfc2518 import *
from txdav.xml.rfc3253 import *
from txdav.xml.rfc3744 import *
from txdav.xml.rfc4331 import *
from txdav.xml.rfc5842 import *
from txdav.xml.extensions import *

#
# Register all XML elements with the parser
#

from txdav.xml import base as b
from txdav.xml import parser as p
from txdav.xml import rfc2518 as r1
from txdav.xml import rfc3253 as r2
from txdav.xml import rfc3744 as r3
from txdav.xml import rfc4331 as r4
from txdav.xml import rfc5842 as r5
from txdav.xml import extensions as e

from txdav.xml.element import registerElements

__all__ = (
    registerElements(b) +
    registerElements(p) +
    registerElements(r1) +
    registerElements(r2) +
    registerElements(r3) +
    registerElements(r4) +
    registerElements(r5) +
    registerElements(e)
)
