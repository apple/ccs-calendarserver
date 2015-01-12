# -*- test-case-name: txdav.common.datastore.upgrade.sql.test -*-
# #
# Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Update

from twisted.internet.defer import inlineCallbacks

from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import _ABO_KIND_GROUP, schema
from txdav.common.datastore.upgrade.sql.upgrades.util import updateAddressBookDataVersion, \
    doToEachHomeNotAtVersion, removeProperty, cleanPropertyStore, \
    logUpgradeStatus
from txdav.xml import element

"""
AddressBook Data upgrade from database version 1 to 2
"""

UPGRADE_TO_VERSION = 2

@inlineCallbacks
def doUpgrade(sqlStore):
    """
    fill in members tables and increment data version
    """
    yield populateMemberTables(sqlStore)
    yield removeResourceType(sqlStore)

    # bump data version
    yield updateAddressBookDataVersion(sqlStore, UPGRADE_TO_VERSION)



@inlineCallbacks
def populateMemberTables(sqlStore):
    """
    Set the group kind and and members tables
    """
    @inlineCallbacks
    def doIt(txn, homeResourceID):
        """
        KIND is set to person by schema upgrade.
        To upgrade MEMBERS and FOREIGN_MEMBERS:
            1. Set group KIND (avoids assert)
            2. Write groups.  Write logic will fill in MEMBERS and FOREIGN_MEMBERS
                (Remember that all members resource IDs must already be in the address book).
        """
        home = yield txn.addressbookHomeWithResourceID(homeResourceID)
        abObjectResources = yield home.addressbook().objectResources()
        for abObject in abObjectResources:
            component = yield abObject.component()
            lcResourceKind = component.resourceKind().lower() if component.resourceKind() else component.resourceKind()
            if lcResourceKind == "group":
                # update kind
                abo = schema.ADDRESSBOOK_OBJECT
                yield Update(
                    {abo.KIND: _ABO_KIND_GROUP},
                    Where=abo.RESOURCE_ID == abObject._resourceID,
                ).on(txn)
                abObject._kind = _ABO_KIND_GROUP
                # update rest
                yield abObject.setComponent(component)

    logUpgradeStatus("Starting Addressbook Populate Members")

    # Do this to each calendar home not already at version 2
    yield doToEachHomeNotAtVersion(sqlStore, schema.ADDRESSBOOK_HOME, UPGRADE_TO_VERSION, doIt, "Populate Members")



@inlineCallbacks
def removeResourceType(sqlStore):
    logUpgradeStatus("Starting Addressbook Remove Resource Type")

    sqlTxn = sqlStore.newTransaction(label="addressbook_upgrade_from_1_to_2.removeResourceType")
    yield removeProperty(sqlTxn, PropertyName.fromElement(element.ResourceType))
    yield sqlTxn.commit()
    yield cleanPropertyStore()

    logUpgradeStatus("End Addressbook Remove Resource Type")
