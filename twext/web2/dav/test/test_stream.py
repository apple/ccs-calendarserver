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
##

from twisted.python.hashlib import md5
from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase
from twext.web2.stream import MemoryStream
from twext.web2.dav.stream import MD5StreamWrapper


class AsynchronousDummyStream(object):
    """
    An L{IByteStream} implementation which always returns a L{Deferred} from
    C{read} and lets an external driver fire them.
    """
    def __init__(self):
        self._readResults = []


    def read(self):
        result = Deferred()
        self._readResults.append(result)
        return result


    def _write(self, bytes):
        self._readResults.pop(0).callback(bytes)



class MD5StreamWrapperTests(TestCase):
    """
    Tests for L{MD5StreamWrapper}.
    """
    data = "I am sorry Dave, I can't do that.\n--HAL 9000"
    digest = md5(data).hexdigest()

    def test_synchronous(self):
        """
        L{MD5StreamWrapper} computes the MD5 hash of the contents of the stream
        around which it is wrapped.  It supports L{IByteStream} providers which
        return C{str} from their C{read} method.
        """
        dataStream = MemoryStream(self.data)
        md5Stream = MD5StreamWrapper(dataStream)

        self.assertEquals(str(md5Stream.read()), self.data)
        self.assertIdentical(md5Stream.read(), None)
        md5Stream.close()

        self.assertEquals(self.digest, md5Stream.getMD5())


    def test_asynchronous(self):
        """
        L{MD5StreamWrapper} also supports L{IByteStream} providers which return
        L{Deferreds} from their C{read} method.
        """
        dataStream = AsynchronousDummyStream()
        md5Stream = MD5StreamWrapper(dataStream)

        result = md5Stream.read()
        dataStream._write(self.data)
        result.addCallback(self.assertEquals, self.data)

        def cbRead(ignored):
            result = md5Stream.read()
            dataStream._write(None)
            result.addCallback(self.assertIdentical, None)
            return result
        result.addCallback(cbRead)

        def cbClosed(ignored):
            md5Stream.close()
            self.assertEquals(md5Stream.getMD5(), self.digest)
        result.addCallback(cbClosed)

        return result


    def test_getMD5FailsBeforeClose(self):
        """
        L{MD5StreamWrapper.getMD5} raises L{RuntimeError} if called before
        L{MD5StreamWrapper.close}.
        """
        dataStream = MemoryStream(self.data)
        md5Stream = MD5StreamWrapper(dataStream)
        self.assertRaises(RuntimeError, md5Stream.getMD5)


    def test_initializationFailsWithoutStream(self):
        """
        L{MD5StreamWrapper.__init__} raises L{ValueError} if passed C{None} as
        the stream to wrap.
        """
        self.assertRaises(ValueError, MD5StreamWrapper, None)


    def test_readAfterClose(self):
        """
        L{MD5StreamWrapper.read} raises L{RuntimeError} if called after
        L{MD5StreamWrapper.close}.
        """
        dataStream = MemoryStream(self.data)
        md5Stream = MD5StreamWrapper(dataStream)
        md5Stream.close()
        self.assertRaises(RuntimeError, md5Stream.read)
