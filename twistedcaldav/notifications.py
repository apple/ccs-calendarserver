##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
Implements collection change notification functionality. Any change to the contents of a collection will
result in a notification resource deposited into subscriber's notifications collection.
"""

__all__ = [
    "NotificationCollectionResource",
    "NotificationResource",
]

from twisted.web2 import responsecode
from twisted.web2.dav import davxml
from twisted.web2.dav.http import ErrorResponse

from twistedcaldav.customxml import calendarserver_namespace
from twistedcaldav.extensions import DAVResource

class NotificationsCollectionResource (DAVResource):
    def resourceType(self):
        return davxml.ResourceType.notifications

    def isCollection(self):
        return True

    def notify(self):
        # FIXME: Move doNotification() logic from above class to here
        pass

    def http_PUT(self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "notifications-collection-no-client-resources")
        )

    def http_MKCOL (self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "notifications-collection-no-client-resources")
        )

    def http_MKCALENDAR (self, request):
        return ErrorResponse(
            responsecode.FORBIDDEN,
            (calendarserver_namespace, "notifications-collection-no-client-resources")
        )

class NotificationResource(DAVResource):
    """
    Resource that gets stored in a notification collection and which contains
    the notification details in its content as well as via properties.
    """
    liveProperties = DAVResource.liveProperties + (
        (calendarserver_namespace, "time-stamp"),
        (calendarserver_namespace, "changed"   ),
    )
