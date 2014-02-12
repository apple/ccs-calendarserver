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
from twisted.web.template import tags, renderer

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
    def search_value(self, request, tag):
        terms = searchTerms(request)
        if terms:
            return tag(value=u" ".join(terms))
        else:
            return tag


    @renderer
    @inlineCallbacks
    def search_results(self, request, tag):
        terms = searchTerms(request)

        if not terms:
            returnValue(u"")

        records = tuple((
            yield self.recordsForSearchTerms(terms)
        ))

        if records:
            returnValue(tag(recordsTable(records)))
        else:
            returnValue(tag(u"No records found."))


    def recordsForSearchTerms(self, terms):
        return self._directory.recordsMatchingTokens(terms)



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
                    yield tags.br()

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
    if request.args:
        terms = set()

        for query in request.args.get(u"search", []):
            for term in query.split(u" "):
                terms.add(term)

        for term in request.args.get(u"term", []):
            terms.add(term)

        return terms

    else:
        return set()



def recordsTable(records):
    def multiValue(values):
        return ((s, tags.br()) for s in values)

    def recordRows(records):
        attrs_record = {"class": "record"}
        attrs_fullName = {"class": "record_full_name"}
        attrs_uid = {"class": "record_uid"}
        attrs_recordType = {"class": "record_type"}
        attrs_shortName = {"class": "record_short_name"}
        attrs_email = {"class": "record_email"}

        i0 = u"\n" + (6 * u" ") + (0 * 2 * u" ")
        i1 = u"\n" + (6 * u" ") + (1 * 2 * u" ")
        i2 = u"\n" + (6 * u" ") + (2 * 2 * u" ")

        yield (
            i0,
            tags.thead(
                i1,
                tags.tr(
                    i2, tags.th(u"Full name", **attrs_fullName),
                    i2, tags.th(u"UID", **attrs_uid),
                    i2, tags.th(u"Record Type", **attrs_recordType),
                    i2, tags.th(u"Short Name", **attrs_shortName),
                    i2, tags.th(u"Email Address", **attrs_email),
                    i1,
                    **attrs_record
                ),
                i0,
            ),
            i0,
        )

        yield (
            tags.tbody(
                (
                    i1,
                    tags.tr(
                        i2, tags.td(record.fullName, **attrs_fullName),
                        i2, tags.td(record.uid, **attrs_uid),
                        i2, tags.td(record.recordType, **attrs_recordType),
                        i2, tags.td(
                            multiValue(record.shortNames), **attrs_shortName
                        ),
                        i2, tags.td(
                            multiValue(record.emailAddresses), **attrs_email
                        ),
                        i1,
                        onclick=(
                            'window.open("./{0}");'
                            .format(record.uid)
                        ),
                        **attrs_record
                    ),
                )
                for record in sorted(records, key=lambda record: record.uid)
            ),
            i0
        )

    return tags.table(
        tags.caption(u"Records"),
        recordRows(records),
        id="records",
    )
