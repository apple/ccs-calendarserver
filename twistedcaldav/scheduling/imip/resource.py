##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav.noneprops import NonePropertyStore
from twext.web2.http import Response, HTTPError
from twext.web2.http_headers import MimeType
from twisted.internet.defer import succeed, inlineCallbacks, returnValue
from twistedcaldav import caldavxml
from twistedcaldav.config import config
from twistedcaldav.directory.util import transactionFromRequest
from twistedcaldav.ical import Component
from twistedcaldav.resource import CalDAVResource
from twistedcaldav.scheduling.caldav.resource import deliverSchedulePrivilegeSet
from twistedcaldav.scheduling.imip.scheduler import IMIPScheduler
from txdav.xml import element as davxml

__all__ = [
    "IMIPInboxResource",
    "IMIPReplyInboxResource",
    "IMIPInvitationInboxResource",
]

log = Logger()

class IMIPInboxResource(CalDAVResource):
    """
    IMIP-delivery Inbox resource.

    Extends L{DAVResource} to provide IMIP delivery functionality.
    """

    def __init__(self, parent, store):
        """
        @param parent: the parent resource of this one.
        @param store: the store to use for transactions.
        """
        assert parent is not None

        CalDAVResource.__init__(
            self, principalCollections=parent.principalCollections()
        )

        self.parent = parent
        self._newStore = store


    def accessControlList(self, request, inheritance=True,
        expanding=False, inherited_aces=None):

        if not hasattr(self, "iMIPACL"):
            guid = config.Scheduling.iMIP.GUID
            self.iMIPACL = davxml.ACL(
                davxml.ACE(
                    davxml.Principal(
                        davxml.HRef.fromString("/principals/__uids__/%s/"
                                               % (guid,))
                    ),
                    davxml.Grant(
                        davxml.Privilege(caldavxml.ScheduleDeliver()),
                    ),
                ),
            )

        return succeed(self.iMIPACL)


    def resourceType(self):
        return davxml.ResourceType.ischeduleinbox


    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8")


    def isCollection(self):
        return False


    def isCalendarCollection(self):
        return False


    def isPseudoCalendarCollection(self):
        return False


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(None)


    def checkPreconditions(self, request):
        return None


    def render(self, request):
        output = """<html>
<head>
<title>IMIP Delivery Resource</title>
</head>
<body>
<h1>IMIP Delivery Resource.</h1>
</body
</html>"""

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response

    ##
    # File
    ##


    def createSimilarFile(self, path):
        log.err("Attempt to create clone %r of resource %r" % (path, self))
        raise HTTPError(responsecode.NOT_FOUND)

    ##
    # ACL
    ##


    def defaultAccessControlList(self):
        privs = (
            davxml.Privilege(davxml.Read()),
            davxml.Privilege(caldavxml.ScheduleDeliver()),
        )
        if config.Scheduling.CalDAV.OldDraftCompatibility:
            privs += (davxml.Privilege(caldavxml.Schedule()),)
        return davxml.ACL(
            # DAV:Read, CalDAV:schedule-deliver for all principals (includes
            # anonymous)
            davxml.ACE(
                davxml.Principal(davxml.All()),
                davxml.Grant(*privs),
                davxml.Protected(),
            ),
        )


    def supportedPrivileges(self, request):
        return succeed(deliverSchedulePrivilegeSet)



class IMIPReplyInboxResource(IMIPInboxResource):

    def renderHTTP(self, request):
        """
        Set up a transaction which will be used and committed by implicit
        scheduling.
        """
        self.transaction = transactionFromRequest(request, self._newStore)
        return super(IMIPReplyInboxResource, self).renderHTTP(request, self.transaction)


    @inlineCallbacks
    def http_POST(self, request):
        """
        The IMIP reply POST method (inbound)
        """

        # Check authentication and access controls
        yield self.authorize(request, (caldavxml.ScheduleDeliver(),))

        # Inject using the IMIPScheduler.
        scheduler = IMIPScheduler(request, self)

        # Do the POST processing treating this as a non-local schedule
        result = (yield scheduler.doSchedulingViaPOST(self.transaction, use_request_headers=True))
        returnValue(result.response())



class IMIPInvitationInboxResource(IMIPInboxResource):

    def __init__(self, parent, store, mailer):
        super(IMIPInvitationInboxResource, self).__init__(parent, store)
        self.mailer = mailer


    @inlineCallbacks
    def http_POST(self, request):
        """
        The IMIP invitation POST method (outbound)
        """

        # Check authentication and access controls
        yield self.authorize(request, (caldavxml.ScheduleDeliver(),))

        # Compute token, add to db, generate email and send it
        calendar = (yield Component.fromIStream(request.stream))
        originator = request.headers.getRawHeaders("originator")[0]
        recipient = request.headers.getRawHeaders("recipient")[0]
        language = config.Localization.Language

        if not (yield self.mailer.outbound(originator,
            recipient, calendar, language=language)):
            returnValue(Response(code=responsecode.BAD_REQUEST))

        returnValue(Response(code=responsecode.OK))
