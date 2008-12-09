##
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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

from twistedcaldav.accounting import emitAccounting
from twistedcaldav.config import config
import twistedcaldav.test.util

import os
import stat

class Accounting (twistedcaldav.test.util.TestCase):

    def setUp(self):
        
        super(Accounting, self).setUp()
        config.AccountingCategories.iTIP = True
        config.AccountingPrincipals = ["*",]
        config.AccountingLogRoot = self.mkdtemp("accounting")[0]

    class _Principal(object):
        
        class _Record(object):
            
            def __init__(self, guid):
                self.guid = guid
                
        def __init__(self, guid):
            
            self.record = self._Record(guid)

    def test_permissions_makedirs(self):
        """
        Test permissions when creating accounting
        """
        
        # Make log root non-writeable
        os.chmod(config.AccountingLogRoot, stat.S_IRUSR)
        
        emitAccounting("iTIP", self._Principal("1234-5678"), "bogus")

    def test_file_instead_of_directory(self):
        """
        Test permissions when creating accounting
        """
        
        # Make log root a file
        config.AccountingLogRoot = self.mktemp()
        open(config.AccountingLogRoot, "w").close()
        
        emitAccounting("iTIP", self._Principal("1234-5678"), "bogus")
