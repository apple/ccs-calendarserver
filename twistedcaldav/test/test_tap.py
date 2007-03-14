##
# Copyright (c) 2007 Apple Inc. All rights reserved.
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
#
# DRI: David Reid, dreid@apple.com
##

import os
from copy import deepcopy

from twisted.trial import unittest

from twisted.python.usage import Options, UsageError
from twisted.python.util import sibpath
from twisted.python.reflect import namedAny
from twisted.application.service import IService
from twisted.application import internet

from twisted.web2.dav import auth
from twisted.web2.log import LogWrapperResource

from twistedcaldav.tap import CalDAVOptions, CalDAVServiceMaker
from twistedcaldav import tap

from twistedcaldav.config import config
from twistedcaldav import config as config_mod
from twistedcaldav.py.plistlib import writePlist

from twistedcaldav.directory.aggregate import AggregateDirectoryService
from twistedcaldav.directory.sudo import SudoDirectoryService
from twistedcaldav.directory.directory import UnknownRecordTypeError


class TestCalDAVOptions(CalDAVOptions):
    """
    A fake implementation of CalDAVOptions that provides
    empty implementations of checkDirectory and checkFile.
    """

    def checkDirectory(*args, **kwargs):
        pass

    def checkFile(*args, **kwargs):
        pass


class CalDAVOptionsTest(unittest.TestCase):
    """
    Test various parameters of our usage.Options subclass
    """

    def setUp(self):
        """
        Set up our options object, giving it a parent, and forcing the
        global config to be loaded from defaults.
        """

        self.config = TestCalDAVOptions()
        self.config.parent = Options()
        self.config.parent['uid'] = 0
        self.config.parent['gid'] = 0
        self.config.parent['nodaemon'] = False

        config_mod.parseConfig('non-existant-config')

    def test_overridesConfig(self):
        """
        Test that values on the command line's -o and --option options
        overide the config file
        """

        argv = ['-o', 'EnableSACLs',
                '-o', 'HTTPPort=80',
                '-o', 'BindAddresses=127.0.0.1,127.0.0.2,127.0.0.3',
                '-o', 'DocumentRoot=/dev/null',
                '-o', 'UserName=None',
                '-o', 'EnableProxyPrincipals=False']

        self.config.parseOptions(argv)

        self.assertEquals(config.EnableSACLs, True)
        self.assertEquals(config.HTTPPort, 80)
        self.assertEquals(config.BindAddresses, ['127.0.0.1',
                                               '127.0.0.2',
                                               '127.0.0.3'])
        self.assertEquals(config.DocumentRoot, '/dev/null')
        self.assertEquals(config.UserName, None)
        self.assertEquals(config.EnableProxyPrincipals, False)

        argv = ['-o', 'Authentication=This Doesn\'t Matter']

        self.assertRaises(UsageError, self.config.parseOptions, argv)

    def test_setsParent(self):
        """
        Test that certain values are set on the parent (i.e. twistd's
        Option's object)
        """

        argv = ['-o', 'ErrorLogFile=/dev/null',
                '-o', 'PIDFile=/dev/null']

        self.config.parseOptions(argv)

        self.assertEquals(self.config.parent['logfile'], '/dev/null')

        self.assertEquals(self.config.parent['pidfile'], '/dev/null')

    def test_specifyConfigFile(self):
        """
        Test that specifying a config file from the command line
        loads the global config with those values properly.
        """

        myConfig = deepcopy(config_mod.defaultConfig)

        myConfig['Authentication']['Basic']['Enabled'] = False

        myConfig['MultiProcess']['LoadBalancer']['Enabled'] = False

        myConfig['HTTPPort'] = 80

        myConfig['ServerHostName'] = 'calendar.calenderserver.org'

        myConfigFile = self.mktemp()
        writePlist(myConfig, myConfigFile)

        args = ['-f', myConfigFile]

        self.config.parseOptions(args)

        self.assertEquals(config.ServerHostName, myConfig['ServerHostName'])

        self.assertEquals(config.MultiProcess['LoadBalancer']['Enabled'],
                          myConfig['MultiProcess']['LoadBalancer']['Enabled'])

        self.assertEquals(config.HTTPPort, myConfig['HTTPPort'])

        self.assertEquals(config.Authentication['Basic']['Enabled'],
                          myConfig['Authentication']['Basic']['Enabled'])
