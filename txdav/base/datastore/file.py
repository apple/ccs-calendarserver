# -*- test-case-name: txdav -*-
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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
Common utility functions for a file based datastore.
"""

from twext.python.log import LoggingMixIn
from twext.enterprise.ienterprise import AlreadyFinishedError
from txdav.idav import IDataStoreObject
from txdav.base.propertystore.base import PropertyName

from twext.web2.dav.element.rfc2518 import GETContentType
from twext.web2.dav.resource import TwistedGETContentMD5

from twisted.python import hashlib

from zope.interface.declarations import implements

def isValidName(name):
    """
    Determine if the given string is a valid name.  i.e. does it conflict with
    any of the other entities which may be on the filesystem?

    @param name: a name which might be given to a calendar.
    """
    return not name.startswith(".")


def hidden(path):
    return path.sibling('.' + path.basename())


def writeOperation(thunk):
    # FIXME: tests
    def inner(self, *a, **kw):
        if self._transaction._termination is not None:
            raise RuntimeError(
                "%s.%s is a write operation, but transaction already %s"
                % (self, thunk.__name__, self._transaction._termination))
        return thunk(self, *a, **kw)
    return inner



class DataStore(LoggingMixIn):
    """
    Generic data store.
    """

    _transactionClass = None    # Derived class must set this

    def __init__(self, path):
        """
        Create a calendar store.

        @param path: a L{FilePath} pointing at a directory on disk.
        """
        self._path = path

#        if not path.isdir():
            # FIXME: Add DataStoreNotFoundError?
#            raise NotFoundError("No such data store")

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._path.path)

    def newTransaction(self, name='no name'):
        """
        Create a new transaction.

        @see Transaction
        """
        return self._transactionClass(self)



class _CommitTracker(object):
    """
    Diagnostic tool to find transactions that were never committed.
    """

    def __init__(self, name):
        self.name = name
        self.done = False
        self.info = []

    def __del__(self):
        if not self.done and self.info:
            print '**** UNCOMMITTED TRANSACTION (%s) BEING GARBAGE COLLECTED ****' % (
                self.name,
            )
            for info in self.info:
                print '   ', info
            print '---- END OF OPERATIONS'



class DataStoreTransaction(LoggingMixIn):
    """
    In-memory implementation of a data store transaction.
    """

    def __init__(self, dataStore, name):
        """
        Initialize a transaction; do not call this directly, instead call
        L{CalendarStore.newTransaction}.

        @param calendarStore: The store that created this transaction.

        @type calendarStore: L{CalendarStore}
        """
        self._dataStore = dataStore
        self._termination = None
        self._operations = []
        self._postCommitOperations = []
        self._postAbortOperations = []
        self._tracker = _CommitTracker(name)


    def store(self):
        return self._dataStore

    def addOperation(self, operation, name):
        self._operations.append(operation)
        self._tracker.info.append(name)


    def _terminate(self, mode):
        """
        Check to see if this transaction has already been terminated somehow,
        either via committing or aborting, and if not, note that it has been
        terminated.

        @param mode: The manner of the termination of this transaction.
        
        @type mode: C{str}

        @raise AlreadyFinishedError: This transaction has already been
            terminated.
        """
        if self._termination is not None:
            raise AlreadyFinishedError("already %s" % (self._termination,))
        self._termination = mode
        self._tracker.done = True


    def abort(self):
        self._terminate("aborted")

        for operation in self._postAbortOperations:
            operation()


    def commit(self):
        self._terminate("committed")

        self.committed = True
        undos = []

        for operation in self._operations:
            try:
                undo = operation()
                if undo is not None:
                    undos.append(undo)
            except:
                self.log_debug("Undoing DataStoreTransaction")
                for undo in undos:
                    try:
                        undo()
                    except:
                        self.log_error("Cannot undo DataStoreTransaction")
                raise

        for operation in self._postCommitOperations:
            operation()

    def postCommit(self, operation):
        self._postCommitOperations.append(operation)

    def postAbort(self, operation):
        self._postAbortOperations.append(operation)

class FileMetaDataMixin(object):
    
    implements(IDataStoreObject)
    
    def name(self):
        """
        Identify the name of the object

        @return: the name of this object.
        @rtype: C{str}
        """

        return self._path.basename()

    def contentType(self):
        """
        The content type of the object's content.

        @rtype: L{MimeType}
        """
        try:
            return self.properties()[PropertyName.fromElement(GETContentType)].mimeType()
        except KeyError:
            return None

    def md5(self):
        """
        The MD5 hex digest of this object's content.

        @rtype: C{str}
        """
        try:
            return str(self.properties()[PropertyName.fromElement(TwistedGETContentMD5)])
        except KeyError:
            # FIXME: Strictly speaking we should not need to read the data as the md5 property should always be
            # present. However, our unit tests use static files for their data store and those currently
            # do not include the md5 xattr.
            try:
                data = self._path.open().read()
            except IOError:
                return None
            md5 = hashlib.md5(data).hexdigest()
            return md5

    def size(self):
        """
        The octet-size of this object's content.

        @rtype: C{int}
        """
        if self._path.exists():
            return int(self._path.getsize())
        else:
            return 0

    def created(self):
        """
        The creation date-time stamp of this object.

        @rtype: C{int}
        """
        if self._path.exists():
            return self._path.getmtime() # No creation time on POSIX
        else:
            return None

    def modified(self):
        """
        The last modification date-time stamp of this object.

        @rtype: C{int}
        """
        if self._path.exists():
            return self._path.getmtime()
        else:
            return None
