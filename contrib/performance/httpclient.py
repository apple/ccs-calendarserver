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

from zope.interface import implements

from twisted.internet.protocol import Protocol
from twisted.internet.defer import Deferred, succeed
from twisted.web.iweb import IBodyProducer

class _DiscardReader(Protocol):
    def __init__(self, finished):
        self.finished = finished


    def dataReceived(self, bytes):
        pass


    def connectionLost(self, reason):
        self.finished.callback(None)



def readBody(response):
    if response.length == 0:
        return succeed(None)
    finished = Deferred()
    response.deliverBody(_DiscardReader(finished))
    return finished



class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self._body = body
        self.length = len(self._body)


    def startProducing(self, consumer):
        consumer.write(self._body)
        return succeed(None)


