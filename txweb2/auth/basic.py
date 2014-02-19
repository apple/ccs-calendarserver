# -*- test-case-name: txweb2.test.test_httpauth -*-
##
# Copyright (c) 2006-2009 Twisted Matrix Laboratories.
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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

from twisted.cred import credentials, error
from twisted.internet.defer import succeed, fail
from txweb2.auth.interfaces import ICredentialFactory

from zope.interface import implements

class BasicCredentialFactory(object):
    """
    Credential Factory for HTTP Basic Authentication
    """

    implements(ICredentialFactory)

    scheme = 'basic'

    def __init__(self, realm):
        self.realm = realm


    def getChallenge(self, peer):
        """
        @see L{ICredentialFactory.getChallenge}
        """
        return succeed({'realm': self.realm})


    def decode(self, response, request):
        """
        Decode the credentials for basic auth.

        @see L{ICredentialFactory.decode}
        """
        try:
            creds = (response + '===').decode('base64')
        except:
            raise error.LoginFailed('Invalid credentials')

        creds = creds.split(':', 1)
        if len(creds) == 2:
            return succeed(credentials.UsernamePassword(*creds))
        else:
            return fail(error.LoginFailed('Invalid credentials'))
