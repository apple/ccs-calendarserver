# Copyright (c) 2009 Twisted Matrix Laboratories.
# See LICENSE for details.

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
#
##

"""
Class that implements a stream that calculates the MD5 hash of the data
as the data is read.
"""

__all__ = ["MD5StreamWrapper"]

from twisted.python.hashlib import md5
from twisted.internet.defer import Deferred
from twext.web2.stream import SimpleStream


class MD5StreamWrapper(SimpleStream):
    """
    An L{IByteStream} wrapper which computes the MD5 hash of the data read from
    the wrapped stream.

    @ivar _stream: The stream which is wrapped.
    @ivar _md5: The object used to compute the running md5 hash.
    @ivar _md5value: The hex encoded md5 hash, only set after C{close}.
    """

    def __init__(self, wrap):
        if wrap is None:
            raise ValueError("Stream to wrap must be provided")
        self._stream = wrap
        self._md5 = md5()


    def _update(self, value):
        """
        Update the MD5 hash object.

        @param value: L{None} or a L{str} with which to update the MD5 hash
            object.

        @return: C{value}
        """
        if value is not None:
            self._md5.update(value)
        return value


    def read(self):
        """
        Read from the wrapped stream and update the MD5 hash object.
        """
        if self._stream is None:
            raise RuntimeError("Cannot read after stream is closed")
        b = self._stream.read()

        if isinstance(b, Deferred):
            b.addCallback(self._update)
        else:
            if b is not None:
                self._md5.update(b)
        return b


    def close(self):
        """
        Compute the final hex digest of the contents of the wrapped stream.
        """
        SimpleStream.close(self)
        self._md5value = self._md5.hexdigest()
        self._stream = None
        self._md5 = None


    def getMD5(self):
        """
        Return the hex encoded MD5 digest of the contents of the wrapped
        stream.  This may only be called after C{close}.

        @rtype: C{str}
        @raise RuntimeError: If C{close} has not yet been called.
        """
        if self._md5 is not None:
            raise RuntimeError("Cannot get MD5 value until stream is closed")
        return self._md5value
