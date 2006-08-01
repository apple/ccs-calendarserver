##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
CalDAV POST method.
"""

__version__ = "0.0"

__all__ = ["http_POST"]

from twisted.internet.defer import deferredGenerator, maybeDeferred

from twistedcaldav import caldavxml
from twistedcaldav.method.schedule_common import processScheduleRequest

def http_POST(self, request):

    """
    The CalDAV POST method.
    
    This uses a generator function yielding either L{waitForDeferred} objects or L{Response} objects.
    This allows for code that follows a 'linear' execution pattern rather than having to use nested
    L{Deferred} callbacks. The logic is easier to follow this way plus we don't run into deep nesting
    issues which the other approach would have with large numbers of recipients.
    """

    #
    # Check authentication and access controls
    #
    parent = self.locateParent(request, request.uri)
    parent.securityCheck(request, (caldavxml.Schedule(),))
        
    # Initiate deferred generator
    return maybeDeferred(deferredGenerator(processScheduleRequest), self, "POST", request)
