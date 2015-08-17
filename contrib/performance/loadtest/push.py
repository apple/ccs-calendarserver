from calendarserver.push.amppush import subscribeToIDs
from twisted.internet.defer import succeed

class PushMonitor(object):
    """
    Representation of a watchguard that monitors
    push notifications (AMP Push)
    """

    def __init__(
        self,
        reactor,
        ampPushHost,
        ampPushPort,
        callback
    ):
        """
        reactor: Twisted reactor
        ampPushHost: localhost
        ampPushPort: 62311
        callback: a one-argument function that is fired with a calendar href
                  upon receipt of a push notification for that resource
        """
        self.reactor = reactor
        self.ampPushHost = ampPushHost
        self.ampPushPort = ampPushPort

        # Keep track of AMP parameters for calendar homes we encounter.  This
        # dictionary has calendar home URLs as keys and pushkeys as
        # values.
        self.ampPushkeys = {}

    def begin(self):
        self._monitorAmpPush()

    def end(self):
        pass


    def _monitorAmpPush(self):
        """
        Start monitoring for AMP-based push notifications
        """
        subscribeToIDs(
            self.ampPushHost, self.ampPushPort, self.ampPushkeys,
            self._receivedAMPPush, self.reactor
        )


    def _receivedAMPPush(self, inboundID, dataChangedTimestamp, priority=5):
        print("-" * 64)
        print("{} received a PUSH with ID={}, timestamp={}, priority={}".format(self.record.commonName, inboundID, dataChangedTimestamp, priority))
        print("By the way, my AMP keys are {}".format(self.ampPushkeys))
        print("-" * 64)

        for href, calendar_id in self.ampPushkeys.iteritems():
            if inboundID == calendar_id:
                self.callback(href)
                break
        else:
            # Somehow we are not subscribed to this inboundID
            print("*" * 16 + "Oh no - we're not subscribed to " + str(inboundID) + " but we received a notification anyway!")
            pass

    def unsubscribeFromAll(self):
        return succeed(None)


    def addPushkey(self, href, pushkey):
        pass # Should I subscribe to IDs right now?

    def removePushkey(self, pushkey):
        pass # Should I unsubscribe right now

    def isSubscribedTo(self, href):
        return href in self.ampPushkeys
