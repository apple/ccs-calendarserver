from twisted.trial.unittest import TestCase

from calendarserver.push.amppush import AMPPushMaster

from contrib.performance.loadtest.push import PushMonitor

class PushMonitorTests(TestCase):
    def fakePush(self, inboundID, dataChangedTimestamp, priority=5):
        self.monitor._receivedAMPPush(inboundID, dataChangedTimestamp, priority)

    def setUp(self):
        self.pushMaster = AMPPushMaster()

        self.monitor = PushMonitor(
            None,
            'localhost',
            62311,
            self.receivedPush
        )
        self.monitor.begin()

    def sendNotification(self, href, pushkey):
        self.pushMaster.notify(href, pushkey, None, None)

    def test_addPushkey(self):
        pass

    def test_removePushkey(self):
        pass

    def tearDown(self):
        self.monitor.end()
