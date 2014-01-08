##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
Tests for specialized behavior of L{CachingFilePath}
"""
from errno import EINVAL
from os.path import join as pathjoin

from twisted.internet.task import Clock

from twisted.trial.unittest import TestCase

from twext.python.filepath import CachingFilePath

# Cheat and pull in the Twisted test cases for FilePath.  XXX: Twisteds should
# provide a supported way of doing this for exported interfaces.  Also, it
# should export IFilePath. --glyph

from twisted.test.test_paths import FilePathTestCase

class BaseVerification(FilePathTestCase):
    """
    Make sure that L{CachingFilePath} doesn't break the contracts that
    L{FilePath} tries to provide.
    """

    def setUp(self):
        """
        Set up the test case to set the base attributes to point at
        L{AbstractFilePathTestCase}.
        """
        FilePathTestCase.setUp(self)
        self.root = CachingFilePath(self.root.path)
        self.path = CachingFilePath(self.path.path)



class EINVALTestCase(TestCase):
    """
    Sometimes, L{os.listdir} will raise C{EINVAL}.  This is a transient error,
    and L{CachingFilePath.listdir} should work around it by retrying the
    C{listdir} operation until it succeeds.
    """

    def setUp(self):
        """
        Create a L{CachingFilePath} for the test to use.
        """
        self.cfp = CachingFilePath(self.mktemp())
        self.clock = Clock()
        self.cfp._sleep = self.clock.advance


    def test_testValidity(self):
        """
        If C{listdir} is replaced on a L{CachingFilePath}, we should be able to
        observe exceptions raised by the replacement.  This verifies that the
        test patching done here is actually testing something.
        """
        class CustomException(Exception): "Just for testing."
        def blowUp(dirname):
            raise CustomException()
        self.cfp._listdir = blowUp
        self.assertRaises(CustomException, self.cfp.listdir)
        self.assertRaises(CustomException, self.cfp.children)


    def test_retryLoop(self):
        """
        L{CachingFilePath} should catch C{EINVAL} and respond by retrying the
        C{listdir} operation until it succeeds.
        """
        calls = []
        def raiseEINVAL(dirname):
            calls.append(dirname)
            if len(calls) < 5:
                raise OSError(EINVAL, "This should be caught by the test.")
            return ['a', 'b', 'c']
        self.cfp._listdir = raiseEINVAL
        self.assertEquals(self.cfp.listdir(), ['a', 'b', 'c'])
        self.assertEquals(self.cfp.children(), [
                CachingFilePath(pathjoin(self.cfp.path, 'a')),
                CachingFilePath(pathjoin(self.cfp.path, 'b')),
                CachingFilePath(pathjoin(self.cfp.path, 'c')),])


    def requireTimePassed(self, filenames):
        """
        Create a replacement for listdir() which only fires after a certain
        amount of time.
        """
        self.calls = []
        def thunk(dirname):
            now = self.clock.seconds()
            if now < 20.0:
                self.calls.append(now)
                raise OSError(EINVAL, "Not enough time has passed yet.")
            else:
                return filenames
        self.cfp._listdir = thunk


    def assertRequiredTimePassed(self):
        """
        Assert that calls to the simulated time.sleep() installed by
        C{requireTimePassed} have been invoked the required number of times.
        """
        # Waiting should be growing by *2 each time until the additional wait
        # exceeds BACKOFF_MAX (5), at which point we should wait for 5s each
        # time.
        def cumulative(values):
            current = 0.0
            for value in values:
                current += value
                yield current

        self.assertEquals(self.calls,
                          list(cumulative(
                    [0.0, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 5.0, 5.0])))


    def test_backoff(self):
        """
        L{CachingFilePath} will wait for an increasing interval up to
        C{BACKOFF_MAX} between calls to listdir().
        """
        self.requireTimePassed(['a', 'b', 'c'])
        self.assertEquals(self.cfp.listdir(), ['a', 'b', 'c'])


    def test_siblingExtensionSearch(self):
        """
        L{FilePath.siblingExtensionSearch} is unfortunately not implemented in
        terms of L{FilePath.listdir}, so we need to verify that it will also
        retry.
        """
        filenames = [self.cfp.basename()+'.a',
                     self.cfp.basename() + '.b',
                     self.cfp.basename() + '.c']
        siblings = map(self.cfp.sibling, filenames)
        for sibling in siblings:
            sibling.touch()
        self.requireTimePassed(filenames)
        self.assertEquals(self.cfp.siblingExtensionSearch("*"),
                          siblings[0])
        self.assertRequiredTimePassed()
