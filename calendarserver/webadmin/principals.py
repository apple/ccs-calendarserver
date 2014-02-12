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
        PageElement.__init__(self, "principals")

        self._directory = directory


    def pageSlots(self):
        return {
            u"title": u"Calendar & Contacts Server Principal Management",
        }


    @renderer
    def search_value(self, request, tag):
        terms = searchTerms(request)
        if terms:
            return tag(value=" ".join(terms))
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

    addSlash = False


    def __init__(self, directory):
        TemplateResource.__init__(
            self, lambda: PrincipalsPageElement(directory)
        )



def searchTerms(request):
    if request.args:
        terms = set()

        for query in request.args.get("search", []):
            for term in query.split(" "):
                terms.add(term)

        for term in request.args.get("term", []):
            terms.add(term)

        return terms

    else:
        return set()



def recordsTable(records):
    return tags.table(
        tags.caption(u"Records"),
    )
