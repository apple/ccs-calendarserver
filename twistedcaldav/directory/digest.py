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
##

from twistedcaldav.sql import AbstractSQLDatabase

from twisted.cred import error
from twisted.web2.auth.digest import DigestCredentialFactory
from twisted.web2.auth.digest import DigestedCredentials

from zope.interface import implements, Interface

import cPickle as pickle
from twisted.web2.http_headers import tokenize
from twisted.web2.http_headers import Token
from twisted.web2.http_headers import split
from twisted.web2.http_headers import parseKeyValue
import os
import time

try:
    from sqlite3 import OperationalError
except ImportError:
    from pysqlite2.dbapi2 import OperationalError

from twistedcaldav.log import Logger

log = Logger()

"""
Overrides twisted.web2.auth.digest to allow specifying a qop value as a configuration parameter.
Also adds an sqlite-based credentials cache that is multi-process safe.

"""

class IDigestCredentialsDatabase(Interface):
    """
    An interface to a digest credentials database that is used to hold per-client digest credentials so that fast
    re-authentication can be done with replay attacks etc prevented.
    """
    
    def has_key(self, key):
        """
        See whether the matching key exists.

        @param key:    the key to check.
        @type key:     C{str}.
        
        @return:       C{True} if the key exists, C{False} otherwise.
        """
        pass

    def set(self, key, value):
        """
        Store per-client credential information the first time a nonce is generated and used.

        @param key:        the key for the data to store.
        @type key:         C{str}
        @param value:      the data to store.
        @type value:       any.
        """
        pass
    
    def get(self, key):
        """
        Validate client supplied credentials by comparing with the cached values. If valid, store the new
        cnonce value in the database so that it can be used on the next validate.

        @param key:    the key to check.
        @type key:     C{str}.

        @return:       the value for the corresponding key, or C{None} if the key is not found.
        """
        pass
    
    def delete(self, key):
        """
        Remove the record associated with the supplied key.

        @param key:        the key to remove.
        @type key:         C{str}
        """
        pass

    def deleteMany(self, keys):
        """
        Remove the records associated with the supplied keys.

        @param key:        the key to remove.
        @type key:         C{str}
        """
        pass

    def keys(self):
        """
        Return all the keys currently available.
        
        @return:    a C{list} of C{str} for each key currently in the database.
        """
        pass
    
    def items(self):
        """
        Return all the key/value pairs currently available.
        
        @return:    a C{list} of C{tuple} for each key/value currently in the database.
        """
        pass
    
class DigestCredentialsMap(object):

    implements(IDigestCredentialsDatabase)

    def __init__(self, *args):
        self.db = {}
    
    def has_key(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        return self.db.has_key(key)

    def set(self, key, value):
        """
        See IDigestCredentialsDatabase.
        """
        self.db[key] = value

    def get(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        if self.db.has_key(key):
            return self.db[key]
        else:
            return None

    def delete(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        if self.db.has_key(key):
            del self.db[key]

    def deleteMany(self, keys):
        """
        See IDigestCredentialsDatabase.
        """
        for key in keys:
            if self.db.has_key(key):
                del self.db[key]

    def keys(self):
        """
        See IDigestCredentialsDatabase.
        """
        return self.db.keys()

    def items(self):
        """
        See IDigestCredentialsDatabase.
        """
        return self.db.items()

class DigestCredentialsDB(AbstractSQLDatabase):

    implements(IDigestCredentialsDatabase)

    """
    A database to maintain cached digest credentials.

    SCHEMA:
    
    Database: DIGESTCREDENTIALS
    
    ROW: KEY, VALUE
    
    """
    
    dbType = "DIGESTCREDENTIALSCACHE"
    dbFilename = "digest.sqlite"
    dbFormatVersion = "2"

    exceptionLimit = 10

    def __init__(self, path):
        db_path = os.path.join(path, DigestCredentialsDB.dbFilename)
        super(DigestCredentialsDB, self).__init__(db_path, False, autocommit=False)
        self.exceptions = 0
    
    def has_key(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        try:
            for ignore_key in self._db_execute(
                "select KEY from DIGESTCREDENTIALS where KEY = :1",
                key
            ):
                return True
            else:
                return False
            self.exceptions = 0
        except OperationalError, e:
            self.exceptions += 1
            if self.exceptions >= self.exceptionLimit:
                self._db_close()
                log.err("Reset digest credentials database connection: %s" % (e,))
            raise

    def set(self, key, value):
        """
        See IDigestCredentialsDatabase.
        """
        try:
            pvalue = pickle.dumps(value)
            self._set_in_db(key, pvalue)
            self._db_commit()
            self.exceptions = 0
        except OperationalError, e:
            self._db_rollback()
            self.exceptions += 1
            if self.exceptions >= self.exceptionLimit:
                self._db_close()
                log.err("Reset digest credentials database connection: %s" % (e,))
            raise

    def get(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        try:
            for pvalue in self._db_execute(
                "select VALUE from DIGESTCREDENTIALS where KEY = :1",
                key
            ):
                self.exceptions = 0
                return pickle.loads(str(pvalue[0]))
            else:
                self.exceptions = 0
                return None
        except OperationalError, e:
            self.exceptions += 1
            if self.exceptions >= self.exceptionLimit:
                self._db_close()
                log.err("Reset digest credentials database connection: %s" % (e,))
            raise

    def delete(self, key):
        """
        See IDigestCredentialsDatabase.
        """
        try:
            self._delete_from_db(key)
            self._db_commit()
            self.exceptions = 0
        except OperationalError, e:
            self._db_rollback()
            self.exceptions += 1
            if self.exceptions >= self.exceptionLimit:
                self._db_close()
                log.err("Reset digest credentials database connection: %s" % (e,))
            raise

    def deleteMany(self, keys):
        """
        See IDigestCredentialsDatabase.
        """
        try:
            for key in keys:
                self._delete_from_db(key)
            self._db_commit()
            self.exceptions = 0
        except OperationalError, e:
            self._db_rollback()
            self.exceptions += 1
            if self.exceptions >= self.exceptionLimit:
                self._db_close()
                log.err("Reset digest credentials database connection: %s" % (e,))
            raise

    def keys(self):
        """
        See IDigestCredentialsDatabase.
        """
        try:
            result = []
            for key in self._db_execute("select KEY from DIGESTCREDENTIALS"):
                result.append(str(key[0]))
            
            self.exceptions = 0
            return result
        except OperationalError, e:
            self.exceptions += 1
            if self.exceptions >= self.exceptionLimit:
                self._db_close()
                log.err("Reset digest credentials database connection: %s" % (e,))
            raise

    def items(self):
        """
        See IDigestCredentialsDatabase.
        """
        try:
            result = []
            for key in self._db_execute("select KEY, VALUE from DIGESTCREDENTIALS"):
                result.append((str(key[0]), pickle.loads(str(key[1])),))
            
            self.exceptions = 0
            return result
        except OperationalError, e:
            self.exceptions += 1
            if self.exceptions >= self.exceptionLimit:
                self._db_close()
                log.err("Reset digest credentials database connection: %s" % (e,))
            raise

    def _set_in_db(self, key, value):
        """
        Insert the specified entry into the database, replacing any that might already exist.

        @param key:   the key to add.
        @param value: the value to add.
        """
        self._db().execute(
            """
            insert or replace into DIGESTCREDENTIALS (KEY, VALUE)
            values (:1, :2)
            """, (key, value,)
        )
       
    def _delete_from_db(self, key):
        """
        Deletes the specified entry from the database.

        @param key: the key to remove.
        """
        self._db().execute("delete from DIGESTCREDENTIALS where KEY = :1", (key,))
    
    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return DigestCredentialsDB.dbFormatVersion
        
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
                KEY         text unique,
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
        super(QopDigestCredentialFactory, self).__init__(algorithm, realm)
        self.qop = qop
        self.db = DigestCredentialsDB(db_path)
        
        # Always clean-up when we start-up
        self.cleanup()

    def getChallenge(self, peer):
        """
        Generate the challenge for use in the WWW-Authenticate header
        Do the default behavior but then strip out any 'qop' from the challenge fields
        if no qop was specified.

        @param peer: The L{IAddress} of the requesting client.

        @return: The C{dict} that can be used to generate a WWW-Authenticate
            header.
        """

        c = self.generateNonce()
        
        # Make sure it is not a duplicate
        if self.db.has_key(c):
            raise AssertionError("nonce value already cached in credentials database: %s" % (c,))

        # The database record is a tuple of (client ip, nonce-count, timestamp)
        self.db.set(c, (peer.host, 0, time.time()))

        challenge = {'nonce': c,
                     'qop': 'auth',
                     'algorithm': self.algorithm,
                     'realm': self.realm}

        if self.qop:
            challenge['qop'] = self.qop
        else:
            del challenge['qop']
        
        # If stale was marked when decoding this request's Authorization header, add that to the challenge
        if hasattr(peer, 'stale') and peer.stale:
            challenge['stale'] = 'true'

        return challenge
            

    def decode(self, response, request):
        """
        Do the default behavior but then strip out any 'qop' from the credential fields
        if no qop was specified.
        """

        """
        Decode the given response and attempt to generate a
        L{DigestedCredentials} from it.

        @type response: C{str}
        @param response: A string of comma seperated key=value pairs

        @type request: L{twisted.web2.server.Request}
        @param request: the request being processed

        @return: L{DigestedCredentials}

        @raise: L{error.LoginFailed} if the response does not contain a
            username, a nonce, an opaque, or if the opaque is invalid.
        """
        def unq(s):
            if len(s) != 0 and s[0] == s[-1] == '"':
                return s[1:-1]
            return s
        response = ' '.join(response.splitlines())
        
        try:
            parts = split(tokenize((response,), foldCase=False), Token(","))
    
            auth = {}
    
            for (k, v) in [parseKeyValue(p) for p in parts]:
                auth[k.strip()] = unq(v.strip())
        except ValueError:
            raise error.LoginFailed('Invalid response.')
            
        username = auth.get('username')
        if not username:
            raise error.LoginFailed('Invalid response, no username given.')

        if 'nonce' not in auth:
            raise error.LoginFailed('Invalid response, no nonce given.')

        # Now verify the nonce/cnonce values for this client
        if self.validate(auth, request):

            credentials = DigestedCredentials(username,
                                       request.method,
                                       self.realm,
                                       auth)
            if not self.qop and credentials.fields.has_key('qop'):
                del credentials.fields['qop']
            return credentials
        else:
            raise error.LoginFailed('Invalid nonce/cnonce values')

    def validate(self, auth, request):
        """
        Check that the parameters in the response represent a valid set of credentials that
        may be being re-used.

        @param auth:        the response parameters.
        @type auth:         C{dict}
        @param request:     the request being processed.
        @type request:      L{twisted.web2.server.Request}
        
        @return:            C{True} if validated.
        @raise LoginFailed: if validation fails.
        """

        nonce = auth.get('nonce')
        clientip = request.remoteAddr.host
        nonce_count = auth.get('nc')

        # First check we have this nonce
        if not self.db.has_key(nonce):
            raise error.LoginFailed('Invalid nonce value: %s' % (nonce,))
        db_clientip, db_nonce_count, db_timestamp = self.db.get(nonce)

        # Next check client ip
        if db_clientip != clientip:
            self.invalidate(nonce)
            raise error.LoginFailed('Client IPs do not match: %s and %s' % (clientip, db_clientip,))
        
        # cnonce and nonce-count MUST be present if qop is present
        if auth.get('qop') is not None:
            if auth.get('cnonce') is None:
                self.invalidate(nonce)
                raise error.LoginFailed('cnonce is required when qop is specified')
            if nonce_count is None:
                self.invalidate(nonce)
                raise error.LoginFailed('nonce-count is required when qop is specified')
                
            # Next check the nonce-count is one greater than the previous one and update it in the DB
            try:
                nonce_count = int(nonce_count, 16)
            except ValueError:
                self.invalidate(nonce)
                raise error.LoginFailed('nonce-count is not a valid hex string: %s' % (auth.get('nonce-count'),))            
            if nonce_count != db_nonce_count + 1:
                self.invalidate(nonce)
                raise error.LoginFailed('nonce-count value out of sequence: %s should be one more than %s' % (nonce_count, db_nonce_count,))
            self.db.set(nonce, (db_clientip, nonce_count, db_timestamp))
        else:
            # When not using qop the stored nonce-count must always be zero.
            # i.e. we can't allow a qop auth then a non-qop auth with the same nonce
            if db_nonce_count != 0:
                self.invalidate(nonce)
                raise error.LoginFailed('nonce-count was sent with this nonce: %s' % (nonce,))                
        
        # Now check timestamp
        if db_timestamp + DigestCredentialFactory.CHALLENGE_LIFETIME_SECS <= time.time():
            self.invalidate(nonce)
            if request.remoteAddr:
                request.remoteAddr.stale = True
            raise error.LoginFailed('Digest credentials expired')

        return True
    
    def invalidate(self, nonce):
        """
        Invalidate cached credentials for the specified nonce value.

        @param nonce:    the nonce for the record to invalidate.
        @type nonce:     C{str}
        """
        self.db.delete(nonce)

    def cleanup(self):
        """
        This should be called at regular intervals to remove expired credentials from the cache.
        """
        items = self.db.items()
        oldest_allowed = time.time() - DigestCredentialFactory.CHALLENGE_LIFETIME_SECS
        delete_keys = []
        for key, value in items:
            ignore_clientip, ignore_cnonce, db_timestamp = value
            if db_timestamp <= oldest_allowed:
                delete_keys.append(key)

        try:
            self.db.deleteMany(delete_keys)
        except Exception, e:
            # Clean-up errors can be logged but we should ignore them
            log.err("Failed to clean digest credentials: %s" % (e,))
