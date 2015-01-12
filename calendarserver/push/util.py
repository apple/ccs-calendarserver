##
# Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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

from OpenSSL import crypto
from twext.python.log import Logger
from twisted.python.constants import Values, ValueConstant



class PushPriority(Values):
    """
    Constants to use for push priorities
    """
    low = ValueConstant(1)
    medium = ValueConstant(5)
    high = ValueConstant(10)



def getAPNTopicFromCertificate(certPath):
    """
    Given the path to a certificate, extract the UID value portion of the
    subject, which in this context is used for the associated APN topic.

    @param certPath: file path of the certificate
    @type certPath: C{str}

    @return: C{str} topic, or empty string if value is not found
    """
    certData = open(certPath).read()
    x509 = crypto.load_certificate(crypto.FILETYPE_PEM, certData)
    subject = x509.get_subject()
    components = subject.get_components()
    for name, value in components:
        if name == "UID":
            return value
    return ""



def validToken(token):
    """
    Return True if token is in hex and is 64 characters long, False
    otherwise
    """
    if len(token) != 64:
        return False

    try:
        token.decode("hex")
    except TypeError:
        return False

    return True



class TokenHistory(object):
    """
    Manages a queue of tokens and corresponding identifiers.  Queue is always
    kept below maxSize in length (older entries removed as needed).
    """

    def __init__(self, maxSize=200):
        """
        @param maxSize: How large the history is allowed to grow.  Once this
            size is reached, older entries are pruned as needed.
        @type maxSize: C{int}
        """
        self.maxSize = maxSize
        self.identifier = 0
        self.history = []


    def add(self, token):
        """
        Add a token to the history, and return the new identifier associated
        with this token.  Identifiers begin at 1 and increase each time this
        is called.  If the number of items in the history exceeds maxSize,
        older entries are removed to get the size down to maxSize.

        @param token: The token to store
        @type token: C{str}
        @returns: the message identifier associated with this token, C{int}
        """
        self.identifier += 1
        self.history.append((self.identifier, token))
        del self.history[:-self.maxSize]
        return self.identifier


    def extractIdentifier(self, identifier):
        """
        Look for the token associated with the identifier.  Remove the
        identifier-token pair from the history and return the token.  Return
        None if the identifier is not found in the history.

        @param identifier: The identifier to look up
        @type identifier: C{int}
        @returns: the token associated with this message identifier, C{str},
            or None if not found
        """
        for index, (id, token) in enumerate(self.history):
            if id == identifier:
                del self.history[index]
                return token
        return None



class PushScheduler(object):
    """
    Allows staggered scheduling of push notifications
    """
    log = Logger()

    def __init__(self, reactor, callback, staggerSeconds=1):
        """
        @param callback: The method to call when it's time to send a push
        @type callback: callable
        @param staggerSeconds: The number of seconds to stagger between each
            push
        @type staggerSeconds: integer
        """
        self.outstanding = {}
        self.reactor = reactor
        self.callback = callback
        self.staggerSeconds = staggerSeconds


    def schedule(self, tokens, key, dataChangedTimestamp, priority):
        """
        Schedules a batch of notifications for the given tokens, staggered
        with self.staggerSeconds between each one.  Duplicates are ignored,
        so if a token/key pair is already scheduled and not yet sent, a new
        one will not be scheduled for that pair.

        @param tokens: The device tokens to schedule notifications for
        @type tokens: List of C{str}
        @param key: The key to use for this batch of notifications
        @type key: C{str}
        @param dataChangedTimestamp: Timestamp (epoch seconds) for the data change
            which triggered this notification
        @type key: C{int}
        """
        scheduleTime = 0.0
        for token in tokens:
            internalKey = (token, key)
            if internalKey in self.outstanding:
                self.log.debug(
                    "PushScheduler already has this scheduled: %s" %
                    (internalKey,))
            else:
                self.outstanding[internalKey] = self.reactor.callLater(
                    scheduleTime, self.send, token, key, dataChangedTimestamp,
                    priority)
                self.log.debug(
                    "PushScheduler scheduled: %s in %.0f sec" %
                    (internalKey, scheduleTime))
                scheduleTime += self.staggerSeconds


    def send(self, token, key, dataChangedTimestamp, priority):
        """
        This method is what actually gets scheduled.  Its job is to remove
        its corresponding entry from the outstanding dict and call the
        callback.

        @param token: The device token to send a notification to
        @type token: C{str}
        @param key: The notification key
        @type key: C{str}
        @param dataChangedTimestamp: Timestamp (epoch seconds) for the data change
            which triggered this notification
        @type key: C{int}
        """
        self.log.debug("PushScheduler fired for %s %s %d" % (token, key, dataChangedTimestamp))
        del self.outstanding[(token, key)]
        return self.callback(token, key, dataChangedTimestamp, priority)


    def stop(self):
        """
        Cancel all outstanding delayed calls
        """
        for (token, key), delayed in self.outstanding.iteritems():
            self.log.debug("PushScheduler cancelling %s %s" % (token, key))
            delayed.cancel()
