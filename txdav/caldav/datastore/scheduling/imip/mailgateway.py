##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
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
SQLite implementation of mail token database (deprecated).  This only exists
now in order to migrate tokens from sqlite to the new store.
"""

import datetime
import os
import uuid

from twext.python.log import Logger
from twistedcaldav.sql import AbstractSQLDatabase
from twisted.internet.defer import inlineCallbacks

log = Logger()


class MailGatewayTokensDatabase(AbstractSQLDatabase):
    """
    A database to maintain "plus-address" tokens for IMIP requests.

    SCHEMA:

    Token Database:

    ROW: TOKEN, ORGANIZER, ATTENDEE, ICALUID, DATESTAMP
    """
    log = Logger()

    dbType = "MAILGATEWAYTOKENS"
    dbFilename = "mailgatewaytokens.sqlite"
    dbFormatVersion = "1"


    def __init__(self, path):
        if path != ":memory:":
            path = os.path.join(path, MailGatewayTokensDatabase.dbFilename)
        super(MailGatewayTokensDatabase, self).__init__(path, True)


    def createToken(self, organizer, attendee, icaluid, token=None):
        if token is None:
            token = str(uuid.uuid4())
        self._db_execute(
            """
            insert into TOKENS (TOKEN, ORGANIZER, ATTENDEE, ICALUID, DATESTAMP)
            values (:1, :2, :3, :4, :5)
            """, token, organizer, attendee, icaluid, datetime.date.today()
        )
        self._db_commit()
        return token


    def lookupByToken(self, token):
        results = list(
            self._db_execute(
                """
                select ORGANIZER, ATTENDEE, ICALUID from TOKENS
                where TOKEN = :1
                """, token
            )
        )

        if len(results) != 1:
            return None

        return results[0]


    def getToken(self, organizer, attendee, icaluid):
        token = self._db_value_for_sql(
            """
            select TOKEN from TOKENS
            where ORGANIZER = :1 and ATTENDEE = :2 and ICALUID = :3
            """, organizer, attendee, icaluid
        )
        if token is not None:
            # update the datestamp on the token to keep it from being purged
            self._db_execute(
                """
                update TOKENS set DATESTAMP = :1 WHERE TOKEN = :2
                """, datetime.date.today(), token
            )
            return str(token)
        else:
            return None


    def getAllTokens(self):
        results = list(
            self._db_execute(
                """
                select TOKEN, ORGANIZER, ATTENDEE, ICALUID from TOKENS
                """
            )
        )
        return results


    def deleteToken(self, token):
        self._db_execute(
            """
            delete from TOKENS where TOKEN = :1
            """, token
        )
        self._db_commit()


    def purgeOldTokens(self, before):
        self._db_execute(
            """
            delete from TOKENS where DATESTAMP < :1
            """, before
        )
        self._db_commit()


    def lowercase(self):
        """
        Lowercase mailto: addresses (and uppercase urn:uuid: addresses!) so
        they can be located via normalized names.
        """
        rows = self._db_execute(
            """
            select ORGANIZER, ATTENDEE from TOKENS
            """
        )
        for row in rows:
            organizer = row[0]
            attendee = row[1]
            if organizer.lower().startswith("mailto:"):
                self._db_execute(
                    """
                    update TOKENS set ORGANIZER = :1 WHERE ORGANIZER = :2
                    """, organizer.lower(), organizer
                )
            else:
                from txdav.base.datastore.util import normalizeUUIDOrNot
                self._db_execute(
                    """
                    update TOKENS set ORGANIZER = :1 WHERE ORGANIZER = :2
                    """, normalizeUUIDOrNot(organizer), organizer
                )
            # ATTENDEEs are always mailto: so unconditionally lower().
            self._db_execute(
                """
                update TOKENS set ATTENDEE = :1 WHERE ATTENDEE = :2
                """, attendee.lower(), attendee
            )
        self._db_commit()


    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return MailGatewayTokensDatabase.dbFormatVersion


    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return MailGatewayTokensDatabase.dbType


    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """

        #
        # TOKENS table
        #
        q.execute(
            """
            create table TOKENS (
                TOKEN       text,
                ORGANIZER   text,
                ATTENDEE    text,
                ICALUID     text,
                DATESTAMP   date
            )
            """
        )
        q.execute(
            """
            create index TOKENSINDEX on TOKENS (TOKEN)
            """
        )


    def _db_upgrade_data_tables(self, q, old_version):
        """
        Upgrade the data from an older version of the DB.
        @param q: a database cursor to use.
        @param old_version: existing DB's version number
        @type old_version: str
        """
        pass



@inlineCallbacks
def migrateTokensToStore(path, store):
    """
    Copy all the tokens from the sqlite db into the new store.

    @param path: Filesystem path to directory containing the sqlite db file.
    @type path: C{str}

    @param store: The store to copy tokens into
    @type store: L{CommonDataStore}
    """
    oldDB = MailGatewayTokensDatabase(path)
    txn = store.newTransaction()
    for token, organizer, attendee, icaluid in oldDB.getAllTokens():
        yield txn.imipCreateToken(organizer, attendee, icaluid, token=token)
    yield txn.commit()
    os.remove(oldDB.dbpath)
