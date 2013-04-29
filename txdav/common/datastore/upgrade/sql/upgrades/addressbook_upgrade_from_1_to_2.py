# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
# #
# Copyright (c) 2011-2013 Apple Inc. All rights reserved.
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
# #

from twisted.internet.defer import inlineCallbacks
from txdav.common.datastore.upgrade.sql.upgrades.util import updateAddressBookDataVersion

"""
AddressBook Data upgrade from database version 1 to 2
"""

UPGRADE_TO_VERSION = 2

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    Do the required upgrade steps.
    """

    # bump data version
    yield updateAddressBookDataVersion(sqlStore, UPGRADE_TO_VERSION)
