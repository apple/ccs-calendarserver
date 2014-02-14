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

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.template import tags as html, renderer

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
            u"title": u"Calendar & Contacts Server Principal Search",
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
    def search_results_display(self, request, tag):
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


    def __init__(self, directory):
        TemplateResource.__init__(
            self, lambda: PrincipalsPageElement(directory)
        )

        self._directory = directory


    def getChild(self, name):
        if name == "":
            return self

        record = self._directory.recordWithUID(name)

        if record:
            return PrincipalEditResource(record)
        else:
            return None



class PrincipalEditPageElement(PageElement):
    """
    Principal editing page element.
    """

    def __init__(self, record):
        PageElement.__init__(self, u"principals_edit")

        self._record = record


    def pageSlots(self):
        record = self._record

        def one(value):
            if value is None:
                return u"(no value)"
            else:
                return unicode(value)

        def many(values):
            noValues = True

            for value in values:
                if not noValues:
                    yield html.br()

                yield one(value)

                noValues = False

            if noValues:
                yield u"(no values)"

        return {
            u"title": u"Calendar & Contacts Server Principal Information",
            u"service": (
                u"{service.__class__.__name__}: {service.realmName}"
                .format(service=record.service)
            ),
            u"uid": one(record.uid),
            u"guid": one(record.guid),
            u"record_type": one(record.recordType),
            u"short_names": many(record.shortNames),
            u"full_names": one(record.fullName),
            u"email_addresses": many(record.emailAddresses),
            u"calendar_user_addresses": many(record.calendarUserAddresses),
            u"server_id": one(record.serverID),
        }



class PrincipalEditResource(TemplateResource):
    """
    Principal editing resource.
    """

    addSlash = False


    def __init__(self, record):
        TemplateResource.__init__(
            self, lambda: PrincipalEditPageElement(record)
        )



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



# def slotsForRecord(record):
#     def one(value):
#         if value is None:
#             return u"(no value)"
#         else:
#             try:
#                 return unicode(value)
#             except UnicodeDecodeError:
#                 try:
#                     return unicode(repr(value))
#                 except UnicodeDecodeError:
#                     return u"(error rendering value)"

#     def many(values):
#         noValues = True

#         for value in values:
#             if not noValues:
#                 yield html.br()

#             yield one(value)

#             noValues = False

#         if noValues:
#             yield u"(no values)"

#     return {
#         u"service": (
#             u"{record.service.__class__.__name__}: {record.service.realmName}"
#             .format(record=record)
#         ),
#         u"uid": one(record.uid),
#         u"guid": one(record.guid),
#         u"record_type": one(record.recordType),
#         u"short_names": many(record.shortNames),
#         u"full_names": one(record.fullName),
#         u"email_addresses": many(record.emailAddresses),
#         u"calendar_user_addresses": many(record.calendarUserAddresses),
#         u"server_id": one(record.serverID),
#     }
