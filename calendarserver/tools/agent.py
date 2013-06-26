#!/usr/bin/env python

##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
from __future__ import print_function

import cStringIO
import socket

from calendarserver.tap.util import getRootResource
from twext.python.plistlib import readPlistFromString, writePlistToString
from twisted.application.internet import StreamServerEndpointService
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernameHashedPassword
from twisted.cred.error import UnauthorizedLogin 
from twisted.cred.portal import IRealm, Portal
from twisted.internet.defer import inlineCallbacks, returnValue, succeed, fail
from twisted.internet.endpoints import AdoptedStreamServerEndpoint
from twisted.internet.protocol import Factory
from twisted.protocols import amp
from twisted.web.guard import HTTPAuthSessionWrapper, DigestCredentialFactory
from twisted.web.resource import IResource, Resource, ForbiddenResource
from twisted.web.server import Site, NOT_DONE_YET
from zope.interface import implements


# TODO, implement this:
# from launchd import getLaunchdSocketFds

def getLaunchdSocketFds():
    pass

# For the sample client, below:
from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator

from twext.python.log import Logger
log = Logger()


"""
A service spawned on-demand by launchd, meant to handle configuration requests
from Server.app.  When a request comes in on the socket specified in the launchd
agent.plist, launchd will run "caldavd -t Agent" which ends up creating this
service.  Requests are made using HTTP POSTS to /gateway, and are authenticated
by OpenDirectory.
"""

class DirectoryServiceChecker:
    """
    A checker that knows how to ask OpenDirectory to authenticate via Digest
    """
    implements(ICredentialsChecker)

    credentialInterfaces = (IUsernameHashedPassword,)

    from calendarserver.platform.darwin.od import opendirectory
    directoryModule = opendirectory

    def __init__(self, node):
        """
        @param node: the name of the OpenDirectory node to use, e.g. /Local/Default
        """
        self.node = node
        self.directory = self.directoryModule.odInit(node)

    def requestAvatarId(self, credentials):
        record = self.directoryModule.getUserRecord(self.directory, credentials.username)

        if record is not None:
            try:
                if "algorithm" not in credentials.fields:
                    credentials.fields["algorithm"] = "md5"

                challenge = 'Digest realm="%(realm)s", nonce="%(nonce)s", algorithm=%(algorithm)s' % credentials.fields

                response = (
                    'Digest username="%(username)s", '
                    'realm="%(realm)s", '
                    'nonce="%(nonce)s", '
                    'uri="%(uri)s", '
                    'response="%(response)s",'
                    'algorithm=%(algorithm)s'
                ) % credentials.fields

            except KeyError as e:
                log.error(
                    "OpenDirectory (node=%s) error while performing digest authentication for user %s: "
                    "missing digest response field: %s in: %s"
                    % (self.node, credentials.username, e, credentials.fields)
                )
                return fail(UnauthorizedLogin())

            try:
                if self.directoryModule.authenticateUserDigest(self.directory,
                    self.node,
                    credentials.username,
                    challenge,
                    response,
                    credentials.method
                ):
                    return succeed(credentials.username)
                else:
                    log.error("Failed digest auth with response: %s" % (response,))
                    return fail(UnauthorizedLogin())
            except self.directoryModule.ODNSerror as e:
                log.error(
                    "OpenDirectory error while performing digest authentication for user %s: %s"
                    % (credentials.username, e)
                )
                return fail(UnauthorizedLogin())

        else:
            return fail(UnauthorizedLogin())


class CustomDigestCredentialFactory(DigestCredentialFactory):
    """
    DigestCredentialFactory without qop, to interop with OD.
    """

    def getChallenge(self, address):
        result = DigestCredentialFactory.getChallenge(self, address)
        del result["qop"]
        return result


class AgentRealm(object):
    """
    Only allow a specified list of avatar IDs to access the site
    """
    implements(IRealm)

    def __init__(self, root, allowedAvatarIds):
        """
        @param root: The root resource of the site
        @param allowedAvatarIds: The list of IDs to allow access to
        """
        self.root = root
        self.allowedAvatarIds = allowedAvatarIds

    def requestAvatar(self, avatarId, mind, *interfaces):
        if IResource in interfaces:
            if avatarId in self.allowedAvatarIds:
                return (IResource, self.root, lambda: None)
            else:
                return (IResource, ForbiddenResource(), lambda: None)

        raise NotImplementedError()



class AgentGatewayResource(Resource):
    """
    The gateway resource which forwards incoming requests through gateway.Runner.
    """
    isLeaf = True

    def __init__(self, store, davRootResource, directory):
        """
        @param store: an already opened store
        @param davRootResource: the root resource, required for principal
            operations
        @param directory: a directory service
        """
        Resource.__init__(self)
        self.store = store
        self.davRootResource = davRootResource
        self.directory = directory

    def render_POST(self, request):
        """
        Take the body of the POST request and feed it to gateway.Runner();
        return the result as the response body.
        """

        def onSuccess(result, output):
            txt = output.getvalue()
            output.close()
            request.write(txt)
            request.finish()

        def onError(failure):
            message = failure.getErrorMessage()
            tbStringIO = cStringIO.StringIO()
            failure.printTraceback(file=tbStringIO)
            tbString = tbStringIO.getvalue()
            tbStringIO.close()
            error = {
                "Error" : message,
                "Traceback" : tbString,
            }
            log.error("command failed %s" % (failure,))
            request.write(writePlistToString(error))
            request.finish()

        from calendarserver.tools.gateway import Runner
        body = request.content.read()
        command = readPlistFromString(body)
        output = cStringIO.StringIO()
        runner = Runner(self.davRootResource, self.directory, self.store,
            [command], output=output)
        d = runner.run()
        d.addCallback(onSuccess, output)
        d.addErrback(onError)
        return NOT_DONE_YET





def makeAgentService(store):
    """
    Returns a service which will process GatewayAMPCommands, using a socket
    file descripter acquired by launchd

    @param store: an already opened store
    @returns: service
    """
    from twisted.internet import reactor

    sockets = getLaunchdSocketFds() 
    fd = sockets["AgentSocket"][0]
    
    family = socket.AF_INET
    endpoint = AdoptedStreamServerEndpoint(reactor, fd, family)

    from twistedcaldav.config import config
    davRootResource = getRootResource(config, store)
    directory = davRootResource.getDirectory()

    root = Resource()
    root.putChild("gateway", AgentGatewayResource(store,
        davRootResource, directory))

    realmName = "/Local/Default"
    portal = Portal(AgentRealm(root, ["com.apple.calendarserver"]),
        [DirectoryServiceChecker(realmName)])
    credentialFactory = CustomDigestCredentialFactory("md5", realmName)
    wrapper = HTTPAuthSessionWrapper(portal, [credentialFactory])

    site = Site(wrapper)

    return StreamServerEndpointService(endpoint, site)




#
# Alternate implementation using AMP instead of HTTP
#

class GatewayAMPCommand(amp.Command):
    """
    A command to be executed by gateway.Runner 
    """
    arguments = [('command', amp.String())]
    response = [('result', amp.String())]


class GatewayAMPProtocol(amp.AMP):
    """
    Passes commands to gateway.Runner and returns the results
    """

    def __init__(self, store, davRootResource, directory):
        """
        @param store: an already opened store
        @param davRootResource: the root resource, required for principal
            operations
        @param directory: a directory service
        """
        amp.AMP.__init__(self)
        self.store = store
        self.davRootResource = davRootResource
        self.directory = directory


    @GatewayAMPCommand.responder
    @inlineCallbacks
    def gatewayCommandReceived(self, command):
        """
        Process a command via gateway.Runner

        @param command: GatewayAMPCommand
        @returns: a deferred returning a dict
        """
        command = readPlistFromString(command)
        output = cStringIO.StringIO()
        from calendarserver.tools.gateway import Runner
        runner = Runner(self.davRootResource, self.directory, self.store,
            [command], output=output)

        try:
            yield runner.run()
            result = output.getvalue()
            output.close()
        except Exception as e:
            error = {
                "Error" : str(e),
            }
            result = writePlistToString(error)

        output.close()
        returnValue(dict(result=result))


class GatewayAMPFactory(Factory):
    """
    Builds GatewayAMPProtocols
    """
    protocol = GatewayAMPProtocol

    def __init__(self, store):
        """
        @param store: an already opened store
        """
        self.store = store
        from twistedcaldav.config import config
        self.davRootResource = getRootResource(config, self.store)
        self.directory = self.davRootResource.getDirectory()

    def buildProtocol(self, addr):
        return GatewayAMPProtocol(self.store, self.davRootResource,
            self.directory)



#
# A test AMP client
#

command = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>getLocationAndResourceList</string>
</dict>
</plist>"""

def getList():
    creator = ClientCreator(reactor, amp.AMP)
    d = creator.connectTCP('sagen.apple.com', 62308)

    def connected(ampProto):
        return ampProto.callRemote(GatewayAMPCommand, command=command)
    d.addCallback(connected)

    def resulted(result):
        return result['result']
    d.addCallback(resulted)

    def done(result):
        print('Done: %s' % (result,))
        reactor.stop()
    d.addCallback(done)

if __name__ == '__main__':
    getList()
    reactor.run()
