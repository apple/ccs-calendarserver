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
CalDAV DELETE method.
"""

__version__ = "0.0"

__all__ = ["http_DELETE"]

from twisted.internet.defer import maybeDeferred
from twisted.web2 import responsecode
from twisted.web2.iweb import IResponse

from twistedcaldav.resource import isPseudoCalendarCollectionResource

def http_DELETE(self, request):
    # Override base DELETE request handling to ensure that the calendar
    # index file has the entry for the deleted calendar component removed.

    # Do inherited default behaviour
    d = maybeDeferred(super(CalDAVFile, self).http_DELETE, request)
    
    def deleteFromIndex(response):
        response = IResponse(response)

        if response.code == responsecode.NO_CONTENT:
            # Remove index entry if we are a child of a calendar collection
            parent = self.locateParent(request, request.uri)
            if isPseudoCalendarCollectionResource(parent):
                index = parent.index()
                index.deleteResource(self.fp.basename())

        return response
        
    return d.addCallback(deleteFromIndex)
