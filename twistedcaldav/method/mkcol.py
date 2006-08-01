##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
CalDAV MKCOL method.
"""

__version__ = "0.0"

__all__ = ["http_MKCOL"]

from twisted.web2 import responsecode
from twisted.web2.http import StatusResponse

from twistedcaldav.resource import isPseudoCalendarCollectionResource

def http_MKCOL(self, request):
    #
    # Don't allow DAV collections in a calendar collection for now
    #
    parent = self._checkParents(request, isPseudoCalendarCollectionResource)
    if parent is not None:
        return StatusResponse(
            responsecode.FORBIDDEN,
            "Cannot create collection within special collection %s" % (parent,)
        )

    return super(CalDAVFile, self).http_MKCOL(request)
