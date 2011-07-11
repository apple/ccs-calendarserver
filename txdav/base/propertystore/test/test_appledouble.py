##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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
Tests for txdav.base.propertystore.appledouble_xattr
"""

from twisted.trial.unittest import TestCase

from tarfile import TarFile
from cStringIO import StringIO

from txdav.base.propertystore.appledouble_xattr import (
    attrsFromFile, PropertyStore
)

from txdav.base.propertystore.base import PropertyName
from twisted.python.filepath import FilePath
from twext.web2.dav.element.rfc2518 import GETContentType, HRef, Depth

# This tar file contains a single file, 'f', with 2 xattrs; 'alpha' with
# contents 'beta', and 'gamma' with contents 'delta'.

simpleTarWithXattrs = """
H4sICDvqGk4AA2YudGFyAO2WvU7DMBSFrYofEYmBhdlPkPraTpwMGRBLkUAg2gGmyrShjUhLVFIo
G4/CwMLIy/A82GlCS6RSEAo/wp90Fec4sa4tnZzY9SM5aYSyG47qdvscVQEhxOUcI5GBEeEMGMVa
zwBBMIBLXMd1CDBMgDucIzyppJsS46tUjlQrvfg26b/znEySOGz35KL56Vbw6/WPAAKPo25AfZ96
VBCwKMGdNBqEATAgzHMFF1qT85rr+xbluLnb2Ns/tbvhdUAZ9zw151gUCj0aXgaCCY87FniFOIyj
4UUA1k/v2zDFrsz1Mwr/36nx1vPTZtn/1IGS/xlxXYRJxX1l/HP/o9XtdVRD6EB28GETn+AcraEN
VVTVjSp9//ixJXdareN8qN+4z1eap5brKwityTjpF8f6oDtSWk8OBpl2FqYqm+J04bkbvsQs/av7
CizPf1rOfxAm/7+F5flPP5P/xKJsPv8BOOeMU/MH8EupOvs1y/Jf++Wt/6lDuMl/g8FgqJIXLvCv
wAASAAA=
""".decode('base64')


class DecoderTests(TestCase):
    """
    Tests for decoding extended attributes from AppleDouble format.
    """

    def test_attrsFromFile(self):
        """
        Extracting a simple AppleDouble file representing some extended
        attributes should result in a dictionary of those attributes.
        """
        tarfile = TarFile.gzopen('sample.tgz',
                                 fileobj=StringIO(simpleTarWithXattrs))
        self.assertEqual(attrsFromFile(tarfile.extractfile("./._f")),
                         {"alpha": "beta", "gamma": "delta"})


# The following tar file was also created with a single file, but it was
# assigned a few bogus properties first, with a python program something like
# this:

# ps = PropertyStore("bob", lambda : FilePath("tmp/f"))
# ps[PropertyName.fromElement(HRef)] = HRef("http://sample.example.com/")
# ps[PropertyName.fromElement(Depth)] = Depth("1")
# ps[PropertyName.fromElement(GETContentType)] = GETContentType("text/example")
# ps.flush()


samplePropertyTar = """
H4sICJ/5Gk4AA2YudGFyAO3W3W4SQRQA4EFjiMTGqNErTUavoAjMz/5hJLHRRLZYwVKsRpNmhZWi
lVLcVhpj0gvvfAVfQBOiFSvxAUyKAhW1mnijiXe+gb3RXSilkCjlAn/i+ZKd3T0zTGYze/bg9UW0
XFDXEnrW5524ivqBECIJAkZyHUZE4JQzbMXrqEwwpRKRRJmL5gBCBVFiCOf6spoOszcNLWsuJTk1
n5n8xTgtk5nSJ5Laz/obj4I3zv8IKuPZVCLA/H6mMJlQByM4bqRu6AHKKeF+IimyFdM2x6jAHUzA
0ZNB9cxFb0KfCzAuKIrZJzoYbcZT6emAzBXiFx1UaQbTU6n09QB1/OnnBg3evmV9SzP/F8zrPe8X
BzrzX+ZyR/5zSkWESZ/XVfef5z/accCOtiE0osVxOIov4HVWDO00D4aQLW+ezXvbp61NOTQ2Ntq4
qv/is3l87xiyfT0eRGjfuH7l1ND5Y7et5k5CzxiNbbA5zeYyQgfb+pO6EZ9OG3raMOYzen3cXbO5
hNDetnGTWb3+WufuFxYfLVfOOUOewWp5pRCT3/HIeLASqoZL5VAxtntg5u1SpFj88kRVPc5SBD2s
uJ/Fbs3sKowW+dOa/d5HG/p6ZP9wD/OEPWp1xa1W3K4HR4MxdO3lxoRuNe+shfPBsmdZXaqdjqXs
iB8/XNr63CXn8EgUDbaW+Mrpcj1+88F31ppyNZRfeF369nxNWsOrc+jEi0OlrnvVqv79+wp0r/+s
s/4zCvX/t+he/wWhh/pPHIxvrv+UCoJobjD8A/hL9bv2W7rVfytf2vOfiYxB/QcAAAAAAAAAAAAA
AAAAAACgVz8Aa/aaaQAoAAA=
""".decode('base64')


class PropertyStoreTests(TestCase):
    """
    Tests for decoding WebDAV properties.
    """

    def test_propertiesFromTarball(self):
        """
        Extracting a tarball with included AppleDouble WebDAV property
        information should allow properties to be retrieved using
        L{PropertyStore}.
        """
        tf = TarFile.gzopen('sample.tgz', fileobj=StringIO(samplePropertyTar))
        tmpdir = self.mktemp()

        # Note that 'tarfile' doesn't know anything about xattrs, so while OS
        # X's 'tar' will restore these as actual xattrs, the 'tarfile' module
        # will drop "._" parallel files into the directory structure on all
        # platforms.
        tf.extractall(tmpdir)

        props = PropertyStore("bob", lambda : FilePath(tmpdir).child('f'))

        self.assertEqual(props[PropertyName.fromElement(HRef)],
                         HRef("http://sample.example.com/"))
        self.assertEqual(props[PropertyName.fromElement(Depth)],
                         Depth("1"))
        self.assertEqual(props[PropertyName.fromElement(GETContentType)],
                         GETContentType("text/example"))


