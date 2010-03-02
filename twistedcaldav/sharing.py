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
from twisted.internet.defer import succeed

__all__ = [
    "SharingMixin",
]

from twistedcaldav import customxml
from twext.web2.dav import davxml

"""
Sharing behavior
"""

class SharingMixin(object):
    
    def upgradeToShare(self, request):
        """ Upgrade this collection to a shared state """
        
        # Change resourcetype
        rtype = self.resourceType()
        rtype = davxml.ResourceType(*(rtype.children + (customxml.SharedOwner(),)))
        self.writeDeadProperty(rtype)
        
        # Create empty invite property
        self.writeDeadProperty(customxml.Invite())

        return succeed(True)
    
    def downgradeFromShare(self, request):
        
        # Change resource type
        rtype = self.resourceType()
        rtype = davxml.ResourceType(*([child for child in rtype.children if child != customxml.SharedOwner()]))
        self.writeDeadProperty(rtype)
        
        # Remove all invitees

        # Remove invite property
        self.removeDeadProperty(customxml.Invite)
    
        return succeed(True)

    def addUserToShare(self, userid, request, ace):
        """ Add a user to this shared calendar """
        return succeed(True)

    def removeUserFromShare(self, userid, request):
        """ Remove a user from this shared calendar """
        return succeed(True)

    def isShared(self, request):
        """ Return True if this is an owner shared calendar collection """
        return succeed(self.isSpecialCollection(customxml.SharedOwner))

    def isVirtualShare(self, request):
        """ Return True if this is a shared calendar collection """
        return succeed(self.isSpecialCollection(customxml.Shared))

    def removeVirtualShare(self, request):
        """ As user of a shared calendar, unlink this calendar collection """
        return succeed(False) 

    def getInviteUsers(self, request):
        return succeed(True)

    def sendNotificationOnChange(self, icalendarComponent, request, state="added"):
        """ Possibly send a push and or email notification on a change to a resource in a shared collection """
        return succeed(True)
