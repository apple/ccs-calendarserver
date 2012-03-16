from zope.interface import implements, Interface
from twisted.internet import defer
from twisted.cred import checkers, error, portal
from twext.web2.resource import WrapperResource
from twext.web2.dav import davxml
from twext.web2.dav.davxml import twisted_private_namespace
from txdav.xml.element import registerElement

__all__ = [
    "IPrincipal",
    "DavRealm",
    "IPrincipalCredentials",
    "PrincipalCredentials",
    "AuthenticationWrapper",
]

class AuthenticationWrapper(WrapperResource):
    def __init__(self, resource, portal, credentialFactories, loginInterfaces):
        """
        Wrap the given resource and use the parameters to set up the request
        to allow anyone to challenge and handle authentication.

        @param resource: L{DAVResource} FIXME: This should get promoted to
            twext.web2.auth
        @param portal: The cred portal
        @param credentialFactories: Sequence of credentialFactories that can
            be used to authenticate by resources in this tree.
        @param loginInterfaces: More cred stuff
        """
        super(AuthenticationWrapper, self).__init__(resource)

        self.portal = portal
        self.credentialFactories = dict([(factory.scheme, factory)
                                         for factory in credentialFactories])
        self.loginInterfaces = loginInterfaces

    def hook(self, req):
        req.portal = self.portal
        req.credentialFactories = self.credentialFactories
        req.loginInterfaces = self.loginInterfaces


class IPrincipal(Interface):
    pass

class DavRealm(object):
    implements(portal.IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        if IPrincipal in interfaces:
            return IPrincipal, davxml.Principal(davxml.HRef(avatarId[0])), davxml.Principal(davxml.HRef(avatarId[1]))
        
        raise NotImplementedError("Only IPrincipal interface is supported")


class IPrincipalCredentials(Interface):
    pass


class PrincipalCredentials(object):
    implements(IPrincipalCredentials)

    def __init__(self, authnPrincipal, authzPrincipal, credentials):
        """
        Initialize with both authentication and authorization values. Note that in most cases theses will be the same
        since HTTP auth makes no distinction between the two - but we may be layering some addition auth on top of this
        (.e.g.. proxy auth, cookies, forms etc) that make result in authentication and authorization being different.

        @param authnPrincipal: L{IDAVPrincipalResource} for the authenticated principal.
        @param authnURI: C{str} containing the URI of the authenticated principal.
        @param authzPrincipal: L{IDAVPrincipalResource} for the authorized principal.
        @param authzURI: C{str} containing the URI of the authorized principal.
        @param credentials: L{ICredentials} for the authentication credentials.
        """
        self.authnPrincipal = authnPrincipal
        self.authzPrincipal = authzPrincipal
        self.credentials = credentials

    def checkPassword(self, password):
        return self.credentials.checkPassword(password)


class TwistedPropertyChecker(object):
    implements(checkers.ICredentialsChecker)

    credentialInterfaces = (IPrincipalCredentials,)

    def _cbPasswordMatch(self, matched, principalURIs):
        if matched:
            # We return both URIs
            return principalURIs
        else:
            raise error.UnauthorizedLogin("Bad credentials for: %s" % (principalURIs[0],))

    def requestAvatarId(self, credentials):
        pcreds = IPrincipalCredentials(credentials)
        pswd = str(pcreds.authnPrincipal.readDeadProperty(TwistedPasswordProperty))

        d = defer.maybeDeferred(credentials.checkPassword, pswd)
        d.addCallback(self._cbPasswordMatch, (
            pcreds.authnPrincipal.principalURL(),
            pcreds.authzPrincipal.principalURL(),
            pcreds.authnPrincipal,
            pcreds.authzPrincipal,
        ))
        return d

##
# Utilities
##

class TwistedPasswordProperty (davxml.WebDAVTextElement):
    namespace = twisted_private_namespace
    name = "password"

registerElement(TwistedPasswordProperty)
