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

from txdav.base.propertystore.appledouble_xattr import attrsFromFile

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

