from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from contrib.performance.loadtest.push import PushMonitor

class PushMonitorTests(TestCase):
    def sendFakePush(self, pushkey):
        self.monitor._receivedAMPPush(inboundID=pushkey, dataChangedTimestamp=None, priority=None)

    def receivedPush(self, calendar_href):
        self.history.append(calendar_href)

    def setUp(self):
        """
        Creates and begins a PushMonitor with a history-tracking callback
        """

        self.monitor = PushMonitor(
            None,
            'localhost',
            62311,
            self.receivedPush
        )
        self.history = []
        return self.monitor.begin()

    def test_noPushkey(self):
        """
        Monitor will not react to a push if there are no registered pushkeys
        """
        pushkey = '/CalDAV/abc/def/'
        calendar_home = '/foo/bar/'
        self.assertFalse(self.monitor.isSubscribedTo(calendar_home))
        self.sendFakePush(pushkey)
        self.assertEqual(self.history, [])

    @inlineCallbacks
    def test_addPushkey(self):
        """
        Adding a pushkey triggers a notification for the corresponding calendar home
        """
        pushkey = '/CalDAV/abc/def/'
        calendar_home = '/foo/bar/'
        yield self.monitor.addPushkey(pushkey, calendar_home)
        self.assertTrue(self.monitor.isSubscribedTo(calendar_home))
        self.sendFakePush(pushkey)
        self.assertEqual(self.history, [calendar_home])

    @inlineCallbacks
    def test_removePushkey(self):
        """
        Pushkeys can be unregistered
        """
        pushkey = '/CalDAV/abc/def/'
        calendar_home = '/foo/bar/'
        yield self.monitor.addPushkey(pushkey, calendar_home)
        self.assertTrue(self.monitor.isSubscribedTo(calendar_home))
        yield self.monitor.removePushkey(pushkey)
        self.assertFalse(self.monitor.isSubscribedTo(calendar_home))

        self.sendFakePush(pushkey)
        self.assertEqual(self.history, [])

    @inlineCallbacks
    def test_addDuplicatePushkeys(self):
        """
        Adding the same pushkey twice only registers it once
        """
        pushkey = '/CalDAV/abc/def/'
        calendar_home = '/foo/bar/'
        yield self.monitor.addPushkey(pushkey, calendar_home)
        yield self.monitor.addPushkey(pushkey, calendar_home)
        self.assertTrue(self.monitor.isSubscribedTo(calendar_home))
        self.sendFakePush(pushkey)
        self.assertEqual(self.history, [calendar_home])

    @inlineCallbacks
    def test_addOverridePushkeys(self):
        """
        Adding the same pushkey with a different calendar home
        unregisters the original
        """
        pushkey = '/CalDAV/abc/def/'
        calendar_home = '/foo/bar/'
        calendar_home_2 = '/foo/baz/'
        yield self.monitor.addPushkey(pushkey, calendar_home)
        self.assertTrue(self.monitor.isSubscribedTo(calendar_home))
        yield self.monitor.addPushkey(pushkey, calendar_home_2)
        self.assertFalse(self.monitor.isSubscribedTo(calendar_home))
        self.assertTrue(self.monitor.isSubscribedTo(calendar_home_2))

        self.sendFakePush(pushkey)
        self.assertEqual(self.history, [calendar_home_2])

    @inlineCallbacks
    def test_multiplePushkeys(self):
        """
        Monitor supports registering multiple pushkeys
        """
        pushkey = '/CalDAV/abc/def/'
        pushkey_2 = '/CalDAV/abc/xyz/'
        calendar_home = '/foo/bar/'
        calendar_home_2 = '/foo/baz/'
        yield self.monitor.addPushkey(pushkey, calendar_home)
        self.assertTrue(self.monitor.isSubscribedTo(calendar_home))
        yield self.monitor.addPushkey(pushkey_2, calendar_home_2)
        self.assertTrue(self.monitor.isSubscribedTo(calendar_home_2))
        self.sendFakePush(pushkey_2)
        self.assertEqual(self.history, [calendar_home_2])
        self.sendFakePush(pushkey)
        self.assertEqual(self.history, [calendar_home_2, calendar_home])

    def tearDown(self):
        return self.monitor.end()
