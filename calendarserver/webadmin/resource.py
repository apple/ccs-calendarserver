# -*- test-case-name: calendarserver.webadmin.test.test_resource -*-
##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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

"""
Calendar Server Web Admin UI.
"""

__all__ = [
    "WebAdminResource",
    "WebAdminPage",
    "TemplateResource",
]

import operator
import urlparse

from zope.interface.declarations import implements

from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.modules import getModule
from txweb2.stream import MemoryStream
from txweb2.resource import Resource
from txweb2.http import Response
from txweb2.http_headers import MimeType
from txweb2.http import HTTPError
from txdav.xml import element as davxml

from twisted.web.iweb import ITemplateLoader
from twisted.web.template import (
    Element, renderer, XMLFile, flattenString, tags
)

from twistedcaldav.config import config
from twistedcaldav.extensions import DAVFile, ReadOnlyResourceMixIn

from calendarserver.tools.util import (
    principalForPrincipalID, proxySubprincipal, action_addProxyPrincipal,
    action_removeProxyPrincipal
)



class WebAdminPage(Element):
    """
    Web administration renderer for HTML.

    @ivar resource: a L{WebAdminResource}.
    """

    loader = XMLFile(
        getModule(__name__).filePath.sibling("template.html")
    )

    def __init__(self, resource):
        super(WebAdminPage, self).__init__()
        self.resource = resource


    @renderer
    def main(self, request, tag):
        """
        Main renderer, which fills page-global slots like 'title'.
        """
        searchTerm = request.args.get('resourceSearch', [''])[0]
        return tag.fillSlots(resourceSearch=searchTerm)


    @renderer
    @inlineCallbacks
    def hasSearchResults(self, request, tag):
        """
        Renderer which detects if there are resource search results and
        continues if so.
        """
        if 'resourceSearch' not in request.args:
            returnValue('')
        if (yield self.performSearch(request)):
            returnValue(tag)
        else:
            returnValue('')


    @renderer
    @inlineCallbacks
    def noSearchResults(self, request, tag):
        """
        Renderer which detects if there are resource search results and
        continues if so.
        """
        if 'resourceSearch' not in request.args:
            returnValue('')
        rows = yield self.performSearch(request)
        if rows:
            returnValue("")
        else:
            returnValue(tag)

    _searchResults = None

    @inlineCallbacks
    def performSearch(self, request):
        """
        Perform a directory search for users, groups, and resources based on
        the resourceSearch query parameter.  Cache the results of that search
        so that it will only be done once per request.
        """
        if self._searchResults is not None:
            returnValue(self._searchResults)
        searchTerm = request.args.get('resourceSearch', [''])[0]
        if searchTerm:
            results = sorted((yield self.resource.search(searchTerm)),
                             key=lambda record: record.shortNames[0])
        else:
            results = []
        self._searchResults = results
        returnValue(results)


    @renderer
    def searchResults(self, request, tag):
        """
        Renderer which renders resource search results.
        """
        d = self.performSearch(request)
        return d.addCallback(searchToSlots, tag)


    @renderer
    def resourceDetails(self, request, tag):
        """
        Renderer which fills slots for details of the resource selected by
        the resourceId request parameter.
        """
        resourceId = request.args.get('resourceId', [''])[0]
        propertyName = request.args.get('davPropertyName', [''])[0]
        proxySearch = request.args.get('proxySearch', [''])[0]
        if resourceId:
            principalResource = self.resource.getResourceById(
                request, resourceId)
            return DetailsElement(
                resourceId, principalResource, propertyName, proxySearch, tag,
                self.resource
            )
        else:
            return ""



def searchToSlots(results, tag):
    """
    Convert the result of doing a search to an iterable of tags.
    """
    for idx, record in enumerate(results):
        yield tag.clone().fillSlots(
            rowClass="even" if (idx % 2 == 0) else "odd",
            type=record.recordType,
            shortName=record.shortNames[0],
            name=record.fullName,
            typeStr={
                "users": "User",
                "groups": "Group",
                "locations": "Place",
                "resources": "Resource",
            }.get(record.recordType, repr(record.recordType)),
            shortNames=str(", ".join(record.shortNames)),
            authIds=str(", ".join(record.authIDs)),
            emails=str(", ".join(record.emailAddresses)),
        )



class stan(object):
    """
    L{ITemplateLoader} wrapper for an existing tag, in the style of Nevow's
    'stan' loader.
    """
    implements(ITemplateLoader)

    def __init__(self, tag):
        self.tag = tag


    def load(self):
        return self.tag



class DetailsElement(Element):

    def __init__(self, resourceId, principalResource, davPropertyName,
                 proxySearch, tag, adminResource):
        self.principalResource = principalResource
        self.adminResource = adminResource
        self.proxySearch = proxySearch
        tag.fillSlots(resourceTitle=unicode(principalResource),
                      resourceId=resourceId,
                      davPropertyName=davPropertyName,
                      proxySearch=proxySearch)
        try:
            namespace, name = davPropertyName.split("#")
        except Exception:
            self.namespace = None
            self.name = None
            if davPropertyName:
                self.error = davPropertyName
            else:
                self.error = None
        else:
            self.namespace = namespace
            self.name = name
            self.error = None

        super(DetailsElement, self).__init__(loader=stan(tag))


    @renderer
    def propertyParseError(self, request, tag):
        """
        Renderer to display an error when the user specifies an invalid
        property name.
        """
        if self.error is None:
            return ""
        else:
            return tag.fillSlots(davPropertyName=self.error)


    @renderer
    @inlineCallbacks
    def davProperty(self, request, tag):
        """
        Renderer to display an error when the user specifies an invalid
        property name.
        """
        if self.name is not None:
            try:
                propval = yield self.principalResource.readProperty(
                    (self.namespace, self.name), request
                )
            except HTTPError:
                propval = "No such property: " + "#".join([self.namespace,
                                                           self.name])
            else:
                propval = propval.toxml()
            returnValue(tag.fillSlots(value=propval))
        else:
            returnValue("")


    @renderer
    def autoSchedule(self, request, tag):
        """
        Renderer which elides its tag for non-resource-type principals.
        """
        if (
            self.principalResource.record.recordType != "users" and
            self.principalResource.record.recordType != "groups" or
            self.principalResource.record.recordType == "users" and
            config.Scheduling.Options.AutoSchedule.AllowUsers
        ):
            return tag
        return ""


    @renderer
    def isAutoSchedule(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag if the resource
        is auto-schedule.
        """
        if self.principalResource.getAutoSchedule():
            tag(selected='selected')
        return tag


    @renderer
    def isntAutoSchedule(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag if the resource
        is not auto-schedule.
        """
        if not self.principalResource.getAutoSchedule():
            tag(selected='selected')
        return tag


    @renderer
    def autoScheduleModeDefault(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag based on the
        resource auto-schedule-mode.
        """
        if self.principalResource.getAutoScheduleMode() == "default":
            tag(selected='selected')
        return tag


    @renderer
    def autoScheduleModeNone(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag based on the
        resource auto-schedule-mode.
        """
        if self.principalResource.getAutoScheduleMode() == "none":
            tag(selected='selected')
        return tag


    @renderer
    def autoScheduleModeAcceptAlways(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag based on the
        resource auto-schedule-mode.
        """
        if self.principalResource.getAutoScheduleMode() == "accept-always":
            tag(selected='selected')
        return tag


    @renderer
    def autoScheduleModeDeclineAlways(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag based on the
        resource auto-schedule-mode.
        """
        if self.principalResource.getAutoScheduleMode() == "decline-always":
            tag(selected='selected')
        return tag


    @renderer
    def autoScheduleModeAcceptIfFree(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag based on the
        resource auto-schedule-mode.
        """
        if self.principalResource.getAutoScheduleMode() == "accept-if-free":
            tag(selected='selected')
        return tag


    @renderer
    def autoScheduleModeDeclineIfBusy(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag based on the
        resource auto-schedule-mode.
        """
        if self.principalResource.getAutoScheduleMode() == "decline-if-busy":
            tag(selected='selected')
        return tag


    @renderer
    def autoScheduleModeAutomatic(self, request, tag):
        """
        Renderer which sets the 'selected' attribute on its tag based on the
        resource auto-schedule-mode.
        """
        if (
            self.principalResource.getAutoScheduleMode() == "automatic" or
            not self.principalResource.getAutoScheduleMode()
        ):
            tag(selected='selected')
        return tag

    _matrix = None

    @inlineCallbacks
    def proxyMatrix(self, request):
        """
        Compute a matrix of proxies to display in a 2-column table.

        This value is cached so that multiple renderers may refer to it without
        causing additional back-end queries.

        @return: a L{Deferred} which fires with a list of 2-tuples of
            (readProxy, writeProxy).  If there is an unequal number of read and
            write proxies, the tables will be padded out with C{None}s so that
            some readProxy or writeProxy values will be C{None} at the end of
            the table.
        """
        if self._matrix is not None:
            returnValue(self._matrix)
        (readSubPrincipal, writeSubPrincipal) = (
            proxySubprincipal(self.principalResource, "read"),
            proxySubprincipal(self.principalResource, "write")
        )
        if readSubPrincipal or writeSubPrincipal:
            (readMembers, writeMembers) = (
                (yield readSubPrincipal.readProperty(davxml.GroupMemberSet,
                                                     None)),
                (yield writeSubPrincipal.readProperty(davxml.GroupMemberSet,
                                                      None))
            )
            if readMembers.children or writeMembers.children:
                # FIXME: 'else' case needs to be handled by separate renderer
                readProxies = []
                writeProxies = []

                def getres(ref):
                    return self.adminResource.getResourceById(request,
                                                              str(proxyHRef))
                for proxyHRef in sorted(readMembers.children, key=str):
                    readProxies.append((yield getres(proxyHRef)))
                for proxyHRef in sorted(writeMembers.children, key=str):
                    writeProxies.append((yield getres(proxyHRef)))
                lendiff = len(readProxies) - len(writeProxies)
                if lendiff > 0:
                    writeProxies += [None] * lendiff
                elif lendiff < 0:
                    readProxies += [None] * -lendiff
                self._matrix = zip(readProxies, writeProxies)
            else:
                self._matrix = []
        else:
            self._matrix = []
        returnValue(self._matrix)


    @renderer
    @inlineCallbacks
    def noProxies(self, request, tag):
        """
        Renderer which shows its tag if there are no proxies for this resource.
        """
        mtx = yield self.proxyMatrix(request)
        if mtx:
            returnValue("")
        returnValue(tag)


    @renderer
    @inlineCallbacks
    def hasProxies(self, request, tag):
        """
        Renderer which shows its tag if there are any proxies for this
        resource.
        """
        mtx = yield self.proxyMatrix(request)
        if mtx:
            returnValue(tag)
        returnValue("")


    @renderer
    @inlineCallbacks
    def noProxyResults(self, request, tag):
        """
        Renderer which shows its tag if there are no proxy search results for
        this request.
        """
        if not self.proxySearch:
            returnValue("")
        results = yield self.performProxySearch()
        if results:
            returnValue("")
        else:
            returnValue(tag)


    @renderer
    @inlineCallbacks
    def hasProxyResults(self, request, tag):
        """
        Renderer which shows its tag if there are any proxy search results for
        this request.
        """
        results = yield self.performProxySearch()
        if results:
            returnValue(tag)
        else:
            returnValue("")


    @renderer
    @inlineCallbacks
    def proxyRows(self, request, tag):
        """
        Renderer which does zipping logic to render read-only and read-write
        rows of existing proxies for the currently-viewed resource.
        """
        result = []
        mtx = yield self.proxyMatrix(request)
        for idx, (readProxy, writeProxy) in enumerate(mtx):
            result.append(ProxyRow(tag.clone(), idx, readProxy, writeProxy))
        returnValue(result)

    _proxySearchResults = None

    def performProxySearch(self):
        if self._proxySearchResults is not None:
            return succeed(self._proxySearchResults)

        if self.proxySearch:
            def nameSorted(records):
                records.sort(key=operator.attrgetter('fullName'))
                self._proxySearchResults = records
                return records
            return self.adminResource.search(
                self.proxySearch).addCallback(nameSorted)
        else:
            return succeed([])


    @renderer
    def proxySearchRows(self, request, tag):
        """
        Renderer which renders search results for the proxy form.
        """
        d = self.performProxySearch()
        return d.addCallback(searchToSlots, tag)



class ProxyRow(Element):

    def __init__(self, tag, index, readProxy, writeProxy):
        tag.fillSlots(rowClass="even" if (index % 2 == 0) else "odd")
        super(ProxyRow, self).__init__(loader=stan(tag))
        self.readProxy = readProxy
        self.writeProxy = writeProxy


    def proxies(self, proxyResource, tag):
        if proxyResource is None:
            return ''
        return tag.fillSlots(proxy=str(proxyResource),
                             type=proxyResource.record.recordType,
                             shortName=proxyResource.record.shortNames[0])


    def noProxies(self, proxyResource, tag):
        if proxyResource is None:
            return tag
        else:
            return ""


    @renderer
    def readOnlyProxies(self, request, tag):
        return self.proxies(self.readProxy, tag)


    @renderer
    def noReadOnlyProxies(self, request, tag):
        return self.noProxies(self.readProxy, tag)


    @renderer
    def readWriteProxies(self, request, tag):
        return self.proxies(self.writeProxy, tag)


    @renderer
    def noReadWriteProxies(self, request, tag):
        return self.noProxies(self.writeProxy, tag)



class WebAdminResource (ReadOnlyResourceMixIn, DAVFile):
    """
    Web administration HTTP resource.
    """

    def __init__(self, path, root, directory, store, principalCollections=()):
        self.root = root
        self.directory = directory
        self.store = store
        super(WebAdminResource, self).__init__(
            path, principalCollections=principalCollections
        )


    # Only allow administrators to access
    def defaultAccessControlList(self):
        return succeed(davxml.ACL(*config.AdminACEs))


    def etag(self):
        # Can't be calculated here
        return succeed(None)


    def contentLength(self):
        # Can't be calculated here
        return None


    def lastModified(self):
        return None


    def exists(self):
        return True


    def displayName(self):
        return "Web Admin"


    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8")


    def contentEncoding(self):
        return None


    def createSimilarFile(self, path):
        return DAVFile(path, principalCollections=self.principalCollections())


    @inlineCallbacks
    def resourceActions(self, request, principal):
        """
        Take all actions on the given principal based on the given request.
        """

        def queryValue(arg):
            return request.args.get(arg, [""])[0]

        def queryValues(arg):
            query = urlparse.parse_qs(urlparse.urlparse(request.uri).query,
                                      True)
            matches = []
            for key in query.keys():
                if key.startswith(arg):
                    matches.append(key[len(arg):])
            return matches

        autoSchedule = queryValue("autoSchedule")
        autoScheduleMode = queryValue("autoScheduleMode")
        makeReadProxies = queryValues("mkReadProxy|")
        makeWriteProxies = queryValues("mkWriteProxy|")
        removeProxies = queryValues("rmProxy|")

        # Update the auto-schedule value if specified.
        if autoSchedule is not None and (autoSchedule == "true" or
                                         autoSchedule == "false"):
            if (
                principal.record.recordType != "users" and
                principal.record.recordType != "groups" or
                principal.record.recordType == "users" and
                config.Scheduling.Options.AutoSchedule.AllowUsers
            ):
                yield principal.setAutoSchedule(autoSchedule == "true")
                yield principal.setAutoScheduleMode(autoScheduleMode)

        # Update the proxies if specified.
        for proxyId in removeProxies:
            proxy = self.getResourceById(request, proxyId)
            yield action_removeProxyPrincipal(
                self.root, self.directory, self.store,
                principal, proxy, proxyTypes=["read", "write"]
            )

        for proxyId in makeReadProxies:
            proxy = self.getResourceById(request, proxyId)
            yield action_addProxyPrincipal(
                self.root, self.directory, self.store, principal, "read", proxy
            )

        for proxyId in makeWriteProxies:
            proxy = self.getResourceById(request, proxyId)
            yield action_addProxyPrincipal(
                self.root, self.directory, self.store, principal,
                "write", proxy
            )



    @inlineCallbacks
    def render(self, request):
        """
        Create a L{WebAdminPage} to render HTML content for this request, and
        return a response.
        """
        resourceId = request.args.get('resourceId', [''])[0]
        if resourceId:
            principal = self.getResourceById(request, resourceId)
            yield self.resourceActions(request, principal)
        htmlContent = yield flattenString(request, WebAdminPage(self))
        response = Response()
        response.stream = MemoryStream(htmlContent)
        for (header, value) in (
            ("content-type", self.contentType()),
            ("content-encoding", self.contentEncoding()),
        ):
            if value is not None:
                response.headers.setHeader(header, value)
        returnValue(response)


    def getResourceById(self, request, resourceId):
        if resourceId.startswith("/"):
            return request.locateResource(resourceId)
        else:
            return principalForPrincipalID(
                resourceId, directory=self.directory
            )


    @inlineCallbacks
    def search(self, searchStr):
        records = list((
            yield self.directory.recordsMatchingTokens(
                searchStr.strip().split()
            )
        ))
        returnValue(records)




class PageElement(Element):
    """
    Page element.
    """

    def __init__(self, templateName):
        Element.__init__(self)

        self.loader = XMLFile(
            getModule(__name__).filePath.sibling(
                u"{name}.xhtml".format(name=templateName)
            )
        )


    def pageSlots(self):
        return {}


    @renderer
    def main(self, request, tag):
        """
        Main renderer, which fills page-global slots like 'title'.
        """
        tag.fillSlots(**self.pageSlots())
        return tag


    @renderer
    def stylesheet(self, request, tag):
        return tags.link(
            rel=u"stylesheet",
            media=u"screen",
            href=u"/style.css",
            type=u"text/css",
        )



class TemplateResource(Resource):
    """
    Resource that renders a template.
    """

    # @staticmethod
    # def queryValue(request, argument):
    #     for value in request.args.get(argument, []):
    #         return value

    #     return u""


    # @staticmethod
    # def queryValues(request, arguments):
    #     return request.args.get(arguments, [])


    def __init__(self, elementClass):
        Resource.__init__(self)

        self.elementClass = elementClass


    # def handleQueryArguments(self, request):
    #     return succeed(None)


    @inlineCallbacks
    def render(self, request):
        # yield self.handleQueryArguments(request)

        htmlContent = yield flattenString(request, self.elementClass())

        response = Response()
        response.stream = MemoryStream(htmlContent)
        response.headers.setHeader(
            b"content-type", MimeType.fromString(b"text/html; charset=utf-8")
        )

        returnValue(response)
