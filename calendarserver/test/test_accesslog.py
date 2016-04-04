##
# Copyright (c) 2015-2016 Apple Inc. All rights reserved.
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

        # Disabled
        self.patch(config.Stats, "EnableUnixStatsSocket", False)
        self.patch(config.Stats, "EnableTCPStatsSocket", False)

        logger = RotatingFileAccessLoggingObserver("")
        self.assertTrue(logger.systemStats is None)

        logger.logStats({})
        self.assertTrue(logger.systemStats is None)

        logger.getStats()
        self.assertTrue(logger.systemStats is None)

        # Enabled
        self.patch(config.Stats, "EnableUnixStatsSocket", True)
        self.patch(config.Stats, "EnableTCPStatsSocket", False)

        logger = RotatingFileAccessLoggingObserver("")
        self.assertTrue(logger.systemStats is None)

        logger.logStats({})
        self.assertTrue(logger.systemStats is not None)
        logger.systemStats.stop()

        # Enabled
        self.patch(config.Stats, "EnableUnixStatsSocket", False)
        self.patch(config.Stats, "EnableTCPStatsSocket", True)

        logger = RotatingFileAccessLoggingObserver("")
        self.assertTrue(logger.systemStats is None)

        logger.logStats({})
        self.assertTrue(logger.systemStats is not None)
        logger.systemStats.stop()


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
