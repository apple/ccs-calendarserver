##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
CalDAV ACL method.
"""

__all__ = ["http_ACL"]


from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav.util import parentForURL
from twext.web2.http import HTTPError

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav.resource import isAddressBookCollectionResource,\
    isPseudoCalendarCollectionResource,\
    CalendarHomeResource, AddressBookHomeResource, CalDAVResource

log = Logger()

@inlineCallbacks
def http_ACL(self, request):
    #
    # Override base ACL request handling to ensure that the calendar/address book
    # homes cannot have ACL's set, and calendar/address object resources too.
    #

    if self.exists():
        if isinstance(self, CalendarHomeResource) or isinstance(self, AddressBookHomeResource):
            raise HTTPError(responsecode.NOT_ALLOWED)

        parentURL = parentForURL(request.uri)
        parent = (yield request.locateResource(parentURL))
        if isPseudoCalendarCollectionResource(parent) or isAddressBookCollectionResource(parent):
            raise HTTPError(responsecode.NOT_ALLOWED)

    # Do normal ACL behavior
    response = (yield super(CalDAVResource, self).http_ACL(request))
    returnValue(response)
