##
# Copyright (c) 2012 Apple Computer, Inc. All rights reserved.
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

import collections
from twext.web2.dav.auth import AuthenticationWrapper
import twext.web2.dav.test.util

class AutoWrapperTestCase(twext.web2.dav.test.util.TestCase):

    def test_basicAuthPrevention(self):
        """
        Ensure authentication factories which are not safe to use over an
        "unencrypted wire" are not advertised when an insecure (i.e. non-SSL
        connection is made.
        """
        FakeFactory = collections.namedtuple("FakeFactory", ("scheme,"))
        wireEncryptedfactories = [FakeFactory("basic"), FakeFactory("digest"), FakeFactory("xyzzy")]
        wireUnencryptedfactories = [FakeFactory("digest"), FakeFactory("xyzzy")]

        class FakeChannel(object):
            def __init__(self, secure):
                self.secure = secure
            def getHostInfo(self):
                return "ignored", self.secure

        class FakeRequest(object):
            def __init__(self, secure):
                self.portal = None
                self.loginInterfaces = None
                self.credentialFactories = None
                self.chanRequest = FakeChannel(secure)

        wrapper = AuthenticationWrapper(None, None,
            wireEncryptedfactories, wireUnencryptedfactories, None)
        req = FakeRequest(True) # Connection is over SSL
        wrapper.hook(req)
        self.assertEquals(
            set(req.credentialFactories.keys()),
            set(["basic", "digest", "xyzzy"])
        )
        req = FakeRequest(False) # Connection is not over SSL
        wrapper.hook(req)
        self.assertEquals(
            set(req.credentialFactories.keys()),
            set(["digest", "xyzzy"])
        )
