#!/usr/bin/env python

##
# Copyright (c) 2007 Apple Inc.
#
# This is the MIT license.  This software may also be distributed under the
# same terms as Python (the PSF license).
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
##

import sys
import os
import getopt
import xattr
import zlib

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [-lz] file [file ...]" % (name,)
    print "       %s -p [-lz] attr_name file [file ...]" % (name,)
    print "       %s -w [-z] attr_name attr_value file [file ...]" % (name,)
    print "       %s -d attr_name file [file ...]" % (name,)
    print ""
    print "The first form lists the names of all xattrs on the given file(s)."
    print "The second form (-p) prints the value of the xattr attr_name."
    print "The third form (-w) sets the value of the xattr attr_name to attr_value."
    print "The fourth form (-d) deletes the xattr attr_name."
    print ""
    print "options:"
    print "  -h: print this help"
    print "  -l: print long format (attr_name: attr_value)"
    print "  -z: compress or decompress (if compressed) attribute value in zip format"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

class NullsInString(Exception):
    """Nulls in string."""

_FILTER=''.join([(len(repr(chr(x)))==3) and chr(x) or '.' for x in range(256)])

def _dump(src, length=16):
    result=[]
    for i in xrange(0, len(src), length):
        s = src[i:i+length]
        hexa = ' '.join(["%02X"%ord(x) for x in s])
        printable = s.translate(_FILTER)
        result.append("%04X   %-*s   %s\n" % (i, length*3, hexa, printable))
    return ''.join(result)

def main():
    try:
        (optargs, args) = getopt.getopt(sys.argv[1:], "hlpwdz", ["help"])
    except getopt.GetoptError, e:
        usage(e)

    attr_name   = None
    long_format = False
    read        = False
    write       = False
    delete      = False
    compress    = lambda x: x
    decompress  = compress
    status      = 0

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()
        elif opt == "-l":
            long_format = True
        elif opt == "-p":
            read = True
            if write or delete:
                usage("-p not allowed with -w or -d")
        elif opt == "-w":
            write = True
            if read or delete:
                usage("-w not allowed with -p or -d")
        elif opt == "-d":
            delete = True
            if read or write:
                usage("-d not allowed with -p or -w")
        elif opt == "-z":
            compress   = zlib.compress
            decompress = zlib.decompress

    if write or delete:
        if long_format:
            usage("-l not allowed with -w or -p")

    if read or write or delete:
        if not args:
            usage("No attr_name")
        attr_name = args.pop(0)

    if write:
        if not args:
            usage("No attr_value")
        attr_value = args.pop(0)

    if len(args) > 1:
        multiple_files = True
    else:
        multiple_files = False

    for filename in args:
        def onError(e):
            if not os.path.exists(filename):
                sys.stderr.write("No such file: %s\n" % (filename,))
            else:
                sys.stderr.write(str(e) + "\n")
            status = 1

        try:
            attrs = xattr.xattr(filename)
        except (IOError, OSError), e:
            onError(e)
            continue

        if write:
            try:
                attrs[attr_name] = compress(attr_value)
            except (IOError, OSError), e:
                onError(e)
                continue

        elif delete:
            try:
                del attrs[attr_name]
            except (IOError, OSError), e:
                onError(e)
                continue
            except KeyError:
                onError("No such xattr: %s" % (attr_name,))
                continue

        else:
            try:
                if read:
                    attr_names = (attr_name,)
                else:
                    attr_names = attrs.keys()
            except (IOError, OSError), e:
                onError(e)
                continue

            if multiple_files:
                file_prefix = "%s: " % (filename,)
            else:
                file_prefix = ""

            for attr_name in attr_names:
                try:
                    try:
                        attr_value = decompress(attrs[attr_name])
                    except zlib.error:
                        attr_value = attrs[attr_name]
                except KeyError:
                    onError("%sNo such xattr: %s" % (file_prefix, attr_name))
                    continue

                if long_format:
                    try:
                        if attr_value.find('\0') >= 0:
                            raise NullsInString;
                        print "".join((file_prefix, "%s: " % (attr_name,), attr_value))
                    except (UnicodeDecodeError, NullsInString):
                        print "".join((file_prefix, "%s:" % (attr_name,)))
                        print _dump(attr_value)
                else:
                    if read:
                        print "".join((file_prefix, attr_value))
                    else:
                        print "".join((file_prefix, attr_name))

    sys.exit(status)

if __name__ == "__main__":
    main()
