##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##

from twistedcaldav.sql import AbstractSQLDatabase

from twisted.web2.auth.digest import DigestCredentialFactory, IDigestCredentialsDatabase

from zope.interface.declarations import implements

import cPickle as pickle
import os

"""
Overrides twisted.web2.auth.digest to allow specifying a qop value as a configuration parameter.
Also adds an sqlite-based credentials cache that is multi-process safe.

"""

class DigestCredentialsDB(AbstractSQLDatabase):

    implements(IDigestCredentialsDatabase)

    """
    A database to maintain cached digest credentials.

    SCHEMA:
    
    Database: DIGESTCREDENTIALS
    
    ROW: KEY, VALUE
    
    """
    
    dbType = "DIGESTCREDENTIALSCACHE"
    dbFilename = ".db.digestcredentialscache"
    dbFormatVersion = "1"

    def __init__(self, path):
        db_path = os.path.join(path, DigestCredentialsDB.dbFilename)
        if os.path.exists(db_path):
            os.remove(db_path)
        super(DigestCredentialsDB, self).__init__(db_path, DigestCredentialsDB.dbFormatVersion)
        self.db = {}
    
    def has_key(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        for ignore_key in self._db_execute(
            "select KEY from DIGESTCREDENTIALS where KEY = :1",
            key
        ):
            return True
        else:
            return False

    def set(self, key, value):
        """
        See IDigestCredentialsDatabase.
        """
        self._delete_from_db(key)
        pvalue = pickle.dumps(value)
        self._add_to_db(key, pvalue)
        self._db_commit()

    def get(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        for pvalue in self._db_execute(
            "select VALUE from DIGESTCREDENTIALS where KEY = :1",
            key
        ):
            return pickle.loads(str(pvalue[0]))
        else:
            return None

    def delete(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        self._delete_from_db(key)
        self._db_commit()

    def keys(self):
        """
        See IDigestCredentialsDatabase.
        """
        result = []
        for key in self._db_execute("select KEY from DIGESTCREDENTIALS"):
            result.append(str(key[0]))
        
        return result

    def _add_to_db(self, key, value):
        """
        Insert the specified entry into the database.

        @param key:   the key to add.
        @param value: the value to add.
        """
        self._db_execute(
            """
            insert into DIGESTCREDENTIALS (KEY, VALUE)
            values (:1, :2)
            """, key, value
        )
       
    def _delete_from_db(self, key):
        """
        Deletes the specified entry from the database.

        @param key: the key to remove.
        """
        self._db_execute("delete from DIGESTCREDENTIALS where KEY = :1", key)
    
    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return DigestCredentialsDB.dbType
        
    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
        @param q:           a database cursor to use.
        """

        #
        # DIGESTCREDENTIALS table
        #
        q.execute(
            """
            create table DIGESTCREDENTIALS (
                KEY         text,
                VALUE       text
            )
            """
        )

class QopDigestCredentialFactory(DigestCredentialFactory):
    """
    See twisted.web2.auth.digest.DigestCredentialFactory
    """

    def __init__(self, algorithm, qop, realm, db_path):
        """
        @type algorithm: C{str}
        @param algorithm: case insensitive string that specifies
            the hash algorithm used, should be either, md5, md5-sess
            or sha

        @type qop: C{str}
        @param qop: case insensitive string that specifies
            the qop to use


        @type realm: C{str}
        @param realm: case sensitive string that specifies the realm
            portion of the challenge

        @type db_path: C{str}
        @param db_path: path where the credentials cache is to be stored
        """
        super(QopDigestCredentialFactory, self).__init__(algorithm, realm, mapper=DigestCredentialsDB, mapperargs=[db_path])
        self.qop = qop

    def getChallenge(self, peer):
        """
        Do the default behavior but then strip out any 'qop' from the challenge fields
        if no qop was specified.
        """

        challenge = super(QopDigestCredentialFactory, self).getChallenge(peer)
        if self.qop:
            challenge['qop'] = self.qop
        else:
            del challenge['qop']
        return challenge
            

    def decode(self, response, request):
        """
        Do the default behavior but then strip out any 'qop' from the credential fields
        if no qop was specified.
        """

        credentials = super(QopDigestCredentialFactory, self).decode(response, request)
        if not self.qop and credentials.fields.has_key('qop'):
            del credentials.fields['qop']
        return credentials
