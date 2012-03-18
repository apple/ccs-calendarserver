##
# Copyright (c) 2009-2012 Apple Computer, Inc. All rights reserved.
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
draft-daboo-webdav-sync (Collection Synchronization for WebDAV) XML
Elements

This module provides XML element definitions for use with WebDAV
Synchronization.

See draft-daboo-webdav-sync: http://tools.ietf.org/html/draft-daboo-webdav-sync

Last draft referenced: -08
"""

__all__ = []


from txdav.xml.base import WebDAVElement, WebDAVTextElement, dav_namespace
from txdav.xml.element import registerElement, registerElementClass
from txdav.xml.rfc2518 import MultiStatus


@registerElement
@registerElementClass
class SyncCollection (WebDAVElement):
    """
    DAV report used to retrieve specific calendar component items via
    their URIs.
    """
    name = "sync-collection"

    # To allow for an empty element in a supported-report-set property we need
    # to relax the child restrictions
    allowed_children = {
        (dav_namespace, "sync-token"): (0, 1), # When used in the REPORT this is required
        (dav_namespace, "sync-level"): (0, 1), # When used in the REPORT this is required
        (dav_namespace, "prop"      ): (0, 1),
    }

    def __init__(self, *children, **attributes):
        super(SyncCollection, self).__init__(*children, **attributes)

        self.property = None
        self.sync_token = None
        self.sync_level = None

        for child in self.children:
            qname = child.qname()

            if qname == (dav_namespace, "sync-token"):
                self.sync_token = str(child)

            elif qname == (dav_namespace, "sync-level"):
                self.sync_level = str(child)

            elif qname == (dav_namespace, "prop"):
                if self.property is not None:
                    raise ValueError("Only one of DAV:prop allowed")
                self.property = child


@registerElement
@registerElementClass
class SyncToken (WebDAVTextElement):
    """
    Synchronization token used in report and as a property.
    """
    name = "sync-token"
    hidden = True
    protected = True


@registerElement
@registerElementClass
class SyncLevel (WebDAVTextElement):
    """
    Synchronization level used in report.
    """
    name = "sync-level"


# Extend MultiStatus, to add sync-token
MultiStatus.allowed_children[(dav_namespace, "sync-token")] = (0, 1)
