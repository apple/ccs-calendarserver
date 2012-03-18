##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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
import shutil

from twext.web2 import responsecode
from twext.web2.iweb import IResponse
from twext.web2.stream import MemoryStream
from txdav.xml import element as davxml
from twext.web2.dav.fileop import rmdir
from twext.web2.dav.util import davXMLFromStream
from twext.web2.test.test_server import SimpleRequest

# FIXME: remove this, we should not be importing this module, we should be
# testing the public API.  See comments below about cheating.
from txdav.carddav.datastore.index_file import db_basename

from twistedcaldav import carddavxml, vcard
from twistedcaldav.config import config
from twistedcaldav.test.util import AddressBookHomeTestCase

class AddressBookQuery (AddressBookHomeTestCase):
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
            "/addressbook_query_uid/",
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

        return self.simple_vcard_query("/addressbook_query_vcards/", None, uids)

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

        d = self.simple_vcard_query("/addressbook_query_vcards/", None, uids, limit=1)
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

        d = self.simple_vcard_query("/addressbook_query_vcards/", None, uids, withData=False)
        d.addCallbacks(_restoreValueOK, _restoreValueError)
        return d

    def simple_vcard_query(self, cal_uri, vcard_filter, uids, withData=True, limit=None):
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
                        if qname == (davxml.dav_namespace, "getetag"): continue
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
                    
        return self.addressbook_query(cal_uri, query, got_xml)

    def addressbook_query(self, addressbook_uri, query, got_xml):
        addressbook_path = os.path.join(self.docroot, addressbook_uri[1:])

        if os.path.exists(addressbook_path): rmdir(addressbook_path)

        def do_report(response):
            response = IResponse(response)

            if response.code != responsecode.CREATED:
                self.fail("MKCOL failed: %s" % (response.code,))

            # Add vCards to addressbook
            # We're cheating by simply copying the files in
            for filename in os.listdir(self.vcards_dir):
                if os.path.splitext(filename)[1] != ".vcf": continue
                path = os.path.join(self.vcards_dir, filename)
                shutil.copy(path, addressbook_path)

            # Delete the index because we cheated
            index_path = os.path.join(addressbook_path, db_basename)
            if os.path.isfile(index_path): os.remove(index_path)

            request = SimpleRequest(self.site, "REPORT", addressbook_uri)
            request.stream = MemoryStream(query.toxml())

            def do_test(response):
                response = IResponse(response)

                if response.code != responsecode.MULTI_STATUS:
                    self.fail("REPORT failed: %s" % (response.code,))

                return davXMLFromStream(response.stream).addCallback(got_xml)

            return self.send(request, do_test)

        mkcol = """<?xml version="1.0" encoding="utf-8" ?>
<D:mkcol xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
<D:set>
<D:prop>
<D:resourcetype><D:collection/><C:addressbook/></D:resourcetype>
</D:prop>
</D:set>
</D:mkcol>
"""
        request = SimpleRequest(self.site, "MKCOL", addressbook_uri, content=mkcol)

        return self.send(request, do_report)
