from twisted.internet import protocol
from twisted.internet import address
from twisted.protocols import amp

from twext.web2.resource import WrapperResource

from twext.python.log import LoggingMixIn

class PDClientAddressWrapper(WrapperResource, LoggingMixIn):
    def __init__(self, resource, socket, directory):
        super(PDClientAddressWrapper, self).__init__(resource)

        self.socket = socket
        self.client = None
        self.protocol = None
        
        self.directory = directory
        
    def getDirectory(self):
        return self.directory

    def hook(self, request):
        from twisted.internet import reactor

        def _gotProtocol(proto):
            self.protocol = proto

            return self.hook(request)

        def _gotError(result):
            result.trap(amp.RemoteAmpError)
            if result.value.errorCode != 'UNKNOWN_PORT':
                return result
            self.log_error('Unknown Port: %s' % (request.remoteAddr,))

        def _gotAddress(result):
            self.log_debug('result = %r' % (result,))
            request.remoteAddr = address.IPv4Address(
                'TCP',
                result['host'],
                int(result['port']))
            request._pdRewritten = True

        if self.protocol is not None:
            if hasattr(request, '_pdRewritten'):
                return

            host, port = request.remoteAddr.host, request.remoteAddr.port
            self.log_debug("GetClientAddress(host=%r, port=%r)" % (host, port))
            d = self.protocol.callRemoteString("GetClientAddress",
                                                  host=host,
                                                  port=str(port))
            d.addCallbacks(_gotAddress, _gotError)
            return d

        else:
            self.client = protocol.ClientCreator(reactor, amp.AMP)

            d = self.client.connectUNIX(self.socket)
            d.addCallback(_gotProtocol)

            return d
