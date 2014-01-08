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

from twext.web2.dav.test import util
from txdav.xml import element as davxml
from twext.web2.stream import readStream
from twext.web2.test.test_server import SimpleRequest

class DAVFileTest(util.TestCase):
    def test_renderPrivileges(self):
        """
        Verify that a directory listing includes children which you
        don't have access to.
        """
        request = SimpleRequest(self.site, "GET", "/")

        def setEmptyACL(resource):
            resource.setAccessControlList(davxml.ACL()) # Empty ACL = no access
            return resource

        def renderRoot(_):
            d = request.locateResource("/")
            d.addCallback(lambda r: r.render(request))

            return d

        def assertListing(response):
            data = []
            d = readStream(response.stream, lambda s: data.append(str(s)))
            d.addCallback(lambda _: self.failIf(
                'dir2/' not in "".join(data),
                "'dir2' expected in listing: %r" % (data,)
            ))
            return d

        d = request.locateResource("/dir2")
        d.addCallback(setEmptyACL)
        d.addCallback(renderRoot)
        d.addCallback(assertListing)

        return d
