# -*- test-case-name: twext.enterprise.dal.test.test_record -*-
##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.record import SerializableRecord, fromTable
from twext.enterprise.dal.syntax import utcNowSQL
from twext.python.log import Logger
from twisted.internet.defer import inlineCallbacks, returnValue
from txdav.common.datastore.sql_tables import schema
from txdav.common.icommondatastore import InvalidIMIPTokenValues
from uuid import uuid4

log = Logger()

"""
Classes and methods that relate to iMIP objects in the SQL store.
"""

class iMIPTokensRecord(SerializableRecord, fromTable(schema.IMIP_TOKENS)):
    """
    @DynamicAttrs
    L{Record} for L{schema.IMIP_TOKENS}.
    """
    pass



class imipAPIMixin(object):
    """
    A mixin for L{CommonStoreTransaction} that covers the iMIP API.
    """

    # Create IMIP token
    @inlineCallbacks
    def imipCreateToken(self, organizer, attendee, icaluid, token=None):
        if not (organizer and attendee and icaluid):
            raise InvalidIMIPTokenValues()

        if token is None:
            token = str(uuid4())

        try:
            record = yield iMIPTokensRecord.create(
                self,
                token=token,
                organizer=organizer,
                attendee=attendee,
                icaluid=icaluid
            )
        except Exception:
            # TODO: is it okay if someone else created the same row just now?
            record = yield self.imipGetToken(organizer, attendee, icaluid)
        returnValue(record)


    # Lookup IMIP organizer+attendee+icaluid for token
    def imipLookupByToken(self, token):
        return iMIPTokensRecord.querysimple(self, token=token)


    # Lookup IMIP token for organizer+attendee+icaluid
    @inlineCallbacks
    def imipGetToken(self, organizer, attendee, icaluid):
        records = yield iMIPTokensRecord.querysimple(
            self,
            organizer=organizer,
            attendee=attendee,
            icaluid=icaluid,
        )
        if records:
            # update the timestamp
            record = records[0]
            yield record.update(accessed=utcNowSQL)
        else:
            record = None
        returnValue(record)


    # Remove IMIP token
    def imipRemoveToken(self, token):
        return iMIPTokensRecord.deletesimple(self, token=token)


    # Purge old IMIP tokens
    def purgeOldIMIPTokens(self, olderThan):
        """
        @type olderThan: datetime
        """
        return iMIPTokensRecord.delete(self, iMIPTokensRecord.accessed < olderThan)
