##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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
SMTP sending utility
"""

from cStringIO import StringIO

from twext.internet.adaptendpoint import connect
from twext.internet.gaiendpoint import GAIEndpoint
from twext.python.log import Logger
from twisted.internet import defer, ssl, reactor as _reactor
from twisted.mail.smtp import ESMTPSenderFactory

log = Logger()

class SMTPSender(object):

    def __init__(self, username, password, useSSL, server, port):
        self.username = username
        self.password = password
        self.useSSL = useSSL
        self.server = server
        self.port = port

    def sendMessage(self, fromAddr, toAddr, msgId, message):

        log.debug("Sending: %s" % (message,))
        def _success(result, msgId, fromAddr, toAddr):
            log.info("Sent IMIP message %s from %s to %s" %
                (msgId, fromAddr, toAddr))
            return True

        def _failure(failure, msgId, fromAddr, toAddr):
            log.error("Failed to send IMIP message %s from %s "
                           "to %s (Reason: %s)" %
                           (msgId, fromAddr, toAddr,
                            failure.getErrorMessage()))
            return False

        deferred = defer.Deferred()

        if self.useSSL:
            contextFactory = ssl.ClientContextFactory()
        else:
            contextFactory = None

        factory = ESMTPSenderFactory(
            self.username, self.password,
            fromAddr, toAddr,
            # per http://trac.calendarserver.org/ticket/416 ...
            StringIO(message.replace("\r\n", "\n")), deferred,
            contextFactory=contextFactory,
            requireAuthentication=False,
            requireTransportSecurity=self.useSSL)

        connect(GAIEndpoint(_reactor, self.server, self.port),
                factory)
        deferred.addCallback(_success, msgId, fromAddr, toAddr)
        deferred.addErrback(_failure, msgId, fromAddr, toAddr)
        return deferred
