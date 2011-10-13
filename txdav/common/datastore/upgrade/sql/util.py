##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.syntax import Select, Delete
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
