# -*- test-case-name: txdav.caldav.datastore.test.test_sql -*-
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
"""
SQL backend for CardDAV storage when resources are external.
"""

from twisted.internet.defer import succeed

from twext.python.log import Logger

from txdav.carddav.datastore.sql import AddressBookHome, AddressBook, \
    AddressBookObject
from txdav.common.datastore.sql_external import CommonHomeExternal, CommonHomeChildExternal, \
    CommonObjectResourceExternal

log = Logger()

class AddressBookHomeExternal(CommonHomeExternal, AddressBookHome):

    def __init__(self, transaction, ownerUID, resourceID):

        AddressBookHome.__init__(self, transaction, ownerUID)
        CommonHomeExternal.__init__(self, transaction, ownerUID, resourceID)


    def hasAddressBookResourceUIDSomewhereElse(self, uid, ok_object, mode):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def getAddressBookResourcesForUID(self, uid):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")


    def createdHome(self):
        """
        No children - make this a no-op.
        """
        return succeed(None)


    def addressbook(self):
        """
        No children.
        """
        raise AssertionError("CommonHomeExternal: not supported")



class AddressBookExternal(CommonHomeChildExternal, AddressBook):
    """
    SQL-based implementation of L{IAddressBook}.
    """
    pass



class AddressBookObjectExternal(CommonObjectResourceExternal, AddressBookObject):
    """
    SQL-based implementation of L{ICalendar}.
    """
    pass
