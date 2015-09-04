import uuid

from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.defer import inlineCallbacks, succeed

from calendarserver.push.amppush import SubscribeToID, UnsubscribeFromID, AMPPushClientFactory

class PushMonitor(object):
    """
    Watchguard that monitors push notifications (AMP Push)
    """

    def __init__(
        self,
        reactor,
        ampPushHost,
        ampPushPort,
        callback
    ):
        """
        @param reactor: Twisted reactor
        @type reactor: twisted.web.reactor
        @param ampPushHost: AMP host to connect to (e.g. 'localhost')
        @type ampPushHost: string
        @param ampPushPort: AMP port to connect to (e.g. 62311)
        @type ampPushPort: integer
        @param callback: a one-argument function that is fired
            with a calendar href upon receipt of a push notification
            for that resource
        @type callback: one-argument callable
        """

        if reactor is None:
            from twisted.internet import reactor

        self._reactor = reactor
        self._ampPushHost = ampPushHost
        self._ampPushPort = ampPushPort

        # Keep track of AMP parameters for calendar homes we encounter.  This
        # dictionary has pushkeys as keys and calendar home URLs as values.
        self._ampPushkeys = {}

        self._callback = callback

        self._token = str(uuid.uuid4()) # Unique token for this monitor
        self._endpoint = TCP4ClientEndpoint(self._reactor, self._ampPushHost, self._ampPushPort)
        self._factory = AMPPushClientFactory(self._receivedAMPPush)
        self._connected = False

    @inlineCallbacks
    def begin(self):
        """
        Start monitoring for AMP-based push notifications
        """
        self._protocol = yield self._endpoint.connect(self._factory)
        self._connected = True
        pushkeys = self._ampPushkeys.keys()
        yield self._subscribeToPushkeys(pushkeys)

    @inlineCallbacks
    def end(self):
        """
        Finish monitoring push notifications.
        """
        pushkeys = self._ampPushkeys.keys()
        self._ampPushkeys = {}
        yield self._unsubscribeFromPushkeys(pushkeys)

        # Close the connection between client and server
        yield self._protocol.transport.loseConnection()
        self._connected = False


    def addPushkey(self, pushkey, href):
        """
        Register a pushkey associated with a specific calendar href.

        @param pushkey: AMP pushkey returned by the server, used to listen to notifications
        @type pushkey: C{str}
        @param href: href of calendar home set. When the server triggers a push for the
            associated pushkey, the callback will be fired with this href
        @type href: C{str}

        Example Usage:
            monitor.addPushkey('/CalDAV/localhost/<uid>', '/calendars/__uids__/<uid>')
        """
        self._ampPushkeys[pushkey] = href
        return self._subscribeToPushkey(pushkey)

    def removePushkey(self, pushkey):
        """
        Unregister the calendar home associated with the specified pushkey
        """
        if pushkey in self._ampPushkeys:
            del self._ampPushkeys[pushkey]
        return self._unsubscribeFromPushkey(pushkey)

    def isSubscribedTo(self, href):
        """
        Returns true if and only if the given calendar href is actively being monitored
        """
        return href in self._ampPushkeys.itervalues()

    @inlineCallbacks
    def _subscribeToPushkeys(self, pushkeys):
        for pushkey in pushkeys:
            yield self._subscribeToPushkey(pushkey)

    @inlineCallbacks
    def _unsubscribeFromPushkeys(self, pushkeys):
        for pushkey in pushkeys:
            yield self._unsubscribeFromPushkey(pushkey)

    def _subscribeToPushkey(self, pushkey):
        if not self._connected:
            return succeed(None)
        return self._protocol.callRemote(SubscribeToID, token=self._token, id=pushkey)

    def _unsubscribeFromPushkey(self, pushkey):
        if not self._connected:
            return succeed(None)
        return self._protocol.callRemote(UnsubscribeFromID, id=pushkey)


    def _receivedAMPPush(self, inboundID, dataChangedTimestamp, priority=5):
        if inboundID in self._ampPushkeys:
            # Only react if we're tracking this pushkey
            href = self._ampPushkeys[inboundID]
            self._callback(href)
        else:
            # Somehow we are not subscribed to this pushkey
            pass
