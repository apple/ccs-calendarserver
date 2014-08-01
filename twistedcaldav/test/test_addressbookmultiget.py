##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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

import os

from txweb2 import responsecode
from txweb2.iweb import IResponse
from txweb2.stream import MemoryStream
from txweb2.dav.util import davXMLFromStream, joinURL
from txweb2.http_headers import Headers, MimeType

from twistedcaldav import carddavxml
from twistedcaldav import vcard
from twistedcaldav.config import config
from twistedcaldav.test.util import StoreTestCase, SimpleStoreRequest

from twisted.python.filepath import FilePath
from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.xml import element as davxml



class AddressBookMultiget (StoreTestCase):
    """
    addressbook-multiget REPORT
    """
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    vcards_dir = os.path.join(data_dir, "vCards")


    @inlineCallbacks
    def setUp(self):
        yield StoreTestCase.setUp(self)
        self.authPrincipal = yield self.actualRoot.findPrincipalForAuthID("wsanchez")


    def test_multiget_some_vcards(self):
        """
        All vcards.
        """
        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.vcards_dir)) if r[1] == ".vcf"]
        okuids[:] = okuids[1:5]

        baduids = ["12345%40example.com", "67890%40example.com"]

        return self.simple_vcard_multiget("/addressbook/", okuids, baduids)


    def test_multiget_all_vcards(self):
        """
        All vcards.
        """
        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.vcards_dir)) if r[1] == ".vcf"]

        baduids = ["12345%40example.com", "67890%40example.com"]

        return self.simple_vcard_multiget("/addressbook/", okuids, baduids)


    def test_multiget_limited_with_data(self):
        """
        All vcards.
        """
        oldValue = config.MaxMultigetWithDataHrefs
        config.MaxMultigetWithDataHrefs = 1
        def _restoreValueOK(f):
            config.MaxMultigetWithDataHrefs = oldValue
            self.fail("REPORT must fail with 403")

        def _restoreValueError(f):
            config.MaxMultigetWithDataHrefs = oldValue
            return None

        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.vcards_dir)) if r[1] == ".vcf"]

        baduids = ["12345%40example.com", "67890%40example.com"]

        d = self.simple_vcard_multiget("/addressbook/", okuids, baduids)
        d.addCallbacks(_restoreValueOK, _restoreValueError)
        return d


    def test_multiget_limited_no_data(self):
        """
        All vcards.
        """
        oldValue = config.MaxMultigetWithDataHrefs
        config.MaxMultigetWithDataHrefs = 1
        def _restoreValueOK(f):
            config.MaxMultigetWithDataHrefs = oldValue
            return None

        def _restoreValueError(f):
            config.MaxMultigetWithDataHrefs = oldValue
            self.fail("REPORT must not fail with 403")

        okuids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.vcards_dir)) if r[1] == ".vcf"]

        baduids = ["12345%40example.com", "67890%40example.com"]

        return self.simple_vcard_multiget("/addressbook/", okuids, baduids, withData=False)


    def simple_vcard_multiget(self, vcard_uri, okuids, baduids, data=None, no_init=False, withData=True):

        vcard_uri = joinURL("/addressbooks/users/wsanchez", vcard_uri)

        props = (
            davxml.GETETag(),
        )
        if withData:
            props += (
                carddavxml.AddressData(),
            )
        children = []
        children.append(davxml.PropertyContainer(*props))

        okhrefs = [vcard_uri + x + ".vcf" for x in okuids]
        badhrefs = [vcard_uri + x + ".vcf" for x in baduids]
        for href in okhrefs + badhrefs:
            children.append(davxml.HRef.fromString(href))

        query = carddavxml.AddressBookMultiGet(*children)

        def got_xml(doc):
            if not isinstance(doc.root_element, davxml.MultiStatus):
                self.fail("REPORT response XML root element is not multistatus: %r" % (doc.root_element,))

            for response in doc.root_element.childrenOfType(davxml.PropertyStatusResponse):
                href = str(response.childOfType(davxml.HRef))
                for propstat in response.childrenOfType(davxml.PropertyStatus):
                    status = propstat.childOfType(davxml.Status)

                    if status.code != responsecode.OK:
                        self.fail(
                            "REPORT failed (status %s) to locate properties: %r"
                            % (status.code, href)
                        )

                    properties = propstat.childOfType(davxml.PropertyContainer).children

                    for property in properties:
                        qname = property.qname()
                        if qname == (davxml.dav_namespace, "getetag"):
                            continue
                        if qname != (carddavxml.carddav_namespace, "address-data"):
                            self.fail("Response included unexpected property %r" % (property,))

                        result_address = property.address()

                        if result_address is None:
                            self.fail("Invalid response CalDAV:address-data: %r" % (property,))

                        uid = result_address.resourceUID()

                        if uid in okuids:
                            okuids.remove(uid)
                        else:
                            self.fail("Got address for unexpected UID %r" % (uid,))

                        if data:
                            original_address = vcard.Component.fromStream(data[uid])
                        else:
                            original_filename = file(os.path.join(self.vcards_dir, uid + ".vcf"))
                            original_address = vcard.Component.fromStream(original_filename)

                        self.assertEqual(result_address, original_address)

            for response in doc.root_element.childrenOfType(davxml.StatusResponse):
                href = str(response.childOfType(davxml.HRef))
                propstatus = response.childOfType(davxml.PropertyStatus)
                if propstatus is not None:
                    status = propstatus.childOfType(davxml.Status)
                else:
                    status = response.childOfType(davxml.Status)
                if status.code != responsecode.OK:
                    if href in okhrefs:
                        self.fail(
                            "REPORT failed (status %s) to locate properties: %r"
                            % (status.code, href)
                        )
                    else:
                        if href in badhrefs:
                            badhrefs.remove(href)
                            continue
                        else:
                            self.fail("Got unexpected href %r" % (href,))

            if withData and (len(okuids) + len(badhrefs)):
                self.fail("Some components were not returned: %r, %r" % (okuids, badhrefs))

        return self.addressbook_query(vcard_uri, query, got_xml, data, no_init)


    @inlineCallbacks
    def addressbook_query(self, addressbook_uri, query, got_xml, data, no_init):

        if not no_init:
            ''' FIXME: clear address book, possibly by removing
            mkcol = """<?xml version="1.0" encoding="utf-8" ?>
<D:mkcol xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
<D:set>
<D:prop>
<D:resourcetype><D:collection/><C:addressbook/></D:resourcetype>
</D:prop>
</D:set>
</D:mkcol>
"""
            response = yield self.send(SimpleStoreRequest(self, "MKCOL", addressbook_uri, content=mkcol, authPrincipal=self.authPrincipal))

            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCOL failed: %s" % (response.code,))
            '''
            if data:
                for filename, icaldata in data.iteritems():
                    request = SimpleStoreRequest(
                        self,
                        "PUT",
                        joinURL(addressbook_uri, filename + ".vcf"),
                        headers=Headers({"content-type": MimeType.fromString("text/vcard")}),
                        authPrincipal=self.authPrincipal
                    )
                    request.stream = MemoryStream(icaldata)
                    yield self.send(request)
            else:
                # Add vcards to addressbook
                for child in FilePath(self.vcards_dir).children():
                    if os.path.splitext(child.basename())[1] != ".vcf":
                        continue
                    request = SimpleStoreRequest(
                        self,
                        "PUT",
                        joinURL(addressbook_uri, child.basename()),
                        headers=Headers({"content-type": MimeType.fromString("text/vcard")}),
                        authPrincipal=self.authPrincipal
                    )
                    request.stream = MemoryStream(child.getContent())
                    yield self.send(request)

        request = SimpleStoreRequest(self, "REPORT", addressbook_uri, authPrincipal=self.authPrincipal)
        request.stream = MemoryStream(query.toxml())
        response = yield self.send(request)

        response = IResponse(response)

        if response.code != responsecode.MULTI_STATUS:
            self.fail("REPORT failed: %s" % (response.code,))

        returnValue(
            (yield davXMLFromStream(response.stream).addCallback(got_xml))
        )
