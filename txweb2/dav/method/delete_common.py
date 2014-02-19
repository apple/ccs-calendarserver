# -*- test-case-name: txweb2.dav.test.test_delete -*-
##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
##

"""
WebDAV DELETE method
"""

__all__ = ["deleteResource"]

from twisted.internet.defer import waitForDeferred, deferredGenerator

from twext.python.log import Logger
from txweb2 import responsecode
from txweb2.http import HTTPError
from txweb2.dav.fileop import delete

log = Logger()


def deleteResource(request, resource, resource_uri, depth="0"):
    """
    Handle a resource delete with proper quota etc updates
    """
    if not resource.exists():
        log.error("File not found: %s" % (resource,))
        raise HTTPError(responsecode.NOT_FOUND)

    # Do quota checks before we start deleting things
    myquota = waitForDeferred(resource.quota(request))
    yield myquota
    myquota = myquota.getResult()
    if myquota is not None:
        old_size = waitForDeferred(resource.quotaSize(request))
        yield old_size
        old_size = old_size.getResult()
    else:
        old_size = 0

    # Do delete
    x = waitForDeferred(delete(resource_uri, resource.fp, depth))
    yield x
    result = x.getResult()

    # Adjust quota
    if myquota is not None:
        d = waitForDeferred(resource.quotaSizeAdjust(request, -old_size))
        yield d
        d.getResult()
    
    yield result

deleteResource = deferredGenerator(deleteResource)
