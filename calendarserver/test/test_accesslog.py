##
# Copyright (c) 2015-2017 Apple Inc. All rights reserved.
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

from twisted.trial.unittest import TestCase
from calendarserver.accesslog import SystemMonitor, \
    RotatingFileAccessLoggingObserver
from twistedcaldav.stdconfig import config as stdconfig
from twistedcaldav.config import config
import time
import collections

hasattr(stdconfig, "Servers")   # Quell pyflakes


class AccessLog(TestCase):
    """
    Tests for L{calendarserver.accesslog}.
    """

    def test_systemMonitor(self):
        """
        L{SystemMonitor} generates the correct data.
        """

        monitor = SystemMonitor()
        self.assertNotEqual(monitor.items["cpu count"], 0)
        self.assertEqual(monitor.items["cpu use"], 0.0)

        monitor.update()
        self.assertNotEqual(monitor.items["cpu count"], 0)

        monitor.stop()
        self.assertNotEqual(monitor.items["cpu count"], 0)

    def test_disableSystemMonitor(self):
        """
        L{SystemMonitor} is not created when stats socket not in use.
        """

        logpath = self.mktemp()
        stats = {
            "type": "access-log",
            "log-format": "",
            "method": "GET",
            "uri": "/index.html",
            "statusCode": 200,
        }

        # Disabled
        self.patch(config.Stats, "EnableUnixStatsSocket", False)
        self.patch(config.Stats, "EnableTCPStatsSocket", False)

        logger = RotatingFileAccessLoggingObserver(logpath)
        self.assertTrue(logger.systemStats is None)

        logger.start()
        stats["log-format"] = "test1"
        logger.logStats(stats)
        self.assertTrue(logger.systemStats is None)

        logger.getStats()
        self.assertTrue(logger.systemStats is None)
        logger.stop()
        with open(logpath) as f:
            self.assertIn("test1", f.read())

        # Enabled
        self.patch(config.Stats, "EnableUnixStatsSocket", True)
        self.patch(config.Stats, "EnableTCPStatsSocket", False)

        logger = RotatingFileAccessLoggingObserver(logpath)
        self.assertTrue(logger.systemStats is None)

        logger.start()
        stats["log-format"] = "test2"
        logger.logStats(stats)
        self.assertTrue(logger.systemStats is not None)
        logger.stop()
        with open(logpath) as f:
            self.assertIn("test2", f.read())

        # Enabled
        self.patch(config.Stats, "EnableUnixStatsSocket", False)
        self.patch(config.Stats, "EnableTCPStatsSocket", True)

        logger = RotatingFileAccessLoggingObserver(logpath)
        self.assertTrue(logger.systemStats is None)

        logger.start()
        stats["log-format"] = "test3"
        logger.logStats(stats)
        self.assertTrue(logger.systemStats is not None)
        logger.stop()
        with open(logpath) as f:
            self.assertIn("test3", f.read())

        # Enabled
        self.patch(config.Stats, "EnableUnixStatsSocket", True)
        self.patch(config.Stats, "EnableTCPStatsSocket", True)

        logger = RotatingFileAccessLoggingObserver(logpath)
        self.assertTrue(logger.systemStats is None)

        logger.start()
        stats["log-format"] = "test4"
        logger.logStats(stats)
        self.assertTrue(logger.systemStats is not None)
        logger.stop()
        with open(logpath) as f:
            self.assertIn("test4", f.read())

        SystemMonitor.CPUStats = collections.namedtuple("CPUStats", ("total", "idle",))

    def test_unicodeLog(self):
        """
        Make sure L{RotatingFileAccessLoggingObserver} handles non-ascii data properly.
        """

        logpath = self.mktemp()
        observer = RotatingFileAccessLoggingObserver(logpath)
        observer.start()
        observer.accessLog(u"Can\u2019 log this")
        observer.stop()

        with open(logpath) as f:
            self.assertIn("log this", f.read())

    def test_truncateStats(self):
        """
        Make sure L{RotatingFileAccessLoggingObserver.ensureSequentialStats}
        properly truncates stats data.
        """

        logpath = self.mktemp()
        observer = RotatingFileAccessLoggingObserver(logpath)
        observer.systemStats = SystemMonitor()
        observer.start()

        # Fill stats with some old entries
        t = int(time.time() / 60.0) * 60
        t -= 100 * 60
        for i in range(10):
            observer.statsByMinute.append((t + i * 60, observer.initStats(),))

        self.assertEqual(len(observer.statsByMinute), 10)
        observer.ensureSequentialStats()
        self.assertEqual(len(observer.statsByMinute), 65)
        observer.stop()

    def test_smallerStats(self):
        """
        Make sure "uid" and "user-agent" are not in the
        L{RotatingFileAccessLoggingObserver} stats data.
        """

        logpath = self.mktemp()
        observer = RotatingFileAccessLoggingObserver(logpath)
        observer.systemStats = SystemMonitor()
        observer.start()
        stats = observer.initStats()
        observer.stop()
        self.assertTrue("uid" not in stats)
        self.assertTrue("user-agent" not in stats)
