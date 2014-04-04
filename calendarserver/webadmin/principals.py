# -*- test-case-name: calendarserver.webadmin.test.test_principals -*-
##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

from __future__ import print_function

"""
Calendar Server principal management web UI.
"""

__all__ = [
    "PrincipalsResource",
]

from cStringIO import StringIO
from zipfile import ZipFile

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.template import tags as html, renderer

from txweb2.stream import MemoryStream
from txweb2.resource import Resource
from txweb2.http import Response
from txweb2.http_headers import MimeType

from .resource import PageElement, TemplateResource



class PrincipalsPageElement(PageElement):
    """
    Principal management page element.
    """

    def __init__(self, directory):
        PageElement.__init__(self, u"principals")

        self._directory = directory


    def pageSlots(self):
        return {
            u"title": u"Principal Management",
        }


    @renderer
    def search_terms(self, request, tag):
        """
        Inserts search terms as a text child of C{tag}.
        """
        terms = searchTerms(request)
        if terms:
            return tag(value=u" ".join(terms))
        else:
            return tag


    @renderer
    def if_search_results(self, request, tag):
        """
        Renders C{tag} if there are search results, otherwise removes it.
        """
        if searchTerms(request):
            return tag
        else:
            return u""


    @renderer
    def search_results_row(self, request, tag):
        def rowsForRecords(records):
            for record in records:
                yield tag.clone().fillSlots(
                    **slotsForRecord(record)
                )

        d = self.recordsForSearchTerms(request)
        d.addCallback(rowsForRecords)
        return d


    @inlineCallbacks
    def recordsForSearchTerms(self, request):
        if not hasattr(request, "_search_result_records"):
            terms = searchTerms(request)
            records = yield self._directory.recordsMatchingTokens(terms)
            request._search_result_records = tuple(records)

        returnValue(request._search_result_records)



class PrincipalsResource(TemplateResource):
    """
    Principal management page resource.
    """

    addSlash = True


    def __init__(self, directory, store):
        TemplateResource.__init__(
            self, lambda: PrincipalsPageElement(directory)
        )

        self._directory = directory
        self._store = store


    @inlineCallbacks
    def getChild(self, name):
        if name == "":
            returnValue(self)

        record = yield self._directory.recordWithUID(name)

        if record:
            returnValue(PrincipalResource(record, self._store))
        else:
            returnValue(None)



class PrincipalPageElement(PageElement):
    """
    Principal editing page element.
    """

    def __init__(self, record):
        PageElement.__init__(self, u"principals_edit")

        self._record = record


    def pageSlots(self):
        slots = slotsForRecord(self._record)

        slots[u"title"] = u"Calendar & Contacts Server Principal Information"
        slots[u"service"] = (
            u"{self._record.service.__class__.__name__}: "
            "{self._record.service.realmName}"
            .format(self=self)
        )

        return slots



class PrincipalResource(TemplateResource):
    """
    Principal editing resource.
    """

    addSlash = True


    def __init__(self, record, store):
        TemplateResource.__init__(
            self, lambda: PrincipalPageElement(record)
        )

        self._record = record
        self._store = store


    def getChild(self, name):
        if name == "":
            return self

        if name == "calendars_combined":
            return PrincipalCalendarsExportResource(self._record, self._store)



class PrincipalCalendarsExportResource(Resource):
    """
    Resource that vends a principal's calendars as iCalendar text.
    """

    addSlash = False


    def __init__(self, record, store):
        Resource.__init__(self)

        self._record = record
        self._store = store


    @inlineCallbacks
    def calendarComponents(self):
        uid = self._record.uid

        calendarComponents = []

        txn = self._store.newTransaction()
        try:
            calendarHome = yield txn.calendarHomeWithUID(uid)

            if calendarHome is None:
                raise RuntimeError("No calendar home for UID: {}".format(uid))

            for calendar in (yield calendarHome.calendars()):
                name = calendar.displayName()

                for calendarObject in (yield calendar.calendarObjects()):
                    perUser = yield calendarObject.filteredComponent(uid, True)
                    calendarComponents.add((name, perUser))

        finally:
            txn.abort()

        returnValue(calendarComponents)


    @inlineCallbacks
    def iCalendarZipArchiveData(self):
        calendarComponents = yield self.calendarComponents()

        fileHandle = StringIO()
        try:
            zipFile = ZipFile(fileHandle, "w", allowZip64=True)
            try:
                zipFile.comment = (
                    "Calendars for UID: {}".format(self._record.uid)
                )

                names = set()

                for name, component in calendarComponents:
                    if name in names:
                        i = 0
                        while True:
                            i += 1
                            nextName = "{} {:d}".format(name, i)
                            if nextName not in names:
                                name = nextName
                                break
                            assert i < len(calendarComponents)

                    text = component.getText().encode("utf-8")

                    zipFile.writestr(name.encode("utf-8"), text)

            finally:
                zipFile.close()

            data = fileHandle.getvalue()
        finally:
            fileHandle.close()

        returnValue(data)


    @inlineCallbacks
    def render(self, request):
        response = Response()
        response.stream = MemoryStream((yield self.iCalendarZipArchiveData()))

        # FIXME: Use content-encoding instead?
        response.headers.setHeader(
            b"content-type",
            MimeType.fromString(b"application/zip")
        )

        returnValue(response)



def searchTerms(request):
    if not hasattr(request, "_search_terms"):
        terms = set()

        if request.args:

            for query in request.args.get(u"search", []):
                for term in query.split(u" "):
                    if term:
                        terms.add(term)

            for term in request.args.get(u"term", []):
                if term:
                    terms.add(term)

        request._search_terms = terms

    return request._search_terms


#
# This should work when we switch to twext.who
#
def slotsForRecord(record):
    def asText(obj):
        if obj is None:
            return u"(no value)"
        else:
            try:
                return unicode(obj)
            except UnicodeDecodeError:
                try:
                    return unicode(repr(obj))
                except UnicodeDecodeError:
                    return u"(error rendering value)"

    def joinWithBR(elements):
        noValues = True

        for element in elements:
            if not noValues:
                yield html.br()

            yield asText(element)

            noValues = False

        if noValues:
            yield u"(no values)"


    # slots = {}

    # for field, values in record.fields.iteritems():
    #     if not record.service.fieldName.isMultiValue(field):
    #         values = (values,)

    #     slots[field.name] = joinWithBR(asText(value) for value in values)

    # return slots

    return {
        u"service": (
            u"{record.service.__class__.__name__}: {record.service.realmName}"
            .format(record=record)
        ),
        u"uid": joinWithBR((record.uid,)),
        u"guid": joinWithBR((record.guid,)),
        u"recordType": joinWithBR((record.recordType,)),
        u"shortNames": joinWithBR(record.shortNames),
        u"fullNames": joinWithBR((record.fullName,)),
        u"emailAddresses": joinWithBR(record.emailAddresses),
        u"calendarUserAddresses": joinWithBR(record.calendarUserAddresses),
        u"serverID": joinWithBR((record.serverID,)),
    }
