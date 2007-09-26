

from twisted.cred import error
from twisted.internet import address
from twisted.trial import unittest
from twisted.web2.auth import digest
from twisted.web2.auth.wrapper import UnauthorizedResponse
from twisted.web2.test.test_server import SimpleRequest
from twisted.web2.dav.fileop import rmdir
from twistedcaldav.directory.digest import QopDigestCredentialFactory
import os
import md5

class FakeDigestCredentialFactory(QopDigestCredentialFactory):
    """
    A Fake Digest Credential Factory that generates a predictable
    nonce and opaque
    """

    def __init__(self, *args, **kwargs):
        super(FakeDigestCredentialFactory, self).__init__(*args, **kwargs)

    def generateNonce(self):
        """
        Generate a static nonce
        """
        return '178288758716122392881254770685'


clientAddress = address.IPv4Address('TCP', '127.0.0.1', 80)

challengeOpaque = ('75c4bd95b96b7b7341c646c6502f0833-MTc4Mjg4NzU'
                   '4NzE2MTIyMzkyODgxMjU0NzcwNjg1LHJlbW90ZWhvc3Q'
                   'sMA==')

challengeNonce = '178288758716122392881254770685'

challengeResponse = ('digest',
                     {'nonce': challengeNonce,
                      'qop': 'auth', 'realm': 'test realm',
                      'algorithm': 'md5',})

cnonce = "29fc54aa1641c6fa0e151419361c8f23"

authRequest1 = (('username="username", realm="test realm", nonce="%s", '
                 'uri="/write/", response="%s", algorithm="md5", '
                 'cnonce="29fc54aa1641c6fa0e151419361c8f23", nc=00000001, '
                 'qop="auth"'),
                ('username="username", realm="test realm", nonce="%s", '
                 'uri="/write/", response="%s", algorithm="md5"'))

authRequest2 = (('username="username", realm="test realm", nonce="%s", '
                 'uri="/write/", response="%s", algorithm="md5", '
                 'cnonce="29fc54aa1641c6fa0e151419361c8f23", nc=00000002, '
                 'qop="auth"'),
                ('username="username", realm="test realm", nonce="%s", '
                 'uri="/write/", response="%s", algorithm="md5"'))

authRequest3 = ('username="username", realm="test realm", nonce="%s", '
                'uri="/write/", response="%s", algorithm="md5"')

namelessAuthRequest = 'realm="test realm",nonce="doesn\'t matter"'

emtpyAttributeAuthRequest = 'realm=,nonce="doesn\'t matter"'


class DigestAuthTestCase(unittest.TestCase):
    """
    Test the behavior of DigestCredentialFactory
    """

    def setUp(self):
        """
        Create a DigestCredentialFactory for testing
        """
        self.path1 = self.mktemp()
        self.path2 = self.mktemp()
        os.mkdir(self.path1)
        os.mkdir(self.path2)

        self.credentialFactories = (QopDigestCredentialFactory(
                                          'md5',
                                          'auth',
                                          'test realm',
                                          self.path1
                                      ),
                                      QopDigestCredentialFactory(
                                          'md5',
                                          '',
                                          'test realm',
                                          self.path2
                                      ))

    def tearDown(self):
        rmdir(self.path1)
        rmdir(self.path2)

    def getDigestResponse(self, challenge, ncount):
        """
        Calculate the response for the given challenge
        """
        nonce = challenge.get('nonce')
        algo = challenge.get('algorithm').lower()
        qop = challenge.get('qop')

        if qop:
            expected = digest.calcResponse(
                digest.calcHA1(algo,
                               "username",
                               "test realm",
                               "password",
                               nonce,
                               cnonce),
                algo, nonce, ncount, cnonce, qop, "GET", "/write/", None
                )
        else:
            expected = digest.calcResponse(
                digest.calcHA1(algo,
                               "username",
                               "test realm",
                               "password",
                               nonce,
                               cnonce),
                algo, nonce, None, None, None, "GET", "/write/", None
                )
        return expected

    def test_getChallenge(self):
        """
        Test that all the required fields exist in the challenge,
        and that the information matches what we put into our
        DigestCredentialFactory
        """

        challenge = self.credentialFactories[0].getChallenge(clientAddress)
        self.assertEquals(challenge['qop'], 'auth')
        self.assertEquals(challenge['realm'], 'test realm')
        self.assertEquals(challenge['algorithm'], 'md5')
        self.assertTrue(challenge.has_key("nonce"))

        challenge = self.credentialFactories[1].getChallenge(clientAddress)
        self.assertFalse(challenge.has_key('qop'))
        self.assertEquals(challenge['realm'], 'test realm')
        self.assertEquals(challenge['algorithm'], 'md5')
        self.assertTrue(challenge.has_key("nonce"))

    def test_response(self):
        """
        Test that we can decode a valid response to our challenge
        """

        for ctr, factory in enumerate(self.credentialFactories):
            challenge = factory.getChallenge(clientAddress)
    
            clientResponse = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            creds = factory.decode(clientResponse, _trivial_GET())
            self.failUnless(creds.checkPassword('password'))

    def test_multiResponse(self):
        """
        Test that multiple responses to to a single challenge are handled
        successfully.
        """

        for ctr, factory in enumerate(self.credentialFactories):
            challenge = factory.getChallenge(clientAddress)
    
            clientResponse = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            creds = factory.decode(clientResponse, _trivial_GET())
            self.failUnless(creds.checkPassword('password'))
    
            clientResponse = authRequest2[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000002"),
            )
    
            creds = factory.decode(clientResponse, _trivial_GET())
            self.failUnless(creds.checkPassword('password'))

    def test_failsWithDifferentMethod(self):
        """
        Test that the response fails if made for a different request method
        than it is being issued for.
        """

        for ctr, factory in enumerate(self.credentialFactories):
            challenge = factory.getChallenge(clientAddress)
    
            clientResponse = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            creds = factory.decode(clientResponse,
                                                  SimpleRequest(None, 'POST', '/'))
            self.failIf(creds.checkPassword('password'))

    def test_noUsername(self):
        """
        Test that login fails when our response does not contain a username,
        or the username field is empty.
        """

        # Check for no username
        for factory in self.credentialFactories:
            e = self.assertRaises(error.LoginFailed,
                                  factory.decode,
                                  namelessAuthRequest,
                                  _trivial_GET())
            self.assertEquals(str(e), "Invalid response, no username given.")
    
            # Check for an empty username
            e = self.assertRaises(error.LoginFailed,
                                  factory.decode,
                                  namelessAuthRequest + ',username=""',
                                  _trivial_GET())
            self.assertEquals(str(e), "Invalid response, no username given.")

    def test_noNonce(self):
        """
        Test that login fails when our response does not contain a nonce
        """

        for factory in self.credentialFactories:
            e = self.assertRaises(error.LoginFailed,
                                  factory.decode,
                                  'realm="Test",username="Foo",opaque="bar"',
                                  _trivial_GET())
            self.assertEquals(str(e), "Invalid response, no nonce given.")

    def test_emptyAttribute(self):
        """
        Test that login fails when our response contains an attribute
        with no value,
        """

        # Check for no username
        for factory in self.credentialFactories:
            e = self.assertRaises(error.LoginFailed,
                                  factory.decode,
                                  emtpyAttributeAuthRequest,
                                  _trivial_GET())
            self.assertEquals(str(e), "Invalid response, no username given.")

    def test_checkHash(self):
        """
        Check that given a hash of the form 'username:realm:password'
        we can verify the digest challenge
        """

        for ctr, factory in enumerate(self.credentialFactories):
            challenge = factory.getChallenge(clientAddress)
    
            clientResponse = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            creds = factory.decode(clientResponse, _trivial_GET())
    
            self.failUnless(creds.checkHash(
                    md5.md5('username:test realm:password').hexdigest()))
    
            self.failIf(creds.checkHash(
                    md5.md5('username:test realm:bogus').hexdigest()))

    def test_invalidNonceCount(self):
        """
        Test that login fails when the nonce-count is repeated.
        """

        credentialFactories = (
            FakeDigestCredentialFactory('md5', 'auth', 'test realm', self.path1),
            FakeDigestCredentialFactory('md5', '', 'test realm', self.path2)
        )

        for ctr, factory in enumerate(credentialFactories):
            challenge = factory.getChallenge(clientAddress)
    
            clientResponse1 = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            clientResponse2 = authRequest2[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000002"),
            )
    
            factory.decode(clientResponse1, _trivial_GET())
            factory.decode(clientResponse2, _trivial_GET())
    
            if challenge.get('qop') is not None:
                self.assertRaises(
                    error.LoginFailed,
                    factory.decode,
                    clientResponse2,
                    _trivial_GET()
                )
                
                challenge = factory.getChallenge(clientAddress)

                clientResponse1 = authRequest1[ctr] % (
                    challenge['nonce'],
                    self.getDigestResponse(challenge, "00000001"),
                )
                del challenge['qop']
                clientResponse3 = authRequest3 % (
                    challenge['nonce'],
                    self.getDigestResponse(challenge, "00000002"),
                )
                factory.decode(clientResponse1, _trivial_GET())
                self.assertRaises(
                    error.LoginFailed,
                    factory.decode,
                    clientResponse3,
                    _trivial_GET()
                )

    def test_invalidNonce(self):
        """
        Test that login fails when the given nonce from the response, does not
        match the nonce encoded in the opaque.
        """

        credentialFactories = (
            FakeDigestCredentialFactory('md5', 'auth', 'test realm', self.path1),
            FakeDigestCredentialFactory('md5', '', 'test realm', self.path2)
        )

        for ctr, factory in enumerate(credentialFactories):
            challenge = factory.getChallenge(clientAddress)
            challenge['nonce'] = "noNoncense"
    
            clientResponse = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            request = _trivial_GET()
            self.assertRaises(
                error.LoginFailed,
                factory.decode,
                clientResponse,
                request
            )

            factory.invalidate(factory.generateNonce())
            response = UnauthorizedResponse({"Digest":factory}, request.remoteAddr)
            wwwhdrs = response.headers.getHeader("www-authenticate")[0][1]

    def test_incompatibleClientIp(self):
        """
        Test that the login fails when the request comes from a client ip
        other than what is encoded in the opaque.
        """

        credentialFactories = (
            FakeDigestCredentialFactory('md5', 'auth', 'test realm', self.path1),
            FakeDigestCredentialFactory('md5', '', 'test realm', self.path2)
        )

        for ctr, factory in enumerate(credentialFactories):
            challenge = factory.getChallenge(address.IPv4Address('TCP', '127.0.0.2', 80))
    
            clientResponse = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            request = _trivial_GET()
            self.assertRaises(
                error.LoginFailed,
                factory.decode,
                clientResponse,
                request
            )

            response = UnauthorizedResponse({"Digest":factory}, request.remoteAddr)
            wwwhdrs = response.headers.getHeader("www-authenticate")[0][1]
            self.assertTrue('stale' not in wwwhdrs, msg="Stale parameter in Digest WWW-Authenticate headers: %s" % (wwwhdrs,))

    def test_oldNonce(self):
        """
        Test that the login fails when the given opaque is older than
        DigestCredentialFactory.CHALLENGE_LIFETIME_SECS
        """

        credentialFactories = (
            FakeDigestCredentialFactory('md5', 'auth', 'test realm', self.path1),
            FakeDigestCredentialFactory('md5', '', 'test realm', self.path2)
        )

        for ctr, factory in enumerate(credentialFactories):
            challenge = factory.getChallenge(clientAddress)
            clientip, nonce_count, timestamp = factory.db.get(challenge['nonce'])
            factory.db.set(challenge['nonce'], (clientip, nonce_count, timestamp - 2 * digest.DigestCredentialFactory.CHALLENGE_LIFETIME_SECS))
    
            clientResponse = authRequest1[ctr] % (
                challenge['nonce'],
                self.getDigestResponse(challenge, "00000001"),
            )
    
            request = _trivial_GET()
            self.assertRaises(
                error.LoginFailed,
                factory.decode,
                clientResponse,
                request
            )
            
            response = UnauthorizedResponse({"Digest":factory}, request.remoteAddr)
            wwwhdrs = response.headers.getHeader("www-authenticate")[0][1]
            self.assertTrue('stale' in wwwhdrs, msg="No stale parameter in Digest WWW-Authenticate headers: %s" % (wwwhdrs,))
            self.assertEquals(wwwhdrs['stale'], 'true', msg="stale parameter not set to true in Digest WWW-Authenticate headers: %s" % (wwwhdrs,))

    def test_incompatibleCalcHA1Options(self):
        """
        Test that the appropriate error is raised when any of the
        pszUsername, pszRealm, or pszPassword arguments are specified with
        the preHA1 keyword argument.
        """

        arguments = (
            ("user", "realm", "password", "preHA1"),
            (None, "realm", None, "preHA1"),
            (None, None, "password", "preHA1"),
            )

        for pszUsername, pszRealm, pszPassword, preHA1 in arguments:
            self.assertRaises(
                TypeError,
                digest.calcHA1,
                "md5",
                pszUsername,
                pszRealm,
                pszPassword,
                "nonce",
                "cnonce",
                preHA1=preHA1
                )


def _trivial_GET():
    return SimpleRequest(None, 'GET', '/')

