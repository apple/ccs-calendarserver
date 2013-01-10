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
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.base.propertystore.base import PropertyName
from txdav.common.datastore.sql_tables import schema

@inlineCallbacks
def rowsForProperty(txn, propelement):
    pname = PropertyName.fromElement(propelement)

    rp = schema.RESOURCE_PROPERTY
    rows = yield Select(
        [rp.RESOURCE_ID, rp.VALUE,],
        From=rp,
        Where=rp.NAME == pname.toString(),
    ).on(txn)
    
    returnValue(rows)

@inlineCallbacks
def removeProperty(txn, propelement):
    pname = PropertyName.fromElement(propelement)

    rp = schema.RESOURCE_PROPERTY
    yield Delete(
        From=rp,
        Where=rp.NAME == pname.toString(),
    ).on(txn)

@inlineCallbacks
def updateDataVersion(store, key, version):

    txn = store.newTransaction("updateDataVersion")    
    cs = schema.CALENDARSERVER
    yield Update(
        {cs.VALUE: version},
        Where=cs.NAME == key,
    ).on(txn)
    yield txn.commit()

def updateCalendarDataVersion(store, version):
    return updateDataVersion(store, "CALENDAR-DATAVERSION", version)

def updateAddressBookDataVersion(store, version):
    return updateDataVersion(store, "ADDRESSBOOK-DATAVERSION", version)

@inlineCallbacks
def doToEachCalendarHomeNotAtVersion(store, version, doIt):
    """
    Do something to each calendar home whose version column indicates it is older
    than the specified version. Do this in batches as there may be a lot of work to do.
    """

    while True:
        
        # Get the next home with an old version
        txn = store.newTransaction("updateDataVersion")   
        try: 
            ch = schema.CALENDAR_HOME
            rows = yield Select(
                [ch.RESOURCE_ID, ch.OWNER_UID,],
                From=ch,
                Where=ch.DATAVERSION < version,
                OrderBy=ch.OWNER_UID,
                Limit=1,
            ).on(txn)
            
            if len(rows) == 0:
                yield txn.commit()
                returnValue(None)
            
            # Apply to the home
            resource_id, _ignore_owner_uid = rows[0]
            home = yield txn.calendarHomeWithResourceID(resource_id)
            yield doIt(home)
    
            # Update the home to the current version
            yield Update(
                {ch.DATAVERSION: version},
                Where=ch.RESOURCE_ID == resource_id,
            ).on(txn)
            yield txn.commit()
        except RuntimeError:
            yield txn.abort()
