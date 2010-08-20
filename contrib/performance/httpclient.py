
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


