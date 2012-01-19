##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

from twisted.web.client import HTTPPageGetter, HTTPClientFactory
from twisted.internet import reactor

def usernameForAuthToken(token, host="localhost", port=4444):
    """
    Send a GET request to the wiki collabd service to retrieve the user record
    name associated with the provided auth token.

    @param token: An auth token, usually passed in via cookie when webcal
        makes a request.
    @type token: C{str}
    @return: deferred returning a record name (C{str}) if successful, or
        if the auth token is not recognized a twisted.web.error.Error with
        status FORBIDDEN will errBack.
    """
    url = "http://%s:%d/cal/userForSession/%s" % (host, port, token,)
    return _getPage(url, host, port)


def accessForUserToWiki(user, wiki, host="localhost", port=4444):
    """
    Send a GET request to the wiki collabd service to retrieve the access level
    the given user (in GUID form) has to the given wiki (in wiki short-name
    form).

    @param user: The GUID of the user
    @type user: C{str}
    @param wiki: The short name of the wiki
    @type wiki: C{str}
    @return: deferred returning a access level (C{str}) if successful, or
        if the user is not recognized a twisted.web.error.Error with
        status FORBIDDEN will errBack; an unknown wiki will have a status
        of NOT_FOUND
    """
    url = "http://%s:%s/cal/accessLevelForUserWikiCalendar/%s/%s" % (host, port,
        user, wiki)
    return _getPage(url, host, port)


def _getPage(url, host, port):
    """
    Fetch the body of the given url via HTTP, connecting to the given host
    and port.

    @param url: The URL to GET
    @type url: C{str}
    @param host: The hostname to connect to
    @type host: C{str}
    @param port: The port number to connect to
    @type port: C{int}
    @return: A deferred; upon 200 success the body of the response is returned,
        otherwise a twisted.web.error.Error is the result.
    """
    factory = HTTPClientFactory(url)
    factory.protocol = HTTPPageGetter
    reactor.connectTCP(host, port, factory)
    return factory.deferred
