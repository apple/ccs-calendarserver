#!/usr/bin/env python
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

import struct
import sys

# A lot of this is copied from python/plat-mac/applesingle.py,
# with data structure information taken from
# http://www.opensource.apple.com/source/Libc/Libc-391/darwin/copyfile.c

# File header format: magic, version, unused, number of entries
AS_HEADER_FORMAT=">LL16sh"
AS_HEADER_LENGTH=26

# The flag words for AppleDouble
AS_MAGIC=0x00051607
AS_VERSION=0x00020000

# Entry header format: id, offset, length
AS_ENTRY_FORMAT=">lll"
AS_ENTRY_LENGTH=12

# The id values
AS_DATAFORK=1
AS_RESOURCEFORK=2
AS_REALNAME=3
AS_COMMENT=4
AS_ICONBW=5
AS_ICONCOLOR=6
AS_DATESINFO=8
AS_FINDERINFO=9
AS_MACFILEINFO=10
AS_PRODOSFILEINFO=11
AS_MSDOSFILEINFO=12
AS_SHORTNAME=13
AS_AFPFILEINFO=14
AS_DIECTORYID=15

FINDER_INFO_LENGTH = 32
XATTR_OFFSET = FINDER_INFO_LENGTH + 2

XATTR_HDR_MAGIC = 0x41545452    # ATTR
XATTR_HEADER = ">llllllllhh"
XATTR_HEADER_LENGTH = 36
XATTR_ENTRY = ">llhb"
XATTR_ENTRY_LENGTH = 11

class AppleDouble(object):

    def __init__(self, fileobj, verbose=False):
        
        self.xattrs = {}

        # Get the top-level header
        header = fileobj.read(AS_HEADER_LENGTH)
        try:
            magic, version, _ignore, nentry = struct.unpack(AS_HEADER_FORMAT, header)
        except ValueError, arg:
            raise ValueError("Unpack header error: %s" % (arg,))
        if verbose:
            print 'Magic:   0x%8.8x' % (magic,)
            print 'Version: 0x%8.8x' % (version,)
            print 'Entries: %d' % (nentry,)
        if magic != AS_MAGIC:
            raise ValueError("Unknown AppleDouble magic number 0x%8.8x" % (magic,))
        if version != AS_VERSION:
            raise ValueError("Unknown AppleDouble version number 0x%8.8x" % (version,))
        if nentry <= 0:
            raise ValueError("AppleDouble file contains no forks")

        # Get each entry
        headers = [fileobj.read(AS_ENTRY_LENGTH) for _ignore in xrange(nentry)]
        for hdr in headers:
            try:
                restype, offset, length = struct.unpack(AS_ENTRY_FORMAT, hdr)
            except ValueError, arg:
                raise ValueError("Unpack entry error: %s" % (arg,))
            if verbose:
                print "\n-- Fork %d, offset %d, length %d" % (restype, offset, length)
                
            # Look for the FINDERINFO entry with extra bits
            if restype == AS_FINDERINFO and length > FINDER_INFO_LENGTH:
                
                # Get the xattr header
                fileobj.seek(offset+XATTR_OFFSET)
                data = fileobj.read(length-XATTR_OFFSET)
                if len(data) != length-XATTR_OFFSET:
                    raise ValueError("Short read: expected %d bytes got %d" % (length-XATTR_OFFSET, len(data)))
                magic, _ignore_tag, total_size, data_start, data_length, \
                _ignore_reserved1, _ignore_reserved2, _ignore_reserved3, \
                flags, num_attrs = struct.unpack(XATTR_HEADER, data[:XATTR_HEADER_LENGTH])
                if magic != XATTR_HDR_MAGIC:
                    raise ValueError("No xattrs found")
                if verbose:
                    print "\n  Xattr Header"
                    print '  Magic:       0x%08X' % (magic,)
                    print '  Total Size:  %d' % (total_size,)
                    print '  Data Start:  0x%02X' % (data_start,)
                    print '  Data Length: %d' % (data_length,)
                    print '  Flags:       0x%02X' % (flags,)
                    print '  Number:      %d' % (num_attrs,)
                
                # Get each xattr entry
                data = data[XATTR_HEADER_LENGTH:]
                for _ignore in xrange(num_attrs):
                    xattr_offset, xattr_length, xattr_flags, xattr_name_len = struct.unpack(XATTR_ENTRY, data[:XATTR_ENTRY_LENGTH])
                    xattr_name = data[XATTR_ENTRY_LENGTH:XATTR_ENTRY_LENGTH+xattr_name_len]
                    fileobj.seek(xattr_offset)
                    xattr_value = fileobj.read(xattr_length)
                    if verbose:
                        print "\n    Xattr Entry"
                        print '    Offset:      0x%02X' % (xattr_offset,)
                        print '    Length:      %d' % (xattr_length,)
                        print '    Flags:       0x%02X' % (xattr_flags,)
                        print '    Name:        %s' % (xattr_name,)
                        print '    Value:        %s' % (xattr_value,)
                    self.xattrs[xattr_name] = xattr_value
                    
                    # Skip over entry taking padding into account
                    advance = (XATTR_ENTRY_LENGTH + xattr_name_len + 3) & ~3
                    data = data[advance:]

def _test():
    if len(sys.argv) < 2:
        print 'Usage: appledouble_xattr.py [-v] appledoublefile'
        sys.exit(1)
    if sys.argv[1] == '-v':
        verbose = True
        del sys.argv[1]
    else:
        verbose = False

    adfile = AppleDouble(open(sys.argv[1]), verbose=verbose)
    for k, v in adfile.xattrs.items():
        print "%s: %s" % (k, v)

if __name__ == '__main__':
    _test()
