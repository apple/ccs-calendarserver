##
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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
Various file utilities.
"""

from twext.web2.dav.fileop import copy
from twext.web2.dav.fileop import put
from twext.web2.dav.xattrprops import xattrPropertyStore

# This class simulates a DAVFile with enough information for use with xattrPropertyStore.
class FakeXAttrResource(object):
    
    def __init__(self, fp):
        self.fp = fp

def putWithXAttrs(stream, filepath):
    """
    Write a file to a possibly existing path and preserve any xattrs at that path.
    
    @param stream: the stream to write to the destination.
    @type stream: C{file}
    @param filepath: the destination file.
    @type filepath: L{FilePath}
    """
    
    # Preserve existings xattrs
    props = []
    if filepath.exists():
        xold = xattrPropertyStore(FakeXAttrResource(filepath))
        for item in xold.list():
            props.append((xold.get(item)))
        xold = None
    
    # First do the actual file copy
    def _gotResponse(response):
    
        # Restore original xattrs.
        if props:
            xnew = xattrPropertyStore(FakeXAttrResource(filepath))
            for prop in props:
                xnew.set(prop)
            xnew = None
    
        return response

    d = put(stream, filepath)
    d.addCallback(_gotResponse)
    return d

def copyWithXAttrs(source_filepath, destination_filepath, destination_uri):
    """
    Copy a file from one path to another and also copy xattrs we care about.
    
    @param source_filepath: the file to copy from
    @type source_filepath: L{FilePath}
    @param destination_filepath: the file to copy to
    @type destination_filepath: L{FilePath}
    @param destination_uri: the URI of the destination resource
    @type destination_uri: C{str}
    """
    
    # First do the actual file copy
    def _gotResponse(response):
    
        # Now copy over xattrs.
        copyXAttrs(source_filepath, destination_filepath)
        
        return response
    
    d = copy(source_filepath, destination_filepath, destination_uri, "0")
    d.addCallback(_gotResponse)
    return d

def copyToWithXAttrs(from_fp, to_fp):
    """
    Copy a file from one path to another and also copy xattrs we care about.
    
    @param from_fp: file being copied
    @type from_fp: L{FilePath}
    @param to_fp: file to copy to
    @type to_fp: L{FilePath}
    """
    
    # First do the actual file copy.
    from_fp.copyTo(to_fp)

    # Now copy over xattrs.
    copyXAttrs(from_fp, to_fp)

def copyXAttrs(from_fp, to_fp):    
    # Create xattr stores for each file and copy over all xattrs.
    xfrom = xattrPropertyStore(FakeXAttrResource(from_fp))
    xto = xattrPropertyStore(FakeXAttrResource(to_fp))

    for item in xfrom.list():
        xto.set(xfrom.get(item))
