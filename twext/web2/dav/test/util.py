##
# Copyright (c) 2005 Apple Computer, Inc. All rights reserved.
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

import os
from urllib import quote as url_quote
from filecmp import dircmp as DirCompare
from tempfile import mkdtemp
from shutil import copy

from twisted.trial import unittest
from twisted.internet.defer import Deferred

from twext.python.log import Logger
from twext.web2.http import HTTPError, StatusResponse
from twext.web2 import responsecode
from twext.web2.dav.resource import TwistedACLInheritable
from twext.web2.dav.static import DAVFile
from twext.web2.dav.util import joinURL
from txdav.xml import element
from txdav.xml.base import encodeXMLName

log = Logger()


class InMemoryPropertyStore (object):
    """
    A dead property store for keeping properties in memory

    DO NOT USE OUTSIDE OF UNIT TESTS!
    """
    def __init__(self, resource):
        self._dict = {}

    def get(self, qname):
        try:
            property = self._dict[qname]
        except KeyError:
            raise HTTPError(StatusResponse(
                responsecode.NOT_FOUND,
                "No such property: %s" % (encodeXMLName(*qname),)
            ))

        doc = element.WebDAVDocument.fromString(property)
        return doc.root_element

    def set(self, property):
        self._dict[property.qname()] = property.toxml()

    def delete(self, qname):
        try:
            del(self._dict[qname])
        except KeyError:
            pass

    def contains(self, qname):
        return qname in self._dict

    def list(self):
        return self._dict.keys()

class TestFile (DAVFile):
    _cachedPropertyStores = {}

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            dp = TestFile._cachedPropertyStores.get(self.fp.path)
            if dp is None:
                TestFile._cachedPropertyStores[self.fp.path] = InMemoryPropertyStore(self)
                dp = TestFile._cachedPropertyStores[self.fp.path]

            self._dead_properties = dp

        return self._dead_properties

    def parent(self):
        return TestFile(self.fp.parent())

class TestCase (unittest.TestCase):
    resource_class = TestFile

    def grant(*privileges):
        return element.ACL(*[
            element.ACE(
                element.Grant(element.Privilege(privilege)),
                element.Principal(element.All())
            )
            for privilege in privileges
        ])

    grant = staticmethod(grant)

    def grantInherit(*privileges):
        return element.ACL(*[
            element.ACE(
                element.Grant(element.Privilege(privilege)),
                element.Principal(element.All()),
                TwistedACLInheritable()
            )
            for privilege in privileges
        ])

    grantInherit = staticmethod(grantInherit)

    def createDocumentRoot(self):
        docroot = self.mktemp()
        os.mkdir(docroot)
        rootresource = self.resource_class(docroot)
        rootresource.setAccessControlList(self.grantInherit(element.All()))

        dirnames = (
            os.path.join(docroot, "dir1"),                          # 0
            os.path.join(docroot, "dir2"),                          # 1
            os.path.join(docroot, "dir2", "subdir1"),               # 2
            os.path.join(docroot, "dir3"),                          # 3
            os.path.join(docroot, "dir4"),                          # 4
            os.path.join(docroot, "dir4", "subdir1"),               # 5
            os.path.join(docroot, "dir4", "subdir1", "subsubdir1"), # 6
            os.path.join(docroot, "dir4", "subdir2"),               # 7
            os.path.join(docroot, "dir4", "subdir2", "dir1"),       # 8
            os.path.join(docroot, "dir4", "subdir2", "dir2"),       # 9
        )

        for dir in dirnames:
            os.mkdir(dir)

        src = os.path.dirname(__file__)
        filenames = [
            os.path.join(src, f)
            for f in os.listdir(src)
            if os.path.isfile(os.path.join(src, f))
        ]

        for dirname in (docroot,) + dirnames[3:8+1]:
            for filename in filenames[:5]:
                copy(filename, dirname)
        return docroot


    def _getDocumentRoot(self):
        if not hasattr(self, "_docroot"):
            log.msg("Setting up docroot for %s" % (self.__class__,))

            self._docroot = self.createDocumentRoot()

        return self._docroot

    def _setDocumentRoot(self, value):
        self._docroot = value

    docroot = property(_getDocumentRoot, _setDocumentRoot)

    def _getSite(self):
        if not hasattr(self, "_site"):
            rootresource = self.resource_class(self.docroot)
            rootresource.setAccessControlList(self.grantInherit(element.All()))
            self._site = Site(rootresource)
        return self._site

    def _setSite(self, site):
        self._site = site

    site = property(_getSite, _setSite)

    def setUp(self):
        unittest.TestCase.setUp(self)
        TestFile._cachedPropertyStores = {}

    def tearDown(self):
        unittest.TestCase.tearDown(self)


    def mkdtemp(self, prefix):
        """
        Creates a new directory in the document root and returns its path and
        URI.
        """
        path = mkdtemp(prefix=prefix + "_", dir=self.docroot)
        uri  = joinURL("/", url_quote(os.path.basename(path))) + "/"

        return (os.path.abspath(path), uri)


    def send(self, request, callback=None):
        log.msg("Sending %s request for URI %s" % (request.method, request.uri))

        d = request.locateResource(request.uri)
        d.addCallback(lambda resource: resource.renderHTTP(request))
        d.addCallback(request._cbFinishRender)

        if callback:
            if type(callback) is tuple:
                d.addCallbacks(*callback)
            else:
                d.addCallback(callback)

        return d

class Site:
    # FIXME: There is no ISite interface; there should be.
    # implements(ISite)

    def __init__(self, resource):
        self.resource = resource

def dircmp(dir1, dir2):
    dc = DirCompare(dir1, dir2)
    return bool(
        dc.left_only or dc.right_only or
        dc.diff_files or
        dc.common_funny or dc.funny_files
    )

def serialize(f, work):
    d = Deferred()

    def oops(error):
        d.errback(error)

    def do_serialize(_):
        try:
            args = work.next()
        except StopIteration:
            d.callback(None)
        else:
            r = f(*args)
            r.addCallback(do_serialize)
            r.addErrback(oops)

    do_serialize(None)

    return d
