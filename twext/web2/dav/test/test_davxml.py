
##
# Copyright (c) 2005-2010 Apple Computer, Inc. All rights reserved.
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

from twext.web2.dav.davxml import *

from twistedcaldav.test.util import TestCase

class XML(TestCase):
    def test_sname2qname(self):
        # Empty name
        self.assertRaises(ValueError, sname2qname, "") 
        self.assertRaises(ValueError, sname2qname, "{}")
        self.assertRaises(ValueError, sname2qname, "{x}")

        # Weird bracket cases
        self.assertRaises(ValueError, sname2qname, "{")
        self.assertRaises(ValueError, sname2qname, "x{")
        self.assertRaises(ValueError, sname2qname, "{x")
        self.assertRaises(ValueError, sname2qname, "}")
        self.assertRaises(ValueError, sname2qname, "x}")
        self.assertRaises(ValueError, sname2qname, "}x")  
        self.assertRaises(ValueError, sname2qname, "{{}")
        self.assertRaises(ValueError, sname2qname, "{{}}")
        self.assertRaises(ValueError, sname2qname, "x{}")

        # Empty namespace is OK
        self.assertEquals(sname2qname("{}x"), ("", "x"))

        # Normal case
        self.assertEquals(sname2qname("{namespace}name"), ("namespace", "name"))

    def test_qname2sname(self):
        self.assertEquals(qname2sname(("namespace", "name")), "{namespace}name")
