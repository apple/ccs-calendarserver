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

from twisted.cred.portal import Portal

from twext.web2 import responsecode
from twext.web2.auth import basic
from twext.web2.stream import MemoryStream
from twext.web2.dav.util import davXMLFromStream
from twext.web2.dav.auth import TwistedPasswordProperty, IPrincipal, DavRealm, TwistedPropertyChecker, AuthenticationWrapper
from twext.web2.dav.fileop import rmdir
from twext.web2.test.test_server import SimpleRequest
from twext.web2.dav.test.util import Site, serialize
from twext.web2.dav.test.test_resource import \
    TestDAVPrincipalResource, TestPrincipalsCollection

from txdav.xml import element

import twext.web2.dav.test.util

class ACL(twext.web2.dav.test.util.TestCase):
    """
    RFC 3744 (WebDAV ACL) tests.
    """
    def createDocumentRoot(self):
        docroot = self.mktemp()
        os.mkdir(docroot)

        userResource = TestDAVPrincipalResource("/principals/users/user01")
        userResource.writeDeadProperty(TwistedPasswordProperty("user01"))

        principalCollection = TestPrincipalsCollection(
            "/principals/",
            children={"users": TestPrincipalsCollection(
                    "/principals/users/",
                    children={"user01": userResource})})

        rootResource = self.resource_class(
            docroot, principalCollections=(principalCollection,))

        portal = Portal(DavRealm())
        portal.registerChecker(TwistedPropertyChecker())

        credentialFactories = (basic.BasicCredentialFactory(""),)

        loginInterfaces = (IPrincipal,)

        self.site = Site(AuthenticationWrapper(
            rootResource,
            portal,
            credentialFactories,
            credentialFactories,
            loginInterfaces
        ))

        rootResource.setAccessControlList(self.grant(element.All()))

        for name, acl in (
            ("none"       , self.grant()),
            ("read"       , self.grant(element.Read())),
            ("read-write" , self.grant(element.Read(), element.Write())),
            ("unlock"     , self.grant(element.Unlock())),
            ("all"        , self.grant(element.All())),
        ):
            filename = os.path.join(docroot, name)
            if not os.path.isfile(filename):
                file(filename, "w").close()
            resource = self.resource_class(filename)
            resource.setAccessControlList(acl)

        for name, acl in (
            ("nobind" , self.grant()),
            ("bind"   , self.grant(element.Bind())),
            ("unbind" , self.grant(element.Bind(), element.Unbind())),
        ):
            dirname = os.path.join(docroot, name)
            if not os.path.isdir(dirname):
                os.mkdir(dirname)
            resource = self.resource_class(dirname)
            resource.setAccessControlList(acl)
        return docroot


    def restore(self):
        # Get rid of whatever messed up state the test has now so that we'll
        # get a fresh docroot.  This isn't very cool; tests should be doing
        # less so that they don't need a fresh copy of this state.
        if hasattr(self, "_docroot"):
            rmdir(self._docroot)
            del self._docroot

    def test_COPY_MOVE_source(self):
        """
        Verify source access controls during COPY and MOVE.
        """
        def work():
            dst_path = os.path.join(self.docroot, "copy_dst")
            dst_uri = "/" + os.path.basename(dst_path)

            for src, status in (
                ("nobind", responsecode.FORBIDDEN),
                ("bind",   responsecode.FORBIDDEN),
                ("unbind", responsecode.CREATED),
            ):
                src_path = os.path.join(self.docroot, "src_" + src)
                src_uri = "/" + os.path.basename(src_path)
                if not os.path.isdir(src_path):
                    os.mkdir(src_path)
                src_resource = self.resource_class(src_path)
                src_resource.setAccessControlList({
                    "nobind": self.grant(),
                    "bind"  : self.grant(element.Bind()),
                    "unbind": self.grant(element.Bind(), element.Unbind())
                }[src])
                for name, acl in (
                    ("none"       , self.grant()),
                    ("read"       , self.grant(element.Read())),
                    ("read-write" , self.grant(element.Read(), element.Write())),
                    ("unlock"     , self.grant(element.Unlock())),
                    ("all"        , self.grant(element.All())),
                ):
                    filename = os.path.join(src_path, name)
                    if not os.path.isfile(filename):
                        file(filename, "w").close()
                    self.resource_class(filename).setAccessControlList(acl)

                for method in ("COPY", "MOVE"):
                    for name, code in (
                        ("none"       , {"COPY": responsecode.FORBIDDEN, "MOVE": status}[method]),
                        ("read"       , {"COPY": responsecode.CREATED,   "MOVE": status}[method]),
                        ("read-write" , {"COPY": responsecode.CREATED,   "MOVE": status}[method]),
                        ("unlock"     , {"COPY": responsecode.FORBIDDEN, "MOVE": status}[method]),
                        ("all"        , {"COPY": responsecode.CREATED,   "MOVE": status}[method]),
                    ):
                        path = os.path.join(src_path, name)
                        uri = src_uri + "/" + name
    
                        request = SimpleRequest(self.site, method, uri)
                        request.headers.setHeader("destination", dst_uri)
                        _add_auth_header(request)
    
                        def test(response, code=code, path=path):
                            if os.path.isfile(dst_path):
                                os.remove(dst_path)
    
                            if response.code != code:
                                return self.oops(request, response, code, method, name)
    
                        yield (request, test)

        return serialize(self.send, work())

    def test_COPY_MOVE_dest(self):
        """
        Verify destination access controls during COPY and MOVE.
        """
        def work():
            src_path = os.path.join(self.docroot, "read")
            uri = "/" + os.path.basename(src_path)

            for method in ("COPY", "MOVE"):
                for name, code in (
                    ("nobind" , responsecode.FORBIDDEN),
                    ("bind"   , responsecode.CREATED),
                    ("unbind" , responsecode.CREATED),
                ):
                    dst_parent_path = os.path.join(self.docroot, name)
                    dst_path = os.path.join(dst_parent_path, "dst")

                    request = SimpleRequest(self.site, method, uri)
                    request.headers.setHeader("destination", "/" + name + "/dst")
                    _add_auth_header(request)

                    def test(response, code=code, dst_path=dst_path):
                        if os.path.isfile(dst_path):
                            os.remove(dst_path)

                        if response.code != code:
                            return self.oops(request, response, code, method, name)

                    yield (request, test)
                    self.restore()

        return serialize(self.send, work())

    def test_DELETE(self):
        """
        Verify access controls during DELETE.
        """
        def work():
            for name, code in (
                ("nobind" , responsecode.FORBIDDEN),
                ("bind"   , responsecode.FORBIDDEN),
                ("unbind" , responsecode.NO_CONTENT),
            ):
                collection_path = os.path.join(self.docroot, name)
                path = os.path.join(collection_path, "dst")

                file(path, "w").close()

                request = SimpleRequest(self.site, "DELETE", "/" + name + "/dst")
                _add_auth_header(request)

                def test(response, code=code, path=path):
                    if response.code != code:
                        return self.oops(request, response, code, "DELETE", name)

                yield (request, test)

        return serialize(self.send, work())

    def test_UNLOCK(self):
        """
        Verify access controls during UNLOCK of unowned lock.
        """
        raise NotImplementedError()

    test_UNLOCK.todo = "access controls on UNLOCK unimplemented"

    def test_MKCOL_PUT(self):
        """
        Verify access controls during MKCOL.
        """
        for method in ("MKCOL", "PUT"):
            def work():
                for name, code in (
                    ("nobind" , responsecode.FORBIDDEN),
                    ("bind"   , responsecode.CREATED),
                    ("unbind" , responsecode.CREATED),
                ):
                    collection_path = os.path.join(self.docroot, name)
                    path = os.path.join(collection_path, "dst")

                    if os.path.isfile(path):
                        os.remove(path)
                    elif os.path.isdir(path):
                        os.rmdir(path)

                    request = SimpleRequest(self.site, method, "/" + name + "/dst")
                    _add_auth_header(request)

                    def test(response, code=code, path=path):
                        if response.code != code:
                            return self.oops(request, response, code, method, name)

                    yield (request, test)

        return serialize(self.send, work())

    def test_PUT_exists(self):
        """
        Verify access controls during PUT of existing file.
        """
        def work():
            for name, code in (
                ("none"       , responsecode.FORBIDDEN),
                ("read"       , responsecode.FORBIDDEN),
                ("read-write" , responsecode.NO_CONTENT),
                ("unlock"     , responsecode.FORBIDDEN),
                ("all"        , responsecode.NO_CONTENT),
            ):
                path = os.path.join(self.docroot, name)

                request = SimpleRequest(self.site, "PUT", "/" + name)
                _add_auth_header(request)

                def test(response, code=code, path=path):
                    if response.code != code:
                        return self.oops(request, response, code, "PUT", name)

                yield (request, test)

        return serialize(self.send, work())

    def test_PROPFIND(self):
        """
        Verify access controls during PROPFIND.
        """
        raise NotImplementedError()

    test_PROPFIND.todo = "access controls on PROPFIND unimplemented"

    def test_PROPPATCH(self):
        """
        Verify access controls during PROPPATCH.
        """
        def work():
            for name, code in (
                ("none"       , responsecode.FORBIDDEN),
                ("read"       , responsecode.FORBIDDEN),
                ("read-write" , responsecode.MULTI_STATUS),
                ("unlock"     , responsecode.FORBIDDEN),
                ("all"        , responsecode.MULTI_STATUS),
            ):
                path = os.path.join(self.docroot, name)

                request = SimpleRequest(self.site, "PROPPATCH", "/" + name)
                request.stream = MemoryStream(
                    element.WebDAVDocument(element.PropertyUpdate()).toxml()
                )
                _add_auth_header(request)

                def test(response, code=code, path=path):
                    if response.code != code:
                        return self.oops(request, response, code, "PROPPATCH", name)

                yield (request, test)

        return serialize(self.send, work())

    def test_GET_REPORT(self):
        """
        Verify access controls during GET and REPORT.
        """
        def work():
            for method in ("GET", "REPORT"):
                if method == "GET":
                    ok = responsecode.OK
                elif method == "REPORT":
                    ok = responsecode.MULTI_STATUS
                else:
                    raise AssertionError("We shouldn't be here.  (method = %r)" % (method,))

                for name, code in (
                    ("none"       , responsecode.FORBIDDEN),
                    ("read"       , ok),
                    ("read-write" , ok),
                    ("unlock"     , responsecode.FORBIDDEN),
                    ("all"        , ok),
                ):
                    path = os.path.join(self.docroot, name)

                    request = SimpleRequest(self.site, method, "/" + name)
                    if method == "REPORT":
                        request.stream = MemoryStream(element.PrincipalPropertySearch().toxml())

                    _add_auth_header(request)

                    def test(response, code=code, path=path):
                        if response.code != code:
                            return self.oops(request, response, code, method, name)

                    yield (request, test)

        return serialize(self.send, work())

    def oops(self, request, response, code, method, name):
        def gotResponseData(doc):
            if doc is None:
                doc_xml = None
            else:
                doc_xml = doc.toxml()
    
            def fail(acl):
                self.fail("Incorrect status code %s (!= %s) for %s of resource %s with %s ACL: %s\nACL: %s"
                          % (response.code, code, method, request.uri, name, doc_xml, acl.toxml()))


            def getACL(resource):
                return resource.accessControlList(request)

            d = request.locateResource(request.uri)
            d.addCallback(getACL)
            d.addCallback(fail)
            return d

        d = davXMLFromStream(response.stream)
        d.addCallback(gotResponseData)
        return d

def _add_auth_header(request):
    request.headers.setHeader(
        "authorization",
        ("basic", "user01:user01".encode("base64"))
    )
