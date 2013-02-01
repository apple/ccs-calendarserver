# -*- test-case-name: twext.web2.test.test_httpauth -*-
##
# Copyright (c) 2006-2009 Twisted Matrix Laboratories.
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

"""
Implementation of RFC2617: HTTP Digest Authentication

http://www.faqs.org/rfcs/rfc2617.html
"""

from zope.interface import implements

from twisted.python.hashlib import md5, sha1
from twisted.cred import credentials

# FIXME: Technically speaking - although you can't tell from looking at them -
# these APIs are private, they're defined within twisted.cred._digest.  There
# should probably be some upstream bugs agains Twisted to more aggressively hide
# implementation details like these if they're not supposed to be used, so we
# can see the private-ness more clearly.  The fix is really just to eliminate
# this whole module though, and use the Twisted stuff via the public interface,
# which should be sufficient to do digest auth.

from twisted.cred.credentials import (calcHA1 as _origCalcHA1,
                                      calcResponse as _origCalcResponse,
                                      calcHA2 as _origCalcHA2)
from twisted.internet.defer import maybeDeferred
from twext.web2.auth.interfaces import ICredentialFactory


# The digest math

algorithms = {
    'md5': md5,
    'md5-sess': md5,
    'sha': sha1,
}

# DigestCalcHA1
def calcHA1(pszAlg, pszUserName, pszRealm, pszPassword, pszNonce, pszCNonce,
            preHA1=None):
    """
    @param pszAlg: The name of the algorithm to use to calculate the digest.
        Currently supported are md5 md5-sess and sha.

    @param pszUserName: The username

    @param pszRealm: The realm

    @param pszPassword: The password

    @param pszNonce: The nonce

    @param pszCNonce: The cnonce

    @param preHA1: If available this is a str containing a previously
        calculated HA1 as a hex string.  If this is given then the values for
        pszUserName, pszRealm, and pszPassword are ignored.
    """
    return _origCalcHA1(pszAlg, pszUserName, pszRealm, pszPassword, pszNonce,
                        pszCNonce, preHA1)

# DigestCalcResponse
def calcResponse(
    HA1,
    algo,
    pszNonce,
    pszNonceCount,
    pszCNonce,
    pszQop,
    pszMethod,
    pszDigestUri,
    pszHEntity,
):
    return _origCalcResponse(HA1, _origCalcHA2(algo, pszMethod, pszDigestUri,
                                               pszQop, pszHEntity),
                             algo, pszNonce, pszNonceCount, pszCNonce, pszQop)



DigestedCredentials = credentials.DigestedCredentials

class DigestCredentialFactory(object):
    implements(ICredentialFactory)

    CHALLENGE_LIFETIME_SECS = (
        credentials.DigestCredentialFactory.CHALLENGE_LIFETIME_SECS
    )

    def __init__(self, algorithm, realm):
        self._real = credentials.DigestCredentialFactory(algorithm, realm)

    scheme = 'digest'

    def getChallenge(self, peer):
        return maybeDeferred(self._real.getChallenge, peer.host)


    def generateOpaque(self, *a, **k):
        return self._real._generateOpaque(*a, **k)


    def verifyOpaque(self, opaque, nonce, clientip):
        return self._real._verifyOpaque(opaque, nonce, clientip)


    def decode(self, response, request):
        method = getattr(request, "originalMethod", request.method)
        host = request.remoteAddr.host
        return self._real.decode(response, method, host)
