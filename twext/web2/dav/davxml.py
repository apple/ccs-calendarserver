
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

"""
WebDAV XML Support.

This module provides XML utilities for use with WebDAV.

This API is considered private to static.py and is therefore subject to
change.

See RFC 2518: http://www.ietf.org/rfc/rfc2518.txt (WebDAV)
See RFC 3253: http://www.ietf.org/rfc/rfc3253.txt (WebDAV + Versioning)
See RFC 3744: http://www.ietf.org/rfc/rfc3744.txt (WebDAV ACLs)
"""

#
# Import all XML element definitions
#

from twext.web2.dav.element.base    import *
from twext.web2.dav.element.parser  import *
from twext.web2.dav.element.util    import *
from twext.web2.dav.element.rfc2518 import *
from twext.web2.dav.element.rfc3253 import *
from twext.web2.dav.element.rfc3744 import *
from twext.web2.dav.element.rfc4331 import *
from twext.web2.dav.element.extensions import CurrentUserPrincipal

#
# Register all XML elements with the parser
#

from twext.web2.dav.element import base as b
from twext.web2.dav.element import parser as p
from twext.web2.dav.element import util as u
from twext.web2.dav.element import rfc2518 as r1
from twext.web2.dav.element import rfc3253 as r2
from twext.web2.dav.element import rfc3744 as r3
from twext.web2.dav.element import extensions as e

__all__ = (
    registerElements(b) +
    registerElements(p) +
    registerElements(u) +
    registerElements(r1) +
    registerElements(r2) +
    registerElements(r3) +
    registerElements(e) +
    [
        "sname2qname",
        "qname2sname",
        "ErrorDescription",
        "ErrorResponse",
        "SyncCollection",
        "SyncToken",
    ]
)

#from twext.web2.http import Response

from twext.web2.dav._errorbase import ErrorResponse as SuperErrorResponse
from twext.web2.dav.davxml import dav_namespace, twisted_dav_namespace, WebDAVElement, WebDAVTextElement
from twext.web2.dav.davxml import WebDAVUnknownElement, Error
from twext.web2.http_headers import MimeType


def sname2qname(sname):
    """
    Convert an sname into a qname.

    That is, parse a property name string (eg: C{"{DAV:}displayname"})
    into a tuple (eg: C{("DAV:", "displayname")}).

    @raise ValueError is input is not valid. Note, however, that this
    function does not attempt to fully validate C{sname}.
    """
    def raiseIf(condition):
        if condition:
            raise ValueError("Invalid sname: %s" % (sname,))

    raiseIf(not sname.startswith("{"))

    try:
        i = sname.index("}")
    except ValueError:
        raiseIf(True)

    namespace = sname[1:i]
    name = sname [i+1:]

    raiseIf("{" in namespace or not name)

    return namespace, name

def qname2sname(qname):
    """
    Convert a qname into an sname.
    """
    try:
        return "{%s}%s" % qname
    except TypeError:
        raise ValueError("Invalid qname: %r" % (qname,))





class ErrorDescription(WebDAVTextElement):
    """
    The human-readable description of a failed precondition
    """
    namespace = twisted_dav_namespace
    name = "error-description"
    protected = True


class ErrorResponse(SuperErrorResponse):
    """
    A L{Response} object which contains a status code and a L{davxml.Error}
    element.
    Renders itself as a DAV:error XML document.
    """
    error = None
    unregistered = True     # base class is already registered

    def __init__(self, code, error, description=None):
        """
        @param code: a response code.
        @param error: an L{davxml.WebDAVElement} identifying the error, or a
            tuple C{(namespace, name)} with which to create an empty element
            denoting the error.  (The latter is useful in the case of
            preconditions ans postconditions, not all of which have defined
            XML element classes.)
        @param description: an optional string that, if present, will get
            wrapped in a (twisted_dav_namespace, error-description) element.
        """
        if type(error) is tuple:
            xml_namespace, xml_name = error
            error = WebDAVUnknownElement()
            error.namespace = xml_namespace
            error.name = xml_name

        if description:
            output = Error(error, ErrorDescription(description)).toxml()
        else:
            output = Error(error).toxml()

        SuperErrorResponse.__init__(self, code=code, error=error, stream=output)


    def __repr__(self):
        return "<%s %s %s>" % (self.__class__.__name__, self.code, self.error.sname())

class SyncCollection (WebDAVElement):
    """
    DAV report used to retrieve specific calendar component items via their
    URIs.
    (CalDAV-access-09, section 9.9)
    """
    name = "sync-collection"

    # To allow for an empty element in a supported-report-set property we need
    # to relax the child restrictions
    allowed_children = {
        (dav_namespace, "sync-token"): (0, 1), # When used in the REPORT this is required
        (dav_namespace, "prop"    ):   (0, 1),
    }

    def __init__(self, *children, **attributes):
        super(SyncCollection, self).__init__(*children, **attributes)

        self.property = None
        self.sync_token = None

        for child in self.children:
            qname = child.qname()

            if qname == (dav_namespace, "sync-token"):
                
                self.sync_token = str(child)

            elif qname in (
                (dav_namespace, "prop"    ),
            ):
                if self.property is not None:
                    raise ValueError("Only one of DAV:prop allowed")
                self.property = child

registerElement(SyncCollection)

class SyncToken (WebDAVTextElement):
    """
    Synchronization token used in report and as a property.
    """
    name = "sync-token"
    hidden = True
    protected = True

registerElement(SyncToken)


