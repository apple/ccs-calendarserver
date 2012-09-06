##
# Copyright (c) 2005-2012 Apple Computer, Inc. All rights reserved.
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

from twisted.internet.defer import DeferredList, waitForDeferred, deferredGenerator, succeed
from twisted.cred.portal import Portal
from twext.web2 import responsecode
from twext.web2.http import HTTPError
from twext.web2.auth import basic
from twext.web2.server import Site
from txdav.xml import element as davxml
from twext.web2.dav.resource import DAVResource, AccessDeniedError, \
    DAVPrincipalResource, DAVPrincipalCollectionResource, davPrivilegeSet
from twext.web2.dav.auth import TwistedPasswordProperty, DavRealm, TwistedPropertyChecker, IPrincipal, AuthenticationWrapper
from twext.web2.test.test_server import SimpleRequest
from twext.web2.dav.test.util import InMemoryPropertyStore
import twext.web2.dav.test.util

class TestCase(twext.web2.dav.test.util.TestCase):
    def setUp(self):
        twext.web2.dav.test.util.TestCase.setUp(self)
        TestResource._cachedPropertyStores = {}

class GenericDAVResource(TestCase):
    def setUp(self):
        TestCase.setUp(self)

        rootresource = TestResource(None, {
            "file1": TestResource("/file1"),
            "file2": AuthAllResource("/file2"),
            "dir1": TestResource("/dir1/", {
                "subdir1": TestResource("/dir1/subdir1/",{})
            }),
            "dir2": AuthAllResource("/dir2/", {
                "file1": TestResource("/dir2/file1"),
                "file2": TestResource("/dir2/file2"),
                "subdir1": TestResource("/dir2/subdir1/", {
                    "file1": TestResource("/dir2/subdir1/file1"),
                    "file2": TestResource("/dir2/subdir1/file2")
                })
            })
        })

        self.site = Site(rootresource)

    def test_findChildren(self):
        """
        This test asserts that we have:
        1) not found any unexpected children
        2) found all expected children

        It does this for all depths C{"0"}, C{"1"}, and C{"infintiy"}
        """
        expected_children = {
            "0": [],
            "1": [
                "/file1",
                "/file2",
                "/dir1/",
                "/dir2/",
            ],
            "infinity": [
                "/file1",
                "/file2",
                "/dir1/",
                "/dir1/subdir1/",
                "/dir2/",
                "/dir2/file1",
                "/dir2/file2",
                "/dir2/subdir1/",
                "/dir2/subdir1/file1",
                "/dir2/subdir1/file2",
            ],
        }

        request = SimpleRequest(self.site, "GET", "/")
        resource = waitForDeferred(request.locateResource("/"))
        yield resource
        resource = resource.getResult()

        def checkChildren(resource, uri):
            self.assertEquals(uri, resource.uri)

            if uri not in expected_children[depth]:
                unexpected_children.append(uri)

            else:
                found_children.append(uri)

        for depth in ["0", "1", "infinity"]:
            found_children = []
            unexpected_children = []

            fc = resource.findChildren(depth, request, checkChildren)
            completed = waitForDeferred(fc)
            yield completed
            completed.getResult()

            self.assertEquals(
                unexpected_children, [],
                "Found unexpected children: %r" % (unexpected_children,)
            )

            expected_children[depth].sort()
            found_children.sort()

            self.assertEquals(expected_children[depth], found_children)

    test_findChildren = deferredGenerator(test_findChildren)

    def test_findChildrenWithPrivileges(self):
        """
        This test revokes read privileges for the C{"/file2"} and C{"/dir2/"}
        resource to verify that we can not find them giving our unauthenticated
        privileges.
        """
        
        expected_children = [
            "/file1",
            "/dir1/",
        ]

        request = SimpleRequest(self.site, "GET", "/")
        resource = waitForDeferred(request.locateResource("/"))
        yield resource
        resource = resource.getResult()

        def checkChildren(resource, uri):
            self.assertEquals(uri, resource.uri)

            if uri not in expected_children:
                unexpected_children.append(uri)
            else:
                found_children.append(uri)

        found_children = []
        unexpected_children = []

        privileges = waitForDeferred(resource.currentPrivileges(request))
        yield privileges
        privileges = privileges.getResult()

        fc = resource.findChildren("1", request, checkChildren, privileges)
        completed = waitForDeferred(fc)
        yield completed
        completed.getResult()

        self.assertEquals(
            unexpected_children, [],
            "Found unexpected children: %r" % (unexpected_children,)
        )

        expected_children.sort()
        found_children.sort()

        self.assertEquals(expected_children, found_children)

    test_findChildrenWithPrivileges = deferredGenerator(test_findChildrenWithPrivileges)

    def test_findChildrenCallbackRaises(self):
        """
        Verify that when the user callback raises an exception
        the completion deferred returned by findChildren errbacks

        TODO: Verify that the user callback doesn't get called subsequently
        """

        def raiseOnChild(resource, uri):
            raise Exception("Oh no!")

        def findChildren(resource):
            return self.assertFailure(
                resource.findChildren("infinity", request, raiseOnChild),
                Exception
            )
        
        request = SimpleRequest(self.site, "GET", "/")
        d = request.locateResource("/").addCallback(findChildren)

        return d

class AccessTests(TestCase):
    def setUp(self):
        TestCase.setUp(self)

        gooduser = TestDAVPrincipalResource("/users/gooduser")
        gooduser.writeDeadProperty(TwistedPasswordProperty("goodpass"))

        baduser = TestDAVPrincipalResource("/users/baduser")
        baduser.writeDeadProperty(TwistedPasswordProperty("badpass"))

        rootresource = TestPrincipalsCollection("/", {
                "users": TestResource("/users/",
                                      {"gooduser": gooduser,
                                       "baduser": baduser})
            })

        protected = TestResource(
            "/protected", principalCollections=[rootresource])

        protected.setAccessControlList(davxml.ACL(
            davxml.ACE(
                davxml.Principal(davxml.HRef("/users/gooduser")),
                davxml.Grant(davxml.Privilege(davxml.All())),
                davxml.Protected()
            )
        ))

        rootresource.children["protected"] = protected

        portal = Portal(DavRealm())
        portal.registerChecker(TwistedPropertyChecker())

        credentialFactories = (basic.BasicCredentialFactory(""),)

        loginInterfaces = (IPrincipal,)

        self.rootresource = rootresource
        self.site = Site(AuthenticationWrapper(
            self.rootresource,
            portal,
            credentialFactories,
            loginInterfaces,
        ))

    def checkSecurity(self, request):
        """
        Locate the resource named by the given request's URI, then authorize it
        for the 'Read' permission.
        """
        d = request.locateResource(request.uri)
        d.addCallback(lambda r: r.authorize(request, (davxml.Read(),)))
        return d

    def assertErrorResponse(self, error, expectedcode, otherExpectations=lambda err: None):
        self.assertEquals(error.response.code, expectedcode)
        otherExpectations(error)

    def test_checkPrivileges(self):
        """
        DAVResource.checkPrivileges()
        """
        ds = []

        authAllResource = AuthAllResource()
        requested_access = (davxml.All(),)

        site = Site(authAllResource)

        def expectError(failure):
            failure.trap(AccessDeniedError)
            errors = failure.value.errors

            self.failUnless(len(errors) == 1)

            subpath, denials = errors[0]

            self.failUnless(subpath is None)
            self.failUnless(
                tuple(denials) == requested_access,
                "%r != %r" % (tuple(denials), requested_access)
            )

        def expectOK(result):
            self.failUnlessEquals(result, None)

        def _checkPrivileges(resource):
            d = resource.checkPrivileges(request, requested_access)
            return d

        # No auth; should deny
        request = SimpleRequest(site, "GET", "/")
        d = request.locateResource("/").addCallback(_checkPrivileges).addErrback(expectError)
        ds.append(d)

        # Has auth; should allow
        request = SimpleRequest(site, "GET", "/")
        request.authnUser = davxml.Principal(davxml.HRef("/users/d00d"))
        request.authzUser = davxml.Principal(davxml.HRef("/users/d00d"))
        d = request.locateResource("/")
        d.addCallback(_checkPrivileges)
        d.addCallback(expectOK)
        ds.append(d)

        return DeferredList(ds)


    def test_authorize(self):
        """
        Authorizing a known user with the correct password will not raise an
        exception, indicating that the user is properly authorized given their
        credentials.
        """
        request = SimpleRequest(self.site, "GET", "/protected")
        request.headers.setHeader(
            "authorization",
            ("basic", "gooduser:goodpass".encode("base64")))
        return self.checkSecurity(request)

    def test_badUsernameOrPassword(self):
        request = SimpleRequest(self.site, "GET", "/protected")
        request.headers.setHeader(
            "authorization",
            ("basic", "gooduser:badpass".encode("base64"))
        )
        d = self.assertFailure(self.checkSecurity(request), HTTPError)
        def expectWwwAuth(err):
            self.failUnless(err.response.headers.hasHeader("WWW-Authenticate"),
                            "No WWW-Authenticate header present.")
        d.addCallback(self.assertErrorResponse, responsecode.UNAUTHORIZED, expectWwwAuth)
        return d


    def test_lacksPrivileges(self):
        request = SimpleRequest(self.site, "GET", "/protected")
        request.headers.setHeader(
            "authorization",
            ("basic", "baduser:badpass".encode("base64"))
        )
        d = self.assertFailure(self.checkSecurity(request), HTTPError)
        d.addCallback(self.assertErrorResponse, responsecode.FORBIDDEN)
        return d


##
# Utilities
##

class TestResource (DAVResource):
    """A simple test resource used for creating trees of
    DAV Resources
    """
    _cachedPropertyStores = {}

    acl = davxml.ACL(
        davxml.ACE(
            davxml.Principal(davxml.All()),
            davxml.Grant(davxml.Privilege(davxml.All())),
            davxml.Protected(),
        )
    )

    def __init__(self, uri=None, children=None, principalCollections=()):
        """
        @param uri: A string respresenting the URI of the given resource
        @param children: a dictionary of names to Resources
        """
        DAVResource.__init__(self, principalCollections=principalCollections)
        self.children = children
        self.uri = uri

    def deadProperties(self):
        """
        Retrieve deadProperties from a special place in memory
        """
        if not hasattr(self, "_dead_properties"):
            dp = TestResource._cachedPropertyStores.get(self.uri)
            if dp is None:
                TestResource._cachedPropertyStores[self.uri] = InMemoryPropertyStore(self)
                dp = TestResource._cachedPropertyStores[self.uri]
            self._dead_properties = dp
        return self._dead_properties

    def isCollection(self):
        return self.children is not None

    def listChildren(self):
        return self.children.keys()

    def supportedPrivileges(self, request):
        return succeed(davPrivilegeSet)

    def currentPrincipal(self, request):
        if hasattr(request, "authzUser"):
            return request.authzUser
        else:
            return davxml.Principal(davxml.Unauthenticated())

    def locateChild(self, request, segments):
        child = segments[0]
        if child == "":
            return self, segments[1:]
        elif child in self.children:
            return self.children[child], segments[1:]
        else:
            raise HTTPError(404)

    def setAccessControlList(self, acl):
        self.acl = acl

    def accessControlList(self, request, **kwargs):
        return succeed(self.acl)



class TestPrincipalsCollection(DAVPrincipalCollectionResource, TestResource):
    """
    A full implementation of L{IDAVPrincipalCollectionResource}, implemented as
    a L{TestResource} which assumes a single L{TestResource} child named
    'users'.
    """

    def __init__(self, url, children):
        DAVPrincipalCollectionResource.__init__(self, url)
        TestResource.__init__(self, url, children, principalCollections=(self,))


    def principalForUser(self, user):
        """
        @see L{IDAVPrincipalCollectionResource.principalForUser}.
        """
        return self.principalForShortName('users', user)


    def principalForAuthID(self, creds):
        """
        Retrieve the principal for the authentication identifier from a set of
        credentials.

        Note that although this method is not actually invoked anywhere in
        web2.dav, this test class is currently imported by CalendarServer,
        which requires this method.

        @param creds: credentials which identify a user

        @type creds: L{twisted.cred.credentials.IUsernameHashedPassword} or
            L{twisted.cred.credentials.IUsernamePassword}

        @return: a DAV principal resource representing a user.

        @rtype: L{IDAVPrincipalResource} or C{NoneType}
        """
        # XXX either move this to CalendarServer entirely or document it on
        # IDAVPrincipalCollectionResource
        return self.principalForShortName('users', creds.username)


    def principalForShortName(self, type, shortName):
        """
        Retrieve the principal of a given type from this resource.

        Note that although this method is not actually invoked anywhere (aside
        from test methods) in web2.dav, this test class is currently imported by
        CalendarServer, which requires this method.

        @param: a short string (such as 'users' or 'groups') identifying both
            the principal type, and the name of a resource in the 'children'
            dictionary, which itself is a L{TestResource} with
            L{IDAVPrincipalCollectionResource} children.

        @return: a DAV principal resource of the given type with the given
            name.

        @rtype: L{IDAVPrincipalResource} or C{NoneType}
        """
        # XXX either move this to CalendarServer entirely or document it on
        # IDAVPrincipalCollectionResource
        typeResource = self.children.get(type, None)
        user = None
        if typeResource:
            user = typeResource.children.get(shortName, None)

        return user



class AuthAllResource (TestResource):
    """
    Give Authenticated principals all privileges and deny everyone else.
    """
    acl = davxml.ACL(
        davxml.ACE(
            davxml.Principal(davxml.Authenticated()),
            davxml.Grant(davxml.Privilege(davxml.All())),
            davxml.Protected(),
        )
    )

    
class TestDAVPrincipalResource(DAVPrincipalResource, TestResource):
    """
    Get deadProperties from TestResource
    """
    def principalURL(self):
        return self.uri
