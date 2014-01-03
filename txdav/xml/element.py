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

"""
WebDAV XML elements.
"""

__all__ = [
    "WebDAVDocument",
    "dav_namespace",
    "twisted_dav_namespace",
    "twisted_private_namespace",
    "WebDAVElement",
    "PCDATAElement",
    "WebDAVOneShotElement",
    "WebDAVUnknownElement",
    "WebDAVEmptyElement",
    "WebDAVTextElement",
    "WebDAVDateTimeElement",
    "DateTimeHeaderElement",
    "registerElement",
    "registerElementClass",
    "lookupElement",
]

from txdav.xml.parser import WebDAVDocument
from txdav.xml.base import dav_namespace
from txdav.xml.base import twisted_dav_namespace, twisted_private_namespace
from txdav.xml.base import WebDAVElement
from txdav.xml.base import PCDATAElement, WebDAVOneShotElement, WebDAVUnknownElement
from txdav.xml.base import WebDAVEmptyElement, WebDAVTextElement
from txdav.xml.base import WebDAVDateTimeElement, DateTimeHeaderElement
from txdav.xml.base import _elements_by_qname


##
# XML element registration
##

def registerElement(elementClass):
    """
    Register an XML element class with the parser and add to this module's namespace.
    """
    assert issubclass(elementClass, WebDAVElement), "Not a WebDAVElement: %s" % (elementClass,)
    assert elementClass.namespace, "Element has no namespace: %s" % (elementClass,)
    assert elementClass.name, "Element has no name: %s" % (elementClass,)

    qname = elementClass.namespace, elementClass.name
    
    if qname in _elements_by_qname:
        raise AssertionError(
            "Attempting to register element %s multiple times: (%r, %r)"
            % (elementClass.sname(), _elements_by_qname[qname], elementClass)
        )
    
    if not (qname in _elements_by_qname and issubclass(elementClass, _elements_by_qname[qname])):
        _elements_by_qname[qname] = elementClass

    return elementClass


def registerElementClass(elementClass):
    """
    Add an XML element class to this module's namespace.
    """
    env = globals()
    name = elementClass.__name__

    if name in env:
        raise AssertionError(
            "Attempting to register element class %s multiple times: (%r, %r)"
            % (name, env[name], elementClass)
        )

    env[name] = elementClass
    __all__.append(name)

    return elementClass


def lookupElement(qname):
    """
    Return the element class for the element with the given qname.
    """
    return _elements_by_qname[qname]
