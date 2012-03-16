##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
RFC 4331 (Quota and Size Properties for WebDAV Collections) XML Elements

This module provides XML element definitions for use with WebDAV.

See RFC 4331: http://www.ietf.org/rfc/rfc4331.txt
"""

from txdav.xml.base import WebDAVTextElement


##
# Section 3 & 4 (Quota Properties)
##

class QuotaAvailableBytes (WebDAVTextElement):
    """
    Property which contains the the number of bytes available under the
    current quota to store data in a collection (RFC 4331, section 3)
    """
    name = "quota-available-bytes"
    hidden = True
    protected = True


class QuotaUsedBytes (WebDAVTextElement):
    """
    Property which contains the the number of bytes used under the
    current quota to store data in a collection (RFC 4331, section 4)
    """
    name = "quota-used-bytes"
    hidden = True
    protected = True
