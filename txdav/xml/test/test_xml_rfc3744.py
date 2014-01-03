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
##

from twisted.trial import unittest

from txdav.xml import element as davxml
from txweb2.dav.resource import davPrivilegeSet


class XML_3744(unittest.TestCase):
    """
    RFC 3744 (WebDAV ACL) XML tests.
    """
    def test_Privilege_isAggregateOf(self):
        """
        Privilege.isAggregateOf()
        """
        for a, b in (
            (davxml.All(), davxml.Write()),
            (davxml.All(), davxml.ReadACL()),
            (davxml.Write(), davxml.WriteProperties()),
            (davxml.Write(), davxml.WriteContent()),
            (davxml.Write(), davxml.Bind()),
            (davxml.Write(), davxml.Unbind()),
        ):
            pa = davxml.Privilege(a)
            pb = davxml.Privilege(b)

            self.failUnless(
                pa.isAggregateOf(pb, davPrivilegeSet),
                "%s contains %s" % (a.sname(), b.sname())
            )
            self.failIf(
                pb.isAggregateOf(pa, davPrivilegeSet),
                "%s does not contain %s" % (b.sname(), a.sname())
            )

        for a, b in (
            (davxml.Unlock(), davxml.Write()),
            (davxml.Unlock(), davxml.WriteACL()),
            (davxml.ReadCurrentUserPrivilegeSet(), davxml.WriteProperties()),
        ):
            pa = davxml.Privilege(a)
            pb = davxml.Privilege(b)

            self.failIf(
                pb.isAggregateOf(pa, davPrivilegeSet),
                "%s does not contain %s" % (b.sname(), a.sname())
            )
