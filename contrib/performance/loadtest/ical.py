##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
##

from twisted.python.log import err
from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks
from twisted.web.http_headers import Headers
from twisted.web.client import Agent

from httpclient import StringProducer, readBody
from httpauth import AuthHandlerAgent

def loadRequestBody(label):
    return FilePath(__file__).sibling(label + '.request').getContent()

class SnowLeopard(object):
    """
    Implementation of the SnowLeopard iCal network behavior.
    """

    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody('sl_startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody('sl_startup_principals_report')
    _STARTUP_CALENDARHOME_PROPFIND = loadRequestBody('sl_startup_calendarhome_propfind')
    _STARTUP_NOTIFICATION_PROPFIND = loadRequestBody('sl_startup_notification_propfind')
    _STARTUP_PRINCIPAL_REPORT = loadRequestBody('sl_startup_principal_report')

    def __init__(self, reactor, host, port, user, auth):
        self.reactor = reactor
        self.agent = AuthHandlerAgent(Agent(self.reactor), auth)
        self.root = 'http://%s:%d/' % (host, port)
        self.user = user


    def _request(self, method, url, headers, body):
        # XXX Do return code checking here.
        return self.agent.request(method, url, headers, body)

    
    def _principalPropfind(self, user):
        d = self._request(
            'PROPFIND',
            self.root + 'principals/__uids__/' + user + '/',
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPAL_PROPFIND))
        d.addCallback(readBody)
        return d


    def _principalsReport(self):
        d = self._request(
            'REPORT',
            self.root + 'principals/',
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPALS_REPORT))
        d.addCallback(readBody)
        return d


    def _calendarHomePropfind(self, user):
        d = self._request(
            'PROPFIND',
            self.root + 'calendars/__uids__/' + user + '/',
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['1']}),
            StringProducer(self._STARTUP_CALENDARHOME_PROPFIND))
        d.addCallback(readBody)
        return d


    def _notificationPropfind(self, user):
        d = self._request(
            'PROPFIND',
            self.root + 'calendars/__uids__/' + user + '/notification/',
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['1']}),
            StringProducer(self._STARTUP_NOTIFICATION_PROPFIND))
        d.addCallback(readBody)
        return d

    
    def _principalReport(self, user):
        d = self._request(
            'REPORT',
            self.root + 'principals/__uids__/' + user + '/',
            Headers({
                    'content-type': ['text/xml'],
                    'depth': ['0']}),
            StringProducer(self._STARTUP_PRINCIPAL_REPORT))
        d.addCallback(readBody)
        return d


    @inlineCallbacks
    def run(self):
        """
        Emulate a CalDAV client.
        """
        # Orient ourselves, or something
        print (yield self._principalPropfind(self.user))

        # Do another kind of thing I guess
        print (yield self._principalsReport())

        # Whatever
        print (yield self._calendarHomePropfind(self.user))

        # Learn stuff I guess
        print (yield self._notificationPropfind(self.user))

        # More too
        print (yield self._principalReport(self.user))


def main():
    from urllib2 import HTTPDigestAuthHandler
    from twisted.internet import reactor
    auth = HTTPDigestAuthHandler()
    auth.add_password(
        realm="Test Realm",
        uri="http://127.0.0.1:8008/",
        user="user01",
        passwd="user01")
    client = SnowLeopard(reactor, '127.0.0.1', 8008, 'user01', auth)
    d = client.run()
    d.addErrback(err, "Snow Leopard client run() problem")
    d.addCallback(lambda ignored: reactor.stop())
    reactor.run()


if __name__ == '__main__':
    main()
