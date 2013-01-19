##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks
from txdav.caldav.datastore.sql import CalendarStoreFeatures

"""
Upgrader that checks for any dropbox attachments, and upgrades them all to managed attachments.
"""

@inlineCallbacks
def doUpgrade(upgrader):
    """
    Do the required upgrade steps.
    """

    storeWrapper = CalendarStoreFeatures(upgrader.sqlStore)
    txn = upgrader.sqlStore.newTransaction("attachment_migration.doUpgrade")
    try:
        needUpgrade = (yield storeWrapper.hasDropboxAttachments(txn))
        if needUpgrade:
            upgrader.log_warn("Starting dropbox migration")
            yield storeWrapper.upgradeToManagedAttachments(batchSize=10)
            upgrader.log_warn("Finished dropbox migration")
        else:
            upgrader.log_warn("No dropbox migration needed")
    except RuntimeError:
        yield txn.abort()
        raise
    else:
        yield txn.commit()
