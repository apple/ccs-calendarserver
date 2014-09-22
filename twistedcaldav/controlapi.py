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

"""
Control API resource.

This provides an HTTP API to allow an admin to trigger various "internal" actions on the server.
The intent of this is to primarily support automated testing tools that may need to alter
server behavior during tests via an HTTP-only API.
"""

__all__ = [
    "ControlAPIResource",
]

from calendarserver.tools.util import recordForPrincipalID

from twext.enterprise.jobqueue import JobItem
from twext.python.log import Logger

from twisted.internet import reactor
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twistedcaldav.config import config
from twistedcaldav.extensions import DAVResource, \
    DAVResourceWithoutChildrenMixin
from twistedcaldav.resource import ReadOnlyNoCopyResourceMixIn

from txdav.who.groups import GroupCacherPollingWork, GroupRefreshWork, \
    GroupAttendeeReconciliationWork, GroupDelegateChangesWork, \
    GroupShareeReconciliationWork
from txdav.xml import element as davxml

from txweb2 import responsecode
from txweb2.dav.method.propfind import http_PROPFIND
from txweb2.dav.noneprops import NonePropertyStore
from txweb2.dav.util import allDataFromStream
from txweb2.http import HTTPError, JSONResponse, StatusResponse
from txweb2.http import Response
from txweb2.http_headers import MimeType

import json

log = Logger()

class ControlAPIResource (ReadOnlyNoCopyResourceMixIn, DAVResourceWithoutChildrenMixin, DAVResource):
    """
    Resource used to execute admin commands.

    Extends L{DAVResource} to provide service functionality.
    """

    def __init__(self, root, directory, store, principalCollections=()):
        """
        @param parent: the parent resource of this one.
        """

        DAVResource.__init__(self, principalCollections=principalCollections)

        self.parent = root
        self._store = store
        self._directory = directory


    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = NonePropertyStore(self)
        return self._dead_properties


    def etag(self):
        return succeed(None)


    def checkPreconditions(self, request):
        return None


    def defaultAccessControlList(self):
        return succeed(davxml.ACL(*config.AdminACEs))


    def contentType(self):
        return MimeType.fromString("text/html; charset=utf-8")


    def resourceType(self):
        return None


    def isCollection(self):
        return False


    def isCalendarCollection(self):
        return False


    def isPseudoCalendarCollection(self):
        return False


    def render(self, request):
        output = """<html>
<head>
<title>Control API Resource</title>
</head>
<body>
<h1>Control API Resource.</h1>
</body
</html>"""

        response = Response(200, {}, output)
        response.headers.setHeader("content-type", MimeType("text", "html"))
        return response

    http_PROPFIND = http_PROPFIND

    def http_GET(self, request):
        """
        GET just returns HTML description.
        """
        return self.render(request)


    def _ok(self, status, description, result=None):
        if result is None:
            result = {}
        result["status"] = status
        result["description"] = description
        return JSONResponse(
            responsecode.OK,
            result,
        )


    def _error(self, status, description):
        raise HTTPError(JSONResponse(
            responsecode.BAD_REQUEST,
            {
                "status": status,
                "description": description,
            },
        ))


    def _recordsToJSON(self, records):
        results = []
        for record in sorted(records, key=lambda r: r.uid):
            try:
                shortNames = record.shortNames
            except AttributeError:
                shortNames = []
            results.append(
                {
                    "type": record.recordType.name,
                    "cn": record.displayName,
                    "uid": record.uid,
                    "sn": shortNames
                }
            )
        return results


    @inlineCallbacks
    def http_POST(self, request):
        """
        POST method with JSON body is used for control.
        """

        #
        # Check authentication and access controls
        #
        yield self.authorize(request, (davxml.Read(),))

        contentType = request.headers.getHeader("content-type")
        # Check content first
        if "{}/{}".format(contentType.mediaType, contentType.mediaSubtype) != "application/json":
            self.log.error("MIME type {mime} not allowed in request", mime=contentType)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "MIME type {} not allowed in request".format(contentType)))

        body = (yield allDataFromStream(request.stream))
        try:
            j = json.loads(body)
        except (ValueError, TypeError) as e:
            self.log.error("Invalid JSON data in request: {ex}\n{body}", ex=e, body=body)
            raise HTTPError(StatusResponse(responsecode.BAD_REQUEST, "Invalid JSON data in request: {}\n{}".format(e, body)))

        try:
            action = j["action"]
        except KeyError:
            self._error("error", "No 'action' member in root JSON object.")

        method = "action_{}".format(action)
        if not hasattr(self, method):
            self._error("error", "The action '{}' is not supported.".format(action))

        result = yield getattr(self, method)(j)
        returnValue(result)


    @inlineCallbacks
    def action_listgroupmembers(self, j):
        try:
            grpID = j["group"]
        except KeyError:
            self._error("error", "No 'group' member in root JSON object.")

        try:
            record = yield recordForPrincipalID(self._directory, grpID)
        except ValueError:
            record = None
        if record is None:
            self._error("error", "No group with id '{}' in the directory.".format(grpID))

        members = yield record.members()

        returnValue(self._ok("ok", "Group membership", {
            "group": grpID,
            "members": self._recordsToJSON(members),
        }))


    @inlineCallbacks
    def action_addgroupmembers(self, j):
        try:
            grpID = j["group"]
        except KeyError:
            self._error("error", "No 'group' member in root JSON object.")
        try:
            memberIDs = j["members"]
        except KeyError:
            self._error("error", "No 'members' member in root JSON object.")

        try:
            record = yield recordForPrincipalID(self._directory, grpID)
        except ValueError:
            record = None
        if record is None:
            self._error("error", "No group with id '{}' in the directory.".format(grpID))

        existingMembers = yield record.members()
        existingMemberUIDs = set([member.uid for member in existingMembers])
        add = set()
        invalid = set()
        exists = set()
        for memberID in memberIDs:
            memberRecord = yield recordForPrincipalID(self._directory, memberID)
            if memberRecord is None:
                invalid.add(memberID)
            elif memberRecord.uid in existingMemberUIDs:
                exists.add(memberRecord)
            else:
                add.add(memberRecord)

        if add:
            yield record.addMembers(add)
            yield record.service.updateRecords([record], create=False)

        returnValue(self._ok("ok", "Added group members", {
            "group": grpID,
            "added": self._recordsToJSON(add),
            "exists": self._recordsToJSON(exists),
            "invalid": sorted(invalid),
        }))


    @inlineCallbacks
    def action_removegroupmembers(self, j):
        try:
            grpID = j["group"]
        except KeyError:
            self._error("error", "No 'group' member in root JSON object.")
        try:
            memberIDs = j["members"]
        except KeyError:
            self._error("error", "No 'members' member in root JSON object.")

        try:
            record = yield recordForPrincipalID(self._directory, grpID)
        except ValueError:
            record = None
        if record is None:
            self._error("error", "No group with id '{}' in the directory.".format(grpID))

        existingMembers = yield record.members()
        existingMemberUIDs = set([member.uid for member in existingMembers])
        remove = set()
        invalid = set()
        missing = set()
        for memberID in memberIDs:
            memberRecord = yield recordForPrincipalID(self._directory, memberID)
            if memberRecord is None:
                invalid.add(memberID)
            elif memberRecord.uid not in existingMemberUIDs:
                missing.add(memberRecord)
            else:
                remove.add(memberRecord)

        if remove:
            record.removeMembers(remove)
            yield record.service.updateRecords([record], create=False)

        returnValue(self._ok("ok", "Removed group members", {
            "group": grpID,
            "removed": self._recordsToJSON(remove),
            "missing": self._recordsToJSON(missing),
            "invalid": sorted(invalid),
        }))


    @inlineCallbacks
    def action_refreshgroups(self, j):
        txn = self._store.newTransaction()
        wp = yield GroupCacherPollingWork.reschedule(txn, 0, force=True)
        jobID = wp.workItem.jobID
        yield txn.commit()

        if "wait" in j and j["wait"]:
            yield JobItem.waitJobDone(self._store.newTransaction, reactor, 60.0, jobID)
            yield JobItem.waitWorkDone(self._store.newTransaction, reactor, 60.0, (
                GroupRefreshWork, GroupAttendeeReconciliationWork, GroupDelegateChangesWork, GroupShareeReconciliationWork,
            ))

        returnValue(self._ok("ok", "Group refresh scheduled"))
