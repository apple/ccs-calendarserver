##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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

from txweb2 import responsecode
from txweb2.iweb import IResponse
from txweb2.stream import FileStream

import txweb2.dav.test.util
from txweb2.test.test_server import SimpleRequest
from txweb2.dav.test.util import Site
from txdav.xml import element as davxml
import os

class QuotaBase(txweb2.dav.test.util.TestCase):

    def createDocumentRoot(self):
        docroot = self.mktemp()
        os.mkdir(docroot)
        rootresource = self.resource_class(docroot)
        rootresource.setAccessControlList(self.grantInherit(davxml.All()))
        self.site = Site(rootresource)
        self.site.resource.setQuotaRoot(None, 100000)
        return docroot


    def checkQuota(self, value):
        def _defer(quota):
            self.assertEqual(quota, value)

        d = self.site.resource.currentQuotaUse(None)
        d.addCallback(_defer)
        return d

class QuotaEmpty(QuotaBase):

    def test_Empty_Quota(self):

        return self.checkQuota(0)

class QuotaPUT(QuotaBase):

    def test_Quota_PUT(self):
        """
        Quota change on PUT
        """
        dst_uri = "/dst"

        def checkResult(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("Incorrect response code for PUT (%s != %s)"
                          % (response.code, responsecode.CREATED))

            return self.checkQuota(100)

        request = SimpleRequest(self.site, "PUT", dst_uri)
        request.stream = FileStream(file(os.path.join(os.path.dirname(__file__), "data", "quota_100.txt"), "rb"))
        return self.send(request, checkResult)

class QuotaDELETE(QuotaBase):

    def test_Quota_DELETE(self):
        """
        Quota change on DELETE
        """
        dst_uri = "/dst"

        def checkPUTResult(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("Incorrect response code for PUT (%s != %s)"
                          % (response.code, responsecode.CREATED))

            def doDelete(_ignore):
                def checkDELETEResult(response):
                    response = IResponse(response)

                    if response.code != responsecode.NO_CONTENT:
                        self.fail("Incorrect response code for PUT (%s != %s)"
                                  % (response.code, responsecode.NO_CONTENT))

                    return self.checkQuota(0)

                request = SimpleRequest(self.site, "DELETE", dst_uri)
                return self.send(request, checkDELETEResult)

            d = self.checkQuota(100)
            d.addCallback(doDelete)
            return d

        request = SimpleRequest(self.site, "PUT", dst_uri)
        request.stream = FileStream(file(os.path.join(os.path.dirname(__file__), "data", "quota_100.txt"), "rb"))
        return self.send(request, checkPUTResult)

class OverQuotaPUT(QuotaBase):

    def test_Quota_PUT(self):
        """
        Quota change on PUT
        """
        dst_uri = "/dst"

        self.site.resource.setQuotaRoot(None, 90)

        def checkResult(response):
            response = IResponse(response)

            if response.code != responsecode.INSUFFICIENT_STORAGE_SPACE:
                self.fail("Incorrect response code for PUT (%s != %s)"
                          % (response.code, responsecode.INSUFFICIENT_STORAGE_SPACE))

            return self.checkQuota(0)

        request = SimpleRequest(self.site, "PUT", dst_uri)
        request.stream = FileStream(file(os.path.join(os.path.dirname(__file__), "data", "quota_100.txt"), "rb"))
        return self.send(request, checkResult)

class QuotaOKAdjustment(QuotaBase):

    def test_Quota_OK_Adjustment(self):
        """
        Quota adjustment OK
        """
        dst_uri = "/dst"

        def checkPUTResult(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("Incorrect response code for PUT (%s != %s)"
                          % (response.code, responsecode.CREATED))

            def doOKAdjustment(_ignore):
                def checkAdjustmentResult(_ignore):
                    return self.checkQuota(10)

                d = self.site.resource.quotaSizeAdjust(None, -90)
                d.addCallback(checkAdjustmentResult)
                return d

            d = self.checkQuota(100)
            d.addCallback(doOKAdjustment)
            return d

        request = SimpleRequest(self.site, "PUT", dst_uri)
        request.stream = FileStream(file(os.path.join(os.path.dirname(__file__), "data", "quota_100.txt"), "rb"))
        return self.send(request, checkPUTResult)

class QuotaBadAdjustment(QuotaBase):

    def test_Quota_Bad_Adjustment(self):
        """
        Quota adjustment too much
        """
        dst_uri = "/dst"

        def checkPUTResult(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("Incorrect response code for PUT (%s != %s)"
                          % (response.code, responsecode.CREATED))

            def doBadAdjustment(_ignore):
                def checkAdjustmentResult(_ignore):
                    return self.checkQuota(100)

                d = self.site.resource.quotaSizeAdjust(None, -200)
                d.addCallback(checkAdjustmentResult)
                return d

            d = self.checkQuota(100)
            d.addCallback(doBadAdjustment)
            return d

        request = SimpleRequest(self.site, "PUT", dst_uri)
        request.stream = FileStream(file(os.path.join(os.path.dirname(__file__), "data", "quota_100.txt"), "rb"))
        return self.send(request, checkPUTResult)
