##
# Copyright (c) 2004-2007 Twisted Matrix Laboratories.
# Copyright (c) 2010-2013 Apple Computer, Inc. All rights reserved.
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

from zope.interface import Interface, Attribute

class ICredentialFactory(Interface):
    """
    A credential factory provides state between stages in HTTP
    authentication.  It is ultimately in charge of creating an
    ICredential for the specified scheme, that will be used by
    cred to complete authentication.
    """
    scheme = Attribute(("string indicating the authentication scheme "
                        "this factory is associated with."))

    def getChallenge(peer):
        """
        Generate a challenge the client may respond to.

        @type peer: L{twisted.internet.interfaces.IAddress}
        @param peer: The client's address

        @rtype: C{dict}
        @return: Deferred returning dictionary of challenge arguments
        """

    def decode(response, request):
        """
        Create a credentials object from the given response.
        May raise twisted.cred.error.LoginFailed if the response is invalid.

        @type response: C{str}
        @param response: scheme specific response string

        @type request: L{txweb2.server.Request}
        @param request: the request being processed

        @return: Deferred returning ICredentials
        """


class IAuthenticatedRequest(Interface):
    """
    A request that has been authenticated with the use of Cred,
    and holds a reference to the avatar returned by portal.login
    """

    avatarInterface = Attribute(("The credential interface implemented by "
                                 "the avatar"))

    avatar = Attribute("The application specific avatar returned by "
                       "the application's realm")


class IHTTPUser(Interface):
    """
    A generic interface that can implemented by an avatar to provide
    access to the username used when authenticating.
    """

    username = Attribute(("A string representing the username portion of "
                          "the credentials used for authentication"))
