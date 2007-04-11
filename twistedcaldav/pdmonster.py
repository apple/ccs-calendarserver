from twisted.internet import protocol
from twisted.internet import address
from twisted.protocols import amp

from twisted.web2.resource import WrapperResource

from twistedcaldav import logging

class PDClientAddressWrapper(WrapperResource):
    def __init__(self, resource, socket):
        super(PDClientAddressWrapper, self).__init__(resource)

        self.socket = socket
        self.client = None
        self.protocol = None

    def hook(self, request):
        from twisted.internet import reactor

        def _gotProtocol(proto):
            self.protocol = proto

            return self.hook(request)

        def _gotAddress(result):
            logging.debug('result = %r' % (result,))
            request.remoteAddr = address.IPv4Address(
                'TCP',
                result['host'],
                int(result['port']))

        if self.protocol is not None:
            host, port = request.remoteAddr.host, request.remoteAddr.port
            logging.debug("GetClientAddress(host=%r, port=%r)" % (host, port))
            d = self.protocol.callRemoteString("GetClientAddress",
                                                  host=host,
                                                  port=str(port))
            d.addCallback(_gotAddress)
            return d

        else:
            self.client = protocol.ClientCreator(reactor, amp.AMP)

            d = self.client.connectUNIX(self.socket)
            d.addCallback(_gotProtocol)

            return d
