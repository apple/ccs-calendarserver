##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Tests for L{twext.python.launchd}.
"""

import sys, os, plistlib, socket, json

if __name__ == '__main__':
    # This module is loaded as a launchd job by test-cases below; the following
    # code looks up an appropriate function to run.
    testID = sys.argv[1]
    a, b = testID.rsplit(".", 1)
    from twisted.python.reflect import namedAny
    try:
        namedAny(".".join([a, b.replace("test_", "job_")]))()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        skt = socket.socket()
        skt.connect(("127.0.0.1", int(os.environ["TESTING_PORT"])))
    sys.exit(0)



try:
    from twext.python.launchd import (
        lib, ffi, _LaunchDictionary, _LaunchArray, _managed, constants,
        plainPython, checkin, _launchify, getLaunchDSocketFDs
    )
except ImportError:
    skip = "LaunchD not available."
else:
    skip = False

from twisted.trial.unittest import TestCase
from twisted.python.filepath import FilePath


class LaunchDataStructures(TestCase):
    """
    Tests for L{_launchify} converting data structures from launchd's internals
    to Python objects.
    """

    def test_fd(self):
        """
        Test converting a launchd FD to an integer.
        """
        fd = _managed(lib.launch_data_new_fd(2))
        self.assertEquals(_launchify(fd), 2)


    def test_bool(self):
        """
        Test converting a launchd bool to a Python bool.
        """
        t = _managed(lib.launch_data_new_bool(True))
        f = _managed(lib.launch_data_new_bool(False))
        self.assertEqual(_launchify(t), True)
        self.assertEqual(_launchify(f), False)


    def test_real(self):
        """
        Test converting a launchd real to a Python float.
        """
        notQuitePi = _managed(lib.launch_data_new_real(3.14158))
        self.assertEqual(_launchify(notQuitePi), 3.14158)



class DictionaryTests(TestCase):
    """
    Tests for L{_LaunchDictionary}
    """

    def setUp(self):
        """
        Assemble a test dictionary.
        """
        self.testDict = _managed(
            lib.launch_data_alloc(lib.LAUNCH_DATA_DICTIONARY)
        )
        key1 = ffi.new("char[]", "alpha")
        val1 = lib.launch_data_new_string("alpha-value")
        key2 = ffi.new("char[]", "beta")
        val2 = lib.launch_data_new_string("beta-value")
        key3 = ffi.new("char[]", "gamma")
        val3 = lib.launch_data_new_integer(3)
        lib.launch_data_dict_insert(self.testDict, val1, key1)
        lib.launch_data_dict_insert(self.testDict, val2, key2)
        lib.launch_data_dict_insert(self.testDict, val3, key3)
        self.assertEquals(lib.launch_data_dict_get_count(self.testDict), 3)


    def test_len(self):
        """
        C{len(_LaunchDictionary())} returns the number of keys in the
        dictionary.
        """
        self.assertEquals(len(_LaunchDictionary(self.testDict)), 3)


    def test_keys(self):
        """
        L{_LaunchDictionary.keys} returns keys present in a C{launch_data_dict}.
        """
        dictionary = _LaunchDictionary(self.testDict)
        self.assertEquals(set(dictionary.keys()),
                          set([b"alpha", b"beta", b"gamma"]))


    def test_values(self):
        """
        L{_LaunchDictionary.values} returns keys present in a
        C{launch_data_dict}.
        """
        dictionary = _LaunchDictionary(self.testDict)
        self.assertEquals(set(dictionary.values()),
                          set([b"alpha-value", b"beta-value", 3]))


    def test_items(self):
        """
        L{_LaunchDictionary.items} returns all (key, value) tuples present in a
        C{launch_data_dict}.
        """
        dictionary = _LaunchDictionary(self.testDict)
        self.assertEquals(set(dictionary.items()),
                          set([(b"alpha", b"alpha-value"),
                               (b"beta", b"beta-value"), (b"gamma", 3)]))


    def test_plainPython(self):
        """
        L{plainPython} will convert a L{_LaunchDictionary} into a Python
        dictionary.
        """
        self.assertEquals({b"alpha": b"alpha-value", b"beta": b"beta-value",
                           b"gamma": 3},
                           plainPython(_LaunchDictionary(self.testDict)))


    def test_plainPythonNested(self):
        """
        L{plainPython} will convert a L{_LaunchDictionary} containing another
        L{_LaunchDictionary} into a nested Python dictionary.
        """
        otherDict = lib.launch_data_alloc(lib.LAUNCH_DATA_DICTIONARY)
        lib.launch_data_dict_insert(otherDict,
                                    lib.launch_data_new_string("bar"), "foo")
        lib.launch_data_dict_insert(self.testDict, otherDict, "delta")
        self.assertEquals({b"alpha": b"alpha-value", b"beta": b"beta-value",
                           b"gamma": 3, b"delta": {b"foo": b"bar"}},
                           plainPython(_LaunchDictionary(self.testDict)))


class ArrayTests(TestCase):
    """
    Tests for L{_LaunchArray}
    """

    def setUp(self):
        """
        Assemble a test array.
        """
        self.testArray = ffi.gc(
            lib.launch_data_alloc(lib.LAUNCH_DATA_ARRAY),
            lib.launch_data_free
        )

        lib.launch_data_array_set_index(
            self.testArray, lib.launch_data_new_string("test-string-1"), 0
        )
        lib.launch_data_array_set_index(
            self.testArray, lib.launch_data_new_string("another string."), 1
        )
        lib.launch_data_array_set_index(
            self.testArray, lib.launch_data_new_integer(4321), 2
        )


    def test_length(self):
        """
        C{len(_LaunchArray(...))} returns the number of elements in the array.
        """
        self.assertEquals(len(_LaunchArray(self.testArray)), 3)


    def test_indexing(self):
        """
        C{_LaunchArray(...)[n]} returns the n'th element in the array.
        """
        array = _LaunchArray(self.testArray)
        self.assertEquals(array[0], b"test-string-1")
        self.assertEquals(array[1], b"another string.")
        self.assertEquals(array[2], 4321)


    def test_indexTooBig(self):
        """
        C{_LaunchArray(...)[n]}, where C{n} is greater than the length of the
        array, raises an L{IndexError}.
        """
        array = _LaunchArray(self.testArray)
        self.assertRaises(IndexError, lambda: array[3])


    def test_iterating(self):
        """
        Iterating over a C{_LaunchArray} returns each item in sequence.
        """
        array = _LaunchArray(self.testArray)
        i = iter(array)
        self.assertEquals(i.next(), b"test-string-1")
        self.assertEquals(i.next(), b"another string.")
        self.assertEquals(i.next(), 4321)
        self.assertRaises(StopIteration, i.next)


    def test_plainPython(self):
        """
        L{plainPython} converts a L{_LaunchArray} into a Python list.
        """
        array = _LaunchArray(self.testArray)
        self.assertEquals(plainPython(array),
                          [b"test-string-1", b"another string.", 4321])


    def test_plainPythonNested(self):
        """
        L{plainPython} converts a L{_LaunchArray} containing another
        L{_LaunchArray} into a Python list.
        """
        sub = lib.launch_data_alloc(lib.LAUNCH_DATA_ARRAY)
        lib.launch_data_array_set_index(sub, lib.launch_data_new_integer(7), 0)
        lib.launch_data_array_set_index(self.testArray, sub, 3)
        array = _LaunchArray(self.testArray)
        self.assertEqual(plainPython(array), [b"test-string-1",
                                              b"another string.", 4321, [7]])



class SimpleStringConstants(TestCase):
    """
    Tests for bytestring-constants wrapping.
    """

    def test_constant(self):
        """
        C{launchd.constants.LAUNCH_*} will return a bytes object corresponding
        to a constant.
        """
        self.assertEqual(constants.LAUNCH_JOBKEY_SOCKETS,
                         b"Sockets")
        self.assertRaises(AttributeError, getattr, constants,
                          "launch_data_alloc")
        self.assertEquals(constants.LAUNCH_DATA_ARRAY, 2)



class CheckInTests(TestCase):
    """
    Integration tests making sure that actual checkin with launchd results in
    the expected values.
    """

    def setUp(self):
        fp = FilePath(self.mktemp())
        fp.makedirs()
        from twisted.internet.protocol import Protocol, Factory
        from twisted.internet import reactor, defer
        d = defer.Deferred()
        class JustLetMeMoveOn(Protocol):
            def connectionMade(self):
                d.callback(None)
                self.transport.abortConnection()
        f = Factory()
        f.protocol = JustLetMeMoveOn
        port = reactor.listenTCP(0, f, interface="127.0.0.1")
        @self.addCleanup
        def goodbyePort():
            return port.stopListening()
        env = dict(os.environ)
        env["TESTING_PORT"] = repr(port.getHost().port)
        self.stdout = fp.child("stdout.txt")
        self.stderr = fp.child("stderr.txt")
        self.launchLabel = ("org.calendarserver.UNIT-TESTS." +
                            str(os.getpid()) + "." + self.id())
        plist = {
            "Label": self.launchLabel,
            "ProgramArguments": [sys.executable, "-m", __name__, self.id()],
            "EnvironmentVariables": env,
            "KeepAlive": False,
            "StandardOutPath": self.stdout.path,
            "StandardErrorPath": self.stderr.path,
            "Sockets": {
                "Awesome": [{"SecureSocketWithKey": "GeneratedSocket"}]
            },
            "RunAtLoad": True,
        }
        self.job = fp.child("job.plist")
        self.job.setContent(plistlib.writePlistToString(plist))
        os.spawnlp(os.P_WAIT, "launchctl", "launchctl", "load", self.job.path)
        return d


    @staticmethod
    def job_test():
        """
        Do something observable in a subprocess.
        """
        sys.stdout.write("Sample Value.")
        sys.stdout.flush()


    def test_test(self):
        """
        Since this test framework is somewhat finicky, let's just make sure
        that a test can complete.
        """
        self.assertEquals("Sample Value.", self.stdout.getContent())


    @staticmethod
    def job_checkin():
        """
        Check in in the subprocess.
        """
        sys.stdout.write(json.dumps(plainPython(checkin())))


    def test_checkin(self):
        """
        L{checkin} performs launchd checkin and returns a launchd data
        structure.
        """
        d = json.loads(self.stdout.getContent())
        self.assertEqual(d[constants.LAUNCH_JOBKEY_LABEL], self.launchLabel)
        self.assertIsInstance(d, dict)
        sockets = d[constants.LAUNCH_JOBKEY_SOCKETS]
        self.assertEquals(len(sockets), 1)
        self.assertEqual(['Awesome'], sockets.keys())
        awesomeSocket = sockets['Awesome']
        self.assertEqual(len(awesomeSocket), 1)
        self.assertIsInstance(awesomeSocket[0], int)


    @staticmethod
    def job_getFDs():
        """
        Check-in via the high-level C{getLaunchDSocketFDs} API, that just gives
        us listening FDs.
        """
        sys.stdout.write(json.dumps(getLaunchDSocketFDs()))


    def test_getFDs(self):
        """
        L{getLaunchDSocketFDs} returns a Python dictionary mapping the names of
        sockets specified in the property list to lists of integers
        representing FDs.
        """
        sockets = json.loads(self.stdout.getContent())
        self.assertEquals(len(sockets), 1)
        self.assertEqual(['Awesome'], sockets.keys())
        awesomeSocket = sockets['Awesome']
        self.assertEqual(len(awesomeSocket), 1)
        self.assertIsInstance(awesomeSocket[0], int)


    def tearDown(self):
        """
        Un-load the launchd job and report any errors it encountered.
        """
        os.spawnlp(os.P_WAIT, "launchctl",
                   "launchctl", "unload", self.job.path)
        err = self.stderr.getContent()
        if 'Traceback' in err:
            self.fail(err)


