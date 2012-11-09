##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

import twistedcaldav.test.util
from cStringIO import StringIO
from twistedcaldav.xmlutil import readXML, writeXML, addSubElement,\
    changeSubElementText, createElement, elementToXML, readXMLString

class XMLUtil(twistedcaldav.test.util.TestCase):
    """
    XML Util tests
    """
    
    data1 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE test SYSTEM "test.dtd">
<test>
  <help>me</help>
  <nesting>
    <nested/>
  </nesting>
</test>
"""

    data2 = """Not XML!"""

    data3 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE test SYSTEM "test.dtd">

<test>
  <help>me</help>
  <nesting>
    <nested />
  </nesting>
</test>
"""

    data4 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE test SYSTEM "test.dtd">

<test>
  <help>me</help>
  <nesting>
    <nested />
  </nesting>
  <added>added text</added>
</test>
"""

    data5 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE test SYSTEM "test.dtd">

<test>
  <help>changed text</help>
  <nesting>
    <nested />
  </nesting>
</test>
"""

    data6 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE test SYSTEM "test.dtd">

<test>
  <help>me</help>
  <nesting>
    <nested />
  </nesting>
  <new>new text</new>
</test>
"""

    def _checkXML(self, node, data):
        xmlfile = self.mktemp()
        writeXML(xmlfile, node)
        newdata = open(xmlfile).read()
        self.assertEqual(newdata, data)
        
    def test_readXML_noverify(self):
        
        io = StringIO(XMLUtil.data1)
        etree, root = readXML(io)
        self.assertEqual(etree.getroot(), root)
        self.assertEqual(root.tag, "test")

    def test_readXML_verify_ok(self):
        
        io = StringIO(XMLUtil.data1)
        etree, root = readXML(io, expectedRootTag="test")
        self.assertEqual(etree.getroot(), root)
        self.assertEqual(root.tag, "test")

    def test_readXML_verify_bad(self):
        
        io = StringIO(XMLUtil.data1)
        self.assertRaises(ValueError, readXML, io, "test1")

    def test_readXML_data_bad(self):
        
        io = StringIO(XMLUtil.data2)
        self.assertRaises(ValueError, readXML, io)

    def test_writeXML(self):
        
        io = StringIO(XMLUtil.data1)
        _ignore_etree, root = readXML(io)
        self._checkXML(root, XMLUtil.data3)

    def test_addElement(self):
        
        io = StringIO(XMLUtil.data1)
        _ignore_etree, root = readXML(io)
        addSubElement(root, "added", "added text")
        self._checkXML(root, XMLUtil.data4)

    def test_changeElement_existing(self):
        
        io = StringIO(XMLUtil.data1)
        _ignore_etree, root = readXML(io)
        changeSubElementText(root, "help", "changed text")
        self._checkXML(root, XMLUtil.data5)

    def test_changeElement_new(self):
        
        io = StringIO(XMLUtil.data1)
        _ignore_etree, root = readXML(io)
        changeSubElementText(root, "new", "new text")
        self._checkXML(root, XMLUtil.data6)


    def test_emoji(self):
        """
        Verify we can serialize and parse unicode values above 0xFFFF
        """
        name = u"Emoji \U0001F604"
        elem = createElement("test", text=name)
        xmlString1 = elementToXML(elem)
        parsed = readXMLString(xmlString1)[1]
        xmlString2 = elementToXML(parsed)
        self.assertEquals(xmlString1, xmlString2)
