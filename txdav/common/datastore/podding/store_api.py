##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
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

from twisted.internet.defer import inlineCallbacks, returnValue

from txdav.caldav.datastore.scheduling.cuaddress import calendarUserFromCalendarUserAddress
from txdav.caldav.datastore.scheduling.freebusy import FreebusyQuery
from txdav.common.datastore.podding.util import UtilityConduitMixin
from txdav.common.datastore.sql_tables import _HOME_STATUS_DISABLED

from pycalendar.period import Period

from datetime import datetime


class StoreAPIConduitMixin(object):
    """
    Defines common cross-pod API for generic access to remote resources.
    """

    @inlineCallbacks
    def send_home_resource_id(self, txn, recipient, migrating=False):
        """
        Lookup the remote resourceID matching the specified directory uid.

        @param ownerUID: directory record for user whose home is needed
        @type ownerUID: L{DirectroryRecord}
        @param migrating: if L{True} then also return a disbaled home
        @type migrating: L{bool}
        """

        request = {
            "action": "home-resource_id",
            "ownerUID": recipient.uid,
            "migrating": migrating,
        }

        response = yield self.sendRequest(txn, recipient, request)
        returnValue(response)


    @inlineCallbacks
    def recv_home_resource_id(self, txn, request):
        """
        Process an addAttachment cross-pod request. Request arguments as per L{send_add_attachment}.

        @param request: request arguments
        @type request: C{dict}
        """

        home = yield txn.calendarHomeWithUID(request["ownerUID"])
        if home is None and request["migrating"]:
            home = yield txn.calendarHomeWithUID(request["ownerUID"], status=_HOME_STATUS_DISABLED)
        returnValue(home.id() if home is not None else None)


    @inlineCallbacks
    def send_freebusy(
        self,
        calresource,
        organizer,
        recipient,
        timerange,
        matchtotal,
        excludeuid,
        event_details,
    ):
        """
        Request free busy information for a shared calendar collection hosted on a different pod. See
        L{txdav.caldav.datastore.scheduling.freebusy} for the base free busy lookup behavior.
        """
        txn, request, server = yield self._getRequestForStoreObject("freebusy", calresource, False)

        request["organizer"] = organizer
        request["recipient"] = recipient
        request["timerange"] = timerange.getText()
        request["matchtotal"] = matchtotal
        request["excludeuid"] = excludeuid
        request["event_details"] = event_details

        response = yield self.sendRequestToServer(txn, server, request)
        returnValue((response["fbresults"], response["matchtotal"],))


    @inlineCallbacks
    def recv_freebusy(self, txn, request):
        """
        Process a freebusy cross-pod request. Message arguments as per L{send_freebusy}.

        @param request: request arguments
        @type request: C{dict}
        """

        # Operate on the L{CommonHomeChild}
        calresource, _ignore = yield self._getStoreObjectForRequest(txn, request)

        organizer = yield calendarUserFromCalendarUserAddress(request["organizer"], txn) if request["organizer"] else None
        recipient = yield calendarUserFromCalendarUserAddress(request["recipient"], txn) if request["recipient"] else None

        freebusy = FreebusyQuery(
            organizer=organizer,
            recipient=recipient,
            timerange=Period.parseText(request["timerange"]),
            excludeUID=request["excludeuid"],
            event_details=request["event_details"],
        )
        fbinfo = FreebusyQuery.FBInfo([], [], [])
        matchtotal = yield freebusy.generateFreeBusyInfo(
            [calresource, ],
            fbinfo,
            matchtotal=request["matchtotal"],
        )

        # Convert L{Period} objects to text for JSON response
        returnValue({
            "fbresults": [
                [item.getText() for item in fbinfo.busy],
                [item.getText() for item in fbinfo.tentative],
                [item.getText() for item in fbinfo.unavailable],
            ],
            "matchtotal": matchtotal,
        })


    @inlineCallbacks
    def send_migrated_home(self, txn, ownerUID):
        """
        Tell another pod that user data migration is done.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param server: server to query
        @type server: L{Server}
        @param ownerUID: directory UID of the user whose data has been migrated
        @type ownerUID: L{str}
        """

        recipient = yield self.store.directoryService().recordWithUID(ownerUID)
        request = {
            "action": "migrated-home",
            "ownerUID": ownerUID,
        }
        yield self.sendRequestToServer(txn, recipient.server(), request)


    @inlineCallbacks
    def recv_migrated_home(self, txn, request):
        """
        Process a migrated homes cross-pod request. Request arguments as per L{send_migrated_home}.

        @param request: request arguments
        @type request: C{dict}
        """

        yield txn.migratedHome(request["ownerUID"])


    @staticmethod
    def _to_serialize_pair_list(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        return [[a.serialize(), b.serialize(), ] for a, b in value]


    @staticmethod
    def _to_serialize_dict_value(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        return dict([(k, v.serialize(),) for k, v in value.items()])


    @staticmethod
    def _to_serialize_dict_list_serialized_value(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        return dict([(k, UtilityConduitMixin._to_serialize_list(v),) for k, v in value.items()])


    @staticmethod
    def _to_serialize_search_value(value):
        """
        Convert the value to the external (JSON-based) representation.
        """
        def _convert(item):
            return map(lambda x: x.isoformat(" ") if isinstance(x, datetime) else x, item)
        return map(_convert, value)

# These are the actions on store objects we need to expose via the conduit api

# Calls on L{CommonHome} objects
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_metadata", "serialize")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_set_status", "setStatus")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_get_all_group_attendees", "getAllGroupAttendees", transform_recv_result=StoreAPIConduitMixin._to_serialize_pair_list)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_shared_to_records", "sharedToBindRecords", transform_recv_result=StoreAPIConduitMixin._to_serialize_dict_list_serialized_value)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_imip_tokens", "iMIPTokens", transform_recv_result=UtilityConduitMixin._to_serialize_list)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_pause_work", "pauseWork")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_unpause_work", "unpauseWork")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "home_work_items", "workItems")

# Calls on L{CommonHomeChild} objects
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_listobjects", "listObjects", classMethod=True)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_loadallobjects", "loadAllObjects", classMethod=True, transform_recv_result=UtilityConduitMixin._to_serialize_list)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_objectwith", "objectWith", classMethod=True, transform_recv_result=UtilityConduitMixin._to_serialize)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_movehere", "moveObjectResourceHere")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_moveaway", "moveObjectResourceAway")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_synctokenrevision", "syncTokenRevision")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_resourcenamessincerevision", "resourceNamesSinceRevision", transform_send_result=UtilityConduitMixin._to_tuple)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_search", "search", transform_recv_result=StoreAPIConduitMixin._to_serialize_search_value)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_sharing_records", "sharingBindRecords", transform_recv_result=StoreAPIConduitMixin._to_serialize_dict_value)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_migrate_sharing_records", "migrateBindRecords")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "homechild_group_sharees", "groupSharees", transform_recv_result=StoreAPIConduitMixin._to_serialize_dict_list_serialized_value)

# Calls on L{CommonObjectResource} objects
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_loadallobjects", "loadAllObjects", classMethod=True, transform_recv_result=UtilityConduitMixin._to_serialize_list)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_loadallobjectswithnames", "loadAllObjectsWithNames", classMethod=True, transform_recv_result=UtilityConduitMixin._to_serialize_list)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_listobjects", "listObjects", classMethod=True)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_countobjects", "countObjects", classMethod=True)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_objectwith", "objectWith", classMethod=True, transform_recv_result=UtilityConduitMixin._to_serialize)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_resourcenameforuid", "resourceNameForUID", classMethod=True)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_resourceuidforname", "resourceUIDForName", classMethod=True)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_create", "create", classMethod=True, transform_recv_result=UtilityConduitMixin._to_serialize)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_setcomponent", "setComponent")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_component", "component", transform_recv_result=UtilityConduitMixin._to_string)
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "objectresource_remove", "remove")

# Calls on L{NotificationCollection} objects
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "notification_set_status", "setStatus")
UtilityConduitMixin._make_simple_action(StoreAPIConduitMixin, "notification_all_records", "notificationObjectRecords", transform_recv_result=UtilityConduitMixin._to_serialize_list)
