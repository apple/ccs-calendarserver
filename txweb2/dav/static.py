# -*- test-case-name: txweb2.dav.test.test_static -*-
##
# Copyright (c) 2005-2014 Apple Computer, Inc. All rights reserved.
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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
WebDAV-aware static resources.
"""

__all__ = ["DAVFile"]

from twisted.python.filepath import InsecurePath
from twisted.internet.defer import succeed, deferredGenerator, waitForDeferred

from twext.python.log import Logger
from txweb2 import http_headers
from txweb2 import responsecode
from txweb2.dav.resource import DAVResource, davPrivilegeSet
from txweb2.dav.resource import TwistedGETContentMD5
from txweb2.dav.util import bindMethods
from txweb2.http import HTTPError, StatusResponse
from txweb2.static import File

log = Logger()


try:
    from txweb2.dav.xattrprops import xattrPropertyStore as DeadPropertyStore
except ImportError:
    log.info("No dead property store available; using nonePropertyStore.")
    log.info("Setting of dead properties will not be allowed.")
    from txweb2.dav.noneprops import NonePropertyStore as DeadPropertyStore

class DAVFile (DAVResource, File):
    """
    WebDAV-accessible File resource.

    Extends txweb2.static.File to handle WebDAV methods.
    """
    def __init__(
        self, path,
        defaultType="text/plain", indexNames=None,
        principalCollections=()
    ):
        """
        @param path: the path of the file backing this resource.
        @param defaultType: the default mime type (as a string) for this
            resource and (eg. child) resources derived from it.
        @param indexNames: a sequence of index file names.
        @param acl: an L{IDAVAccessControlList} with the .
        """
        File.__init__(
            self, path,
            defaultType = defaultType,
            ignoredExts = (),
            processors = None,
            indexNames = indexNames,
        )
        DAVResource.__init__(self, principalCollections=principalCollections)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.fp.path)

    ##
    # WebDAV
    ##

    def etag(self):
        if not self.fp.exists(): return succeed(None)
        if self.hasDeadProperty(TwistedGETContentMD5):
            return succeed(http_headers.ETag(str(self.readDeadProperty(TwistedGETContentMD5))))
        else:
            return super(DAVFile, self).etag()

    def davComplianceClasses(self):
        return ("1", "access-control") # Add "2" when we have locking

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = DeadPropertyStore(self)
        return self._dead_properties

    def isCollection(self):
        """
        See L{IDAVResource.isCollection}.
        """
        return self.fp.isdir()

    ##
    # ACL
    ##

    def supportedPrivileges(self, request):
        return succeed(davPrivilegeSet)

    ##
    # Quota
    ##

    def quotaSize(self, request):
        """
        Get the size of this resource.
        TODO: Take into account size of dead-properties. Does stat
            include xattrs size?

        @return: an L{Deferred} with a C{int} result containing the size of the resource.
        """
        if self.isCollection():
            def walktree(top):
                """
                Recursively descend the directory tree rooted at top,
                calling the callback function for each regular file
                
                @param top: L{FilePath} for the directory to walk.
                """
            
                total = 0
                for f in top.listdir():
                    child = top.child(f)
                    if child.isdir():
                        # It's a directory, recurse into it
                        result = waitForDeferred(walktree(child))
                        yield result
                        total += result.getResult()
                    elif child.isfile():
                        # It's a file, call the callback function
                        total += child.getsize()
                    else:
                        # Unknown file type, print a message
                        pass
            
                yield total
            
            walktree = deferredGenerator(walktree)
    
            return walktree(self.fp)
        else:
            return succeed(self.fp.getsize())

    ##
    # Workarounds for issues with File
    ##

    def ignoreExt(self, ext):
        """
        Does nothing; doesn't apply to this subclass.
        """
        pass

    def locateChild(self, req, segments):
        """
        See L{IResource}C{.locateChild}.
        """
        # If getChild() finds a child resource, return it
        try:
            child = self.getChild(segments[0])
            if child is not None:
                return (child, segments[1:])
        except InsecurePath:
            raise HTTPError(StatusResponse(responsecode.FORBIDDEN, "Invalid URL path"))
        
        # If we're not backed by a directory, we have no children.
        # But check for existance first; we might be a collection resource
        # that the request wants created.
        self.fp.restat(False)
        if self.fp.exists() and not self.fp.isdir():
            return (None, ())

        # OK, we need to return a child corresponding to the first segment
        path = segments[0]
        
        if path == "":
            # Request is for a directory (collection) resource
            return (self, ())

        return (self.createSimilarFile(self.fp.child(path).path), segments[1:])

    def createSimilarFile(self, path):
        return self.__class__(
            path, defaultType=self.defaultType, indexNames=self.indexNames[:],
            principalCollections=self.principalCollections())

#
# Attach method handlers to DAVFile
#

import txweb2.dav.method

bindMethods(txweb2.dav.method, DAVFile)
