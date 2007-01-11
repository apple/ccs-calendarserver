##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
#
# DRI: David Reid, dreid@apple.com
##

import os

from twistedcaldav.root import RootResource

from twistedcaldav.test.util import TestCase
from twistedcaldav.directory.principal import DirectoryPrincipalProvisioningResource
from twistedcaldav.directory.xmlfile import XMLDirectoryService
from twistedcaldav.directory.test.test_xmlfile import xmlFile

from twisted.internet import defer

from twisted.web2.http import HTTPError

from twisted.web2.dav import auth
from twisted.web2.dav import davxml

from twisted.web2 import server
from twisted.web2.auth import basic
from twisted.web2 import http_headers

from twisted.cred.portal import Portal

from twisted.web2.test.test_server import SimpleRequest

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
        self.docroot = self.mktemp()

        RootResource.CheckSACL = FakeCheckSACL(sacls={
                'calendar': ['dreid']})

        directory = XMLDirectoryService(xmlFile)

        principals = DirectoryPrincipalProvisioningResource(
            os.path.join(self.docroot, 'principals'),
            '/principals/',
            directory)

        # Otherwise the tests that never touch the root resource will 
        # fail on teardown.
        principals.provision()

        root = RootResource(self.docroot, 
                            principalCollections=[principals])

        root.putChild('principals',
                      principals)

        portal = Portal(auth.DavRealm())
        portal.registerChecker(directory)

        self.root = auth.AuthenticationWrapper(
            root, 
            portal, 
            credentialFactories=(basic.BasicCredentialFactory("Test realm"),),
            loginInterfaces=(auth.IPrincipal,))

        self.site = server.Site(self.root)

    def test_noSacls(self):
        """
        Test the behaviour of locateChild when SACLs are not enabled.
        
        should return a valid resource
        """
        self.root.resource.useSacls = False

        request = SimpleRequest(self.site,
                                "GET",
                                "/principals/")

        resrc, segments = self.root.locateChild(request,
                                         ['principals'])

        resrc, segments = resrc.locateChild(request, ['principals'])

        self.failUnless(
            isinstance(resrc,
                       DirectoryPrincipalProvisioningResource),
            "Did not get a DirectoryPrincipalProvisioningResource: %s" % (resrc,))

        self.assertEquals(segments, [])

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
                    'Authorization': ['basic', '%s' % (
                            'dreid:dierd'.encode('base64'),)]}))
        
        resrc, segments = self.root.locateChild(request,
                                         ['principals'])

        def _Cb((resrc, segments)):
            self.failUnless(
                isinstance(resrc,
                           DirectoryPrincipalProvisioningResource),
                "Did not get a DirectoryPrincipalProvisioningResource: %s" % (resrc,))

            self.assertEquals(segments, [])

            self.assertEquals(request.authzUser, 
                              davxml.Principal(
                    davxml.HRef('/principals/users/dreid/')))
            
        d = defer.maybeDeferred(resrc.locateChild, request, ['principals'])
        d.addCallback(_Cb)

        return d

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
                    'Authorization': ['basic', '%s' % (
                            'wsanchez:zehcnasw'.encode('base64'),)]}))
        
        resrc, segments = self.root.locateChild(request,
                                         ['principals'])

        def _Eb(failure):
            self.assertEquals(failure.value.response.code, 403)
            
        d = defer.maybeDeferred(resrc.locateChild, request, ['principals'])
        d.addErrback(_Eb)

        return d

    def test_unauthenticated(self):
        """
        Test the behavior of locateChild when SACLs are enabled and the request
        is unauthenticated
        
        should return a 401 UnauthorizedResponse
        """

        self.root.resource.useSacls = True
        request = SimpleRequest(self.site,
                                "GET",
                                "/principals/")

        resrc, segments = self.root.locateChild(request,
                                                ['principals'])

        def _Cb(result):
            raise AssertionError(("RootResource.locateChild did not return "
                                  "an error"))

        def _Eb(failure):
            failure.trap(HTTPError)

            self.assertEquals(failure.value.response.code, 401)

        d = defer.maybeDeferred(resrc.locateChild, request, ['principals'])

        d.addCallback(_Cb)
        d.addErrback(_Eb)

        return d

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
                    'Authorization': ['basic', '%s' % (
                            'dreid:dreid'.encode('base64'),)]}))
        
        resrc, segments = self.root.locateChild(request,
                                         ['principals'])

        def _Eb(failure):
            self.assertEquals(failure.value.response.code, 401)
            
        d = defer.maybeDeferred(resrc.locateChild, request, ['principals'])
        d.addErrback(_Eb)

        return d
