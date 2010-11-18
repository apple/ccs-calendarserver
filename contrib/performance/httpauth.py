##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

import shlex, urlparse

from twisted.web.http_headers import Headers

class BasicChallenge(object):
    def __init__(self, realm):
        self.realm = realm


    def response(self, uri, keyring):
        username, password = keyring.passwd.find_user_password(self.realm, uri)
        credentials = ('%s:%s' % (username, password)).encode('base64').strip()
        authorization = 'basic ' + credentials
        return {'authorization': [authorization]}



class AuthHandlerAgent(object):
    def __init__(self, agent, authinfo):
        self._agent = agent
        self._authinfo = authinfo
        self._challenged = {}


    def _authKey(self, method, uri):
        return urlparse.urlparse(uri)[:2]


    def request(self, method, uri, headers=None, bodyProducer=None):
        key = self._authKey(method, uri)
        if key in self._challenged:
            return self._respondToChallenge(self._challenged[key], method, uri, headers, bodyProducer)
        d = self._agent.request(method, uri, headers, bodyProducer)
        d.addCallback(self._authenticate, method, uri, headers, bodyProducer)
        return d


    def _parse(self, authorization):
        parts = shlex.split(authorization)
        scheme = parts.pop(0)
        args = dict([p.split('=', 1) for p in parts])
        if scheme == 'basic':
            return BasicChallenge(**args)
        return None

    
    def _respondToChallenge(self, challenge, method, uri, headers, bodyProducer):
        if headers is None:
            headers = Headers()
        else:
            headers = Headers(dict(headers.getAllRawHeaders()))
        for k, vs in challenge.response(uri, self._authinfo).iteritems():
            for v in vs:
                headers.addRawHeader(k, v)
        return self._agent.request(method, uri, headers, bodyProducer)


    def _authenticate(self, response, method, uri, headers, bodyProducer):
        if response.code == 401:
            # Look for a challenge
            authorization = response.headers.getRawHeaders('www-authenticate')
            if authorization is None:
                raise Exception("401 response with no WWW-Authenticate header")

            for auth in authorization:
                challenge = self._parse(auth)
                if challenge is None:
                    continue
                self._challenged[self._authKey(method, uri)] = challenge
                return self._respondToChallenge(challenge, method, uri, headers, bodyProducer)
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
        print response.code
        print response.headers
        reactor.stop()
    d.addCallback(deleted)
    d.addErrback(err)
    d.addCallback(lambda ign: reactor.stop())
    reactor.run()
