##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
PUT/COPY/MOVE common behavior.
"""

__version__ = "0.0"

__all__ = ["storeResource"]

from twisted.python.failure import Failure
from twext.python.filepath import CachingFilePath as FilePath
from twisted.internet.defer import deferredGenerator, maybeDeferred, waitForDeferred

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav.fileop import copy, delete, put
from twext.web2.dav.http import ErrorResponse
from twext.web2.dav.resource import TwistedGETContentMD5
from twext.web2.stream import MD5Stream
from twext.web2.http import HTTPError
from twext.web2.http_headers import generateContentType
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream

from txdav.xml import element as davxml
from txdav.xml.base import dav_namespace

log = Logger()



def storeResource(
    request,
    source=None, source_uri=None, data=None,
    destination=None, destination_uri=None,
    deletesource=False,
    depth="0"
):
    """
    Function that does common PUT/COPY/MOVE behaviour.
    
    @param request:           the L{twext.web2.server.Request} for the current HTTP request.
    @param source:            the L{DAVFile} for the source resource to copy from, or None if source data
                              is to be read from the request.
    @param source_uri:        the URI for the source resource.
    @param data:              a C{str} to copy data from instead of the request stream.
    @param destination:       the L{DAVFile} for the destination resource to copy into.
    @param destination_uri:   the URI for the destination resource.
    @param deletesource:      True if the source resource is to be deleted on successful completion, False otherwise.
    @param depth:             a C{str} containing the COPY/MOVE Depth header value.
    @return:                  status response.
    """
    
    try:
        assert request is not None and destination is not None and destination_uri is not None
        assert (source is None) or (source is not None and source_uri is not None)
        assert not deletesource or (deletesource and source is not None)
    except AssertionError:
        log.error("Invalid arguments to storeResource():")
        log.error("request=%s\n" % (request,))
        log.error("source=%s\n" % (source,))
        log.error("source_uri=%s\n" % (source_uri,))
        log.error("data=%s\n" % (data,))
        log.error("destination=%s\n" % (destination,))
        log.error("destination_uri=%s\n" % (destination_uri,))
        log.error("deletesource=%s\n" % (deletesource,))
        log.error("depth=%s\n" % (depth,))
        raise

    class RollbackState(object):
        """
        This class encapsulates the state needed to rollback the entire PUT/COPY/MOVE
        transaction, leaving the server state the same as it was before the request was
        processed. The DoRollback method will actually execute the rollback operations.
        """
        
        def __init__(self):
            self.active = True
            self.source_copy = None
            self.destination_copy = None
            self.destination_created = False
            self.source_deleted = False
        
        def Rollback(self):
            """
            Rollback the server state. Do not allow this to raise another exception. If
            rollback fails then we are going to be left in an awkward state that will need
            to be cleaned up eventually.
            """
            if self.active:
                self.active = False
                log.error("Rollback: rollback")
                try:
                    if self.source_copy and self.source_deleted:
                        self.source_copy.moveTo(source.fp)
                        log.error("Rollback: source restored %s to %s" % (self.source_copy.path, source.fp.path))
                        self.source_copy = None
                        self.source_deleted = False
                    if self.destination_copy:
                        destination.fp.remove()
                        log.error("Rollback: destination restored %s to %s" % (self.destination_copy.path, destination.fp.path))
                        self.destination_copy.moveTo(destination.fp)
                        self.destination_copy = None
                    elif self.destination_created:
                        destination.fp.remove()
                        log.error("Rollback: destination removed %s" % (destination.fp.path,))
                        self.destination_created = False
                except:
                    log.error("Rollback: exception caught and not handled: %s" % Failure())

        def Commit(self):
            """
            Commit the resource changes by wiping the rollback state.
            """
            if self.active:
                log.error("Rollback: commit")
                self.active = False
                if self.source_copy:
                    self.source_copy.remove()
                    log.error("Rollback: removed source backup %s" % (self.source_copy.path,))
                    self.source_copy = None
                if self.destination_copy:
                    self.destination_copy.remove()
                    log.error("Rollback: removed destination backup %s" % (self.destination_copy.path,))
                    self.destination_copy = None
                self.destination_created = False
                self.source_deleted = False
    
    rollback = RollbackState()

    try:
        """
        Handle validation operations here.
        """

        """
        Handle rollback setup here.
        """

        # Do quota checks on destination and source before we start messing with adding other files
        destquota = waitForDeferred(destination.quota(request))
        yield destquota
        destquota = destquota.getResult()
        if destquota is not None and destination.exists():
            old_dest_size = waitForDeferred(destination.quotaSize(request))
            yield old_dest_size
            old_dest_size = old_dest_size.getResult()
        else:
            old_dest_size = 0
            
        if source is not None:
            sourcequota = waitForDeferred(source.quota(request))
            yield sourcequota
            sourcequota = sourcequota.getResult()
            if sourcequota is not None and source.exists():
                old_source_size = waitForDeferred(source.quotaSize(request))
                yield old_source_size
                old_source_size = old_source_size.getResult()
            else:
                old_source_size = 0
        else:
            sourcequota = None
            old_source_size = 0

        # We may need to restore the original resource data if the PUT/COPY/MOVE fails,
        # so rename the original file in case we need to rollback.
        overwrite = destination.exists()
        if overwrite:
            rollback.destination_copy = FilePath(destination.fp.path)
            rollback.destination_copy.path += ".rollback"
            destination.fp.copyTo(rollback.destination_copy)
        else:
            rollback.destination_created = True

        if deletesource:
            rollback.source_copy = FilePath(source.fp.path)
            rollback.source_copy.path += ".rollback"
            source.fp.copyTo(rollback.source_copy)
    
        """
        Handle actual store operations here.
        """

        # Do put or copy based on whether source exists
        if source is not None:
            response = maybeDeferred(copy, source.fp, destination.fp, destination_uri, depth)
        else:
            datastream = request.stream
            if data is not None:
                datastream = MemoryStream(data)
            md5 = MD5Stream(datastream)
            response = maybeDeferred(put, md5, destination.fp)

        response = waitForDeferred(response)
        yield response
        response = response.getResult()

        # Update the MD5 value on the resource
        if source is not None:
            # Copy MD5 value from source to destination
            if source.hasDeadProperty(TwistedGETContentMD5):
                md5 = source.readDeadProperty(TwistedGETContentMD5)
                destination.writeDeadProperty(md5)
        else:
            # Finish MD5 calc and write dead property
            md5.close()
            md5 = md5.getMD5()
            destination.writeDeadProperty(TwistedGETContentMD5.fromString(md5))

        # Update the content-type value on the resource if it is not been copied or moved
        if source is None:
            content_type = request.headers.getHeader("content-type")
            if content_type is not None:
                destination.writeDeadProperty(davxml.GETContentType.fromString(generateContentType(content_type)))

        response = IResponse(response)
        
        # Do quota check on destination
        if destquota is not None:
            # Get size of new/old resources
            new_dest_size = waitForDeferred(destination.quotaSize(request))
            yield new_dest_size
            new_dest_size = new_dest_size.getResult()
            diff_size = new_dest_size - old_dest_size
            if diff_size >= destquota[0]:
                log.error("Over quota: available %d, need %d" % (destquota[0], diff_size))
                raise HTTPError(ErrorResponse(
                    responsecode.INSUFFICIENT_STORAGE_SPACE,
                    (dav_namespace, "quota-not-exceeded")
                ))
            d = waitForDeferred(destination.quotaSizeAdjust(request, diff_size))
            yield d
            d.getResult()

        if deletesource:
            # Delete the source resource
            if sourcequota is not None:
                delete_size = 0 - old_source_size
                d = waitForDeferred(source.quotaSizeAdjust(request, delete_size))
                yield d
                d.getResult()

            delete(source_uri, source.fp, depth)
            rollback.source_deleted = True

        # Can now commit changes and forget the rollback details
        rollback.Commit()

        yield response
        return
        
    except:
        # Roll back changes to original server state. Note this may do nothing
        # if the rollback has already ocurred or changes already committed.
        rollback.Rollback()
        raise

storeResource = deferredGenerator(storeResource)
