##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from __future__ import print_function
from caldavclientlibrary.protocol.http.authentication.digest import Digest
from twisted.python.log import msg
from twisted.web.http import UNAUTHORIZED
from twisted.web.http_headers import Headers
import urlparse
import urllib2

class BasicChallenge(object):
    def __init__(self, realm):
        self.realm = realm


    def response(self, uri, method, keyring):
        if type(keyring) is dict:
            keyring = keyring['basic']
        username, password = keyring.passwd.find_user_password(self.realm, uri)
        credentials = ('%s:%s' % (username, password)).encode('base64').strip()
        authorization = 'basic ' + credentials
        return {'authorization': [authorization]}



class DigestChallenge(object):
    def __init__(self, realm, **fields):
        self.realm = realm
        self.fields = fields
        self.fields['realm'] = realm


    def response(self, uri, method, keyring):
        if type(keyring) is dict:
            keyring = keyring['digest']
        username, password = keyring.passwd.find_user_password(self.realm, uri)
        if username is None:
            raise RuntimeError("Credentials for realm=%s uri=%s not found" % (self.realm, uri))
        digest = Digest(username, password, [])
        digest.fields.update(self.fields)
        authorization = []

        class BigSigh:
            def getURL(self):
                return uri
        BigSigh.method = method
        BigSigh.url = uri

        digest.addHeaders(authorization, BigSigh())
        return {'authorization': [value for (_ignore_name, value) in authorization]}



class AuthHandlerAgent(object):
    def __init__(self, agent, authinfo):
        self._agent = agent
        self._authinfo = authinfo
        self._challenged = {}


    def _authKey(self, method, uri):
        return urlparse.urlparse(uri)[:2]


    def request(self, method, uri, headers=None, bodyProducer=None):
        return self._requestWithAuth(method, uri, headers, bodyProducer)


    def _requestWithAuth(self, method, uri, headers, bodyProducer):
        key = self._authKey(method, uri)
        if key in self._challenged:
            d = self._respondToChallenge(self._challenged[key], method, uri, headers, bodyProducer)
        else:
            d = self._agent.request(method, uri, headers, bodyProducer)
        d.addCallback(self._authenticate, method, uri, headers, bodyProducer)
        return d


    def _parse(self, authorization):
        try:
            scheme, rest = authorization.split(None, 1)
        except ValueError:
            # Probably "negotiate", which we don't support
            scheme = authorization
            rest = ""
        args = urllib2.parse_keqv_list(urllib2.parse_http_list(rest))
        challengeType = {
            'basic': BasicChallenge,
            'digest': DigestChallenge,
            }.get(scheme.lower())
        if challengeType is None:
            return "", None
        return scheme.lower(), challengeType(**args)


    def _respondToChallenge(self, challenge, method, uri, headers, bodyProducer):
        if headers is None:
            headers = Headers()
        else:
            headers = Headers(dict(headers.getAllRawHeaders()))
        for k, vs in challenge.response(uri, method, self._authinfo).iteritems():
            for v in vs:
                headers.addRawHeader(k, v)
        return self._agent.request(method, uri, headers, bodyProducer)


    def _authenticate(self, response, method, uri, headers, bodyProducer):
        if response.code == UNAUTHORIZED:
            if headers is None:
                authorization = None
            else:
                authorization = headers.getRawHeaders('authorization')
            msg("UNAUTHORIZED response to %s %s (Authorization=%r)" % (
                    method, uri, authorization))
            # Look for a challenge
            authorization = response.headers.getRawHeaders('www-authenticate')
            if authorization is None:
                raise Exception(
                    "UNAUTHORIZED response with no WWW-Authenticate header")

            # Always choose digest over basic if both present
            challenges = dict([self._parse(auth) for auth in authorization])
            if 'digest' in challenges:
                key = 'digest'
            elif 'basic' in challenges:
                key = 'basic'
            else:
                key = None
            if key:
                self._challenged[self._authKey(method, uri)] = challenges[key]
                return self._respondToChallenge(challenges[key], method, uri, headers, bodyProducer)
        return response



if __name__ == '__main__':
    from urllib2 import HTTPDigestAuthHandler
    handler = HTTPDigestAuthHandler()
    handler.add_password(
        realm="Test Realm",
        uri="http://localhost:8008/",
        user="user01",
        passwd="user01")

    from twisted.web.client import Agent
    from twisted.internet import reactor
    from twisted.python.log import err
    agent = AuthHandlerAgent(Agent(reactor), handler)
    d = agent.request(
        'DELETE', 'http://localhost:8008/calendars/users/user01/monkeys3/')
    def deleted(response):
        print(response.code)
        print(response.headers)
        reactor.stop()
    d.addCallback(deleted)
    d.addErrback(err)
    d.addCallback(lambda ign: reactor.stop())
    reactor.run()
