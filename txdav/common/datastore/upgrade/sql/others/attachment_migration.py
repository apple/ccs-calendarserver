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

from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.caldav.datastore.sql import CalendarStoreFeatures

"""
Upgrader that checks for any dropbox attachments, and upgrades them all to managed attachments.

This makes use of a MANAGED-ATTACHMENTS flag in the CALENDARSERVER table to determine whether the upgrade has been
done for this store. If it has been done, the store will advertise that to the app layer and that must prevent the
use of dropbox in the future.
"""

@inlineCallbacks
def doUpgrade(upgrader):
    """
    Do the required upgrade steps. Also, make sure we correctly set the store for having attachments enabled.
    """

    # Ignore if the store is not enabled for managed attachments
    if not upgrader.sqlStore.enableManagedAttachments:
        upgrader.log.warn("No dropbox migration - managed attachments not enabled")
        returnValue(None)

    statusKey = "MANAGED-ATTACHMENTS"
    storeWrapper = CalendarStoreFeatures(upgrader.sqlStore)
    txn = upgrader.sqlStore.newTransaction("attachment_migration.doUpgrade")
    try:
        managed = (yield txn.calendarserverValue(statusKey, raiseIfMissing=False))
        if managed is None:
            upgrader.log.warn("Checking for dropbox migration")
            needUpgrade = (yield storeWrapper.hasDropboxAttachments(txn))
        else:
            needUpgrade = False
        if needUpgrade:
            upgrader.log.warn("Starting dropbox migration")
            yield storeWrapper.upgradeToManagedAttachments(batchSize=10)
            upgrader.log.warn("Finished dropbox migration")
        else:
            upgrader.log.warn("No dropbox migration needed")
        if managed is None:
            yield txn.setCalendarserverValue(statusKey, "1")
    except RuntimeError:
        yield txn.abort()
        raise
    else:
        yield txn.commit()
