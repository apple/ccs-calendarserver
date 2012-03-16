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

"""
WebDAV XML elements.
"""

__all__ = [
    "registerElement",
    "registerElements",
    "lookupElement",
]

from txdav.xml.base import dav_namespace
from txdav.xml.base import twisted_dav_namespace, twisted_private_namespace

from txdav.xml.base import WebDAVElement


##
# XML element registration
##

_elements_by_qname = {}


def registerElements(module):
    """
    Register XML elements defined in the given module with the parser.
    """
    element_names = []

    items = module.__all__ if hasattr(module, "__all__") else dir(module)
    for element_class_name in items:
        element_class = getattr(module, element_class_name)

        if type(element_class) is type and issubclass(element_class, WebDAVElement):
            if element_class.namespace is None: continue
            if element_class.name is None: continue
            if element_class.unregistered: continue

            registerElement(element_class)

            element_names.append(element_class.__name__)

    return element_names


def registerElement(element_class):
    """
    Register the supplied XML elements with the parser.
    """
    qname = element_class.namespace, element_class.name
    
    if qname in _elements_by_qname:
        raise AssertionError(
            "Attempting to register qname %s multiple times: (%r, %r)"
            % (qname, _elements_by_qname[qname], element_class)
        )
    
    if not (qname in _elements_by_qname and issubclass(element_class, _elements_by_qname[qname])):
        _elements_by_qname[qname] = element_class


def lookupElement(qname):
    """
    Return the element class for the element with the given qname.
    """
    return _elements_by_qname[qname]
