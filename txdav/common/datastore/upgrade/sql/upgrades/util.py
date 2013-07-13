##
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
##

from twext.enterprise.dal.syntax import Select, Delete, Update
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.base.propertystore.base import PropertyName
from txdav.base.propertystore.sql import PropertyStore
from txdav.common.datastore.sql_tables import schema
from twisted.python.failure import Failure

log = Logger()

@inlineCallbacks
def rowsForProperty(txn, propelement, with_uid=False, batch=None):
    pname = PropertyName.fromElement(propelement)

    rp = schema.RESOURCE_PROPERTY
    columns = [rp.RESOURCE_ID, rp.VALUE, ]
    if with_uid:
        columns.append(rp.VIEWER_UID)
    rows = yield Select(
        columns,
        From=rp,
        Where=rp.NAME == pname.toString(),
        Limit=batch,
    ).on(txn)

    returnValue(rows)



@inlineCallbacks
def cleanPropertyStore():
    """
    We have manually manipulated the SQL property store by-passing the underlying implementation's caching
    mechanism. We need to clear out the cache.
    """
    yield PropertyStore._cacher.flushAll()



@inlineCallbacks
def removeProperty(txn, propelement):
    pname = PropertyName.fromElement(propelement)

    rp = schema.RESOURCE_PROPERTY
    yield Delete(
        From=rp,
        Where=rp.NAME == pname.toString(),
    ).on(txn)



@inlineCallbacks
def updateAllCalendarHomeDataVersions(store, version):

    txn = store.newTransaction("updateAllCalendarHomeDataVersions")
    ch = schema.CALENDAR_HOME
    yield Update(
        {ch.DATAVERSION: version},
        Where=None,
    ).on(txn)
    yield txn.commit()



@inlineCallbacks
def updateAllAddressBookHomeDataVersions(store, version):

    txn = store.newTransaction("updateAllAddressBookHomeDataVersions")
    ah = schema.ADDRESSBOOK_HOME
    yield Update(
        {ah.DATAVERSION: version},
    ).on(txn)
    yield txn.commit()



@inlineCallbacks
def _updateDataVersion(store, key, version):

    txn = store.newTransaction("updateDataVersion")
    cs = schema.CALENDARSERVER
    yield Update(
        {cs.VALUE: version},
        Where=cs.NAME == key,
    ).on(txn)
    yield txn.commit()



def updateCalendarDataVersion(store, version):
    return _updateDataVersion(store, "CALENDAR-DATAVERSION", version)



def updateAddressBookDataVersion(store, version):
    return _updateDataVersion(store, "ADDRESSBOOK-DATAVERSION", version)



@inlineCallbacks
def doToEachHomeNotAtVersion(store, homeSchema, version, doIt):
    """
    Do something to each home whose version column indicates it is older
    than the specified version. Do this in batches as there may be a lot of work to do.
    """

    while True:

        # Get the next home with an old version
        txn = store.newTransaction("updateDataVersion")
        try:
            rows = yield Select(
                [homeSchema.RESOURCE_ID, homeSchema.OWNER_UID, ],
                From=homeSchema,
                Where=homeSchema.DATAVERSION < version,
                OrderBy=homeSchema.OWNER_UID,
                Limit=1,
            ).on(txn)

            if len(rows) == 0:
                yield txn.commit()
                returnValue(None)

            # Apply to the home
            homeResourceID, _ignore_owner_uid = rows[0]
            yield doIt(txn, homeResourceID)

            # Update the home to the current version
            yield Update(
                {homeSchema.DATAVERSION: version},
                Where=homeSchema.RESOURCE_ID == homeResourceID,
            ).on(txn)
            yield txn.commit()
        except RuntimeError, e:
            f = Failure()
            log.error("Failed to upgrade %s to %s: %s" % (homeSchema, version, e))
            yield txn.abort()
            f.raiseException()
