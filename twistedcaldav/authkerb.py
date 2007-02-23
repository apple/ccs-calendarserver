##
# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Kerberos authentication module.

This implements two authentication modes:

  1. An alternative to password based BASIC authentication in which the BASIC credentials are
     verified against Kerberos.
   
  2. The NEGOTIATE mechanism (as defined in http://www.ietf.org/internet-drafts/draft-jaganathan-kerberos-http-01.txt)
     that implements full GSSAPI authentication.
"""

__all__ = [
    "BasicKerberosCredentials",
    "BasicKerberosAuthorizer",
    "BasicKerberosCredentialsChecker",
    "NegotiateCredentials",
    "NegotiateAuthorizer",
    "NegotiateCredentialsChecker",
]

from zope.interface import implements

from twisted.cred import checkers, credentials, error
from twisted.internet.defer import succeed
from twisted.web2.auth.interfaces import ICredentialFactory
from twisted.web2.dav.auth import IPrincipalCredentials

from twistedcaldav import logging

import kerberos

class BasicKerberosCredentials(credentials.UsernamePassword):
    """
    A set of user/password credentials that checks itself against Kerberos.
    """

    def __init__(self, username, password, service, realm):
        credentials.UsernamePassword.__init__(self, username, password)
        
        # Convert Kerberos principal spec into service and realm
        self.service = service
        self.default_realm = realm
        
class BasicKerberosCredentialFactory:
    """
    Authorizer for insecure Basic (base64-encoded plaintext) authentication.

    This form of authentication is insecure and should only be used when SSL is in effect.
    Right now we do not check for that.
    """

    implements(ICredentialFactory)

    scheme = 'basic'

    def __init__(self, service, realm):
        """
        The realm string can be of the form service/realm@domain. We split that
        into service@domain, and realm.
        """
        self.service = service
        self.realm = realm

    def getChallenge(self, peer):
        return {'realm': self.realm}

    def decode(self, response, request): #@UnusedVariable
        try:
            creds = (response + '===').decode('base64')
        except:
            raise error.LoginFailed('Invalid credentials')

        creds = creds.split(':', 1)
        if len(creds) == 2:
            c = BasicKerberosCredentials(creds[0], creds[1], self.service, self.realm)
            return c
        raise error.LoginFailed('Invalid credentials')

class BasicKerberosCredentialsChecker:

    implements(checkers.ICredentialsChecker)

    credentialInterfaces = (IPrincipalCredentials,)

    def requestAvatarId(self, credentials):

        # If there is no calendar principal URI then the calendar user is disabled.
        pcreds = IPrincipalCredentials(credentials)

        creds = pcreds.credentials
        if isinstance(creds, BasicKerberosCredentials):
            try:
                kerberos.checkPassword(creds.username, creds.password, creds.service, creds.default_realm)
            except kerberos.BasicAuthError, ex:
                logging.err("%s" % (ex[0],), system="BasicKerberosCredentialsChecker")
                raise error.UnauthorizedLogin("Bad credentials for: %s (%s: %s)" % (pcreds.authnURI, ex[0], ex[1],))
            else:
                return succeed((pcreds.authnURI, pcreds.authzURI,))
        
        raise error.UnauthorizedLogin("Bad credentials for: %s" % (pcreds.authnURI,))

class NegotiateCredentials:
    """
    A set of user/password credentials that checks itself against Kerberos.
    """

    implements(credentials.ICredentials)

    def __init__(self, username):
        
        self.username = username
        
class NegotiateCredentialFactory:
    """
    Authorizer for insecure Basic (base64-encoded plaintext) authentication.

    This form of authentication is insecure and should only be used when SSL is in effect.
    Right now we do not check for that.
    """

    implements(ICredentialFactory)

    scheme = 'negotiate'

    def __init__(self, service, realm):

        self.service = service
        self.realm = realm

    def getChallenge(self, peer):
        return {}

    def decode(self, base64data, request):
        
        # Init GSSAPI first
        try:
            result, context = kerberos.authGSSServerInit(self.service);
        except kerberos.GSSError, ex:
            logging.err("authGSSServerInit: %s(%s)" % (ex[0][0], ex[1][0],), system="NegotiateCredentialFactory")
            raise error.LoginFailed('Authentication System Failure: %s(%s)' % (ex[0][0], ex[1][0],))

        # Do the GSSAPI step and get response and username
        try:
            kerberos.authGSSServerStep(context, base64data);
        except kerberos.GSSError, ex:
            logging.err("authGSSServerStep: %s(%s)" % (ex[0][0], ex[1][0],), system="NegotiateCredentialFactory")
            kerberos.authGSSServerClean(context)
            raise error.UnauthorizedLogin('Bad credentials: %s(%s)' % (ex[0][0], ex[1][0],))
        except kerberos.KrbError, ex:
            logging.err("authGSSServerStep: %s" % (ex[0],), system="NegotiateCredentialFactory")
            kerberos.authGSSServerClean(context)
            raise error.UnauthorizedLogin('Bad credentials: %s' % (ex[0],))

        response = kerberos.authGSSServerResponse(context)
        username = kerberos.authGSSServerUserName(context)
        realmname = ""
        
        # Username may include realm suffix which we want to strip
        if username.find("@") != -1:
            splits = username.split("@", 1)
            username = splits[0]
            realmname = splits[1]
        
        # We currently do not support cross-realm authentciation, so we
        # must verify that the realm we got exactly matches the one we expect.
        if realmname != self.realm:
            logging.err("authGSSServer Realms do not match: %s vs %s" % (realmname, self.realm,), system="NegotiateCredentialFactory")
            kerberos.authGSSServerClean(context)
            raise error.UnauthorizedLogin('Bad credentials: mismatched realm')


        # Close the context
        try:
            result = kerberos.authGSSServerClean(context);
        except kerberos.GSSError, ex:
            logging.err("authGSSServerClean: %s" % (ex[0][0], ex[1][0],), system="NegotiateCredentialFactory")
            raise error.LoginFailed('Authentication System Failure %s(%s)' % (ex[0][0], ex[1][0],))
        
        # If we successfully decoded and verified the Kerberos credentials we need to add the Kerberos
        # response data to the outgoing request

        wwwauth = '%s %s' % (self.scheme, response)

        def responseFilterAddWWWAuthenticate(request, response): #@UnusedVariable
            response.headers.addRawHeader('www-authenticate', wwwauth)
            return response

        responseFilterAddWWWAuthenticate.handleErrors = True

        request.addResponseFilter(responseFilterAddWWWAuthenticate)

        return NegotiateCredentials(username)

class NegotiateCredentialsChecker:

    implements(checkers.ICredentialsChecker)

    credentialInterfaces = (IPrincipalCredentials,)

    def requestAvatarId(self, credentials):
        # NB If we get here authentication has already succeeded as it is done in NegotiateCredentialsFactory.decode
        # So all we need to do is return the principal URIs from the credentials.

        # Look for proper credential type.
        pcreds = IPrincipalCredentials(credentials)

        creds = pcreds.credentials
        if isinstance(creds, NegotiateCredentials):
            return succeed((pcreds.authnURI, pcreds.authzURI,))
        
        raise error.UnauthorizedLogin("Bad credentials for: %s" % (pcreds.authnURI,))

