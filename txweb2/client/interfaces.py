# -*- test-case-name: txweb2.test.test_client -*-
##
# Copyright (c) 2007 Twisted Matrix Laboratories.
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
##

from zope.interface import Interface

class IHTTPClientManager(Interface):
    """I coordinate between multiple L{HTTPClientProtocol} objects connected to a
    single server to facilite request queuing and pipelining.
    """

    def clientBusy(proto):
        """Called when the L{HTTPClientProtocol} doesn't want to accept anymore
        requests.

        @param proto: The L{HTTPClientProtocol} that is changing state.
        @type proto: L{HTTPClientProtocol}
        """
        pass


    def clientIdle(proto):
        """Called when an L{HTTPClientProtocol} is able to accept more requests.

        @param proto: The L{HTTPClientProtocol} that is changing state.
        @type proto: L{HTTPClientProtocol}
        """
        pass


    def clientPipelining(proto):
        """Called when the L{HTTPClientProtocol} determines that it is able to
        support request pipelining.

        @param proto: The L{HTTPClientProtocol} that is changing state.
        @type proto: L{HTTPClientProtocol}
        """
        pass


    def clientGone(proto):
        """Called when the L{HTTPClientProtocol} disconnects from the server.

        @param proto: The L{HTTPClientProtocol} that is changing state.
        @type proto: L{HTTPClientProtocol}
        """
        pass
