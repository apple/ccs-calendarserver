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
CalDAV POST method.
"""

__all__ = ["http_POST"]

from twisted.web2.dav.util import parentForURL

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
    d = request.locateResource(parentForURL(request.uri))
    # Check authentication and access controls
    d.addCallback(lambda parent: parent.authorize(request, (caldavxml.Schedule(),)))
    # Do the work
    d.addCallback(lambda _: processScheduleRequest(self, "POST", request))
    return d
