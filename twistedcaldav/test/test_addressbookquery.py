##
# Copyright (c) 2005-2013 Apple Inc. All rights reserved.
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

from twext.web2 import responsecode
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream
from txdav.xml import element as davxml
from twext.web2.dav.util import davXMLFromStream, joinURL

from twistedcaldav import carddavxml, vcard
from twistedcaldav.config import config
from twistedcaldav.test.util import StoreTestCase, SimpleStoreRequest
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python.filepath import FilePath

class AddressBookQuery(StoreTestCase):
    """
    addressbook-query REPORT
    """
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    vcards_dir = os.path.join(data_dir, "vCards")

    def test_addressbook_query_by_uid(self):
        """
        vCard by UID.
        """
        uid = "ED7A5AEC-AB19-4CE0-AD6A-2923A3E5C4E1:ABPerson"

        return self.simple_vcard_query(
            "/addressbook/",
            carddavxml.PropertyFilter(
                carddavxml.TextMatch.fromString(uid),
                name="UID",
            ),
            [uid]
        )


    def test_addressbook_query_all_vcards(self):
        """
        All vCards.
        """
        uids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.vcards_dir)) if r[1] == ".vcf"]

        return self.simple_vcard_query("/addressbook/", None, uids)


    def test_addressbook_query_limited_with_data(self):
        """
        All vCards.
        """

        oldValue = config.MaxQueryWithDataResults
        config.MaxQueryWithDataResults = 1
        def _restoreValueOK(f):
            config.MaxQueryWithDataResults = oldValue
            return None

        def _restoreValueError(f):
            config.MaxQueryWithDataResults = oldValue
            self.fail("REPORT must not fail with 403")

        uids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.vcards_dir)) if r[1] == ".vcf"]

        d = self.simple_vcard_query("/addressbook/", None, uids, limit=1)
        d.addCallbacks(_restoreValueOK, _restoreValueError)
        return d


    def test_addressbook_query_limited_without_data(self):
        """
        All vCards.
        """

        oldValue = config.MaxQueryWithDataResults
        config.MaxQueryWithDataResults = 1
        def _restoreValueOK(f):
            config.MaxQueryWithDataResults = oldValue
            return None

        def _restoreValueError(f):
            config.MaxQueryWithDataResults = oldValue
            self.fail("REPORT must not fail with 403")

        uids = [r[0] for r in (os.path.splitext(f) for f in os.listdir(self.vcards_dir)) if r[1] == ".vcf"]

        d = self.simple_vcard_query("/addressbook/", None, uids, withData=False)
        d.addCallbacks(_restoreValueOK, _restoreValueError)
        return d


    def simple_vcard_query(self, vcard_uri, vcard_filter, uids, withData=True, limit=None):

        vcard_uri = joinURL("/addressbooks/users/wsanchez", vcard_uri)

        props = (
            davxml.GETETag(),
        )
        if withData:
            props += (
                carddavxml.AddressData(),
            )
        query = carddavxml.AddressBookQuery(
            davxml.PropertyContainer(*props),
            carddavxml.Filter(
                vcard_filter,
            ),
        )

        def got_xml(doc):
            if not isinstance(doc.root_element, davxml.MultiStatus):
                self.fail("REPORT response XML root element is not multistatus: %r" % (doc.root_element,))

            count = 0
            for response in doc.root_element.childrenOfType(davxml.PropertyStatusResponse):
                for propstat in response.childrenOfType(davxml.PropertyStatus):
                    status = propstat.childOfType(davxml.Status)

                    if status.code == responsecode.INSUFFICIENT_STORAGE_SPACE and limit is not None:
                        continue
                    if status.code != responsecode.OK:
                        self.fail("REPORT failed (status %s) to locate properties: %r"
                                  % (status.code, propstat))
                    elif limit is not None:
                        count += 1
                        continue

                    properties = propstat.childOfType(davxml.PropertyContainer).children

                    for property in properties:
                        qname = property.qname()
                        if qname == (davxml.dav_namespace, "getetag"):
                            continue
                        if qname != (carddavxml.carddav_namespace, "address-data"):
                            self.fail("Response included unexpected property %r" % (property,))

                        result_addressbook = property.address()

                        if result_addressbook is None:
                            self.fail("Invalid response CardDAV:address-data: %r" % (property,))

                        uid = result_addressbook.resourceUID()

                        if uid in uids:
                            uids.remove(uid)
                        else:
                            self.fail("Got addressbook for unexpected UID %r" % (uid,))

                        original_filename = file(os.path.join(self.vcards_dir, uid + ".vcf"))
                        original_addressbook = vcard.Component.fromStream(original_filename)

                        self.assertEqual(result_addressbook, original_addressbook)

                if limit is not None and count != limit:
                    self.fail("Wrong number of limited results: %d" % (count,))

        return self.addressbook_query(vcard_uri, query, got_xml)


    @inlineCallbacks
    def addressbook_query(self, addressbook_uri, query, got_xml):
        '''
        mkcol = """<?xml version="1.0" encoding="utf-8" ?>
<D:mkcol xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
<D:set>
<D:prop>
<D:resourcetype><D:collection/><C:addressbook/></D:resourcetype>
</D:prop>
</D:set>
</D:mkcol>
"""
        response = yield self.send(SimpleStoreRequest(self, "MKCOL", addressbook_uri, content=mkcol, authid="wsanchez"))

        response = IResponse(response)

        if response.code != responsecode.CREATED:
            self.fail("MKCOL failed: %s" % (response.code,))
        '''
        # Add vCards to addressbook
        for child in FilePath(self.vcards_dir).children():
            if os.path.splitext(child.basename())[1] != ".vcf":
                continue
            request = SimpleStoreRequest(self, "PUT", joinURL(addressbook_uri, child.basename()), authid="wsanchez")
            request.stream = MemoryStream(child.getContent())
            yield self.send(request)

        request = SimpleStoreRequest(self, "REPORT", addressbook_uri, authid="wsanchez")
        request.stream = MemoryStream(query.toxml())
        response = yield self.send(request)

        response = IResponse(response)

        if response.code != responsecode.MULTI_STATUS:
            self.fail("REPORT failed: %s" % (response.code,))

        returnValue(
            (yield davXMLFromStream(response.stream).addCallback(got_xml))
        )
