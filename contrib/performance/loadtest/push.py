from calendarserver.push.amppush import subscribeToIDs
from twisted.internet.defer import succeed

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
            with a calendar hrefupon receipt of a push notification
            for that resource
        @type callback: one-argument callable
        """
        self._reactor = reactor
        self._ampPushHost = ampPushHost
        self._ampPushPort = ampPushPort

        # Keep track of AMP parameters for calendar homes we encounter.  This
        # dictionary has calendar home URLs as keys and pushkeys as
        # values.
        self._ampPushkeys = {}

    def begin(self):
        """
        Start monitoring for AMP-based push notifications
        """
        self._subscribeToIDs(self.ampPushkeys)

    def end(self):
        """
        Finish monitoring push notifications. Any other cleanup should be done here
        """
        self._unsubscribeFromAll()

    def _subscribeToIDs(self, ids):

        subscribeToIDs(
            self._ampPushHost,
            self._ampPushPort,
            ids,
            self._receivedAmpPush,
            self._reactor
        )

    def _receivedAMPPush(self, inboundID, dataChangedTimestamp, priority=5):
        print("-" * 64)
        print("{} received a PUSH with ID={}, timestamp={}, priority={}".format(self.record.commonName, inboundID, dataChangedTimestamp, priority))
        print("By the way, my AMP keys are {}".format(self._ampPushkeys))
        print("-" * 64)

        for href, calendar_id in self.ampPushkeys.iteritems():
            if inboundID == calendar_id:
                self.callback(href)
                break
        else:
            # Somehow we are not subscribed to this inboundID
            print("*" * 16 + "Oh no - we're not subscribed to " + str(inboundID) + " but we received a notification anyway!")
            pass

    def _unsubscribeFromAll(self):
        # For now, the server doesn't support unsubscribing from pushkeys, so we simply
        # "forget" about our registered pushkeys
        self._ampPushkeys = {}


    def addPushkey(self, href, pushkey):
        self._ampPushkeys[href] = pushkey
        self.subscribeToIDs()


    def removePushkey(self, pushkey):
        # if self.ampPushkeys.has_value(pushkey):
        #     del self.ampPushKeys
        pass

    def isSubscribedTo(self, href):
        return href in self.ampPushkeys
