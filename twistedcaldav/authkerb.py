##
# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Kerberos authentication module.

This implements two authentication modes:

1) An alternative to password based BASIC authentication in which the BASIC credentials are
   verified against Kerberos.
   
2) The NEGOTIATE mechanism (as defined in http://www.ietf.org/internet-drafts/draft-jaganathan-kerberos-http-01.txt)
   that implements full GSSAPI authentication.
"""

from twisted.web2.dav import auth
from zope import interface
from twisted.cred.credentials import ICredentials

__all__ = [
    "BasicKerberosCredentials",
    "BasicKerberosAuthorizer",
    #"NegotiateCredentials",
    #"NegotiateAuthorizer",
]

from twisted.cred import credentials, error
from twisted.python import log
from twisted.web2.dav import davxml
from zope.interface import implements

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

    def verify(self, request, resource):
        """
        Check this set of credentials to verify they are correct and extract the current principal
        authorization identifier.
        
        @param request:  the L{IRequest} for the request in progress.
        @param resource: the L{DAVResource} for which credentials are being supplied.
        @return:         tuple of (result, principal) where: result is True if the credentials match,
            or false otherwise; principal is the L{davxml.Principal} that matches the credentials if result
            is True, or None if result is False.
        """

        # In our default setup the user's password is stored as a property on the principal, so
        # we first find the matching principal and then get the password and do the comparison.
        
        # Try to match principals in each principal collection on the resource
        result = kerberos.checkPassword(self.username, self.password, self.service, self.default_realm)
        if not result:
            log.err("Client authentication password for %s incorrect" % (self.username,))
            return False, None

        pdetails = resource.findPrincipalForAuthID(request, self.username)
        if pdetails:
            principalURI = pdetails[1]
            return True, davxml.Principal(davxml.HRef().fromString(principalURI))
        else:
            return False, None
        
class BasicKerberosAuthorizer:
    """
    Authorizer for insecure Basic (base64-encoded plaintext) authentication.

    This form of authentication is insecure and should only be used when SSL is in effect.
    Right now we do not check for that.
    """

    implements(auth.IAuthorizer)

    def __init__(self, realm):

        self.realm = realm

        self.service = ""
        if len(self.realm) > 0:
            splits = self.realm.split('/', 1)
            if len(splits) == 2:
                service = splits[0]
                splits = splits[1].split('@', 1)
                if len(splits) == 2:
                    self.service = service + "@" + splits[1]
                    self.realm = splits[0]

    def validForRequest(self, request): #@UnusedVariable
        """
        Determine whether this authorizer type is valid for the current request.
        This is where we should check whether SSL is in use or not and reject authorizer
        that are insecure if SSL is not being used.

        @param request: the L{IRequest} for the request in progress.
        @return:        True if the authorizer can safely be used during this request, False otherwise.
        """
        # Always available irrespective of SSL.
        return True

    def getScheme(self):
        return "basic"

    def hasChallenge(self):
        """
        Indicates whether this authenticator sends some data in the initial WWW-Authenticate challenge.
        
        @return: True if a challenge needs to be sent back, False if not.
        """
        return True
    
    def getChallenge(self):
        return 'realm="%s"' % self.realm

    def hasResponse(self):
        """
        Indicates whether this authenticator sends back a WWW-Authenticate response after
        the initial client challenge.
        
        @return: True if a response needs to be sent back, False if not.
        """
        return False

    def getResponse(self):
        """
        The response to send back to the client.
        
        @return: the C{str} for the response to send back.
        """
        return ""

    def decode(self, response, method=None): #@UnusedVariable
        # At least one SIP client improperly pads its Base64 encoded messages
        for i in range(3):
            try:
                creds = (response + ('=' * i)).decode('base64')
            except:
                pass
            else:
                break
        else:
            # Totally bogus
            raise error.LoginFailed('Invalid credentials')
        p = creds.split(':', 1)
        if len(p) == 2:
            c = BasicKerberosCredentials(p[0], p[1], self.service, self.realm)
            return c
        raise error.LoginFailed('Invalid credentials')


class NegotiateCredentials(credentials.UsernamePassword):
    """
    A set of user/password credentials that checks itself against Kerberos.
    """

    interface.implements(ICredentials)

    def __init__(self, user):
        
        self.username = user

    def verify(self, request, resource):
        """
        Check this set of credentials to verify they are correct and extract the current principal
        authorization identifier.
        
        @param request:  the L{IRequest} for the request in progress.
        @param resource: the L{DAVResource} for which credentials are being supplied.
        @return:         tuple of (result, principal) where: result is True if the credentials match,
            or false otherwise; principal is the L{davxml.Principal} that matches the credentials if result
            is True, or None if result is False.
        """

        # When we get here we know that Kerberos authentication succeeded if the user name is not empty.
        if len(self.username) == 0:
            log.err("Client authentication failed")
            return False, None
        
        # Try to match principals in each principal collection on the resource
        pdetails = resource.findPrincipalForAuthID(request, self.username)
        if pdetails:
            principalURI = pdetails[1]
            return True, davxml.Principal(davxml.HRef().fromString(principalURI))
        else:
            return False, None
        
class NegotiateAuthorizer:
    """
    Authorizer for insecure Basic (base64-encoded plaintext) authentication.

    This form of authentication is insecure and should only be used when SSL is in effect.
    Right now we do not check for that.
    """

    implements(auth.IAuthorizer)

    def __init__(self, service):

        self.service = service
        self.response = ""

    def validForRequest(self, request): #@UnusedVariable
        """
        Determine whether this authorizer type is valid for the current request.
        This is where we should check whether SSL is in use or not and reject authorizer
        that are insecure if SSL is not being used.

        @param request: the L{IRequest} for the request in progress.
        @return:        True if the authorizer can safely be used during this request, False otherwise.
        """
         # Always available irrespective of SSL.
        return True

    def getScheme(self):
        return "negotiate"

    def hasChallenge(self):
        """
        Indicates whether this authenticator sends some data in the initial WWW-Authenticate challenge.
        
        @return: True if a challenge needs to be sent back, False if not.
        """
        return False
    
    def getChallenge(self):
        return ""

    def hasResponse(self):
        """
        Indicates whether this authenticator sends back a WWW-Authenticate response after
        the initial client challenge.
        
        @return: True if a response needs to be sent back, False if not.
        """
        return True

    def getResponse(self):
        """
        The response to send back to the client.
        
        @return: the C{str} for the response to send back.
        """
        return self.response

    def decode(self, response, method=None): #@UnusedVariable
        
        # Init GSSAPI first
        result, context = kerberos.authGSSServerInit(self.service);
        if result != 1:
            raise error.LoginFailed('Authentication System Failure')

        # Do the GSSAPI step and get response and username
        result = kerberos.authGSSServerStep(context, response);
        if result == -1:
            self.response = ""
            username = ""
        else:
            self.response = kerberos.authGSSServerResponse(context)
            username = kerberos.authGSSServerUserName(context)
            
            # Username may include realm suffix which we want to strip
            if username.find("@") != -1:
                username = username.split("@", 1)[0]

        # Close the context
        result = kerberos.authGSSServerClean(context);
        if result != 1:
            raise error.LoginFailed('Authentication System Failure')
        
        return NegotiateCredentials(username)
