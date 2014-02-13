##
# Copyright (c) 2005-2014 Apple Computer, Inc. All rights reserved.
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

import os
import sys

from twisted.internet import utils
from txweb2.test import test_server
from txweb2 import resource
from txweb2 import http
from txweb2.test import test_http

from twisted.internet.defer import waitForDeferred, deferredGenerator

from twisted.python import util

class Pipeline(test_server.BaseCase):
    """
    Pipelined request
    """
    class TestResource(resource.LeafResource):
        def render(self, req):
            return http.Response(stream="Host:%s, Path:%s" % (req.host, req.path))


    def setUp(self):
        self.root = self.TestResource()


    def chanrequest(self, root, uri, length, headers, method, version, prepath, content):
        self.cr = super(Pipeline, self).chanrequest(root, uri, length, headers, method, version, prepath, content)
        return self.cr


    def test_root(self):

        def _testStreamRead(x):
            self.assertTrue(self.cr.request.stream.length == 0)

        return self.assertResponse(
            (self.root, 'http://host/path', {"content-type": "text/plain", }, "PUT", None, '', "This is some text."),
            (405, {}, None)).addCallback(_testStreamRead)



class SSLPipeline(test_http.SSLServerTest):

    @deferredGenerator
    def testAdvancedWorkingness(self):
        args = ('-u', util.sibpath(__file__, "tworequest_client.py"), "basic",
                str(self.port), self.type)
        d = waitForDeferred(utils.getProcessOutputAndValue(sys.executable,
                                                           args=args,
                                                           env=os.environ))
        yield d
        out, err, code = d.getResult()
        print err
        self.assertEquals(code, 0, "Error output:\n%s" % (err,))
        self.assertEquals(out, "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\nHTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
