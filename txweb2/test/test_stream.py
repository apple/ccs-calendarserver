# Copyright (c) 2008 Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the stream implementations in L{txweb2}.
"""

import os
import sys
import tempfile

from zope.interface import implements

from twisted.python.util import sibpath
sibpath # sibpath is *not* unused - the doctests use it.
from twisted.python.hashlib import md5
from twisted.internet import reactor, defer, interfaces
from twisted.trial import unittest
from txweb2 import stream


def bufstr(data):
    try:
        return str(buffer(data))
    except TypeError:
        raise TypeError("%s doesn't conform to the buffer interface" % (data,))



class SimpleStreamTests:
    text = '1234567890'
    def test_split(self):
        for point in range(10):
            s = self.makeStream(0)
            a, b = s.split(point)
            if point > 0:
                self.assertEquals(bufstr(a.read()), self.text[:point])
            self.assertEquals(a.read(), None)
            if point < len(self.text):
                self.assertEquals(bufstr(b.read()), self.text[point:])
            self.assertEquals(b.read(), None)

        for point in range(7):
            s = self.makeStream(2, 6)
            self.assertEquals(s.length, 6)
            a, b = s.split(point)
            if point > 0:
                self.assertEquals(bufstr(a.read()), self.text[2:point + 2])
            self.assertEquals(a.read(), None)
            if point < 6:
                self.assertEquals(bufstr(b.read()), self.text[point + 2:8])
            self.assertEquals(b.read(), None)


    def test_read(self):
        s = self.makeStream()
        self.assertEquals(s.length, len(self.text))
        self.assertEquals(bufstr(s.read()), self.text)
        self.assertEquals(s.read(), None)

        s = self.makeStream(0, 4)
        self.assertEquals(s.length, 4)
        self.assertEquals(bufstr(s.read()), self.text[0:4])
        self.assertEquals(s.read(), None)
        self.assertEquals(s.length, 0)

        s = self.makeStream(4, 6)
        self.assertEquals(s.length, 6)
        self.assertEquals(bufstr(s.read()), self.text[4:10])
        self.assertEquals(s.read(), None)
        self.assertEquals(s.length, 0)



class FileStreamTest(SimpleStreamTests, unittest.TestCase):
    def makeStream(self, *args, **kw):
        return stream.FileStream(self.f, *args, **kw)


    def setUp(self):
        """
        Create a file containing C{self.text} to be streamed.
        """
        f = tempfile.TemporaryFile('w+')
        f.write(self.text)
        f.seek(0, 0)
        self.f = f


    def test_close(self):
        s = self.makeStream()
        s.close()

        self.assertEquals(s.length, 0)
        # Make sure close doesn't close file
        # would raise exception if f is closed
        self.f.seek(0, 0)


    def test_read2(self):
        s = self.makeStream(0)
        s.CHUNK_SIZE = 6
        self.assertEquals(s.length, 10)
        self.assertEquals(bufstr(s.read()), self.text[0:6])
        self.assertEquals(bufstr(s.read()), self.text[6:10])
        self.assertEquals(s.read(), None)

        s = self.makeStream(0)
        s.CHUNK_SIZE = 5
        self.assertEquals(s.length, 10)
        self.assertEquals(bufstr(s.read()), self.text[0:5])
        self.assertEquals(bufstr(s.read()), self.text[5:10])
        self.assertEquals(s.read(), None)

        s = self.makeStream(0, 20)
        self.assertEquals(s.length, 20)
        self.assertEquals(bufstr(s.read()), self.text)
        self.assertRaises(RuntimeError, s.read) # ran out of data



class MMapFileStreamTest(SimpleStreamTests, unittest.TestCase):
    text = SimpleStreamTests.text
    text = text * (stream.MMAP_THRESHOLD // len(text) + 1)

    def makeStream(self, *args, **kw):
        return stream.FileStream(self.f, *args, **kw)


    def setUp(self):
        """
        Create a file containing C{self.text}, which should be long enough to
        trigger the mmap-case in L{stream.FileStream}.
        """
        f = tempfile.TemporaryFile('w+')
        f.write(self.text)
        f.seek(0, 0)
        self.f = f


    def test_mmapwrapper(self):
        self.assertRaises(TypeError, stream.mmapwrapper)
        self.assertRaises(TypeError, stream.mmapwrapper, offset=0)
        self.assertRaises(TypeError, stream.mmapwrapper, offset=None)

    if not stream.mmap:
        test_mmapwrapper.skip = 'mmap not supported here'



class MemoryStreamTest(SimpleStreamTests, unittest.TestCase):
    def makeStream(self, *args, **kw):
        return stream.MemoryStream(self.text, *args, **kw)


    def test_close(self):
        s = self.makeStream()
        s.close()
        self.assertEquals(s.length, 0)


    def test_read2(self):
        self.assertRaises(ValueError, self.makeStream, 0, 20)


testdata = """I was angry with my friend:
I told my wrath, my wrath did end.
I was angry with my foe:
I told it not, my wrath did grow.

And I water'd it in fears,
Night and morning with my tears;
And I sunned it with smiles,
And with soft deceitful wiles.

And it grew both day and night,
Till it bore an apple bright;
And my foe beheld it shine,
And he knew that is was mine,

And into my garden stole
When the night had veil'd the pole:
In the morning glad I see
My foe outstretch'd beneath the tree"""


class TestBufferedStream(unittest.TestCase):

    def setUp(self):
        self.data = testdata.replace('\n', '\r\n')
        s = stream.MemoryStream(self.data)
        self.s = stream.BufferedStream(s)


    def _cbGotData(self, data, expected):
        self.assertEqual(data, expected)


    def test_readline(self):
        """Test that readline reads a line."""
        d = self.s.readline()
        d.addCallback(self._cbGotData, 'I was angry with my friend:\r\n')
        return d


    def test_readlineWithSize(self):
        """Test the size argument to readline"""
        d = self.s.readline(size=5)
        d.addCallback(self._cbGotData, 'I was')
        return d


    def test_readlineWithBigSize(self):
        """Test the size argument when it's bigger than the length of the line."""
        d = self.s.readline(size=40)
        d.addCallback(self._cbGotData, 'I was angry with my friend:\r\n')
        return d


    def test_readlineWithZero(self):
        """Test readline with size = 0."""
        d = self.s.readline(size=0)
        d.addCallback(self._cbGotData, '')
        return d


    def test_readlineFinished(self):
        """Test readline on a finished stream."""
        nolines = len(self.data.split('\r\n'))
        for _ in range(nolines):
            self.s.readline()
        d = self.s.readline()
        d.addCallback(self._cbGotData, '')
        return d


    def test_readlineNegSize(self):
        """Ensure that readline with a negative size raises an exception."""
        self.assertRaises(ValueError, self.s.readline, size=-1)


    def test_readlineSizeInDelimiter(self):
        """
        Test behavior of readline when size falls inside the
        delimiter.
        """
        d = self.s.readline(size=28)
        d.addCallback(self._cbGotData, "I was angry with my friend:\r")
        d.addCallback(lambda _: self.s.readline())
        d.addCallback(self._cbGotData, "\nI told my wrath, my wrath did end.\r\n")


    def test_readExactly(self):
        """Make sure readExactly with no arg reads all the data."""
        d = self.s.readExactly()
        d.addCallback(self._cbGotData, self.data)
        return d


    def test_readExactlyLimited(self):
        """
        Test readExactly with a number.
        """
        d = self.s.readExactly(10)
        d.addCallback(self._cbGotData, self.data[:10])
        return d


    def test_readExactlyBig(self):
        """
        Test readExactly with a number larger than the size of the
        datastream.
        """
        d = self.s.readExactly(100000)
        d.addCallback(self._cbGotData, self.data)
        return d


    def test_read(self):
        """
        Make sure read() also functions. (note that this test uses
        an implementation detail of this particular stream. s.read()
        isn't guaranteed to return self.data on all streams.)
        """
        self.assertEqual(str(self.s.read()), self.data)



class TestStreamer:
    implements(stream.IStream, stream.IByteStream)

    length = None

    readCalled = 0
    closeCalled = 0

    def __init__(self, list):
        self.list = list


    def read(self):
        self.readCalled += 1
        if self.list:
            return self.list.pop(0)
        return None


    def close(self):
        self.closeCalled += 1
        self.list = []



class FallbackSplitTest(unittest.TestCase):

    def test_split(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        left, right = stream.fallbackSplit(s, 5)
        self.assertEquals(left.length, 5)
        self.assertEquals(right.length, None)
        self.assertEquals(bufstr(left.read()), 'abcd')
        d = left.read()
        d.addCallback(self._cbSplit, left, right)
        return d


    def _cbSplit(self, result, left, right):
        self.assertEquals(bufstr(result), 'e')
        self.assertEquals(left.read(), None)

        self.assertEquals(bufstr(right.read().result), 'fgh')
        self.assertEquals(bufstr(right.read()), 'ijkl')
        self.assertEquals(right.read(), None)


    def test_split2(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        left, right = stream.fallbackSplit(s, 4)

        self.assertEquals(left.length, 4)
        self.assertEquals(right.length, None)

        self.assertEquals(bufstr(left.read()), 'abcd')
        self.assertEquals(left.read(), None)

        self.assertEquals(bufstr(right.read().result), 'efgh')
        self.assertEquals(bufstr(right.read()), 'ijkl')
        self.assertEquals(right.read(), None)


    def test_splitsplit(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        left, right = stream.fallbackSplit(s, 5)
        left, middle = left.split(3)

        self.assertEquals(left.length, 3)
        self.assertEquals(middle.length, 2)
        self.assertEquals(right.length, None)

        self.assertEquals(bufstr(left.read()), 'abc')
        self.assertEquals(left.read(), None)

        self.assertEquals(bufstr(middle.read().result), 'd')
        self.assertEquals(bufstr(middle.read().result), 'e')
        self.assertEquals(middle.read(), None)

        self.assertEquals(bufstr(right.read().result), 'fgh')
        self.assertEquals(bufstr(right.read()), 'ijkl')
        self.assertEquals(right.read(), None)


    def test_closeboth(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        left, right = stream.fallbackSplit(s, 5)
        left.close()
        self.assertEquals(s.closeCalled, 0)
        right.close()

        # Make sure nothing got read
        self.assertEquals(s.readCalled, 0)
        self.assertEquals(s.closeCalled, 1)


    def test_closeboth_rev(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        left, right = stream.fallbackSplit(s, 5)
        right.close()
        self.assertEquals(s.closeCalled, 0)
        left.close()

        # Make sure nothing got read
        self.assertEquals(s.readCalled, 0)
        self.assertEquals(s.closeCalled, 1)


    def test_closeleft(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        left, right = stream.fallbackSplit(s, 5)
        left.close()
        d = right.read()
        d.addCallback(self._cbCloseleft, right)
        return d


    def _cbCloseleft(self, result, right):
        self.assertEquals(bufstr(result), 'fgh')
        self.assertEquals(bufstr(right.read()), 'ijkl')
        self.assertEquals(right.read(), None)


    def test_closeright(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        left, right = stream.fallbackSplit(s, 3)
        right.close()

        self.assertEquals(bufstr(left.read()), 'abc')
        self.assertEquals(left.read(), None)

        self.assertEquals(s.closeCalled, 1)



class ProcessStreamerTest(unittest.TestCase):

    if interfaces.IReactorProcess(reactor, None) is None:
        skip = "Platform lacks spawnProcess support, can't test process streaming."


    def runCode(self, code, inputStream=None):
        if inputStream is None:
            inputStream = stream.MemoryStream("")
        return stream.ProcessStreamer(inputStream, sys.executable,
                                      [sys.executable, "-u", "-c", code],
                                      os.environ)


    def test_output(self):
        p = self.runCode("import sys\nfor i in range(100): sys.stdout.write('x' * 1000)")
        l = []
        d = stream.readStream(p.outStream, l.append)
        def verify(_):
            self.assertEquals("".join(l), ("x" * 1000) * 100)
        d2 = p.run()
        return d.addCallback(verify).addCallback(lambda _: d2)


    def test_errouput(self):
        p = self.runCode("import sys\nfor i in range(100): sys.stderr.write('x' * 1000)")
        l = []
        d = stream.readStream(p.errStream, l.append)
        def verify(_):
            self.assertEquals("".join(l), ("x" * 1000) * 100)
        p.run()
        return d.addCallback(verify)


    def test_input(self):
        p = self.runCode("import sys\nsys.stdout.write(sys.stdin.read())",
                         "hello world")
        l = []
        d = stream.readStream(p.outStream, l.append)
        d2 = p.run()
        def verify(_):
            self.assertEquals("".join(l), "hello world")
            return d2
        return d.addCallback(verify)


    def test_badexit(self):
        p = self.runCode("raise ValueError")
        l = []
        from twisted.internet.error import ProcessTerminated
        def verify(_):
            self.assertEquals(l, [1])
            self.assert_(p.outStream.closed)
            self.assert_(p.errStream.closed)
        return p.run().addErrback(lambda _: _.trap(ProcessTerminated) and l.append(1)).addCallback(verify)


    def test_inputerror(self):
        p = self.runCode("import sys\nsys.stdout.write(sys.stdin.read())",
                         TestStreamer(["hello", defer.fail(ZeroDivisionError())]))
        l = []
        d = stream.readStream(p.outStream, l.append)
        d2 = p.run()
        def verify(_):
            self.assertEquals("".join(l), "hello")
            return d2
        def cbVerified(ignored):
            excs = self.flushLoggedErrors(ZeroDivisionError)
            self.assertEqual(len(excs), 1)
        return d.addCallback(verify).addCallback(cbVerified)


    def test_processclosedinput(self):
        p = self.runCode("import sys; sys.stdout.write(sys.stdin.read(3));" +
                         "sys.stdin.close(); sys.stdout.write('def')",
                         "abc123")
        l = []
        d = stream.readStream(p.outStream, l.append)
        def verify(_):
            self.assertEquals("".join(l), "abcdef")
        d2 = p.run()
        return d.addCallback(verify).addCallback(lambda _: d2)



class AdapterTestCase(unittest.TestCase):

    def test_adapt(self):
        fName = self.mktemp()
        f = file(fName, "w")
        f.write("test")
        f.close()
        for i in ("test", buffer("test"), file(fName)):
            s = stream.IByteStream(i)
            self.assertEquals(str(s.read()), "test")
            self.assertEquals(s.read(), None)



class ReadStreamTestCase(unittest.TestCase):


    def test_pull(self):
        l = []
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        return stream.readStream(s, l.append).addCallback(
            lambda _: self.assertEquals(l, ["abcd", "efgh", "ijkl"]))


    def test_pullFailure(self):
        l = []
        s = TestStreamer(['abcd', defer.fail(RuntimeError()), 'ijkl'])
        def test(result):
            result.trap(RuntimeError)
            self.assertEquals(l, ["abcd"])
        return stream.readStream(s, l.append).addErrback(test)


    def test_pullException(self):
        class Failer:
            def read(self):
                raise RuntimeError
        return stream.readStream(Failer(), lambda _: None).addErrback(
            lambda _: _.trap(RuntimeError))


    def test_processingException(self):
        s = TestStreamer(['abcd', defer.succeed('efgh'), 'ijkl'])
        return stream.readStream(s, lambda x: 1 / 0).addErrback(
            lambda _: _.trap(ZeroDivisionError))



class ProducerStreamTestCase(unittest.TestCase):

    def test_failfinish(self):
        p = stream.ProducerStream()
        p.write("hello")
        p.finish(RuntimeError())
        self.assertEquals(p.read(), "hello")
        d = p.read()
        l = []
        d.addErrback(lambda _: (l.append(1), _.trap(RuntimeError))).addCallback(
            lambda _: self.assertEquals(l, [1]))
        return d



class CompoundStreamTest:
    """
    CompoundStream lets you combine many streams into one continuous stream.
    For example, let's make a stream:
    >>> s = stream.CompoundStream()

    Then, add a couple streams:
    >>> s.addStream(stream.MemoryStream("Stream1"))
    >>> s.addStream(stream.MemoryStream("Stream2"))

    The length is the sum of all the streams:
    >>> s.length
    14

    We can read data from the stream:
    >>> str(s.read())
    'Stream1'

    After having read some data, length is now smaller, as you might expect:
    >>> s.length
    7

    So, continue reading...
    >>> str(s.read())
    'Stream2'

    Now that the stream is exhausted:
    >>> s.read() is None
    True
    >>> s.length
    0

    We can also create CompoundStream more easily like so:
    >>> s = stream.CompoundStream(['hello', stream.MemoryStream(' world')])
    >>> str(s.read())
    'hello'
    >>> str(s.read())
    ' world'

    For a more complicated example, let's try reading from a file:
    >>> s = stream.CompoundStream()
    >>> s.addStream(stream.FileStream(open(sibpath(__file__, "stream_data.txt"))))
    >>> s.addStream("================")
    >>> s.addStream(stream.FileStream(open(sibpath(__file__, "stream_data.txt"))))

    Again, the length is the sum:
    >>> int(s.length)
    58

    >>> str(s.read())
    "We've got some text!\\n"
    >>> str(s.read())
    '================'

    What if you close the stream?
    >>> s.close()
    >>> s.read() is None
    True
    >>> s.length
    0

    Error handling works using Deferreds:
    >>> m = stream.MemoryStream("after")
    >>> s = stream.CompoundStream([TestStreamer([defer.fail(ZeroDivisionError())]), m]) # z<
    >>> l = []; x = s.read().addErrback(lambda _: l.append(1))
    >>> l
    [1]
    >>> s.length
    0
    >>> m.length # streams after the failed one got closed
    0

    """



class AsynchronousDummyStream(object):
    """
    An L{IByteStream} implementation which always returns a
    L{defer.Deferred} from C{read} and lets an external driver fire
    them.
    """
    def __init__(self):
        self._readResults = []


    def read(self):
        result = defer.Deferred()
        self._readResults.append(result)
        return result


    def _write(self, bytes):
        self._readResults.pop(0).callback(bytes)



class MD5StreamTest(unittest.TestCase):
    """
    Tests for L{stream.MD5Stream}.
    """
    data = "I am sorry Dave, I can't do that.\n--HAL 9000"
    digest = md5(data).hexdigest()

    def test_synchronous(self):
        """
        L{stream.MD5Stream} computes the MD5 hash of the contents of the stream
        around which it is wrapped.  It supports L{IByteStream} providers which
        return C{str} from their C{read} method.
        """
        dataStream = stream.MemoryStream(self.data)
        md5Stream = stream.MD5Stream(dataStream)

        self.assertEquals(str(md5Stream.read()), self.data)
        self.assertIdentical(md5Stream.read(), None)
        md5Stream.close()

        self.assertEquals(self.digest, md5Stream.getMD5())


    def test_asynchronous(self):
        """
        L{stream.MD5Stream} also supports L{IByteStream} providers which return
        L{Deferreds} from their C{read} method.
        """
        dataStream = AsynchronousDummyStream()
        md5Stream = stream.MD5Stream(dataStream)

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
        L{stream.MD5Stream.getMD5} raises L{RuntimeError} if called before
        L{stream.MD5Stream.close}.
        """
        dataStream = stream.MemoryStream(self.data)
        md5Stream = stream.MD5Stream(dataStream)
        self.assertRaises(RuntimeError, md5Stream.getMD5)


    def test_initializationFailsWithoutStream(self):
        """
        L{stream.MD5Stream.__init__} raises L{ValueError} if passed C{None} as
        the stream to wrap.
        """
        self.assertRaises(ValueError, stream.MD5Stream, None)


    def test_readAfterClose(self):
        """
        L{stream.MD5Stream.read} raises L{RuntimeError} if called after
        L{stream.MD5Stream.close}.
        """
        dataStream = stream.MemoryStream(self.data)
        md5Stream = stream.MD5Stream(dataStream)
        md5Stream.close()
        self.assertRaises(RuntimeError, md5Stream.read)



__doctests__ = ['txweb2.test.test_stream']
# TODO:
# CompoundStreamTest
# more tests for ProducerStreamTest
# StreamProducerTest
