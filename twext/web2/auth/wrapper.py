# -*- test-case-name: twext.web2.test.test_httpauth -*-
##
# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# Copyright (c) 2010-2014 Apple Computer, Inc. All rights reserved.
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
##

"""
Wrapper Resources for rfc2617 HTTP Auth.
"""
from zope.interface import implements, directlyProvides
from twisted.cred import error, credentials
from twisted.internet.defer import gatherResults, succeed
from twisted.python import failure
from twext.web2 import responsecode
from twext.web2 import http
from twext.web2 import iweb
from twext.web2.auth.interfaces import IAuthenticatedRequest

class UnauthorizedResponse(http.StatusResponse):
    """A specialized response class for generating www-authenticate headers
    from the given L{CredentialFactory} instances
    """

    def __init__(self):
        super(UnauthorizedResponse, self).__init__(
            responsecode.UNAUTHORIZED,
            "You are not authorized to access this resource.")

    def _generateHeaders(self, factories, remoteAddr=None):
        """
        Set up the response's headers.

        @param factories: A L{dict} of {'scheme': ICredentialFactory}
        @param remoteAddr: An L{IAddress} for the connecting client.
        """
        schemes = []
        challengeDs = []
        for factory in factories.itervalues():
            schemes.append(factory.scheme)
            challengeDs.append(factory.getChallenge(remoteAddr))
        def _setAuthHeader(challenges):
            authHeaders = zip(schemes, challenges)
            self.headers.setHeader('www-authenticate', authHeaders)
        return gatherResults(challengeDs).addCallback(_setAuthHeader)


    @classmethod
    def makeResponse(cls, factories, remoteAddr=None):
        """
        Create an Unauthorized response.

        @param factories: A L{dict} of {'scheme': ICredentialFactory}
        @param remoteAddr: An L{IAddress} for the connecting client.

        @return: a Deferred that fires with the L{UnauthorizedResponse}
        instance.
        """
        response = UnauthorizedResponse()
        d = response._generateHeaders(factories, remoteAddr)
        d.addCallback(lambda _:response)
        return d



class HTTPAuthResource(object):
    """I wrap a resource to prevent it being accessed unless the authentication
       can be completed using the credential factory, portal, and interfaces
       specified.
    """

    implements(iweb.IResource)

    def __init__(self, wrappedResource, credentialFactories,
                 portal, interfaces):
        """
        @param wrappedResource: A L{twext.web2.iweb.IResource} to be returned
                                from locateChild and render upon successful
                                authentication.

        @param credentialFactories: A list of instances that implement
                                    L{ICredentialFactory}.
        @type credentialFactories: L{list}

        @param portal: Portal to handle logins for this resource.
        @type portal: L{twisted.cred.portal.Portal}

        @param interfaces: the interfaces that are allowed to log in via the
                           given portal
        @type interfaces: L{tuple}
        """

        self.wrappedResource = wrappedResource

        self.credentialFactories = dict([(factory.scheme, factory)
                                         for factory in credentialFactories])
        self.portal = portal
        self.interfaces = interfaces

    def _loginSucceeded(self, avatar, request):
        """
        Callback for successful login.

        @param avatar: A tuple of the form (interface, avatar) as
            returned by your realm.

        @param request: L{IRequest} that encapsulates this auth
            attempt.

        @return: the IResource in C{self.wrappedResource}
        """
        request.avatarInterface, request.avatar = avatar

        directlyProvides(request, IAuthenticatedRequest)

        def _addAuthenticateHeaders(request, response):
            """
            A response filter that adds www-authenticate headers
            to an outgoing response if it's code is UNAUTHORIZED (401)
            and it does not already have them.
            """
            if response.code == responsecode.UNAUTHORIZED:
                if not response.headers.hasHeader('www-authenticate'):
                    d = UnauthorizedResponse.makeResponse(
                        self.credentialFactories,
                        request.remoteAddr)
                    def _respond(newResp):
                        response.headers.setHeader(
                            'www-authenticate',
                            newResp.headers.getHeader('www-authenticate'))
                        return response
                    d.addCallback(_respond)
                    return d

            return succeed(response)

        _addAuthenticateHeaders.handleErrors = True

        request.addResponseFilter(_addAuthenticateHeaders)

        return self.wrappedResource


    def _loginFailed(self, ignored, request):
        """
        Errback for failed login.


        @param request: L{IRequest} that encapsulates this auth
            attempt.

        @return: A Deferred L{Failure} containing an L{HTTPError} containing the
            L{UnauthorizedResponse} if C{result} is an L{UnauthorizedLogin}
            or L{UnhandledCredentials} error
        """
        d = UnauthorizedResponse.makeResponse(self.credentialFactories,
                                              request.remoteAddr)

        def _fail(response):
            return failure.Failure(http.HTTPError(response))
        return d.addCallback(_fail)


    def login(self, factory, response, request):
        """
        @param factory: An L{ICredentialFactory} that understands the given
            response.

        @param response: The client's authentication response as a string.

        @param request: The request that prompted this authentication attempt.

        @return: A L{Deferred} that fires with the wrappedResource on success
            or a failure containing an L{UnauthorizedResponse}
        """
        d = factory.decode(response, request)
        def _decodeFailure(err):
            err.trap(error.LoginFailed)
            d = UnauthorizedResponse.makeResponse(self.credentialFactories,
                                                  request.remoteAddr)
            def _respond(response):
                return failure.Failure(http.HTTPError(response))
            return d.addCallback(_respond)
        def _login(creds):
            return self.portal.login(creds, None, *self.interfaces
                                     ).addCallbacks(self._loginSucceeded,
                                                    self._loginFailed,
                                                    (request,), None,
                                                    (request,), None)
        return d.addErrback(_decodeFailure).addCallback(_login)


    def authenticate(self, request):
        """
        Attempt to authenticate the given request

        @param request: An L{IRequest} to be authenticated.
        """
        authHeader = request.headers.getHeader('authorization')

        if authHeader is None:
            return self.portal.login(credentials.Anonymous(),
                                     None,
                                     *self.interfaces
                                     ).addCallbacks(self._loginSucceeded,
                                                    self._loginFailed,
                                                    (request,), None,
                                                    (request,), None)

        elif authHeader[0] not in self.credentialFactories:
            return self._loginFailed(None, request)
        else:
            return self.login(self.credentialFactories[authHeader[0]],
                              authHeader[1], request)


    def locateChild(self, request, seg):
        """
        Authenticate the request then return the C{self.wrappedResource}
        and the unmodified segments.
        """
        return self.authenticate(request), seg

    def renderHTTP(self, request):
        """
        Authenticate the request then return the result of calling renderHTTP
        on C{self.wrappedResource}
        """
        def _renderResource(resource):
            return resource.renderHTTP(request)

        d = self.authenticate(request)
        d.addCallback(_renderResource)

        return d
