##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

try:
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService
except ImportError:
    pass
else:
    import twistedcaldav.directory.test.util

    # Wonky hack to prevent unclean reactor shutdowns
    class DummyReactor(object):
        @staticmethod
        def callLater(*args):
            pass
    import twistedcaldav.directory.appleopendirectory
    twistedcaldav.directory.appleopendirectory.reactor = DummyReactor

    class OpenDirectory (
        twistedcaldav.directory.test.util.BasicTestCase,
        twistedcaldav.directory.test.util.DigestTestCase
    ):
        """
        Test Open Directory directory implementation.
        """
        recordTypes = set(("user", "group", "resource"))

        def service(self):
            return OpenDirectoryService(node="/Local")
