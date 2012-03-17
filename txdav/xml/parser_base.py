##
# Copyright (c) 2005-2012 Apple Computer, Inc. All rights reserved.
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

__all__ = [
    "AbstractWebDAVDocument",
]

from cStringIO import StringIO

from txdav.xml.base import WebDAVElement


class AbstractWebDAVDocument(object):
    """
    WebDAV XML document.
    """
    @classmethod
    def fromStream(cls, source):
        raise NotImplementedError()

    @classmethod
    def fromString(cls, source):
        source = StringIO(source)
        try:
            return cls.fromStream(source)
        finally:
            source.close()

    def __init__(self, root_element):
        """
        root_element must be a WebDAVElement instance.
        """
        super(AbstractWebDAVDocument, self).__init__()

        if not isinstance(root_element, WebDAVElement):
            raise ValueError("Not a WebDAVElement: %r" % (root_element,))

        self.root_element = root_element

    def __str__(self):
        return self.toxml()

    def __eq__(self, other):
        if isinstance(other, AbstractWebDAVDocument):
            return self.root_element == other.root_element
        else:
            return NotImplemented

    def writeXML(self, output):
        raise NotImplementedError()

    def toxml(self):
        output = StringIO()
        self.writeXML(output)
        return output.getvalue()
