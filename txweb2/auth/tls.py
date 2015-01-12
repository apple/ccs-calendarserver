##
# Copyright (c) 2014-2015 Apple Inc. All rights reserved.
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

"""
TLS client certificate authentication module.
"""

__all__ = [
    "TLSCredentials",
    "TLSCredentialsFactory",
    "TLSCredentialsChecker",
]

from zope.interface import implements

from twisted.cred import checkers, credentials, error
from twisted.internet.defer import succeed
from txweb2.dav.auth import IPrincipalCredentials


class TLSCredentials(object):
    """
    Credentials for TLS auth - basically just the client certificate.
    """

    implements(credentials.ICredentials)

    CERTIFICATE_HEADER = "X-TLS-Client-Certificate"
    USERNAME_HEADER = "X-TLS-Client-User-Name"

    def __init__(self, certificate, username=None):

        self.certificate = certificate

        if certificate is not None:
            try:
                self.username = self.getSubject().emailAddress.split("@")[0]
            except KeyError:
                self.username = None
        else:
            self.username = username


    def getSubject(self):
        return self.certificate.getSubject()



class TLSCredentialsFactory(object):
    """
    Authorizer for TLS authentication (http://tools.ietf.org/html/draft-thomson-httpbis-cant-01).
    """

    scheme = 'clientcertificate'

    def __init__(self, realm=None, dn=None, sha256=None):
        """

        @param realm: realm for authentication, or L{None} for no realm
        @type realm: L{str}
        @param dn: list DNs for acceptable CA certs
        @type dn: L{list} of L{str}
        @param sha256: list of sha-256 fingerprint values for acceptable CA certs
        @type sha256: L{list} of L{str}
        """
        self.realm = realm
        self.dn = dn
        self.sha256 = sha256


    def getChallenge(self, _ignore_peer):
        challenge = {}
        if self.realm:
            challenge['realm'] = self.realm
        if self.dn:
            challenge['dn'] = self.dn
        if self.sha256:
            challenge['sha-256'] = self.sha256
        return succeed(challenge)


    def decode(self, credentials, request):
        return succeed(credentials)



class TLSCredentialsChecker(object):

    implements(checkers.ICredentialsChecker)

    credentialInterfaces = (IPrincipalCredentials,)

    def requestAvatarId(self, credentials):
        # NB If we get here authentication has already succeeded as it is done in TLSCredentialsFactory.decode
        # So all we need to do is return the principal URIs from the credentials.

        # Look for proper credential type.
        pcreds = IPrincipalCredentials(credentials)

        creds = pcreds.credentials
        if isinstance(creds, TLSCredentials):
            return succeed((
                pcreds.authnPrincipal,
                pcreds.authzPrincipal,
            ))

        raise error.UnauthorizedLogin("Bad credentials for: %s" % (pcreds.authnURI,))
