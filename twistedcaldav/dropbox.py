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
Implements drop-box functionality. A drop box is an external attachment store that provides
for automatic notification of changes to subscribed users.
"""

__all__ = [
    "DropBox",
]

from twistedcaldav.customxml import davxml, apple_namespace

import os

class DropBox(object):
    
    # These are all options that will be set from a .plist configuration file.

    enabled = True                     # Whether or not drop box functionaility is enabled.
    dropboxName = "dropbox"            # Name of the collection in which drop boxes can be created.
    inheritedACLs = True               # Whether or not ACLs set on a drop box collection are automatically
                                       # inherited by child resources.
    notifications = True               # Whether to post notification messages into per-user notification collection.
    notificationName = "notifications" # Name of the collection in which notifications will be stored.
    
    @classmethod
    def enable(clzz, enabled, inheritedACLs=None, notifications=None):
        """
        This method must be used to enable drop box support as it will setup live properties etc,
        and turn on the notification system. It must only be called once

        @param enable: C{True} if drop box feature is enabled, C{False} otherwise
        @param dropboxName: C{str} containing the name of the drop box home collection
        @param inheritedACLs: C{True} if ACLs on drop boxes should be inherited by their contents, C{False} otehrwise.
        @param notifications: C{True} if automatic notifications are to be sent when a drop box changes, C{False} otherwise.
        @param notificationName: C{str} containing the name of the collection used to store per-user notifications.
        """
        DropBox.enabled = enabled
        if inheritedACLs:
            DropBox.inheritedACLs = inheritedACLs
        if notifications:
            DropBox.notifications = notifications

        if DropBox.enabled:

            # Need to setup live properties
            from twistedcaldav.resource import CalendarPrincipalResource
            assert (apple_namespace, "dropbox-home-URL") not in CalendarPrincipalResource.liveProperties, \
                "DropBox.enable must only be called once"

            CalendarPrincipalResource.liveProperties += (
                (apple_namespace, "dropbox-home-URL"  ),
                (apple_namespace, "notifications-URL" ),
            )

    @classmethod
    def provision(clzz, cuhome):
        """
        Provision user account with appropriate collections for drop box
        and notifications.
        
        @param principal: the L{CalendarPrincipalResource} for the principal to provision
        @param cuhome: L{DAVResource} - resource of user calendar home
        """
        
        # Only if enabled
        if not DropBox.enabled:
            return
        
        # Create drop box collection in calendar-home collection resource if not already present.
        
        from twistedcaldav.static import CalDAVFile
        child = CalDAVFile(os.path.join(cuhome.fp.path, DropBox.dropboxName))
        child_exists = child.exists()
        if not child_exists:
            c = child.createSpecialCollection(davxml.ResourceType.dropboxhome)
            assert c.called
            c = c.result
        
        if not DropBox.notifications:
            return
        
        child = CalDAVFile(os.path.join(cuhome.fp.path, DropBox.notificationName))
        child_exists = child.exists()
        if not child_exists:
            c = child.createSpecialCollection(davxml.ResourceType.notifications)
            assert c.called
            c = c.result
        