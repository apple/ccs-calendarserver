##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
CalDAV DELETE method.
"""

__all__ = ["http_DELETE"]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.web2 import responsecode
from twisted.web2.dav.util import parentForURL

from twistedcaldav import customxml
from twistedcaldav.dropbox import DropBox
from twistedcaldav.notifications import Notification
from twistedcaldav.resource import isPseudoCalendarCollectionResource

def http_DELETE(self, request):
    #
    # Override base DELETE request handling to ensure that the calendar
    # index file has the entry for the deleted calendar component removed.
    #
    # Also handle notifications in a drop box collection.
    #

    parentURL = parentForURL(request.uri)
    parent = waitForDeferred(request.locateResource(parentURL))
    yield parent
    parent = parent.getResult()

    d = waitForDeferred(super(CalDAVFile, self).http_DELETE(request))
    yield d
    response = d.getResult()

    if response == responsecode.NO_CONTENT:

        if isPseudoCalendarCollectionResource(parent):
            index = parent.index()
            index.deleteResource(self.fp.basename())

        elif DropBox.enabled and parent.isSpecialCollection(customxml.DropBox):
            # We need to handle notificiations
            notification = Notification(parentURL=parentURL)
            d = waitForDeferred(notification.doNotification(request, parent))
            yield d
            d.getResult()

    yield response

http_DELETE = deferredGenerator(http_DELETE)
