##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Implements notification functionality.
"""

__all__ = [
    "NotificationResource",
    "NotificationCollectionResource",
]

from twext.web2 import responsecode
from twext.web2.dav import davxml
from twext.web2.dav.resource import DAVResource

from twext.python.log import Logger

from twisted.internet.defer import succeed

log = Logger()

class NotificationResource(DAVResource):
    """
    An xml resource in a Notification collection.
    """
    def principalCollections(self):
        return self._parent.principalCollections()

    def isCollection(self):
        return False

    def http_PUT(self, request):
        return responsecode.FORBIDDEN

class NotificationCollectionResource(DAVResource):
    
    def isCollection(self):
        return True

    def resourceType(self):
        return davxml.ResourceType.notification

    def getNotifictionMessages(self, request, componentType=None, returnLatestVersion=True):
        return succeed([])

    def getNotifictionMessagesByUID(self, request, uid):
        return succeed([])

    def deleteSchedulingMessagesByUID(self, request, uid):
        return succeed(True)

