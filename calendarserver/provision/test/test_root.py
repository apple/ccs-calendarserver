##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

import os

from twisted.cred.portal import Portal
from twisted.internet.defer import inlineCallbacks, maybeDeferred, returnValue

from twext.web2 import http_headers
from twext.web2 import responsecode
from twext.web2 import server
from twext.web2.auth import basic
from twext.web2.dav import auth
from txdav.xml import element as davxml
from twext.web2.http import HTTPError
from twext.web2.iweb import IResponse
from twext.web2.test.test_server import SimpleRequest

from twistedcaldav.test.util import TestCase
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile, augmentsFile

from calendarserver.provision.root import RootResource
from twistedcaldav.directory import augment
from twistedcaldav.config import config

class FakeCheckSACL(object):
    def __init__(self, sacls=None):
        self.sacls = sacls or {}

    def __call__(self, username, service):
        if service not in self.sacls:
            return 1

        if username in self.sacls[service]:
            return 0

        return 1

class RootTests(TestCase):

    def setUp(self):
        super(RootTests, self).setUp()

        self.docroot = self.mktemp()
        os.mkdir(self.docroot)

        RootResource.CheckSACL = FakeCheckSACL(sacls={"calendar": ["dreid"]})

        directory = XMLDirectoryService(
            {
                "xmlFile" : xmlFile,
                "augmentService" :
                    augment.AugmentXMLDB(xmlFiles=(augmentsFile.path,))
            }
        )

        principals = DirectoryPrincipalProvisioningResource(
            "/principals/",
            directory
        )

        root = RootResource(self.docroot, principalCollections=[principals])

        root.putChild("principals",
                      principals)

        portal = Portal(auth.DavRealm())
        portal.registerChecker(directory)

        self.root = auth.AuthenticationWrapper(
            root,
            portal,
            credentialFactories=(basic.BasicCredentialFactory("Test realm"),),
            loginInterfaces=(auth.IPrincipal,))

        self.site = server.Site(self.root)



class ComplianceTests(RootTests):
    """
    Tests to verify CalDAV compliance of the root resource.
    """

    @inlineCallbacks
    def issueRequest(self, segments, method="GET"):
        """
        Get a resource from a particular path from the root URI, and return a
        Deferred which will fire with (something adaptable to) an HTTP response
        object.
        """
        request = SimpleRequest(self.site, method, ("/".join([""] + segments)))
        rsrc = self.root
        while segments:
            rsrc, segments = (yield maybeDeferred(
                rsrc.locateChild, request, segments
            ))

        result = yield rsrc.renderHTTP(request)
        returnValue(result)


    @inlineCallbacks
    def test_optionsIncludeCalendar(self):
        """
        OPTIONS request should include a DAV header that mentions the
        addressbook capability.
        """
        response = yield self.issueRequest([""], "OPTIONS")
        self.assertIn("addressbook", response.headers.getHeader("DAV"))



class SACLTests(RootTests):
    
    @inlineCallbacks
    def test_noSacls(self):
        """
        Test the behaviour of locateChild when SACLs are not enabled.

        should return a valid resource
        """
        self.root.resource.useSacls = False

        request = SimpleRequest(self.site,
                                "GET",
                                "/principals/")

        resrc, segments = (yield maybeDeferred(
            self.root.locateChild, request, ["principals"]
        ))

        resrc, segments = (yield maybeDeferred(
            resrc.locateChild, request, ["principals"]
        ))

        self.failUnless(
            isinstance(resrc, DirectoryPrincipalProvisioningResource),
            "Did not get a DirectoryPrincipalProvisioningResource: %s"
            % (resrc,)
        )

        self.assertEquals(segments, [])

    @inlineCallbacks
    def test_inSacls(self):
        """
        Test the behavior of locateChild when SACLs are enabled and the
        user is in the SACL group

        should return a valid resource
        """
        self.root.resource.useSacls = True

        request = SimpleRequest(
            self.site,
            "GET",
            "/principals/",
            headers=http_headers.Headers({
                "Authorization": [
                    "basic",
                    "%s" % ("dreid:dierd".encode("base64"),)
                ]
            })
        )

        resrc, segments = (yield maybeDeferred(
            self.root.locateChild, request, ["principals"]
        ))

        resrc, segments = (yield maybeDeferred(
            resrc.locateChild, request, ["principals"]
        ))

        self.failUnless(
            isinstance(resrc, DirectoryPrincipalProvisioningResource),
            "Did not get a DirectoryPrincipalProvisioningResource: %s"
            % (resrc,)
        )

        self.assertEquals(segments, [])

        self.assertEquals(
            request.authzUser,
            davxml.Principal(
                davxml.HRef(
                    "/principals/__uids__/"
                    "5FF60DAD-0BDE-4508-8C77-15F0CA5C8DD1/"
                )
            )
        )

    @inlineCallbacks
    def test_notInSacls(self):
        """
        Test the behavior of locateChild when SACLs are enabled and the
        user is not in the SACL group

        should return a 403 forbidden response
        """
        self.root.resource.useSacls = True

        request = SimpleRequest(
            self.site,
            "GET",
            "/principals/",
            headers=http_headers.Headers({
                "Authorization": [
                    "basic",
                    "%s" % ("wsanchez:zehcnasw".encode("base64"),)
                ]
            })
        )

        resrc, segments = (yield maybeDeferred(
            self.root.locateChild, request, ["principals"]
        ))

        try:
            resrc, segments = (yield maybeDeferred(
                resrc.locateChild, request, ["principals"]
            ))
        except HTTPError, e:
            self.assertEquals(e.response.code, 403)

    @inlineCallbacks
    def test_unauthenticated(self):
        """
        Test the behavior of locateChild when SACLs are enabled and the request
        is unauthenticated

        should return a 401 UnauthorizedResponse
        """

        self.root.resource.useSacls = True
        request = SimpleRequest(
            self.site,
            "GET",
            "/principals/"
        )

        resrc, segments = (yield maybeDeferred(
            self.root.locateChild, request, ["principals"]
        ))

        try:
            resrc, segments = (yield maybeDeferred(
                resrc.locateChild, request, ["principals"]
            ))
            raise AssertionError(
                "RootResource.locateChild did not return an error"
            )
        except HTTPError, e:
            self.assertEquals(e.response.code, 401)

    @inlineCallbacks
    def test_badCredentials(self):
        """
        Test the behavior of locateChild when SACLS are enabled, and
        incorrect credentials are given.

        should return a 401 UnauthorizedResponse
        """
        self.root.resource.useSacls = True

        request = SimpleRequest(
            self.site,
            "GET",
            "/principals/",
            headers=http_headers.Headers({
                    "Authorization": ["basic", "%s" % (
                            "dreid:dreid".encode("base64"),)]}))

        resrc, segments = (yield maybeDeferred(
            self.root.locateChild, request, ["principals"]
        ))

        try:
            resrc, segments = (yield maybeDeferred(
                resrc.locateChild, request, ["principals"]
            ))
        except HTTPError, e:
            self.assertEquals(e.response.code, 401)

    @inlineCallbacks
    def test_internalAuthHeader(self):
        """
        Test the behavior of locateChild when x-calendarserver-internal
        header is set.

        authnuser and authzuser will be set to the internal principal
        """
        self.patch(config.Scheduling.iMIP, "Password", "xyzzy")

        headers = http_headers.Headers({})
        headers.setRawHeaders("x-calendarserver-internal", ["xyzzy"])

        request = SimpleRequest(
            self.site,
            "GET",
            "/principals/",
            headers=headers,
        )

        resrc, segments = (yield
            RootResource.locateChild(self.root.resource, request, ["principals"]
        ))

        expected = "<?xml version='1.0' encoding='UTF-8'?>\n<principal xmlns='DAV:'>\r\n  <href>/principals/__uids__/%s/</href>\r\n</principal>" % (config.Scheduling.iMIP.GUID,)
        self.assertEquals(request.authnUser.toxml(), expected)
        self.assertEquals(request.authzUser.toxml(), expected)


    def test_DELETE(self):
        def do_test(response):
            response = IResponse(response)

            if response.code != responsecode.FORBIDDEN:
                self.fail("Incorrect response for DELETE /: %s"
                          % (response.code,))

        request = SimpleRequest(self.site, "DELETE", "/")
        return self.send(request, do_test)

    def test_COPY(self):
        def do_test(response):
            response = IResponse(response)

            if response.code != responsecode.FORBIDDEN:
                self.fail("Incorrect response for COPY /: %s"
                          % (response.code,))

        request = SimpleRequest(
            self.site,
            "COPY",
            "/",
            headers=http_headers.Headers({"Destination":"/copy/"})
        )
        return self.send(request, do_test)

    def test_MOVE(self):
        def do_test(response):
            response = IResponse(response)

            if response.code != responsecode.FORBIDDEN:
                self.fail("Incorrect response for MOVE /: %s"
                          % (response.code,))

        request = SimpleRequest(
            self.site,
            "MOVE",
            "/",
            headers=http_headers.Headers({"Destination":"/copy/"})
        )
        return self.send(request, do_test)

class SACLCacheTests(RootTests):
    
    class StubResponseCacheResource(object):
        def __init__(self):
            self.cache = {}
            self.responseCache = self
            self.cacheHitCount = 0

        def getResponseForRequest(self, request):
            if str(request) in self.cache:
                self.cacheHitCount += 1
                return self.cache[str(request)]
    
    
        def cacheResponseForRequest(self, request, response):
            self.cache[str(request)] = response
            return response

    def setUp(self):
        super(SACLCacheTests, self).setUp()
        self.root.resource.responseCache = SACLCacheTests.StubResponseCacheResource()

    def test_PROPFIND(self):
        self.root.resource.useSacls = True

        body = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
<D:prop>
<D:getetag/>
<D:displayname/>
</D:prop>
</D:propfind>
"""

        request = SimpleRequest(
            self.site,
            "PROPFIND",
            "/principals/users/dreid/",
            headers=http_headers.Headers({
                    'Authorization': ['basic', '%s' % ('dreid:dierd'.encode('base64'),)],
                    'Content-Type': 'application/xml; charset="utf-8"',
                    'Depth':'1',
            }),
            content=body
        )

        def gotResponse1(response):
            if response.code != responsecode.MULTI_STATUS:
                self.fail("Incorrect response for PROPFIND /principals/: %s" % (response.code,))

            request = SimpleRequest(
                self.site,
                "PROPFIND",
                "/principals/users/dreid/",
                headers=http_headers.Headers({
                        'Authorization': ['basic', '%s' % ('dreid:dierd'.encode('base64'),)],
                        'Content-Type': 'application/xml; charset="utf-8"',
                        'Depth':'1',
                }),
                content=body
            )

            d = self.send(request, gotResponse2)
            return d

        def gotResponse2(response):
            if response.code != responsecode.MULTI_STATUS:
                self.fail("Incorrect response for PROPFIND /principals/: %s" % (response.code,))
            self.assertEqual(self.root.resource.responseCache.cacheHitCount, 1)

        d = self.send(request, gotResponse1)
        return d

class WikiTests(RootTests):
    
    @inlineCallbacks
    def test_oneTime(self):
        """
        Make sure wiki auth lookup is only done once per request;
        request.checkedWiki will be set to True
        """

        request = SimpleRequest(self.site, "GET", "/principals/")

        resrc, segments = (yield maybeDeferred(
            self.root.locateChild, request, ["principals"]
        ))
        resrc, segments = (yield maybeDeferred(
            resrc.locateChild, request, ["principals"]
        ))
        self.assertTrue(request.checkedWiki)
