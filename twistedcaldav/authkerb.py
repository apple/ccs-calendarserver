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

class KerberosCredentialFactoryBase(object):
    """
    Code common to Kerberos-based credential factories.
    """

    implements(ICredentialFactory)

    def __init__(self, principal=None, type=None, hostname=None):
        """
        
        @param principal:  full Kerberos principal (e.g., 'http/server.example.com@EXAMPLE.COM'). If C{None}
            then the type and hostname arguments are used instead.
        @type service:     str
        @param type:       service type for Kerberos (e.g., 'http'). Must be C{None} if principal used.
        @type type:        str
        @param hostname:   hostname for this server. Must be C{None} if principal used.
        @type hostname:    str
        """

        # Only certain combinations of arguments allowed
        assert (principal and not type and not hostname) or (not principal and type and hostname)

        if not principal:
            # Look up the Kerberos principal given the service type and hostname, and extract
            # the realm and a service principal value for later use.
            try:
                principal = kerberos.getServerPrincipalDetails(type, hostname)
            except kerberos.KrbError, ex:
                logging.err("getServerPrincipalDetails: %s" % (ex[0],), system="KerberosCredentialFactoryBase")
                raise ValueError('Authentication System Failure: %s' % (ex[0],))

        try:
            splits = principal.split("/")
            servicetype = splits[0]
            splits = splits[1].split("@")
            service = splits[0].upper()
            realm = splits[1]
        except IndexError:
            logging.err("Invalid Kerberos principal: %s" % (principal,), system="KerberosCredentialFactoryBase")
            raise ValueError('Authentication System Failure: Invalid Kerberos principal: %s' % (principal,))
                
        self.service = "%s@%s" % (servicetype, service,)
        self.realm = realm

class BasicKerberosCredentials(credentials.UsernamePassword):
    """
    A set of user/password credentials that checks itself against Kerberos.
    """

    def __init__(self, username, password, service, realm):
        """
        
        @param username:   user name of user to authenticate
        @type username:    str
        @param password:   password for user being authenticated
        @type password:    str
        @param service:    service principal
        @type service:     str
        @param hostname:   realm
        @type hostname:    str
        """
        credentials.UsernamePassword.__init__(self, username, password)
        
        # Convert Kerberos principal spec into service and realm
        self.service = service
        self.default_realm = realm
        
class BasicKerberosCredentialFactory(KerberosCredentialFactoryBase):
    """
    Authorizer for insecure Basic (base64-encoded plaintext) authentication.

    This form of authentication is insecure and should only be used when SSL is in effect.
    Right now we do not check for that.
    """

    scheme = 'basic'

    def __init__(self, principal=None, type=None, hostname=None):
        """
        
        @param principal:  full Kerberos principal (e.g., 'http/server.example.com@EXAMPLE.COM'). If C{None}
            then the type and hostname arguments are used instead.
        @type service:     str
        @param type:       service type for Kerberos (e.g., 'http'). Must be C{None} if principal used.
        @type type:        str
        @param hostname:   hostname for this server. Must be C{None} if principal used.
        @type hostname:    str
        """

        super(BasicKerberosCredentialFactory, self).__init__(principal, type, hostname)

    def getChallenge(self, _ignore_peer):
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

class BasicKerberosCredentialsChecker(object):

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

class NegotiateCredentials(object):
    """
    A set of user/password credentials that checks itself against Kerberos.
    """

    implements(credentials.ICredentials)

    def __init__(self, username):
        
        self.username = username
        
class NegotiateCredentialFactory(KerberosCredentialFactoryBase):
    """
    Authorizer for insecure Basic (base64-encoded plaintext) authentication.

    This form of authentication is insecure and should only be used when SSL is in effect.
    Right now we do not check for that.
    """

    scheme = 'negotiate'

    def __init__(self, principal=None, type=None, hostname=None):
        """
        
        @param principal:  full Kerberos principal (e.g., 'http/server.example.com@EXAMPLE.COM'). If C{None}
            then the type and hostname arguments are used instead.
        @type service:     str
        @param type:       service type for Kerberos (e.g., 'http'). Must be C{None} if principal used.
        @type type:        str
        @param hostname:   hostname for this server. Must be C{None} if principal used.
        @type hostname:    str
        """

        super(NegotiateCredentialFactory, self).__init__(principal, type, hostname)

    def getChallenge(self, _ignore_peer):
        return {}

    def decode(self, base64data, request):
        
        # Init GSSAPI first
        try:
            _ignore_result, context = kerberos.authGSSServerInit(self.service);
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
            kerberos.authGSSServerClean(context);
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

class NegotiateCredentialsChecker(object):

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

