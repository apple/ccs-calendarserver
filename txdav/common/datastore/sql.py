# -*- test-case-name: txdav.caldav.datastore.test.test_sql,txdav.carddav.datastore.test.test_sql -*-
##
# Copyright (c) 2010-2014 Apple Inc. All rights reserved.
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
SQL data store.
"""

__all__ = [
    "CommonDataStore",
    "CommonStoreTransaction",
    "CommonHome",
]

from cStringIO import StringIO

from pycalendar.datetime import DateTime

from twext.enterprise.dal.syntax import (
    Delete, utcNowSQL, Union, Insert, Len, Max, Parameter, SavepointAction,
    Select, Update, ColumnSyntax, TableSyntax, Upper, Count, ALL_COLUMNS, Sum,
    DatabaseLock, DatabaseUnlock)
from twext.enterprise.ienterprise import AlreadyFinishedError
from twext.enterprise.jobqueue import LocalQueuer
from twext.enterprise.util import parseSQLTimestamp
from twext.internet.decorate import memoizedKey, Memoizable
from twext.python.clsprop import classproperty
from twext.python.log import Logger
from txweb2.http_headers import MimeType

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python import hashlib
from twisted.python.failure import Failure
from twisted.python.modules import getModule
from twisted.python.util import FancyEqMixin

from twistedcaldav.config import config
from twistedcaldav.dateops import datetimeMktime, pyCalendarTodatetime

from txdav.base.datastore.util import QueryCacher
from txdav.base.datastore.util import normalizeUUIDOrNot
from txdav.base.propertystore.base import PropertyName
from txdav.base.propertystore.none import PropertyStore as NonePropertyStore
from txdav.base.propertystore.sql import PropertyStore
from txdav.caldav.icalendarstore import ICalendarTransaction, ICalendarStore
from txdav.carddav.iaddressbookstore import IAddressBookTransaction
from txdav.common.datastore.common import HomeChildBase
from txdav.common.datastore.podding.conduit import PoddingConduit
from txdav.common.datastore.sql_tables import _BIND_MODE_DIRECT, \
    _BIND_MODE_INDIRECT, _BIND_MODE_OWN, _BIND_STATUS_ACCEPTED, \
    _BIND_STATUS_DECLINED, _BIND_STATUS_DELETED, _BIND_STATUS_INVALID, \
    _BIND_STATUS_INVITED, _HOME_STATUS_EXTERNAL, _HOME_STATUS_NORMAL, \
    _HOME_STATUS_PURGING, schema, splitSQLString
from txdav.common.icommondatastore import ConcurrentModification, \
    RecordNotAllowedError, ExternalShareFailed, ShareNotAllowed, \
    IndexedSearchException, NotFoundError
from txdav.common.icommondatastore import HomeChildNameNotAllowedError, \
    HomeChildNameAlreadyExistsError, NoSuchHomeChildError, \
    ObjectResourceNameNotAllowedError, ObjectResourceNameAlreadyExistsError, \
    NoSuchObjectResourceError, AllRetriesFailed, InvalidSubscriptionValues, \
    InvalidIMIPTokenValues, TooManyObjectResourcesError, \
    SyncTokenValidException
from txdav.common.idirectoryservice import IStoreDirectoryService, \
    DirectoryRecordNotFoundError
from txdav.common.inotifications import INotificationCollection, \
    INotificationObject
from txdav.idav import ChangeCategory
from txdav.xml import element

from uuid import uuid4, UUID

from zope.interface import implements, directlyProvides

from collections import namedtuple
import datetime
import inspect
import itertools
import json
import sys
import time

current_sql_schema = getModule(__name__).filePath.sibling("sql_schema").child("current.sql").getContent()

log = Logger()

ECALENDARTYPE = 0
EADDRESSBOOKTYPE = 1
ENOTIFICATIONTYPE = 2

# Labels used to identify the class of resource being modified, so that
# notification systems can target the correct application
NotifierPrefixes = {
    ECALENDARTYPE: "CalDAV",
    EADDRESSBOOKTYPE: "CardDAV",
}


class CommonDataStore(Service, object):
    """
    Shared logic for SQL-based data stores, between calendar and addressbook
    storage.

    @ivar sqlTxnFactory: A 0-arg factory callable that produces an
        L{IAsyncTransaction}.

    @ivar _notifierFactories: a C{dict} of L{IStoreNotifierFactory} objects
        from which the store can create notifiers for store objects. The keys
        are "tokens" that determine the type of notifier.

    @ivar attachmentsPath: a L{FilePath} indicating a directory where
        attachments may be stored.

    @ivar enableCalendars: a boolean, C{True} if this data store should provide
        L{ICalendarStore}, C{False} if not.

    @ivar enableAddressBooks: a boolean, C{True} if this data store should
        provide L{IAddressbookStore}, C{False} if not.

    @ivar label: A string, used for tagging debug messages in the case where
        there is more than one store.  (Useful mostly for unit tests.)

    @ivar quota: the amount of space granted to each calendar home (in bytes)
        for storing attachments, or C{None} if quota should not be enforced.
    @type quota: C{int} or C{NoneType}

    @ivar queuer: An object with an C{enqueueWork} method, from
        L{twext.enterprise.jobqueue}.  Initially, this is a L{LocalQueuer}, so it
        is always usable, but in a properly configured environment it will be
        upgraded to a more capable object that can distribute work throughout a
        cluster.
    """

    implements(ICalendarStore)

    def __init__(
        self,
        sqlTxnFactory,
        notifierFactories,
        directoryService,
        attachmentsPath,
        attachmentsURIPattern,
        enableCalendars=True,
        enableAddressBooks=True,
        enableManagedAttachments=True,
        label="unlabeled",
        quota=(2 ** 20),
        logLabels=False,
        logStats=False,
        logStatsLogFile=None,
        logSQL=False,
        logTransactionWaits=0,
        timeoutTransactions=0,
        cacheQueries=True,
        cachePool="Default",
        cacheExpireSeconds=3600
    ):
        assert enableCalendars or enableAddressBooks

        self.sqlTxnFactory = sqlTxnFactory
        self._notifierFactories = notifierFactories if notifierFactories is not None else {}
        self._directoryService = IStoreDirectoryService(directoryService) if directoryService is not None else None
        self.attachmentsPath = attachmentsPath
        self.attachmentsURIPattern = attachmentsURIPattern
        self.enableCalendars = enableCalendars
        self.enableAddressBooks = enableAddressBooks
        self.enableManagedAttachments = enableManagedAttachments
        self.label = label
        self.quota = quota
        self.logLabels = logLabels
        self.logStats = logStats
        self.logStatsLogFile = logStatsLogFile
        self.logSQL = logSQL
        self.logTransactionWaits = logTransactionWaits
        self.timeoutTransactions = timeoutTransactions
        self.queuer = LocalQueuer(self.newTransaction)
        self._migrating = False
        self._enableNotifications = True
        self._newTransactionCallbacks = set()

        if cacheQueries:
            self.queryCacher = QueryCacher(
                cachePool=cachePool,
                cacheExpireSeconds=cacheExpireSeconds
            )
        else:
            self.queryCacher = None

        self.conduit = PoddingConduit(self)

        # Always import these here to trigger proper "registration" of the calendar and address book
        # home classes
        __import__("txdav.caldav.datastore.sql")
        __import__("txdav.carddav.datastore.sql")


    def availablePrimaryStoreTypes(self):
        """
        The list of store home types supported.
        """
        return (ECALENDARTYPE, EADDRESSBOOKTYPE,)


    def directoryService(self):
        return self._directoryService


    def setDirectoryService(self, directoryService):
        self._directoryService = directoryService


    def callWithNewTransactions(self, callback):
        """
        Registers a method to be called whenever a new transaction is
        created.

        @param callback: callable taking a single argument, a transaction
        """
        self._newTransactionCallbacks.add(callback)


    @inlineCallbacks
    def _withEachHomeDo(self, homeTable, homeFromTxn, action, batchSize, processExternal=False):
        """
        Implementation of L{ICalendarStore.withEachCalendarHomeDo} and
        L{IAddressbookStore.withEachAddressbookHomeDo}.
        """
        txn = yield self.newTransaction()
        try:
            allUIDs = yield (Select([homeTable.OWNER_UID], From=homeTable).on(txn))
            for [uid] in allUIDs:
                home = yield homeFromTxn(txn, uid)
                if not processExternal and home.external():
                    continue
                yield action(txn, (yield homeFromTxn(txn, uid)))
        except:
            a, b, c = sys.exc_info()
            yield txn.abort()
            raise a, b, c
        else:
            yield txn.commit()


    def withEachCalendarHomeDo(self, action, batchSize=None, processExternal=False):
        """
        Implementation of L{ICalendarStore.withEachCalendarHomeDo}.
        """
        return self._withEachHomeDo(
            schema.CALENDAR_HOME,
            lambda txn, uid: txn.calendarHomeWithUID(uid),
            action, batchSize, processExternal
        )


    def withEachAddressbookHomeDo(self, action, batchSize=None, processExternal=False):
        """
        Implementation of L{IAddressbookStore.withEachAddressbookHomeDo}.
        """
        return self._withEachHomeDo(
            schema.ADDRESSBOOK_HOME,
            lambda txn, uid: txn.addressbookHomeWithUID(uid),
            action, batchSize, processExternal
        )


    def newTransaction(self, label="unlabeled", disableCache=False, authz_uid=None):
        """
        @see: L{IDataStore.newTransaction}
        """
        txn = CommonStoreTransaction(
            self,
            self.sqlTxnFactory(label=label),
            self.enableCalendars,
            self.enableAddressBooks,
            self._notifierFactories if self._enableNotifications else {},
            label,
            self._migrating,
            disableCache,
            authz_uid,
        )
        if self.logTransactionWaits or self.timeoutTransactions:
            CommonStoreTransactionMonitor(txn, self.logTransactionWaits,
                                          self.timeoutTransactions)
        for callback in self._newTransactionCallbacks:
            callback(txn)
        return txn


    @inlineCallbacks
    def inTransaction(self, label, operation, transactionCreator=None):
        """
        Perform the given operation in a transaction, committing or aborting as
        required.

        @param label: the label to pass to the transaction creator

        @param operation: a 1-arg callable that takes an L{IAsyncTransaction} and
            returns a value.

        @param transactionCreator: a 1-arg callable that takes a "label" arg and
            returns a transaction

        @return: a L{Deferred} that fires with C{operation}'s result or fails with
            its error, unless there is an error creating, aborting or committing
            the transaction.
        """

        if transactionCreator is None:
            transactionCreator = self.newTransaction

        txn = transactionCreator(label=label)

        try:
            result = yield operation(txn)
        except:
            f = Failure()
            yield txn.abort()
            returnValue(f)
        else:
            yield txn.commit()
            returnValue(result)


    def setMigrating(self, state):
        """
        Set the "migrating" state
        """
        self._migrating = state
        self._enableNotifications = not state


    def setUpgrading(self, state):
        """
        Set the "upgrading" state
        """
        self._enableNotifications = not state


    @inlineCallbacks
    def dropboxAllowed(self, txn):
        """
        Determine whether dropbox attachments are allowed. Once we have migrated to managed attachments,
        we should never allow dropbox-style attachments to be created.
        """
        if not hasattr(self, "_dropbox_ok"):
            already_migrated = (yield txn.calendarserverValue("MANAGED-ATTACHMENTS", raiseIfMissing=False))
            self._dropbox_ok = already_migrated is None
        returnValue(self._dropbox_ok)


    def queryCachingEnabled(self):
        """
        Indicate whether SQL statement query caching is enabled. Also controls whether propstore caching is done.

        @return: C{True} if enabled, else C{False}
        @rtype: C{bool}
        """
        return self.queryCacher is not None


    @inlineCallbacks
    def uidInStore(self, txn, uid):
        """
        Indicate whether the specified user UID is hosted in the current store, or
        possibly in another pod.

        @param txn: transaction to use
        @type txn: L{CommonStoreTransaction}
        @param uid: the user UID to test
        @type uid: L{str}

        @return: a tuple of L{bool}, L{str} - the first indicates whether the user is
            hosted, the second the serviceNodeUID of the pod hosting the user or
            C{None} if on this pod.
        @rtype: L{tuple}
        """

        # Check if locally stored first
        for storeType in self.availablePrimaryStoreTypes():
            home = yield txn.homeWithUID(storeType, uid)
            if home is not None:
                if home.external():
                    # TODO: locate the pod where the user is hosted
                    returnValue((True, "unknown",))
                else:
                    returnValue((True, None,))
        else:
            returnValue((False, None,))



class TransactionStatsCollector(object):
    """
    Used to log each SQL query and statistics about that query during the course of a single transaction.
    Results can be printed out where ever needed at the end of the transaction.
    """

    def __init__(self, label, logFileName=None):
        self.label = label
        self.logFileName = logFileName
        self.statements = []
        self.startTime = time.time()


    def startStatement(self, sql, args):
        """
        Called prior to an SQL query being run.

        @param sql: the SQL statement to execute
        @type sql: C{str}
        @param args: the arguments (binds) to the SQL statement
        @type args: C{list}

        @return: C{tuple} containing the index in the statement list for this statement, and the start time
        """
        args = ["%s" % (arg,) for arg in args]
        args = [((arg[:10] + "...") if len(arg) > 40 else arg) for arg in args]
        self.statements.append(["%s %s" % (sql, args,), 0, 0, 0])
        return len(self.statements) - 1, time.time()


    def endStatement(self, context, rows):
        """
        Called after an SQL query has executed.

        @param context: the tuple returned from startStatement
        @type context: C{tuple}
        @param rows: number of rows returned from the query
        @type rows: C{int}
        """
        index, tstamp = context
        t = time.time()
        self.statements[index][1] = len(rows) if rows else 0
        self.statements[index][2] = t - tstamp
        self.statements[index][3] = t


    def printReport(self):
        """
        Print a report of all the SQL statements executed to date.
        """

        total_statements = len(self.statements)
        total_rows = sum([statement[1] for statement in self.statements])
        total_time = sum([statement[2] for statement in self.statements]) * 1000.0

        toFile = StringIO()
        toFile.write("*** SQL Stats ***\n")
        toFile.write("\n")
        toFile.write("Label: %s\n" % (self.label,))
        toFile.write("Unique statements: %d\n" % (len(set([statement[0] for statement in self.statements]),),))
        toFile.write("Total statements: %d\n" % (total_statements,))
        toFile.write("Total rows: %d\n" % (total_rows,))
        toFile.write("Total time (ms): %.3f\n" % (total_time,))
        t_last_end = self.startTime
        for sql, rows, t_taken, t_end in self.statements:
            toFile.write("\n")
            toFile.write("SQL: %s\n" % (sql,))
            toFile.write("Rows: %s\n" % (rows,))
            toFile.write("Time (ms): %.3f\n" % (t_taken * 1000.0,))
            toFile.write("Idle (ms): %.3f\n" % ((t_end - t_taken - t_last_end) * 1000.0,))
            toFile.write("Elapsed (ms): %.3f\n" % ((t_end - self.startTime) * 1000.0,))
            t_last_end = t_end
        toFile.write("Commit (ms): %.3f\n" % ((time.time() - t_last_end) * 1000.0,))
        toFile.write("***\n\n")

        if self.logFileName:
            open(self.logFileName, "a").write(toFile.getvalue())
        else:
            log.error(toFile.getvalue())

        return (total_statements, total_rows, total_time,)



class CommonStoreTransactionMonitor(object):
    """
    Object that monitors the state of a transaction over time and logs or times out
    the transaction.
    """

    callLater = reactor.callLater

    def __init__(self, txn, logTimerSeconds, timeoutSeconds):
        self.txn = txn
        self.delayedLog = None
        self.delayedTimeout = None
        self.logTimerSeconds = logTimerSeconds
        self.timeoutSeconds = timeoutSeconds

        self.txn.postCommit(self._cleanTxn)
        self.txn.postAbort(self._cleanTxn)

        self._installLogTimer()
        self._installTimeout()


    def _cleanTxn(self):
        self.txn = None
        if self.delayedLog:
            self.delayedLog.cancel()
            self.delayedLog = None
        if self.delayedTimeout:
            self.delayedTimeout.cancel()
            self.delayedTimeout = None
        return succeed(None)


    def _installLogTimer(self):
        def _logTransactionWait():
            if self.txn is not None:
                log.error(
                    "Transaction wait: {me.txn}, "
                    "Statements: {me.txn.statementCount:d}, "
                    "IUDs: {me.txn.iudCount:d}, "
                    "Statement: {me.txn.currentStatement}",
                    me=self
                )
                self.delayedLog = self.callLater(
                    self.logTimerSeconds, _logTransactionWait
                )

        if self.logTimerSeconds:
            self.delayedLog = self.callLater(
                self.logTimerSeconds, _logTransactionWait
            )


    def _installTimeout(self):
        def _forceAbort():
            if self.txn is not None:
                log.error(
                    "Transaction abort too long: {me.txn}, "
                    "Statements: {me.txn.statementCount:d}, "
                    "IUDs: {me.txn.iudCount:d}, "
                    "Statement: {me.txn.currentStatement}",
                    me=self
                )
                self.delayedTimeout = None
                if self.delayedLog:
                    self.delayedLog.cancel()
                    self.delayedLog = None
                self.txn.timeout()

        if self.timeoutSeconds:
            self.delayedTimeout = self.callLater(
                self.timeoutSeconds, _forceAbort
            )



class CommonStoreTransaction(object):
    """
    Transaction implementation for SQL database.
    """
    _homeClass = {}

    id = 0

    def __init__(
        self, store, sqlTxn,
        enableCalendars, enableAddressBooks,
        notifierFactories, label, migrating=False, disableCache=False,
        authz_uid=None,
    ):
        if label == "unlabeled" or not label:
            tr = inspect.getframeinfo(inspect.currentframe().f_back.f_back)
            label = "{}#{}${}".format(tr.filename, tr.lineno, tr.function)

        self._store = store
        self._queuer = self._store.queuer
        self._calendarHomes = {}
        self._addressbookHomes = {}
        self._notificationHomes = {}
        self._notifierFactories = notifierFactories
        self._notifiedAlready = set()
        self._bumpedRevisionAlready = set()
        self._label = label
        self._migrating = migrating
        self._primaryHomeType = None
        self._disableCache = disableCache or not store.queryCachingEnabled()
        if disableCache:
            self._queryCacher = None
        else:
            self._queryCacher = store.queryCacher
        self._authz_uid = authz_uid

        CommonStoreTransaction.id += 1
        self._txid = CommonStoreTransaction.id

        extraInterfaces = []
        if enableCalendars:
            extraInterfaces.append(ICalendarTransaction)
            self._primaryHomeType = ECALENDARTYPE
        if enableAddressBooks:
            extraInterfaces.append(IAddressBookTransaction)
            if self._primaryHomeType is None:
                self._primaryHomeType = EADDRESSBOOKTYPE
        directlyProvides(self, *extraInterfaces)

        self._sqlTxn = sqlTxn
        self.paramstyle = sqlTxn.paramstyle
        self.dialect = sqlTxn.dialect

        self._stats = (
            TransactionStatsCollector(self._label, self._store.logStatsLogFile)
            if self._store.logStats else None
        )
        self.statementCount = 0
        self.iudCount = 0
        self.currentStatement = None
        self.timedout = False

        self.logItems = {}


    def enqueue(self, workItem, **kw):
        """
        Enqueue a L{twext.enterprise.jobqueue.WorkItem} for later execution.

        For example::

            yield (txn.enqueue(MyWorkItem, workDescription="some work to do"))

        @return: a work proposal describing various events in the work's
            life-cycle.
        @rtype: L{twext.enterprise.jobqueue.WorkProposal}
        """
        return self._store.queuer.enqueueWork(self, workItem, **kw)


    def store(self):
        return self._store


    def directoryService(self):
        return self._store.directoryService()


    def __repr__(self):
        return 'PG-TXN<%s>' % (self._label,)


    @classproperty
    def _calendarserver(cls):
        cs = schema.CALENDARSERVER
        return Select(
            [cs.VALUE, ],
            From=cs,
            Where=cs.NAME == Parameter('name'),
        )


    @inlineCallbacks
    def calendarserverValue(self, key, raiseIfMissing=True):
        result = yield self._calendarserver.on(self, name=key)
        if result and len(result) == 1:
            returnValue(result[0][0])
        if raiseIfMissing:
            raise RuntimeError("Database key %s cannot be determined." % (key,))
        else:
            returnValue(None)


    @inlineCallbacks
    def setCalendarserverValue(self, key, value):
        cs = schema.CALENDARSERVER
        yield Insert(
            {cs.NAME: key, cs.VALUE: value},
        ).on(self)


    @inlineCallbacks
    def updateCalendarserverValue(self, key, value):
        cs = schema.CALENDARSERVER
        yield Update(
            {cs.VALUE: value},
            Where=cs.NAME == key,
        ).on(self)


    def _determineMemo(self, storeType, uid, create=False, authzUID=None):
        """
        Determine the memo dictionary to use for homeWithUID.
        """
        if storeType == ECALENDARTYPE:
            return self._calendarHomes
        else:
            return self._addressbookHomes


    @inlineCallbacks
    def homes(self, storeType):
        """
        Load all calendar or addressbook homes.
        """

        # Get all UIDs and load them - this will memoize all existing ones
        uids = (yield self._homeClass[storeType].listHomes(self))
        for uid in uids:
            yield self.homeWithUID(storeType, uid, create=False)

        # Return the memoized list directly
        returnValue([kv[1] for kv in sorted(self._determineMemo(storeType, None).items(), key=lambda x: x[0])])


    @memoizedKey("uid", _determineMemo)
    def homeWithUID(self, storeType, uid, create=False, authzUID=None):
        """
        We need to distinguish between various different users "looking" at a home and its
        child resources because we have per-user properties that depend on which user is "looking".
        By default the viewer is set to the authz_uid on the transaction, or the owner if no authz,
        but it can be overridden using L{authzUID}. This is useful when the store needs to get to
        other user's homes with the viewer being the owner of that home as opposed to authz_uid. That
        often happens when manipulating shares.
        """
        if storeType not in (ECALENDARTYPE, EADDRESSBOOKTYPE):
            raise RuntimeError("Unknown home type.")

        return self._homeClass[storeType].homeWithUID(self, uid, create, authzUID)


    def calendarHomeWithUID(self, uid, create=False, authzUID=None):
        return self.homeWithUID(ECALENDARTYPE, uid, create=create, authzUID=authzUID)


    def addressbookHomeWithUID(self, uid, create=False, authzUID=None):
        return self.homeWithUID(EADDRESSBOOKTYPE, uid, create=create, authzUID=authzUID)


    @inlineCallbacks
    def homeWithResourceID(self, storeType, rid):
        """
        Load a calendar or addressbook home by its integer resource ID.
        """
        uid = (yield self._homeClass[storeType].homeUIDWithResourceID(self, rid))
        if uid:
            # Always get the owner's view of the home = i.e., authzUID=uid
            result = (yield self.homeWithUID(storeType, uid, authzUID=uid))
        else:
            result = None
        returnValue(result)


    def calendarHomeWithResourceID(self, rid):
        return self.homeWithResourceID(ECALENDARTYPE, rid)


    def addressbookHomeWithResourceID(self, rid):
        return self.homeWithResourceID(EADDRESSBOOKTYPE, rid)


    @memoizedKey("uid", "_notificationHomes")
    def notificationsWithUID(self, uid, create=True):
        """
        Implement notificationsWithUID.
        """
        return NotificationCollection.notificationsWithUID(self, uid, create)


    @memoizedKey("rid", "_notificationHomes")
    def notificationsWithResourceID(self, rid):
        """
        Implement notificationsWithResourceID.
        """
        return NotificationCollection.notificationsWithResourceID(self, rid)


    @classproperty
    def _insertAPNSubscriptionQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Insert({apn.TOKEN: Parameter("token"),
                       apn.RESOURCE_KEY: Parameter("resourceKey"),
                       apn.MODIFIED: Parameter("modified"),
                       apn.SUBSCRIBER_GUID: Parameter("subscriber"),
                       apn.USER_AGENT: Parameter("userAgent"),
                       apn.IP_ADDR: Parameter("ipAddr")})


    @classproperty
    def _updateAPNSubscriptionQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Update({apn.MODIFIED: Parameter("modified"),
                       apn.SUBSCRIBER_GUID: Parameter("subscriber"),
                       apn.USER_AGENT: Parameter("userAgent"),
                       apn.IP_ADDR: Parameter("ipAddr")},
                      Where=(apn.TOKEN == Parameter("token")).And(
                             apn.RESOURCE_KEY == Parameter("resourceKey")))


    @classproperty
    def _selectAPNSubscriptionQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Select([apn.MODIFIED, apn.SUBSCRIBER_GUID], From=apn,
                Where=(
                    apn.TOKEN == Parameter("token")).And(
                    apn.RESOURCE_KEY == Parameter("resourceKey")
                )
            )


    @inlineCallbacks
    def addAPNSubscription(self, token, key, timestamp, subscriber,
        userAgent, ipAddr):
        if not (token and key and timestamp and subscriber):
            raise InvalidSubscriptionValues()

        # Cap these values at 255 characters
        userAgent = userAgent[:255]
        ipAddr = ipAddr[:255]

        row = yield self._selectAPNSubscriptionQuery.on(self,
            token=token, resourceKey=key)
        if not row:  # Subscription does not yet exist
            try:
                yield self._insertAPNSubscriptionQuery.on(self,
                    token=token, resourceKey=key, modified=timestamp,
                    subscriber=subscriber, userAgent=userAgent,
                    ipAddr=ipAddr)
            except Exception:
                # Subscription may have been added by someone else, which is fine
                pass

        else:  # Subscription exists, so update with new timestamp and subscriber
            try:
                yield self._updateAPNSubscriptionQuery.on(self,
                    token=token, resourceKey=key, modified=timestamp,
                    subscriber=subscriber, userAgent=userAgent,
                    ipAddr=ipAddr)
            except Exception:
                # Subscription may have been added by someone else, which is fine
                pass


    @classproperty
    def _removeAPNSubscriptionQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Delete(From=apn,
                      Where=(apn.TOKEN == Parameter("token")).And(
                          apn.RESOURCE_KEY == Parameter("resourceKey")))


    def removeAPNSubscription(self, token, key):
        return self._removeAPNSubscriptionQuery.on(self,
            token=token, resourceKey=key)


    @classproperty
    def _purgeOldAPNSubscriptionQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Delete(From=apn,
                      Where=(apn.MODIFIED < Parameter("olderThan")))


    def purgeOldAPNSubscriptions(self, olderThan):
        return self._purgeOldAPNSubscriptionQuery.on(self,
            olderThan=olderThan)


    @classproperty
    def _apnSubscriptionsByTokenQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Select([apn.RESOURCE_KEY, apn.MODIFIED, apn.SUBSCRIBER_GUID],
                      From=apn, Where=apn.TOKEN == Parameter("token"))


    def apnSubscriptionsByToken(self, token):
        return self._apnSubscriptionsByTokenQuery.on(self, token=token)


    @classproperty
    def _apnSubscriptionsByKeyQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Select([apn.TOKEN, apn.SUBSCRIBER_GUID],
                      From=apn, Where=apn.RESOURCE_KEY == Parameter("resourceKey"))


    def apnSubscriptionsByKey(self, key):
        return self._apnSubscriptionsByKeyQuery.on(self, resourceKey=key)


    @classproperty
    def _apnSubscriptionsBySubscriberQuery(cls):
        apn = schema.APN_SUBSCRIPTIONS
        return Select([apn.TOKEN, apn.RESOURCE_KEY, apn.MODIFIED, apn.USER_AGENT, apn.IP_ADDR],
                      From=apn, Where=apn.SUBSCRIBER_GUID == Parameter("subscriberGUID"))


    def apnSubscriptionsBySubscriber(self, guid):
        return self._apnSubscriptionsBySubscriberQuery.on(self, subscriberGUID=guid)


    # Create IMIP token

    @classproperty
    def _insertIMIPTokenQuery(cls):
        imip = schema.IMIP_TOKENS
        return Insert({imip.TOKEN: Parameter("token"),
                       imip.ORGANIZER: Parameter("organizer"),
                       imip.ATTENDEE: Parameter("attendee"),
                       imip.ICALUID: Parameter("icaluid"),
                      })


    @inlineCallbacks
    def imipCreateToken(self, organizer, attendee, icaluid, token=None):
        if not (organizer and attendee and icaluid):
            raise InvalidIMIPTokenValues()

        if token is None:
            token = str(uuid4())

        try:
            yield self._insertIMIPTokenQuery.on(self,
                token=token, organizer=organizer, attendee=attendee,
                icaluid=icaluid)
        except Exception:
            # TODO: is it okay if someone else created the same row just now?
            pass
        returnValue(token)

    # Lookup IMIP organizer+attendee+icaluid for token


    @classproperty
    def _selectIMIPTokenByTokenQuery(cls):
        imip = schema.IMIP_TOKENS
        return Select([imip.ORGANIZER, imip.ATTENDEE, imip.ICALUID], From=imip,
                      Where=(imip.TOKEN == Parameter("token")))


    def imipLookupByToken(self, token):
        return self._selectIMIPTokenByTokenQuery.on(self, token=token)

    # Lookup IMIP token for organizer+attendee+icaluid


    @classproperty
    def _selectIMIPTokenQuery(cls):
        imip = schema.IMIP_TOKENS
        return Select([imip.TOKEN], From=imip,
                      Where=(imip.ORGANIZER == Parameter("organizer")).And(
                             imip.ATTENDEE == Parameter("attendee")).And(
                             imip.ICALUID == Parameter("icaluid")))


    @classproperty
    def _updateIMIPTokenQuery(cls):
        imip = schema.IMIP_TOKENS
        return Update({imip.ACCESSED: utcNowSQL, },
                      Where=(imip.ORGANIZER == Parameter("organizer")).And(
                             imip.ATTENDEE == Parameter("attendee")).And(
                             imip.ICALUID == Parameter("icaluid")))


    @inlineCallbacks
    def imipGetToken(self, organizer, attendee, icaluid):
        row = (yield self._selectIMIPTokenQuery.on(self, organizer=organizer,
            attendee=attendee, icaluid=icaluid))
        if row:
            token = row[0][0]
            # update the timestamp
            yield self._updateIMIPTokenQuery.on(self, organizer=organizer,
                attendee=attendee, icaluid=icaluid)
        else:
            token = None
        returnValue(token)


    # Remove IMIP token
    @classproperty
    def _removeIMIPTokenQuery(cls):
        imip = schema.IMIP_TOKENS
        return Delete(From=imip,
                      Where=(imip.TOKEN == Parameter("token")))


    def imipRemoveToken(self, token):
        return self._removeIMIPTokenQuery.on(self, token=token)


    # Purge old IMIP tokens
    @classproperty
    def _purgeOldIMIPTokensQuery(cls):
        imip = schema.IMIP_TOKENS
        return Delete(From=imip,
                      Where=(imip.ACCESSED < Parameter("olderThan")))


    def purgeOldIMIPTokens(self, olderThan):
        """
        @type olderThan: datetime
        """
        return self._purgeOldIMIPTokensQuery.on(self, olderThan=olderThan)

    # End of IMIP


    # Groups

    @classproperty
    def _addGroupQuery(cls):
        gr = schema.GROUPS
        return Insert(
            {
                gr.NAME: Parameter("name"),
                gr.GROUP_UID: Parameter("groupUID"),
                gr.MEMBERSHIP_HASH: Parameter("membershipHash")
            },
            Return=gr.GROUP_ID
        )


    @classproperty
    def _updateGroupQuery(cls):
        gr = schema.GROUPS
        return Update(
            {
                gr.MEMBERSHIP_HASH: Parameter("membershipHash"),
                gr.NAME: Parameter("name"),
                gr.MODIFIED: Parameter("timestamp"),
                gr.EXTANT: Parameter("extant"),
            },
            Where=(gr.GROUP_UID == Parameter("groupUID"))
        )


    @classproperty
    def _groupByUID(cls):
        gr = schema.GROUPS
        return Select(
            [gr.GROUP_ID, gr.NAME, gr.MEMBERSHIP_HASH, gr.MODIFIED, gr.EXTANT],
            From=gr,
            Where=(gr.GROUP_UID == Parameter("groupUID"))
        )


    @classproperty
    def _groupByID(cls):
        gr = schema.GROUPS
        return Select(
            [gr.GROUP_UID, gr.NAME, gr.MEMBERSHIP_HASH, gr.EXTANT],
            From=gr,
            Where=(gr.GROUP_ID == Parameter("groupID"))
        )


    @classproperty
    def _deleteGroup(cls):
        gr = schema.GROUPS
        return Delete(
            From=gr,
            Where=(gr.GROUP_ID == Parameter("groupID"))
        )


    @inlineCallbacks
    def addGroup(self, groupUID, name, membershipHash):
        """
        @type groupUID: C{unicode}
        @type name: C{unicode}
        @type membershipHash: C{str}
        """
        groupID = yield self._addGroupQuery.on(
            self,
            name=name.encode("utf-8"),
            groupUID=groupUID.encode("utf-8"),
            membershipHash=membershipHash
        )

        record = yield self.directoryService().recordWithUID(groupUID)
        yield self._refreshGroup(
            groupUID, record, groupID, name.encode("utf-8"), membershipHash
        )
        returnValue(groupID)


    def updateGroup(self, groupUID, name, membershipHash, extant=True):
        """
        @type groupUID: C{unicode}
        @type name: C{unicode}
        @type membershipHash: C{str}
        @type extant: C{boolean}
        """
        timestamp = datetime.datetime.utcnow()
        return self._updateGroupQuery.on(
            self,
            name=name.encode("utf-8"),
            groupUID=groupUID.encode("utf-8"),
            timestamp=timestamp,
            membershipHash=membershipHash,
            extant=(1 if extant else 0)
        )


    @inlineCallbacks
    def groupByUID(self, groupUID, create=True):
        """
        Return or create a record for the group UID.

        @type groupUID: C{unicode}

        @return: Deferred firing with tuple of group ID C{str}, group name
            C{unicode}, membership hash C{str}, modified timestamp, and
            extant C{boolean}
        """
        results = (
            yield self._groupByUID.on(
                self, groupUID=groupUID.encode("utf-8")
            )
        )
        if results:
            returnValue((
                results[0][0],  # group id
                results[0][1].decode("utf-8"),  # name
                results[0][2],  # membership hash
                results[0][3],  # modified timestamp
                bool(results[0][4]),  # extant
            ))
        elif create:
            savepoint = SavepointAction("groupByUID")
            yield savepoint.acquire(self)
            try:
                yield self.addGroup(groupUID, u"", "")
            except Exception:
                yield savepoint.rollback(self)
                results = (
                    yield self._groupByUID.on(
                        self, groupUID=groupUID.encode("utf-8")
                    )
                )
                if results:
                    returnValue((
                        results[0][0],  # group id
                        results[0][1].decode("utf-8"),  # name
                        results[0][2],  # membership hash
                        results[0][3],  # modified timestamp
                        bool(results[0][4]),  # extant
                    ))
                else:
                    raise
            else:
                yield savepoint.release(self)
                results = (
                    yield self._groupByUID.on(
                        self, groupUID=groupUID.encode("utf-8")
                    )
                )
                if results:
                    returnValue((
                        results[0][0],  # group id
                        results[0][1].decode("utf-8"),  # name
                        results[0][2],  # membership hash
                        results[0][3],  # modified timestamp
                        bool(results[0][4]),  # extant
                    ))
                else:
                    raise
        else:
            returnValue((None, None, None, None, None))


    @inlineCallbacks
    def groupByID(self, groupID):
        """
        Given a group ID, return the group UID, or raise NotFoundError

        @type groupID: C{str}
        @return: Deferred firing with a tuple of group UID C{unicode},
            group name C{unicode}, membership hash C{str}, and extant C{boolean}
        """
        try:
            results = (yield self._groupByID.on(self, groupID=groupID))[0]
            if results:
                results = (
                    results[0].decode("utf-8"),
                    results[1].decode("utf-8"),
                    results[2],
                    bool(results[3])
                )
            returnValue(results)
        except IndexError:
            raise NotFoundError


    def deleteGroup(self, groupID):
        return self._deleteGroup.on(self, groupID=groupID)

    # End of Groups


    # Group Members

    @classproperty
    def _addMemberToGroupQuery(cls):
        gm = schema.GROUP_MEMBERSHIP
        return Insert(
            {
                gm.GROUP_ID: Parameter("groupID"),
                gm.MEMBER_UID: Parameter("memberUID")
            }
        )


    @classproperty
    def _removeMemberFromGroupQuery(cls):
        gm = schema.GROUP_MEMBERSHIP
        return Delete(
            From=gm,
            Where=(
                gm.GROUP_ID == Parameter("groupID")
            ).And(
                gm.MEMBER_UID == Parameter("memberUID")
            )
        )


    @classproperty
    def _selectGroupMembersQuery(cls):
        gm = schema.GROUP_MEMBERSHIP
        return Select(
            [gm.MEMBER_UID],
            From=gm,
            Where=(
                gm.GROUP_ID == Parameter("groupID")
            )
        )


    @classproperty
    def _selectGroupsForQuery(cls):
        gr = schema.GROUPS
        gm = schema.GROUP_MEMBERSHIP

        return Select(
            [gr.GROUP_UID],
            From=gr,
            Where=(
                gr.GROUP_ID.In(
                    Select(
                        [gm.GROUP_ID],
                        From=gm,
                        Where=(
                            gm.MEMBER_UID == Parameter("uid")
                        )
                    )
                )
            )
        )


    def addMemberToGroup(self, memberUID, groupID):
        return self._addMemberToGroupQuery.on(
            self, groupID=groupID, memberUID=memberUID.encode("utf-8")
        )


    def removeMemberFromGroup(self, memberUID, groupID):
        return self._removeMemberFromGroupQuery.on(
            self, groupID=groupID, memberUID=memberUID.encode("utf-8")
        )


    @inlineCallbacks
    def groupMemberUIDs(self, groupID):
        """
        Returns the cached set of UIDs for members of the given groupID.
        Sub-groups are not returned in the results but their members are,
        because the group membership has already been expanded/flattened
        before storing in the db.

        @param groupID: the group ID
        @type groupID: C{int}
        @return: the set of member UIDs
        @rtype: a Deferred which fires with a set() of C{str} UIDs
        """
        members = set()
        results = (yield self._selectGroupMembersQuery.on(self, groupID=groupID))
        for row in results:
            members.add(row[0].decode("utf-8"))
        returnValue(members)


    @inlineCallbacks
    def refreshGroup(self, groupUID):
        """
        Refreshes the group membership cache.

        @param groupUID: the group UID
        @type groupUID: C{unicode}

        @return: Deferred firing with tuple of group ID C{str}, and
            membershipChanged C{boolean}

        """
        log.debug("Faulting in group: {g}", g=groupUID)
        record = (yield self.directoryService().recordWithUID(groupUID))
        if record is None:
            # the group has disappeared from the directory
            log.info("Group is missing: {g}", g=groupUID)
        else:
            log.debug("Got group record: {u}", u=record.uid)

        (
            groupID, cachedName, cachedMembershipHash, _ignore_modified,
            _ignore_extant
        ) = yield self.groupByUID(
            groupUID,
            create=(record is not None)
        )

        membershipChanged = False
        if groupID:
            membershipChanged = yield self._refreshGroup(
                groupUID, record, groupID, cachedName, cachedMembershipHash
            )

        returnValue((groupID, membershipChanged))


    @inlineCallbacks
    def _refreshGroup(self, groupUID, record, groupID, cachedName, cachedMembershipHash):
        """
        @param groupUID: the directory record
        @type groupUID: C{unicode}
        @param record: the directory record
        @type record: C{iDirectoryRecord}
        @param groupID: group resource id
        @type groupID: C{str}
        @param cachedName: group name in the database
        @type cachedName: C{unicode}
        @param cachedMembershipHash: membership hash in the database
        @type cachedMembershipHash: C{str}

        @return: Deferred firing with membershipChanged C{boolean}

        """
        if record is not None:
            members = yield record.expandedMembers()
            name = record.displayName
            extant = True
        else:
            members = frozenset()
            name = cachedName
            extant = False

        membershipHashContent = hashlib.md5()
        members = list(members)
        members.sort(key=lambda x: x.uid)
        for member in members:
            membershipHashContent.update(str(member.uid))
        membershipHash = membershipHashContent.hexdigest()

        if cachedMembershipHash != membershipHash:
            membershipChanged = True
            log.debug(
                "Group '{group}' changed", group=name
            )
        else:
            membershipChanged = False

        if membershipChanged or record is not None:
            # also updates group mod date
            yield self.updateGroup(
                groupUID, name, membershipHash, extant=extant
            )

        if membershipChanged:
            newMemberUIDs = set()
            for member in members:
                newMemberUIDs.add(member.uid)
            yield self.synchronizeMembers(groupID, newMemberUIDs)

        returnValue(membershipChanged)


    @inlineCallbacks
    def synchronizeMembers(self, groupID, newMemberUIDs):
        numRemoved = numAdded = 0
        cachedMemberUIDs = (yield self.groupMemberUIDs(groupID))

        for memberUID in cachedMemberUIDs:
            if memberUID not in newMemberUIDs:
                numRemoved += 1
                yield self.removeMemberFromGroup(memberUID, groupID)

        for memberUID in newMemberUIDs:
            if memberUID not in cachedMemberUIDs:
                numAdded += 1
                yield self.addMemberToGroup(memberUID, groupID)

        returnValue((numAdded, numRemoved))


    @inlineCallbacks
    def groupMembers(self, groupID):
        """
        The members of the given group as recorded in the db
        """
        members = set()
        memberUIDs = (yield self.groupMemberUIDs(groupID))
        for uid in memberUIDs:
            record = (yield self.directoryService().recordWithUID(uid))
            if record is not None:
                members.add(record)
        returnValue(members)


    @inlineCallbacks
    def groupUIDsFor(self, uid):
        """
        Returns the cached set of UIDs for the groups this given uid is
        a member of.

        @param uid: the uid
        @type uid: C{unicode}
        @return: the set of group IDs
        @rtype: a Deferred which fires with a set() of C{int} group IDs
        """
        groups = set()
        results = (
            yield self._selectGroupsForQuery.on(
                self, uid=uid.encode("utf-8")
            )
        )
        for row in results:
            groups.add(row[0].decode("utf-8"))
        returnValue(groups)

    # End of Group Members

    # Delegates


    @classproperty
    def _addDelegateQuery(cls):
        de = schema.DELEGATES
        return Insert({de.DELEGATOR: Parameter("delegator"),
                       de.DELEGATE: Parameter("delegate"),
                       de.READ_WRITE: Parameter("readWrite"),
                       })


    @classproperty
    def _addDelegateGroupQuery(cls):
        ds = schema.DELEGATE_GROUPS
        return Insert({ds.DELEGATOR: Parameter("delegator"),
                       ds.GROUP_ID: Parameter("groupID"),
                       ds.READ_WRITE: Parameter("readWrite"),
                       ds.IS_EXTERNAL: Parameter("isExternal"),
                       })


    @classproperty
    def _removeDelegateQuery(cls):
        de = schema.DELEGATES
        return Delete(
            From=de,
            Where=(
                de.DELEGATOR == Parameter("delegator")
            ).And(
                de.DELEGATE == Parameter("delegate")
            ).And(
                de.READ_WRITE == Parameter("readWrite")
            )
        )


    @classproperty
    def _removeDelegatesQuery(cls):
        de = schema.DELEGATES
        return Delete(
            From=de,
            Where=(
                de.DELEGATOR == Parameter("delegator")
            ).And(
                de.READ_WRITE == Parameter("readWrite")
            )
        )


    @classproperty
    def _removeDelegateGroupQuery(cls):
        ds = schema.DELEGATE_GROUPS
        return Delete(
            From=ds,
            Where=(
                ds.DELEGATOR == Parameter("delegator")
            ).And(
                ds.GROUP_ID == Parameter("groupID")
            ).And(
                ds.READ_WRITE == Parameter("readWrite")
            )
        )


    @classproperty
    def _removeDelegateGroupsQuery(cls):
        ds = schema.DELEGATE_GROUPS
        return Delete(
            From=ds,
            Where=(
                ds.DELEGATOR == Parameter("delegator")
            ).And(
                ds.READ_WRITE == Parameter("readWrite")
            )
        )


    @classproperty
    def _selectDelegatesQuery(cls):
        de = schema.DELEGATES
        return Select(
            [de.DELEGATE],
            From=de,
            Where=(
                de.DELEGATOR == Parameter("delegator")
            ).And(
                de.READ_WRITE == Parameter("readWrite")
            )
        )


    @classproperty
    def _selectDelegatorsToGroupQuery(cls):
        dg = schema.DELEGATE_GROUPS
        return Select(
            [dg.DELEGATOR],
            From=dg,
            Where=(
                dg.GROUP_ID == Parameter("delegateGroup")
            ).And(
                dg.READ_WRITE == Parameter("readWrite")
            )
        )


    @classproperty
    def _selectDelegateGroupsQuery(cls):
        ds = schema.DELEGATE_GROUPS
        gr = schema.GROUPS

        return Select(
            [gr.GROUP_UID],
            From=gr,
            Where=(
                gr.GROUP_ID.In(
                    Select(
                        [ds.GROUP_ID],
                        From=ds,
                        Where=(
                            ds.DELEGATOR == Parameter("delegator")
                        ).And(
                            ds.READ_WRITE == Parameter("readWrite")
                        )
                    )
                )
            )
        )


    @classproperty
    def _selectDirectDelegatorsQuery(cls):
        de = schema.DELEGATES
        return Select(
            [de.DELEGATOR],
            From=de,
            Where=(
                de.DELEGATE == Parameter("delegate")
            ).And(
                de.READ_WRITE == Parameter("readWrite")
            )
        )


    @classproperty
    def _selectIndirectDelegatorsQuery(cls):
        dg = schema.DELEGATE_GROUPS
        gm = schema.GROUP_MEMBERSHIP

        return Select(
            [dg.DELEGATOR],
            From=dg,
            Where=(
                dg.GROUP_ID.In(
                    Select(
                        [gm.GROUP_ID],
                        From=gm,
                        Where=(gm.MEMBER_UID == Parameter("delegate"))
                    )
                ).And(
                    dg.READ_WRITE == Parameter("readWrite")
                )
            )
        )


    @classproperty
    def _selectIndirectDelegatesQuery(cls):
        dg = schema.DELEGATE_GROUPS
        gm = schema.GROUP_MEMBERSHIP

        return Select(
            [gm.MEMBER_UID],
            From=gm,
            Where=(
                gm.GROUP_ID.In(
                    Select(
                        [dg.GROUP_ID],
                        From=dg,
                        Where=(dg.DELEGATOR == Parameter("delegator")).And(
                            dg.READ_WRITE == Parameter("readWrite"))
                    )
                )
            )
        )


    @classproperty
    def _selectExternalDelegateGroupsQuery(cls):
        edg = schema.EXTERNAL_DELEGATE_GROUPS
        return Select(
            [edg.DELEGATOR, edg.GROUP_UID_READ, edg.GROUP_UID_WRITE],
            From=edg
        )


    @classproperty
    def _removeExternalDelegateGroupsPairQuery(cls):
        edg = schema.EXTERNAL_DELEGATE_GROUPS
        return Delete(
            From=edg,
            Where=(
                edg.DELEGATOR == Parameter("delegator")
            )
        )


    @classproperty
    def _storeExternalDelegateGroupsPairQuery(cls):
        edg = schema.EXTERNAL_DELEGATE_GROUPS
        return Insert(
            {
                edg.DELEGATOR: Parameter("delegator"),
                edg.GROUP_UID_READ: Parameter("readDelegate"),
                edg.GROUP_UID_WRITE: Parameter("writeDelegate"),
            }
        )


    @classproperty
    def _removeExternalDelegateGroupsQuery(cls):
        ds = schema.DELEGATE_GROUPS
        return Delete(
            From=ds,
            Where=(
                ds.DELEGATOR == Parameter("delegator")
            ).And(
                ds.IS_EXTERNAL == 1
            )
        )


    @inlineCallbacks
    def addDelegate(self, delegator, delegate, readWrite):
        """
        Adds a row to the DELEGATES table.  The delegate should not be a
        group.  To delegate to a group, call addDelegateGroup() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegate: the UID of the delegate
        @type delegate: C{unicode}
        @param readWrite: grant read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """

        def _addDelegate(subtxn):
            return self._addDelegateQuery.on(
                subtxn,
                delegator=delegator.encode("utf-8"),
                delegate=delegate.encode("utf-8"),
                readWrite=1 if readWrite else 0
            )

        try:
            yield self.subtransaction(_addDelegate, retries=0, failureOK=True)
        except AllRetriesFailed:
            pass


    @inlineCallbacks
    def addDelegateGroup(self, delegator, delegateGroupID, readWrite,
                         isExternal=False):
        """
        Adds a row to the DELEGATE_GROUPS table.  The delegate should be a
        group.  To delegate to a person, call addDelegate() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegateGroupID: the GROUP_ID of the delegate group
        @type delegateGroupID: C{int}
        @param readWrite: grant read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """

        def _addDelegateGroup(subtxn):
            return self._addDelegateGroupQuery.on(
                subtxn,
                delegator=delegator.encode("utf-8"),
                groupID=delegateGroupID,
                readWrite=1 if readWrite else 0,
                isExternal=1 if isExternal else 0
            )

        try:
            yield self.subtransaction(_addDelegateGroup, retries=0, failureOK=True)
        except AllRetriesFailed:
            pass


    def removeDelegate(self, delegator, delegate, readWrite):
        """
        Removes a row from the DELEGATES table.  The delegate should not be a
        group.  To remove a delegate group, call removeDelegateGroup() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegate: the UID of the delegate
        @type delegate: C{unicode}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return self._removeDelegateQuery.on(
            self,
            delegator=delegator.encode("utf-8"),
            delegate=delegate.encode("utf-8"),
            readWrite=1 if readWrite else 0
        )


    def removeDelegates(self, delegator, readWrite):
        """
        Removes all rows for this delegator/readWrite combination from the
        DELEGATES table.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return self._removeDelegatesQuery.on(
            self,
            delegator=delegator.encode("utf-8"),
            readWrite=1 if readWrite else 0
        )


    def removeDelegateGroup(self, delegator, delegateGroupID, readWrite):
        """
        Removes a row from the DELEGATE_GROUPS table.  The delegate should be a
        group.  To remove a delegate person, call removeDelegate() instead.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param delegateGroupID: the GROUP_ID of the delegate group
        @type delegateGroupID: C{int}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return self._removeDelegateGroupQuery.on(
            self,
            delegator=delegator.encode("utf-8"),
            groupID=delegateGroupID,
            readWrite=1 if readWrite else 0
        )


    def removeDelegateGroups(self, delegator, readWrite):
        """
        Removes all rows for this delegator/readWrite combination from the
        DELEGATE_GROUPS table.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param readWrite: remove read and write access if True, otherwise
            read-only access
        @type readWrite: C{boolean}
        """
        return self._removeDelegateGroupsQuery.on(
            self,
            delegator=delegator.encode("utf-8"),
            readWrite=1 if readWrite else 0
        )


    @inlineCallbacks
    def delegates(self, delegator, readWrite, expanded=False):
        """
        Returns the UIDs of all delegates for the given delegator.  If
        expanded is False, only the direct delegates (users and groups)
        are returned.  If expanded is True, the expanded membmership is
        returned, not including the groups themselves.

        @param delegator: the UID of the delegator
        @type delegator: C{unicode}
        @param readWrite: the access-type to check for; read and write
            access if True, otherwise read-only access
        @type readWrite: C{boolean}
        @returns: the UIDs of the delegates (for the specified access
            type)
        @rtype: a Deferred resulting in a set
        """
        delegates = set()

        # First get the direct delegates
        results = (
            yield self._selectDelegatesQuery.on(
                self,
                delegator=delegator.encode("utf-8"),
                readWrite=1 if readWrite else 0
            )
        )
        for row in results:
            delegates.add(row[0].decode("utf-8"))

        if expanded:
            # Get those who are in groups which have been delegated to
            results = (
                yield self._selectIndirectDelegatesQuery.on(
                    self,
                    delegator=delegator.encode("utf-8"),
                    readWrite=1 if readWrite else 0
                )
            )
            for row in results:
                delegates.add(row[0].decode("utf-8"))

        else:
            # Get the directly-delegated-to groups
            results = (
                yield self._selectDelegateGroupsQuery.on(
                    self,
                    delegator=delegator.encode("utf-8"),
                    readWrite=1 if readWrite else 0
                )
            )
            for row in results:
                delegates.add(row[0].decode("utf-8"))

        returnValue(delegates)


    @inlineCallbacks
    def delegators(self, delegate, readWrite):
        """
        Returns the UIDs of all delegators which have granted access to
        the given delegate, either directly or indirectly via groups.

        @param delegate: the UID of the delegate
        @type delegate: C{unicode}
        @param readWrite: the access-type to check for; read and write
            access if True, otherwise read-only access
        @type readWrite: C{boolean}
        @returns: the UIDs of the delegators (for the specified access
            type)
        @rtype: a Deferred resulting in a set
        """
        delegators = set()

        # First get the direct delegators
        results = (
            yield self._selectDirectDelegatorsQuery.on(
                self,
                delegate=delegate.encode("utf-8"),
                readWrite=1 if readWrite else 0
            )
        )
        for row in results:
            delegators.add(row[0].decode("utf-8"))

        # Finally get those who have delegated to groups the delegate
        # is a member of
        results = (
            yield self._selectIndirectDelegatorsQuery.on(
                self,
                delegate=delegate.encode("utf-8"),
                readWrite=1 if readWrite else 0
            )
        )
        for row in results:
            delegators.add(row[0].decode("utf-8"))

        returnValue(delegators)


    @inlineCallbacks
    def delegatorsToGroup(self, delegateGroupID, readWrite):
        """
        Return the UIDs of those who have delegated to the given group with the
        given access level.

        @param delegateGroupID: the group ID of the delegate group
        @type delegateGroupID: C{int}
        @param readWrite: the access-type to check for; read and write
            access if True, otherwise read-only access
        @type readWrite: C{boolean}
        @returns: the UIDs of the delegators (for the specified access
            type)
        @rtype: a Deferred resulting in a set

        """
        delegators = set()
        results = (
            yield self._selectDelegatorsToGroupQuery.on(
                self,
                delegateGroup=delegateGroupID,
                readWrite=1 if readWrite else 0
            )
        )
        for row in results:
            delegators.add(row[0].decode("utf-8"))
        returnValue(delegators)


    @inlineCallbacks
    def allGroupDelegates(self):
        """
        Return the UIDs of all groups which have been delegated to.  Useful
        for obtaining the set of groups which need to be synchronized from
        the directory.

        @returns: the UIDs of all delegated-to groups
        @rtype: a Deferred resulting in a set
        """
        gr = schema.GROUPS
        dg = schema.DELEGATE_GROUPS

        results = (yield Select(
            [gr.GROUP_UID],
            From=gr,
            Where=(gr.GROUP_ID.In(Select([dg.GROUP_ID], From=dg, Where=None)))
        ).on(self))
        delegates = set()
        for row in results:
            delegates.add(row[0].decode("utf-8"))

        returnValue(delegates)


    @inlineCallbacks
    def externalDelegates(self):
        """
        Returns a dictionary mapping delegate UIDs to (read-group, write-group)
        tuples, including only those assignments that originated from the
        directory.

        @returns: dictionary mapping delegator uid to (readDelegateUID,
            writeDelegateUID) tuples
        @rtype: a Deferred resulting in a dictionary
        """
        delegates = {}

        # Get the externally managed delegates (which are all groups)
        results = (yield self._selectExternalDelegateGroupsQuery.on(self))
        for delegator, readDelegateUID, writeDelegateUID in results:
            delegates[delegator.encode("utf-8")] = (
                readDelegateUID.encode("utf-8") if readDelegateUID else None,
                writeDelegateUID.encode("utf-8") if writeDelegateUID else None
            )

        returnValue(delegates)


    @inlineCallbacks
    def assignExternalDelegates(
        self, delegator, readDelegateGroupID, writeDelegateGroupID,
        readDelegateUID, writeDelegateUID
    ):
        """
        Update the external delegate group table so we can quickly identify
        diffs next time, and update the delegate group table itself

        @param delegator
        @type delegator: C{UUID}
        """

        # Delete existing external assignments for the delegator
        yield self._removeExternalDelegateGroupsQuery.on(
            self,
            delegator=str(delegator)
        )

        # Remove from the external comparison table
        yield self._removeExternalDelegateGroupsPairQuery.on(
            self,
            delegator=str(delegator)
        )

        # Store new assignments in the external comparison table
        if readDelegateUID or writeDelegateUID:
            readDelegateForDB = (
                readDelegateUID.encode("utf-8") if readDelegateUID else ""
            )
            writeDelegateForDB = (
                writeDelegateUID.encode("utf-8") if writeDelegateUID else ""
            )
            yield self._storeExternalDelegateGroupsPairQuery.on(
                self,
                delegator=str(delegator),
                readDelegate=readDelegateForDB,
                writeDelegate=writeDelegateForDB
            )

        # Apply new assignments
        if readDelegateGroupID is not None:
            yield self.addDelegateGroup(
                delegator, readDelegateGroupID, False, isExternal=True
            )
        if writeDelegateGroupID is not None:
            yield self.addDelegateGroup(
                delegator, writeDelegateGroupID, True, isExternal=True
            )


    # End of Delegates


    def preCommit(self, operation):
        """
        Run things before C{commit}.  (Note: only provided by SQL
        implementation, used only for cleaning up database state.)
        """
        return self._sqlTxn.preCommit(operation)


    def postCommit(self, operation):
        """
        Run things after C{commit}.
        """
        return self._sqlTxn.postCommit(operation)


    def postAbort(self, operation):
        """
        Run things after C{abort}.
        """
        return self._sqlTxn.postAbort(operation)


    def isNotifiedAlready(self, obj):
        return obj.id() in self._notifiedAlready


    def notificationAddedForObject(self, obj):
        self._notifiedAlready.add(obj.id())


    def isRevisionBumpedAlready(self, obj):
        """
        Indicates whether or not bumpRevisionForObject has already been
        called for the given object, in order to facilitate changing the
        revision only once per object.
        """
        return obj.id() in self._bumpedRevisionAlready


    def bumpRevisionForObject(self, obj):
        """
        Records the fact that a revision token for the object has been bumped.
        """
        self._bumpedRevisionAlready.add(obj.id())

    _savepointCounter = 0

    def _savepoint(self):
        """
        Generate a new SavepointAction whose name is unique in this transaction.
        """
        self._savepointCounter += 1
        return SavepointAction('sp%d' % (self._savepointCounter,))


    @inlineCallbacks
    def subtransaction(self, thunk, retries=1, failureOK=False):
        """
        Create a limited transaction object, which provides only SQL execution,
        and run a function in a sub-transaction (savepoint) context, with that
        object to execute SQL on.

        @param thunk: a 1-argument callable which returns a Deferred when it is
            done.  If this Deferred fails, the sub-transaction will be rolled
            back.
        @type thunk: L{callable}

        @param retries: the number of times to re-try C{thunk} before deciding
            that it's legitimately failed.
        @type retries: L{int}

        @param failureOK: it is OK if this subtransaction fails so do not log.
        @type failureOK: L{bool}

        @return: a L{Deferred} which fires or fails according to the logic in
            C{thunk}.  If it succeeds, it will return the value that C{thunk}
            returned.  If C{thunk} fails or raises an exception more than
            C{retries} times, then the L{Deferred} resulting from
            C{subtransaction} will fail with L{AllRetriesFailed}.
        """
        # Right now this code is covered mostly by the automated property store
        # tests.  It should have more direct test coverage.

        # TODO: we should really have a list of acceptable exceptions for
        # failure and not blanket catch, but that involves more knowledge of
        # the database driver in use than we currently possess at this layer.
        block = self._sqlTxn.commandBlock()
        sp = self._savepoint()
        failuresToMaybeLog = []

        def end():
            block.end()
            for f in failuresToMaybeLog:
                # TODO: direct tests, to make sure error logging
                # happens correctly in all cases.
                log.error("in subTransaction()", failure=f)
            raise AllRetriesFailed()

        triesLeft = retries
        try:
            while True:
                yield sp.acquire(block)
                try:
                    result = yield thunk(block)
                except:
                    f = Failure()
                    if not failureOK:
                        failuresToMaybeLog.append(f)
                    yield sp.rollback(block)
                    if triesLeft:
                        triesLeft -= 1
                        # Important to get the new block before the old one has
                        # been completed; since we almost certainly have some
                        # writes to do, the caller of commit() will expect that
                        # they actually get done, even if they didn't actually
                        # block or yield to wait for them!  (c.f. property
                        # store writes.)
                        newBlock = self._sqlTxn.commandBlock()
                        block.end()
                        block = newBlock
                        sp = self._savepoint()
                    else:
                        end()
                else:
                    yield sp.release(block)
                    block.end()
                    returnValue(result)
        except AlreadyFinishedError:
            # Interfering agents may disrupt our plans by calling abort()
            # halfway through trying to do this subtransaction.  In that case -
            # and only that case - acquire() or release() or commandBlock() may
            # raise an AlreadyFinishedError (either synchronously, or in the
            # case of the first two, possibly asynchronously as well).  We can
            # safely ignore this error, because it can't have any effect on
            # what gets written; our caller will just get told that it failed
            # in a way they have to be prepared for anyway.
            end()


    @inlineCallbacks
    def execSQL(self, *a, **kw):
        """
        Execute some SQL (delegate to L{IAsyncTransaction}).
        """
        if self._stats:
            statsContext = self._stats.startStatement(a[0], a[1] if len(a) > 1 else ())
        self.currentStatement = a[0]
        if self._store.logTransactionWaits and a[0].split(" ", 1)[0].lower() in ("insert", "update", "delete",):
            self.iudCount += 1
        self.statementCount += 1
        if self._store.logLabels:
            a = ("-- Label: %s\n" % (self._label.replace("%", "%%"),) + a[0],) + a[1:]
        if self._store.logSQL:
            log.error("SQL: {a!r} {kw!r}", a=a, kw=kw)
        results = None
        try:
            results = (yield self._sqlTxn.execSQL(*a, **kw))
        finally:
            self.currentStatement = None
            if self._stats:
                self._stats.endStatement(statsContext, results)
        returnValue(results)


    @inlineCallbacks
    def execSQLBlock(self, sql):
        """
        Execute SQL statements parsed by splitSQLString.
        FIXME: temporary measure for handling large schema upgrades. This should NOT be used
        for regular SQL operations - only upgrades.
        """
        for stmt in splitSQLString(sql):
            yield self.execSQL(stmt)


    def commit(self):
        """
        Commit the transaction and execute any post-commit hooks.
        """

        # Do stats logging as a postCommit because there might be some pending preCommit SQL we want to log
        if self._stats:
            self.postCommit(self.statsReport)
        return self._sqlTxn.commit()


    def abort(self):
        """
        Abort the transaction.
        """
        return self._sqlTxn.abort()


    def timeout(self):
        """
        Abort the transaction due to time out.
        """
        self.timedout = True
        return self.abort()


    def statsReport(self):
        """
        Print the stats report and record log items
        """
        sql_statements, sql_rows, sql_time = self._stats.printReport()
        self.logItems["sql-s"] = str(sql_statements)
        self.logItems["sql-r"] = str(sql_rows)
        self.logItems["sql-t"] = "%.1f" % (sql_time,)


    def _oldEventsBase(self, limit):
        ch = schema.CALENDAR_HOME
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        tr = schema.TIME_RANGE
        kwds = {}
        if limit:
            kwds["Limit"] = limit
        return Select(
            [
                ch.OWNER_UID,
                cb.CALENDAR_RESOURCE_NAME,
                co.RESOURCE_NAME,
                Max(tr.END_DATE)
            ],
            From=ch.join(co).join(cb).join(tr),
            Where=(
                ch.RESOURCE_ID == cb.CALENDAR_HOME_RESOURCE_ID).And(
                tr.CALENDAR_OBJECT_RESOURCE_ID == co.RESOURCE_ID).And(
                cb.CALENDAR_RESOURCE_ID == tr.CALENDAR_RESOURCE_ID).And(
                cb.BIND_MODE == _BIND_MODE_OWN
            ),
            GroupBy=(
                ch.OWNER_UID,
                cb.CALENDAR_RESOURCE_NAME,
                co.RESOURCE_NAME
            ),
            Having=Max(tr.END_DATE) < Parameter("CutOff"),
            OrderBy=Max(tr.END_DATE),
            **kwds
        )


    def eventsOlderThan(self, cutoff, batchSize=None):
        """
        Return up to the oldest batchSize events which exist completely earlier
        than "cutoff" (DateTime)

        Returns a deferred to a list of (uid, calendarName, eventName, maxDate)
        tuples.
        """

        # Make sure cut off is after any lower limit truncation in the DB
        if config.FreeBusyIndexLowerLimitDays:
            truncateLowerLimit = DateTime.getToday()
            truncateLowerLimit.offsetDay(-config.FreeBusyIndexLowerLimitDays)
            if cutoff < truncateLowerLimit:
                raise ValueError("Cannot query events older than %s" % (truncateLowerLimit.getText(),))

        kwds = {"CutOff": pyCalendarTodatetime(cutoff)}
        return self._oldEventsBase(batchSize).on(self, **kwds)


    @inlineCallbacks
    def removeOldEvents(self, cutoff, batchSize=None):
        """
        Remove up to batchSize events older than "cutoff" and return how
        many were removed.
        """

        # Make sure cut off is after any lower limit truncation in the DB
        if config.FreeBusyIndexLowerLimitDays:
            truncateLowerLimit = DateTime.getToday()
            truncateLowerLimit.offsetDay(-config.FreeBusyIndexLowerLimitDays)
            if cutoff < truncateLowerLimit:
                raise ValueError("Cannot query events older than %s" % (truncateLowerLimit.getText(),))

        results = (yield self.eventsOlderThan(cutoff, batchSize=batchSize))
        count = 0
        for uid, calendarName, eventName, _ignore_maxDate in results:
            home = (yield self.calendarHomeWithUID(uid))
            calendar = (yield home.childWithName(calendarName))
            resource = (yield calendar.objectResourceWithName(eventName))
            yield resource.remove(implicitly=False)
            count += 1
        returnValue(count)


    def orphanedAttachments(self, uuid=None, batchSize=None):
        """
        Find attachments no longer referenced by any events.

        Returns a deferred to a list of (calendar_home_owner_uid, quota used, total orphan size, total orphan count) tuples.
        """
        kwds = {}
        if uuid:
            kwds["uuid"] = uuid

        options = {}
        if batchSize:
            options["Limit"] = batchSize

        ch = schema.CALENDAR_HOME
        chm = schema.CALENDAR_HOME_METADATA
        co = schema.CALENDAR_OBJECT
        at = schema.ATTACHMENT

        where = (co.DROPBOX_ID == None).And(at.DROPBOX_ID != ".")
        if uuid:
            where = where.And(ch.OWNER_UID == Parameter('uuid'))

        return Select(
            [ch.OWNER_UID, chm.QUOTA_USED_BYTES, Sum(at.SIZE), Count(at.DROPBOX_ID)],
            From=at.join(
                co, at.DROPBOX_ID == co.DROPBOX_ID, "left outer").join(
                ch, at.CALENDAR_HOME_RESOURCE_ID == ch.RESOURCE_ID).join(
                chm, ch.RESOURCE_ID == chm.RESOURCE_ID
            ),
            Where=where,
            GroupBy=(ch.OWNER_UID, chm.QUOTA_USED_BYTES),
            **options
        ).on(self, **kwds)


    @inlineCallbacks
    def removeOrphanedAttachments(self, uuid=None, batchSize=None):
        """
        Remove attachments that no longer have any references to them
        """

        # TODO: see if there is a better way to import Attachment
        from txdav.caldav.datastore.sql import DropBoxAttachment

        kwds = {}
        if uuid:
            kwds["uuid"] = uuid

        options = {}
        if batchSize:
            options["Limit"] = batchSize

        ch = schema.CALENDAR_HOME
        co = schema.CALENDAR_OBJECT
        at = schema.ATTACHMENT

        sfrom = at.join(co, at.DROPBOX_ID == co.DROPBOX_ID, "left outer")
        where = (co.DROPBOX_ID == None).And(at.DROPBOX_ID != ".")
        if uuid:
            sfrom = sfrom.join(ch, at.CALENDAR_HOME_RESOURCE_ID == ch.RESOURCE_ID)
            where = where.And(ch.OWNER_UID == Parameter('uuid'))

        results = (yield Select(
            [at.DROPBOX_ID, at.PATH],
            From=sfrom,
            Where=where,
            **options
        ).on(self, **kwds))

        count = 0
        for dropboxID, path in results:
            attachment = (yield DropBoxAttachment.load(self, dropboxID, path))
            yield attachment.remove()
            count += 1
        returnValue(count)


    def oldDropboxAttachments(self, cutoff, uuid):
        """
        Find managed attachments attached to only events whose last instance is older than the specified cut-off.

        Returns a deferred to a list of (calendar_home_owner_uid, quota used, total old size, total old count) tuples.
        """
        kwds = {"CutOff": pyCalendarTodatetime(cutoff)}
        if uuid:
            kwds["uuid"] = uuid

        ch = schema.CALENDAR_HOME
        chm = schema.CALENDAR_HOME_METADATA
        co = schema.CALENDAR_OBJECT
        tr = schema.TIME_RANGE
        at = schema.ATTACHMENT

        where = at.DROPBOX_ID.In(Select(
            [at.DROPBOX_ID],
            From=at.join(co, at.DROPBOX_ID == co.DROPBOX_ID, "inner").join(
                tr, co.RESOURCE_ID == tr.CALENDAR_OBJECT_RESOURCE_ID
            ),
            GroupBy=(at.DROPBOX_ID,),
            Having=Max(tr.END_DATE) < Parameter("CutOff"),
        ))

        if uuid:
            where = where.And(ch.OWNER_UID == Parameter('uuid'))

        return Select(
            [ch.OWNER_UID, chm.QUOTA_USED_BYTES, Sum(at.SIZE), Count(at.DROPBOX_ID)],
            From=at.join(
                ch, at.CALENDAR_HOME_RESOURCE_ID == ch.RESOURCE_ID).join(
                chm, ch.RESOURCE_ID == chm.RESOURCE_ID
            ),
            Where=where,
            GroupBy=(ch.OWNER_UID, chm.QUOTA_USED_BYTES),
        ).on(self, **kwds)


    @inlineCallbacks
    def removeOldDropboxAttachments(self, cutoff, uuid, batchSize=None):
        """
        Remove dropbox attachments attached to events in the past.
        """

        # TODO: see if there is a better way to import Attachment
        from txdav.caldav.datastore.sql import DropBoxAttachment

        kwds = {"CutOff": pyCalendarTodatetime(cutoff)}
        if uuid:
            kwds["uuid"] = uuid

        options = {}
        if batchSize:
            options["Limit"] = batchSize

        ch = schema.CALENDAR_HOME
        co = schema.CALENDAR_OBJECT
        tr = schema.TIME_RANGE
        at = schema.ATTACHMENT

        sfrom = at.join(
            co, at.DROPBOX_ID == co.DROPBOX_ID, "inner").join(
            tr, co.RESOURCE_ID == tr.CALENDAR_OBJECT_RESOURCE_ID
        )
        where = None
        if uuid:
            sfrom = sfrom.join(ch, at.CALENDAR_HOME_RESOURCE_ID == ch.RESOURCE_ID)
            where = (ch.OWNER_UID == Parameter('uuid'))

        results = (yield Select(
            [at.DROPBOX_ID, at.PATH, ],
            From=sfrom,
            Where=where,
            GroupBy=(at.DROPBOX_ID, at.PATH,),
            Having=Max(tr.END_DATE) < Parameter("CutOff"),
            **options
        ).on(self, **kwds))

        count = 0
        for dropboxID, path in results:
            attachment = (yield DropBoxAttachment.load(self, dropboxID, path))
            yield attachment.remove()
            count += 1
        returnValue(count)


    def oldManagedAttachments(self, cutoff, uuid):
        """
        Find managed attachments attached to only events whose last instance is older than the specified cut-off.

        Returns a deferred to a list of (calendar_home_owner_uid, quota used, total old size, total old count) tuples.
        """
        kwds = {"CutOff": pyCalendarTodatetime(cutoff)}
        if uuid:
            kwds["uuid"] = uuid

        ch = schema.CALENDAR_HOME
        chm = schema.CALENDAR_HOME_METADATA
        tr = schema.TIME_RANGE
        at = schema.ATTACHMENT
        atco = schema.ATTACHMENT_CALENDAR_OBJECT

        where = at.ATTACHMENT_ID.In(Select(
            [at.ATTACHMENT_ID],
            From=at.join(
                atco, at.ATTACHMENT_ID == atco.ATTACHMENT_ID, "inner").join(
                tr, atco.CALENDAR_OBJECT_RESOURCE_ID == tr.CALENDAR_OBJECT_RESOURCE_ID
            ),
            GroupBy=(at.ATTACHMENT_ID,),
            Having=Max(tr.END_DATE) < Parameter("CutOff"),
        ))

        if uuid:
            where = where.And(ch.OWNER_UID == Parameter('uuid'))

        return Select(
            [ch.OWNER_UID, chm.QUOTA_USED_BYTES, Sum(at.SIZE), Count(at.ATTACHMENT_ID)],
            From=at.join(
                ch, at.CALENDAR_HOME_RESOURCE_ID == ch.RESOURCE_ID).join(
                chm, ch.RESOURCE_ID == chm.RESOURCE_ID
            ),
            Where=where,
            GroupBy=(ch.OWNER_UID, chm.QUOTA_USED_BYTES),
        ).on(self, **kwds)


    @inlineCallbacks
    def removeOldManagedAttachments(self, cutoff, uuid, batchSize=None):
        """
        Remove attachments attached to events in the past.
        """

        # TODO: see if there is a better way to import Attachment
        from txdav.caldav.datastore.sql import ManagedAttachment

        kwds = {"CutOff": pyCalendarTodatetime(cutoff)}
        if uuid:
            kwds["uuid"] = uuid

        options = {}
        if batchSize:
            options["Limit"] = batchSize

        ch = schema.CALENDAR_HOME
        tr = schema.TIME_RANGE
        at = schema.ATTACHMENT
        atco = schema.ATTACHMENT_CALENDAR_OBJECT

        sfrom = atco.join(
            at, atco.ATTACHMENT_ID == at.ATTACHMENT_ID, "inner").join(
            tr, atco.CALENDAR_OBJECT_RESOURCE_ID == tr.CALENDAR_OBJECT_RESOURCE_ID
        )
        where = None
        if uuid:
            sfrom = sfrom.join(ch, at.CALENDAR_HOME_RESOURCE_ID == ch.RESOURCE_ID)
            where = (ch.OWNER_UID == Parameter('uuid'))

        results = (yield Select(
            [atco.ATTACHMENT_ID, atco.MANAGED_ID, ],
            From=sfrom,
            Where=where,
            GroupBy=(atco.ATTACHMENT_ID, atco.MANAGED_ID,),
            Having=Max(tr.END_DATE) < Parameter("CutOff"),
            **options
        ).on(self, **kwds))

        count = 0
        for _ignore, managedID in results:
            attachment = (yield ManagedAttachment.load(self, None, managedID))
            yield attachment.remove()
            count += 1
        returnValue(count)


    def acquireUpgradeLock(self):
        return DatabaseLock().on(self)


    def releaseUpgradeLock(self):
        return DatabaseUnlock().on(self)


    @inlineCallbacks
    def deleteRevisionsBefore(self, minRevision):
        """
        Delete revisions before minRevision
        """
        # Delete old revisions
        for table in (
            schema.CALENDAR_OBJECT_REVISIONS,
            schema.NOTIFICATION_OBJECT_REVISIONS,
            schema.ADDRESSBOOK_OBJECT_REVISIONS,
        ):
            yield Delete(
                From=table,
                Where=(table.REVISION < minRevision)
            ).on(self)

        # get groups where this object was once a member and version info
        aboMembers = schema.ABO_MEMBERS
        groupRows = yield Select(
            [aboMembers.GROUP_ID,
             aboMembers.MEMBER_ID,
             aboMembers.REMOVED,
             aboMembers.REVISION],
            From=aboMembers,
        ).on(self)

        # group results by group, member, and revisionInfo
        groupIDToMemberIDMap = {}
        for groupRow in groupRows:
            groupID, memberID, removed, revision = groupRow
            revisionInfo = [removed, revision]
            if groupID not in groupIDToMemberIDMap:
                groupIDToMemberIDMap[groupID] = {}
            memberIDToRevisionsMap = groupIDToMemberIDMap[groupID]
            if memberID not in memberIDToRevisionsMap:
                memberIDToRevisionsMap[memberID] = []
            revisionInfoList = memberIDToRevisionsMap[memberID]
            revisionInfoList.append(revisionInfo)

        # go though list an delete old revisions, leaving at least one unremoved member
        for groupID, memberIDToRevisionsMap in groupIDToMemberIDMap.iteritems():
            for memberID, revisionInfoList in memberIDToRevisionsMap.iteritems():
                revisionInfosToRemove = []
                revisionInfosToSave = []
                for revisionInfo in revisionInfoList:
                    if revisionInfo[1] < minRevision:
                        revisionInfosToRemove.append(revisionInfo)
                    else:
                        revisionInfosToSave.append(revisionInfo)

                # save at least one revision
                if revisionInfosToRemove and len(revisionInfosToRemove) == len(revisionInfoList):
                    maxRevisionInfoToRemove = max(revisionInfosToRemove, key=lambda info: info[1])
                    revisionInfosToSave.append(maxRevisionInfoToRemove)
                    revisionInfosToRemove.remove(maxRevisionInfoToRemove)

                # get rid of extra removed member revisions
                if revisionInfosToSave and max(revisionInfosToSave, key=lambda info: not info[0])[0]:
                    revisionInfosToRemove += revisionInfosToSave

                if revisionInfosToRemove:
                    revisionsToRemove = [revisionInfoToRemove[1] for revisionInfoToRemove in revisionInfosToRemove]
                    yield Delete(
                        aboMembers,
                        Where=(aboMembers.GROUP_ID == groupID).And(
                            aboMembers.MEMBER_ID == memberID).And(
                                aboMembers.REVISION.In(Parameter("revisionsToRemove", len(revisionsToRemove)))
                            )
                    ).on(self, revisionsToRemove=revisionsToRemove)


    @classproperty
    def _orphanedInboxItemsInHomeIDQuery(cls):
        """
        DAL query to select inbox items that refer to nonexistent events in a
        given home identified by the home resource ID.
        """
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        return Select(
            [co.RESOURCE_NAME],
            From=co.join(cb),
            Where=(
                cb.CALENDAR_HOME_RESOURCE_ID == Parameter("homeID")).And(
                cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                cb.BIND_MODE == _BIND_MODE_OWN).And(
                cb.CALENDAR_RESOURCE_NAME == 'inbox').And(
                co.ICALENDAR_UID.NotIn(
                    Select(
                        [co.ICALENDAR_UID],
                        From=co.join(cb),
                        Where=(
                            cb.CALENDAR_HOME_RESOURCE_ID == Parameter("homeID")).And(
                            cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                            cb.BIND_MODE == _BIND_MODE_OWN).And(
                            cb.CALENDAR_RESOURCE_NAME != 'inbox')
                    )
                )
            ),
        )


    @inlineCallbacks
    def orphanedInboxItemsInHomeID(self, homeID):
        """
        Find inbox item names that refer to nonexistent events in a given home.

        Returns a deferred to a list of orphaned inbox item names
        """
        rows = yield self._orphanedInboxItemsInHomeIDQuery.on(self, homeID=homeID)
        names = [row[0] for row in rows]
        returnValue(names)


    @classproperty
    def _inboxItemsInHomeIDForEventsBeforeCutoffQuery(cls):
        """
        DAL query to select inbox items that refer to events in a before a
        given date.
        """
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        tr = schema.TIME_RANGE
        return Select(
            [co.RESOURCE_NAME],
            From=co.join(cb),
            Where=(
                cb.CALENDAR_HOME_RESOURCE_ID == Parameter("homeID")).And(
                cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                cb.BIND_MODE == _BIND_MODE_OWN).And(
                cb.CALENDAR_RESOURCE_NAME == 'inbox').And(
                co.ICALENDAR_UID.In(
                    Select(
                        [co.ICALENDAR_UID],
                        From=tr.join(co.join(cb)),
                        Where=(
                            cb.CALENDAR_HOME_RESOURCE_ID == Parameter("homeID")).And(
                            cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                            cb.BIND_MODE == _BIND_MODE_OWN).And(
                            cb.CALENDAR_RESOURCE_NAME != 'inbox').And(
                            tr.CALENDAR_OBJECT_RESOURCE_ID == co.RESOURCE_ID).And(
                            tr.END_DATE < Parameter("cutoff"))
                    )
                )
            ),
        )


    @inlineCallbacks
    def listInboxItemsInHomeForEventsBefore(self, homeID, cutoff):
        """
        return a list of inbox item names that refer to events before a given
        date in a given home.

        Returns a deferred to a list of orphaned inbox item names
        """
        rows = yield self._inboxItemsInHomeIDForEventsBeforeCutoffQuery.on(
            self, homeID=homeID, cutoff=cutoff)
        names = [row[0] for row in rows]
        returnValue(names)


    @classproperty
    def _inboxItemsInHomeIDCreatedBeforeCutoffQuery(cls):
        """
        DAL query to select inbox items created before a given date.
        """
        co = schema.CALENDAR_OBJECT
        cb = schema.CALENDAR_BIND
        return Select(
            [co.RESOURCE_NAME],
            From=co.join(cb),
            Where=(
                cb.CALENDAR_HOME_RESOURCE_ID == Parameter("homeID")).And(
                cb.CALENDAR_RESOURCE_ID == co.CALENDAR_RESOURCE_ID).And(
                cb.BIND_MODE == _BIND_MODE_OWN).And(
                cb.CALENDAR_RESOURCE_NAME == 'inbox').And(
                co.CREATED < Parameter("cutoff")),
        )


    @inlineCallbacks
    def listInboxItemsInHomeCreatedBefore(self, homeID, cutoff):
        """
        return a list of inbox item names that creaed before a given date in a
        given home.

        Returns a deferred to a list of orphaned inbox item names
        """
        rows = yield self._inboxItemsInHomeIDCreatedBeforeCutoffQuery.on(
            self, homeID=homeID, cutoff=cutoff)
        names = [row[0] for row in rows]
        returnValue(names)



class _EmptyCacher(object):

    def set(self, key, value):
        return succeed(True)


    def get(self, key, withIdentifier=False):
        return succeed(None)


    def delete(self, key):
        return succeed(True)



class SharingHomeMixIn(object):
    """
    Common class for CommonHome to implement sharing operations
    """

    @inlineCallbacks
    def acceptShare(self, shareUID, summary=None):
        """
        This share is being accepted.
        """

        shareeView = yield self.anyObjectWithShareUID(shareUID)
        if shareeView is not None:
            yield shareeView.acceptShare(summary)

        returnValue(shareeView)


    @inlineCallbacks
    def declineShare(self, shareUID):
        """
        This share is being declined.
        """

        shareeView = yield self.anyObjectWithShareUID(shareUID)
        if shareeView is not None:
            yield shareeView.declineShare()

        returnValue(shareeView is not None)


    #
    # External (cross-pod) sharing - entry point is the sharee's home collection.
    #
    @inlineCallbacks
    def processExternalInvite(
        self, ownerUID, ownerRID, ownerName, shareUID, bindMode, summary,
        copy_invite_properties, supported_components=None
    ):
        """
        External invite received.
        """

        # Get the owner home - create external one if not present
        ownerHome = yield self._txn.homeWithUID(
            self._homeType, ownerUID, create=True
        )
        if ownerHome is None or not ownerHome.external():
            raise ExternalShareFailed("Invalid owner UID: {}".format(ownerUID))

        # Try to find owner calendar via its external id
        ownerView = yield ownerHome.childWithExternalID(ownerRID)
        if ownerView is None:
            try:
                ownerView = yield ownerHome.createChildWithName(
                    ownerName, externalID=ownerRID
                )
            except HomeChildNameAlreadyExistsError:
                # This is odd - it means we possibly have a left over sharer
                # collection which the sharer likely removed and re-created
                # with the same name but now it has a different externalID and
                # is not found by the initial query. What we do is check to see
                # whether any shares still reference the old ID - if they do we
                # are hosed. If not, we can remove the old item and create a new one.
                oldOwnerView = yield ownerHome.childWithName(ownerName)
                invites = yield oldOwnerView.sharingInvites()
                if len(invites) != 0:
                    log.error(
                        "External invite collection name is present with a "
                        "different externalID and still has shares"
                    )
                    raise
                log.error(
                    "External invite collection name is present with a "
                    "different externalID - trying to fix"
                )
                yield ownerHome.removeExternalChild(oldOwnerView)
                ownerView = yield ownerHome.createChildWithName(
                    ownerName, externalID=ownerRID
                )

            if (
                supported_components is not None and
                hasattr(ownerView, "setSupportedComponents")
            ):
                yield ownerView.setSupportedComponents(supported_components)

        # Now carry out the share operation
        if bindMode == _BIND_MODE_DIRECT:
            shareeView = yield ownerView.directShareWithUser(
                self.uid(), shareName=shareUID
            )
        else:
            shareeView = yield ownerView.inviteUIDToShare(
                self.uid(), bindMode, summary, shareName=shareUID
            )

        shareeView.setInviteCopyProperties(copy_invite_properties)


    @inlineCallbacks
    def processExternalUninvite(self, ownerUID, ownerRID, shareUID):
        """
        External invite received.
        """

        # Get the owner home
        ownerHome = yield self._txn.homeWithUID(self._homeType, ownerUID)
        if ownerHome is None or not ownerHome.external():
            raise ExternalShareFailed("Invalid owner UID: {}".format(ownerUID))

        # Try to find owner calendar via its external id
        ownerView = yield ownerHome.childWithExternalID(ownerRID)
        if ownerView is None:
            raise ExternalShareFailed("Invalid share ID: {}".format(shareUID))

        # Now carry out the share operation
        yield ownerView.uninviteUIDFromShare(self.uid())

        # See if there are any references to the external share. If not,
        # remove it
        invites = yield ownerView.sharingInvites()
        if len(invites) == 0:
            yield ownerHome.removeExternalChild(ownerView)


    @inlineCallbacks
    def processExternalReply(
        self, ownerUID, shareeUID, shareUID, bindStatus, summary=None
    ):
        """
        External invite received.
        """

        # Make sure the shareeUID and shareUID match

        # Get the owner home - create external one if not present
        shareeHome = yield self._txn.homeWithUID(self._homeType, shareeUID)
        if shareeHome is None or not shareeHome.external():
            raise ExternalShareFailed(
                "Invalid sharee UID: {}".format(shareeUID)
            )

        # Try to find owner calendar via its external id
        shareeView = yield shareeHome.anyObjectWithShareUID(shareUID)
        if shareeView is None:
            raise ExternalShareFailed("Invalid share UID: {}".format(shareUID))

        # Now carry out the share operation
        if bindStatus == _BIND_STATUS_ACCEPTED:
            yield shareeHome.acceptShare(shareUID, summary)
        elif bindStatus == _BIND_STATUS_DECLINED:
            if shareeView.direct():
                yield shareeView.deleteShare()
            else:
                yield shareeHome.declineShare(shareUID)



class CommonHome(SharingHomeMixIn):
    log = Logger()

    # All these need to be initialized by derived classes for each store type
    _homeType = None
    _homeTable = None
    _homeMetaDataTable = None
    _externalClass = None
    _childClass = None
    _childTable = None
    _notifierPrefix = None

    _dataVersionKey = None
    _dataVersionValue = None

    _cacher = None  # Initialize in derived classes

    @classmethod
    @inlineCallbacks
    def makeClass(cls, transaction, ownerUID, no_cache=False, authzUID=None):
        """
        Build the actual home class taking into account the possibility that we might need to
        switch in the external version of the class.

        @param transaction: transaction
        @type transaction: L{CommonStoreTransaction}
        @param ownerUID: owner UID of home to load
        @type ownerUID: C{str}
        @param no_cache: should cached query be used
        @type no_cache: C{bool}
        """
        home = cls(transaction, ownerUID, authzUID=authzUID)
        actualHome = yield home.initFromStore(no_cache)
        returnValue(actualHome)


    def __init__(self, transaction, ownerUID, authzUID=None):
        self._txn = transaction
        self._ownerUID = ownerUID
        self._authzUID = authzUID
        if self._authzUID is None:
            if self._txn._authz_uid is not None:
                self._authzUID = self._txn._authz_uid
            else:
                self._authzUID = self._ownerUID
        self._resourceID = None
        self._status = _HOME_STATUS_NORMAL
        self._dataVersion = None
        self._childrenLoaded = False
        self._children = {}
        self._notifiers = None
        self._quotaUsedBytes = None
        self._created = None
        self._modified = None
        self._syncTokenRevision = None
        if transaction._disableCache:
            self._cacher = _EmptyCacher()


    @classmethod
    def _register(cls, homeType):
        """
        Register a L{CommonHome} subclass as its respective home type constant
        with L{CommonStoreTransaction}.
        """
        cls._homeType = homeType
        CommonStoreTransaction._homeClass[cls._homeType] = cls


    def quotaAllowedBytes(self):
        return self._txn.store().quota


    @classproperty
    def _homeColumnsFromOwnerQuery(cls):
        home = cls._homeSchema
        return Select(
            cls.homeColumns(),
            From=home,
            Where=home.OWNER_UID == Parameter("ownerUID")
        )


    @classproperty
    def _ownerFromResourceID(cls):
        home = cls._homeSchema
        return Select([home.OWNER_UID],
                      From=home,
                      Where=home.RESOURCE_ID == Parameter("resourceID"))


    @classproperty
    def _metaDataQuery(cls):
        metadata = cls._homeMetaDataSchema
        return Select(cls.metadataColumns(),
                      From=metadata,
                      Where=metadata.RESOURCE_ID == Parameter("resourceID"))


    @classmethod
    def homeColumns(cls):
        """
        Return a list of column names to retrieve when doing an ownerUID->home lookup.
        """

        # Common behavior is to have created and modified

        return (
            cls._homeSchema.RESOURCE_ID,
            cls._homeSchema.OWNER_UID,
            cls._homeSchema.STATUS,
        )


    @classmethod
    def homeAttributes(cls):
        """
        Return a list of attributes names to map L{homeColumns} to.
        """

        # Common behavior is to have created and modified

        return (
            "_resourceID",
            "_ownerUID",
            "_status",
        )


    @classmethod
    def metadataColumns(cls):
        """
        Return a list of column name for retrieval of metadata. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        # Common behavior is to have created and modified

        return (
            cls._homeMetaDataSchema.CREATED,
            cls._homeMetaDataSchema.MODIFIED,
        )


    @classmethod
    def metadataAttributes(cls):
        """
        Return a list of attribute names for retrieval of metadata. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        # Common behavior is to have created and modified

        return (
            "_created",
            "_modified",
        )


    @inlineCallbacks
    def initFromStore(self, no_cache=False):
        """
        Initialize this object from the store. We read in and cache all the
        extra meta-data from the DB to avoid having to do DB queries for those
        individually later.
        """
        result = yield self._cacher.get(self._ownerUID)
        if result is None:
            result = yield self._homeColumnsFromOwnerQuery.on(self._txn, ownerUID=self._ownerUID)
            if result:
                result = result[0]
                if not no_cache:
                    yield self._cacher.set(self._ownerUID, result)

        if result:
            for attr, value in zip(self.homeAttributes(), result):
                setattr(self, attr, value)

            # STOP! If the status is external we need to convert this object to a CommonHomeExternal class which will
            # have the right behavior for non-hosted external users.
            if self._status == _HOME_STATUS_EXTERNAL:
                actualHome = self._externalClass(self._txn, self._ownerUID, self._resourceID)
            else:
                actualHome = self
            yield actualHome.initMetaDataFromStore()
            yield actualHome._loadPropertyStore()

            for factory_type, factory in self._txn._notifierFactories.items():
                actualHome.addNotifier(factory_type, factory.newNotifier(actualHome))

            returnValue(actualHome)
        else:
            returnValue(None)


    @inlineCallbacks
    def initMetaDataFromStore(self):
        """
        Load up the metadata and property store
        """

        queryCacher = self._txn._queryCacher
        if queryCacher:
            # Get cached copy
            cacheKey = queryCacher.keyForHomeMetaData(self._resourceID)
            data = yield queryCacher.get(cacheKey)
        else:
            data = None
        if data is None:
            # Don't have a cached copy
            data = (yield self._metaDataQuery.on(self._txn, resourceID=self._resourceID))[0]
            if queryCacher:
                # Cache the data
                yield queryCacher.setAfterCommit(self._txn, cacheKey, data)

        for attr, value in zip(self.metadataAttributes(), data):
            setattr(self, attr, value)


    @classmethod
    @inlineCallbacks
    def listHomes(cls, txn):
        """
        Retrieve the owner UIDs of all existing homes.

        @return: an iterable of C{str}s.
        """
        rows = yield Select(
            [cls._homeSchema.OWNER_UID],
            From=cls._homeSchema,
        ).on(txn)
        rids = [row[0] for row in rows]
        returnValue(rids)


    @classmethod
    @inlineCallbacks
    def homeWithUID(cls, txn, uid, create=False, authzUID=None):
        """
        @param uid: I'm going to assume uid is utf-8 encoded bytes
        """
        homeObject = yield cls.makeClass(txn, uid, authzUID=authzUID)
        if homeObject is not None:
            returnValue(homeObject)
        else:
            if not create:
                returnValue(None)

            # Determine if the user is local or external
            record = yield txn.directoryService().recordWithUID(uid.decode("utf-8"))
            if record is None:
                raise DirectoryRecordNotFoundError("Cannot create home for UID since no directory record exists: {}".format(uid))

            state = _HOME_STATUS_NORMAL if record.thisServer() else _HOME_STATUS_EXTERNAL

            # Use savepoint so we can do a partial rollback if there is a race condition
            # where this row has already been inserted
            savepoint = SavepointAction("homeWithUID")
            yield savepoint.acquire(txn)

            if cls._dataVersionValue is None:
                cls._dataVersionValue = yield txn.calendarserverValue(cls._dataVersionKey)
            try:
                resourceid = (yield Insert(
                    {
                        cls._homeSchema.OWNER_UID: uid,
                        cls._homeSchema.STATUS: state,
                        cls._homeSchema.DATAVERSION: cls._dataVersionValue,
                    },
                    Return=cls._homeSchema.RESOURCE_ID
                ).on(txn))[0][0]
                yield Insert({cls._homeMetaDataSchema.RESOURCE_ID: resourceid}).on(txn)
            except Exception:  # FIXME: Really want to trap the pg.DatabaseError but in a non-DB specific manner
                yield savepoint.rollback(txn)

                # Retry the query - row may exist now, if not re-raise
                homeObject = yield cls.makeClass(txn, uid, authzUID=authzUID)
                if homeObject:
                    returnValue(homeObject)
                else:
                    raise
            else:
                yield savepoint.release(txn)

                # Note that we must not cache the owner_uid->resource_id
                # mapping in _cacher when creating as we don't want that to appear
                # until AFTER the commit
                home = yield cls.makeClass(txn, uid, no_cache=True, authzUID=authzUID)
                yield home.createdHome()
                returnValue(home)


    @classmethod
    @inlineCallbacks
    def homeUIDWithResourceID(cls, txn, rid):
        rows = (yield cls._ownerFromResourceID.on(txn, resourceID=rid))
        if rows:
            returnValue(rows[0][0])
        else:
            returnValue(None)


    def __repr__(self):
        return "<%s: %s, %s>" % (self.__class__.__name__, self._resourceID, self._ownerUID)


    def id(self):
        """
        Retrieve the store identifier for this home.

        @return: store identifier.
        @rtype: C{int}
        """
        return self._resourceID


    def uid(self):
        """
        Retrieve the unique identifier for this home.

        @return: a string.
        """
        return self._ownerUID


    def authzuid(self):
        """
        Retrieve the unique identifier of the user accessing the data in this home.

        @return: a string.
        """
        return self._authzUID


    def external(self):
        """
        Is this an external home.

        @return: a string.
        """
        return self._status == _HOME_STATUS_EXTERNAL


    def purging(self):
        """
        Is this an external home.

        @return: a string.
        """
        return self._status == _HOME_STATUS_PURGING


    @inlineCallbacks
    def purge(self):
        """
        Mark this home as being purged.
        """
        # Only if normal
        if self._status == _HOME_STATUS_NORMAL:
            yield Update(
                {self._homeSchema.STATUS: _HOME_STATUS_PURGING},
                Where=(self._homeSchema.RESOURCE_ID == self._resourceID),
            ).on(self._txn)
            self._status = _HOME_STATUS_PURGING
            yield self._cacher.delete(self._ownerUID)


    def transaction(self):
        return self._txn


    def directoryService(self):
        return self._txn.store().directoryService()


    def directoryRecord(self):
        return self.directoryService().recordWithUID(self.uid().decode("utf-8"))


    @inlineCallbacks
    def invalidateQueryCache(self):
        queryCacher = self._txn._queryCacher
        if queryCacher is not None:
            cacheKey = queryCacher.keyForHomeMetaData(self._resourceID)
            yield queryCacher.invalidateAfterCommit(self._txn, cacheKey)


    @classproperty
    def _dataVersionQuery(cls):
        ch = cls._homeSchema
        return Select(
            [ch.DATAVERSION], From=ch,
            Where=ch.RESOURCE_ID == Parameter("resourceID")
        )


    @inlineCallbacks
    def dataVersion(self):
        if self._dataVersion is None:
            self._dataVersion = (yield self._dataVersionQuery.on(
                self._txn, resourceID=self._resourceID))[0][0]
        returnValue(self._dataVersion)


    def name(self):
        """
        Implement L{IDataStoreObject.name} to return the uid.
        """
        return self.uid()


    @inlineCallbacks
    def children(self):
        """
        Retrieve children contained in this home.
        """
        x = []
        names = yield self.listChildren()
        for name in names:
            x.append((yield self.childWithName(name)))
        returnValue(x)


    @inlineCallbacks
    def loadChildren(self):
        """
        Load and cache all children - Depth:1 optimization
        """
        results = (yield self._childClass.loadAllObjects(self))
        for result in results:
            self._children[result.name()] = result
            self._children[result._resourceID] = result
        self._childrenLoaded = True
        returnValue(results)


    def listChildren(self):
        """
        Retrieve the names of the children in this home.

        @return: an iterable of C{str}s.
        """

        if self._childrenLoaded:
            return succeed([k for k in self._children.keys() if isinstance(k, str)])
        else:
            return self._childClass.listObjects(self)


    @memoizedKey("name", "_children")
    def childWithName(self, name):
        """
        Retrieve the child with the given C{name} contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child exists.
        """
        return self._childClass.objectWithName(self, name)


    def anyObjectWithShareUID(self, shareUID):
        """
        Retrieve the child accepted or otherwise with the given bind identifier contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child exists.
        """
        return self._childClass.objectWithName(self, shareUID, accepted=None)


    @memoizedKey("resourceID", "_children")
    def childWithID(self, resourceID):
        """
        Retrieve the child with the given C{resourceID} contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child exists.
        """
        return self._childClass.objectWithID(self, resourceID)


    def childWithExternalID(self, externalID):
        """
        Retrieve the child with the given C{externalID} contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child exists.
        """
        return self._childClass.objectWithExternalID(self, externalID)


    def allChildWithID(self, resourceID):
        """
        Retrieve the child with the given C{resourceID} contained in this
        home.

        @param name: a string.
        @return: an L{ICalendar} or C{None} if no such child exists.
        """
        return self._childClass.objectWithID(self, resourceID, accepted=None)


    @inlineCallbacks
    def createChildWithName(self, name, externalID=None):
        if name.startswith("."):
            raise HomeChildNameNotAllowedError(name)

        child = yield self._childClass.create(self, name, externalID=externalID)
        returnValue(child)


    @inlineCallbacks
    def removeChildWithName(self, name):
        child = yield self.childWithName(name)
        if child is None:
            raise NoSuchHomeChildError()
        resourceID = child._resourceID

        yield child.remove()
        self._children.pop(name, None)
        self._children.pop(resourceID, None)


    @classproperty
    def _syncTokenQuery(cls):
        """
        DAL Select statement to find the sync token.

        This is the max(REVISION) from the union of:

        1) REVISION's for all object resources in all home child collections in the targeted home
        2) REVISION's for all child collections in the targeted home

        Note the later is needed to track changes directly to the home child themselves (e.g.
        property changes, deletion etc).
        """
        rev = cls._revisionsSchema
        bind = cls._bindSchema
        return Select(
            [Max(rev.REVISION)],
            From=Select(
                [rev.REVISION],
                From=rev,
                Where=(
                    rev.RESOURCE_ID.In(
                        Select(
                            [bind.RESOURCE_ID],
                            From=bind,
                            Where=bind.HOME_RESOURCE_ID == Parameter("resourceID"),
                        )
                    )
                ),
                SetExpression=Union(
                    Select(
                        [rev.REVISION],
                        From=rev,
                        Where=(rev.HOME_RESOURCE_ID == Parameter("resourceID")).And(rev.RESOURCE_ID == None),
                    ),
                    optype=Union.OPTYPE_ALL,
                )
            ),
        )


    def revisionFromToken(self, token):
        if token is None:
            return 0
        elif isinstance(token, str):
            _ignore_uuid, revision = token.split("_", 1)
            return int(revision)
        else:
            return token


    @inlineCallbacks
    def syncToken(self):
        """
        Return the current sync token for the home. This is an aggregate of sync tokens for child
        collections. We will cache this value to avoid doing the query more than necessary. Care must be
        taken to invalid the cached value properly.
        """
        if self._syncTokenRevision is None:
            self._syncTokenRevision = (yield self._syncTokenQuery.on(
                self._txn, resourceID=self._resourceID))[0][0]
            if self._syncTokenRevision is None:
                self._syncTokenRevision = int((yield self._txn.calendarserverValue("MIN-VALID-REVISION")))
        returnValue("%s_%s" % (self._resourceID, self._syncTokenRevision))


    @classproperty
    def _changesQuery(cls):
        bind = cls._bindSchema
        rev = cls._revisionsSchema
        return Select(
            [
                bind.RESOURCE_NAME,
                rev.COLLECTION_NAME,
                rev.RESOURCE_NAME,
                rev.DELETED,
            ],
            From=rev.join(
                bind,
                (bind.HOME_RESOURCE_ID == Parameter("resourceID")).And
                (rev.RESOURCE_ID == bind.RESOURCE_ID),
                'left outer'
            ),
            Where=(rev.REVISION > Parameter("revision")).And
                  (rev.HOME_RESOURCE_ID == Parameter("resourceID"))
        )


    @inlineCallbacks
    def doChangesQuery(self, revision):
        """
            Do the changes query.
            Subclasses may override.
        """
        result = yield self._changesQuery.on(self._txn,
                                         resourceID=self._resourceID,
                                         revision=revision)
        returnValue(result)


    def resourceNamesSinceToken(self, token, depth):
        """
        Return the changed and deleted resources since a particular sync-token. This simply extracts
        the revision from from the token then calls L{resourceNamesSinceRevision}.

        @param revision: the revision to determine changes since
        @type revision: C{int}
        """

        return self.resourceNamesSinceRevision(self.revisionFromToken(token), depth)


    @inlineCallbacks
    def resourceNamesSinceRevision(self, revision, depth):
        """
        Determine the list of child resources that have changed since the specified sync revision.
        We do the same SQL query for both depth "1" and "infinity", but filter the results for
        "1" to only account for a collection change.

        Now that we are truncating the revision table, we need to handle the full sync (revision == 0)
        case a little differently as the revision table will not contain data for resources that exist,
        but were last modified before the revision cut-off. Instead for revision == 0 we need to list
        all existing child resources.  
  
        We need to handle shared collection a little differently from owned ones. When a shared collection
        is bound into a home we record a revision for it using the sharee home id and sharee collection name.
        That revision is the "starting point" for changes: so if sync occurs with a revision earlier than
        that, we return the list of all resources in the shared collection since they are all "new" as far
        as the client is concerned since the shared collection has just appeared. For a later revision, we
        just report the changes since that one. When a shared collection is removed from a home, we again
        record a revision for the sharee home and sharee collection name with the "deleted" flag set. That way
        the shared collection can be reported as removed.

        For external shared collections we need to report them as invalid as we cannot aggregate the sync token
        for this home with the sync token from the external share which is under the control of the other pod.
        Reporting it as invalid means that clients should do requests directly on the share itself to sync it.

        @param revision: the sync revision to compare to
        @type revision: C{str}
        @param depth: depth for determine what changed
        @type depth: C{str}
        """

        if revision:
            minValidRevision = yield self._txn.calendarserverValue("MIN-VALID-REVISION")
            if revision < int(minValidRevision):
                raise SyncTokenValidException
        else:
            results = yield self.resourceNamesSinceRevisionZero(depth)
            returnValue(results)

        # Use revision table to find changes since the last revision - this will not include
        # changes to child resources of shared collections - those we will get later
        results = [
            (
                path if path else (collection if collection else ""),
                name if name else "",
                wasdeleted
            )
            for path, collection, name, wasdeleted in
            (yield self.doChangesQuery(revision))
        ]

        changed = set()
        deleted = set()
        invalid = set()
        deleted_collections = set()
        for path, name, wasdeleted in results:
            if wasdeleted:
                if name:
                    # Resource deleted - for depth "1" report collection as changed,
                    # otherwise report resource as deleted
                    if depth == "1":
                        changed.add("%s/" % (path,))
                    else:
                        deleted.add("%s/%s" % (path, name,))
                else:
                    # Collection was deleted
                    deleted.add("%s/" % (path,))
                    deleted_collections.add(path)

            if path not in deleted_collections:
                # Always report collection as changed
                changed.add("%s/" % (path,))

                # Resource changed - for depth "infinity" report resource as changed
                if name and depth != "1":
                    changed.add("%s/%s" % (path, name,))

        # Now deal with existing shared collections
        # TODO: think about whether this can be done in one query rather than looping over each share
        for share in (yield self.children()):
            if not share.owned():
                sharedChanged, sharedDeleted, sharedInvalid = yield share.sharedChildResourceNamesSinceRevision(revision, depth)
                changed |= sharedChanged
                changed -= sharedInvalid
                deleted |= sharedDeleted
                deleted -= sharedInvalid
                invalid |= sharedInvalid

        changed = sorted(changed)
        deleted = sorted(deleted)
        invalid = sorted(invalid)
        returnValue((changed, deleted, invalid,))




    @inlineCallbacks
    def resourceNamesSinceRevisionZero(self, depth):
        """
        Revision == 0 specialization of L{resourceNamesSinceRevision} .

        @param depth: depth for determine what changed
        @type depth: C{str}
        """

        # Scan each child
        changed = set()
        deleted = set()
        invalid = set()
        for child in (yield self.children()):
            if child.owned():
                path = child.name()
                # Always report collection as changed
                changed.add("%s/" % (path,))

                # Resource changed - for depth "infinity" report resource as changed
                if depth != "1":
                    for name in (yield child.listObjectResources()):
                        changed.add("%s/%s" % (path, name,))
            else:
                sharedChanged, sharedDeleted, sharedInvalid = yield child.sharedChildResourceNamesSinceRevisionZero(depth)
                changed |= sharedChanged
                changed -= sharedInvalid
                deleted |= sharedDeleted
                deleted -= sharedInvalid
                invalid |= sharedInvalid

        changed = sorted(changed)
        deleted = sorted(deleted)
        invalid = sorted(invalid)
        returnValue((changed, deleted, invalid,))


    @inlineCallbacks
    def _loadPropertyStore(self):

        # Use any authz uid in place of the viewer uid so delegates have their own
        # set of properties
        props = yield PropertyStore.load(
            self.uid(),
            self.uid(),
            self.authzuid(),
            self._txn,
            self._resourceID,
            notifyCallback=self.notifyChanged
        )
        self._propertyStore = props


    def properties(self):
        return self._propertyStore


    # IDataStoreObject
    def contentType(self):
        """
        The content type of objects
        """
        return None


    def md5(self):
        return None


    def size(self):
        return 0


    def created(self):
        return datetimeMktime(parseSQLTimestamp(self._created)) if self._created else None


    def modified(self):
        return datetimeMktime(parseSQLTimestamp(self._modified)) if self._modified else None


    @classmethod
    def _objectResourceQuery(cls, checkBindMode):
        obj = cls._objectSchema
        bind = cls._bindSchema
        where = ((obj.UID == Parameter("uid"))
                 .And(bind.HOME_RESOURCE_ID == Parameter("resourceID")))
        if checkBindMode:
            where = where.And(bind.BIND_MODE == Parameter("bindMode"))
        return Select(
            [obj.PARENT_RESOURCE_ID, obj.RESOURCE_ID],
            From=obj.join(bind, obj.PARENT_RESOURCE_ID == bind.RESOURCE_ID),
            Where=where
        )


    @classproperty
    def _resourceByUIDQuery(cls):
        return cls._objectResourceQuery(checkBindMode=False)


    @classproperty
    def _resourceByUIDBindQuery(cls):
        return cls._objectResourceQuery(checkBindMode=True)


    @inlineCallbacks
    def objectResourcesWithUID(self, uid, ignore_children=[], allowShared=True):
        """
        Return all child object resources with the specified UID, ignoring any
        in the named child collections.
        """
        results = []
        if allowShared:
            rows = (yield self._resourceByUIDQuery.on(
                self._txn, uid=uid, resourceID=self._resourceID
            ))
        else:
            rows = (yield self._resourceByUIDBindQuery.on(
                self._txn, uid=uid, resourceID=self._resourceID,
                bindMode=_BIND_MODE_OWN
            ))
        if rows:
            for childID, objectID in rows:
                child = (yield self.childWithID(childID))
                if child and child.name() not in ignore_children:
                    objectResource = (
                        yield child.objectResourceWithID(objectID)
                    )
                    results.append(objectResource)

        returnValue(results)


    @classmethod
    def _objectResourceIDQuery(cls):
        obj = cls._objectSchema
        return Select(
            [obj.PARENT_RESOURCE_ID],
            From=obj,
            Where=(obj.RESOURCE_ID == Parameter("resourceID")),
        )


    @inlineCallbacks
    def objectResourceWithID(self, rid):
        """
        Return all child object resources with the specified resource-ID.
        """
        rows = (yield self._objectResourceIDQuery().on(
            self._txn, resourceID=rid
        ))
        if rows and len(rows) == 1:
            child = (yield self.childWithID(rows[0][0]))
            objectResource = (
                yield child.objectResourceWithID(rid)
            )
            returnValue(objectResource)

        returnValue(None)


    @classproperty
    def _quotaQuery(cls):
        meta = cls._homeMetaDataSchema
        return Select(
            [meta.QUOTA_USED_BYTES], From=meta,
            Where=meta.RESOURCE_ID == Parameter("resourceID")
        )


    @inlineCallbacks
    def quotaUsedBytes(self):
        if self._quotaUsedBytes is None:
            self._quotaUsedBytes = (yield self._quotaQuery.on(
                self._txn, resourceID=self._resourceID))[0][0]
        returnValue(self._quotaUsedBytes)


    @classproperty
    def _preLockResourceIDQuery(cls):
        meta = cls._homeMetaDataSchema
        return Select(From=meta,
                      Where=meta.RESOURCE_ID == Parameter("resourceID"),
                      ForUpdate=True)


    @classproperty
    def _increaseQuotaQuery(cls):
        meta = cls._homeMetaDataSchema
        return Update({meta.QUOTA_USED_BYTES: meta.QUOTA_USED_BYTES +
                       Parameter("delta")},
                      Where=meta.RESOURCE_ID == Parameter("resourceID"),
                      Return=meta.QUOTA_USED_BYTES)


    @classproperty
    def _resetQuotaQuery(cls):
        meta = cls._homeMetaDataSchema
        return Update({meta.QUOTA_USED_BYTES: 0},
                      Where=meta.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def adjustQuotaUsedBytes(self, delta):
        """
        Adjust quota used. We need to get a lock on the row first so that the
        adjustment is done atomically. It is import to do the 'select ... for
        update' because a race also exists in the 'update ... x = x + 1' case
        as seen via unit tests.
        """
        yield self._preLockResourceIDQuery.on(self._txn,
                                              resourceID=self._resourceID)

        self._quotaUsedBytes = (yield self._increaseQuotaQuery.on(
            self._txn, delta=delta, resourceID=self._resourceID))[0][0]

        # Double check integrity
        if self._quotaUsedBytes < 0:
            log.error(
                "Fixing quota adjusted below zero to {used} by change amount "
                "{delta}",
                used=self._quotaUsedBytes, delta=delta
            )
            yield self._resetQuotaQuery.on(self._txn,
                                           resourceID=self._resourceID)
            self._quotaUsedBytes = 0


    def addNotifier(self, factory_name, notifier):
        if self._notifiers is None:
            self._notifiers = {}
        self._notifiers[factory_name] = notifier


    def getNotifier(self, factory_name):
        return self._notifiers.get(factory_name)


    def notifierID(self):
        return (self._notifierPrefix, self.uid(),)


    @inlineCallbacks
    def notifyChanged(self, category=ChangeCategory.default):
        """
        Send notifications, change sync token and bump last modified because
        the resource has changed.  We ensure we only do this once per object
        per transaction.
        """

        if self._txn.isNotifiedAlready(self):
            returnValue(None)
        self._txn.notificationAddedForObject(self)

        # Update modified if object still exists
        if self._resourceID:
            yield self.bumpModified()

        # Send notifications
        if self._notifiers:
            # cache notifiers run in post commit
            notifier = self._notifiers.get("cache", None)
            if notifier:
                self._txn.postCommit(notifier.notify)
            # push notifiers add their work items immediately
            notifier = self._notifiers.get("push", None)
            if notifier:
                yield notifier.notify(self._txn, priority=category.value)


    @classproperty
    def _lockLastModifiedQuery(cls):
        meta = cls._homeMetaDataSchema
        return Select(
            From=meta,
            Where=meta.RESOURCE_ID == Parameter("resourceID"),
            ForUpdate=True,
            NoWait=True
        )


    @classproperty
    def _changeLastModifiedQuery(cls):
        meta = cls._homeMetaDataSchema
        return Update({meta.MODIFIED: utcNowSQL},
                      Where=meta.RESOURCE_ID == Parameter("resourceID"),
                      Return=meta.MODIFIED)


    @inlineCallbacks
    def bumpModified(self):
        """
        Bump the MODIFIED value. A possible deadlock could happen here if two
        or more simultaneous changes are happening. In that case it is OK for
        the MODIFIED change to fail so long as at least one works. We will use
        SAVEPOINT logic to handle ignoring the deadlock error. We use SELECT
        FOR UPDATE NOWAIT to ensure we do not delay the transaction whilst
        waiting for deadlock detection to kick in.
        """

        # NB if modified is bumped we know that sync token will have changed
        # too, so invalidate the cached value
        self._syncTokenRevision = None

        @inlineCallbacks
        def _bumpModified(subtxn):
            yield self._lockLastModifiedQuery.on(
                subtxn, resourceID=self._resourceID
            )
            result = yield self._changeLastModifiedQuery.on(
                subtxn, resourceID=self._resourceID
            )
            returnValue(result)

        try:
            self._modified = (
                yield self._txn.subtransaction(_bumpModified, retries=0, failureOK=True)
            )[0][0]
            yield self.invalidateQueryCache()

        except AllRetriesFailed:
            log.debug("CommonHome.bumpModified failed")


    @inlineCallbacks
    def removeUnacceptedShares(self):
        """
        Unbinds any collections that have been shared to this home but not yet
        accepted.  Associated invite entries are also removed.
        """
        bind = self._bindSchema
        kwds = {"homeResourceID" : self._resourceID}
        yield Delete(
            From=bind,
            Where=(bind.HOME_RESOURCE_ID == Parameter("homeResourceID")).And(bind.BIND_STATUS != _BIND_STATUS_ACCEPTED)
        ).on(self._txn, **kwds)


    @inlineCallbacks
    def ownerHomeAndChildNameForChildID(self, resourceID):
        """
        Get the owner home for a shared child ID and the owner's name for that bound child.
        Subclasses may override.
        """
        ownerHomeID, ownerName = (yield self._childClass._ownerHomeWithResourceID.on(self._txn, resourceID=resourceID))[0]
        ownerHome = yield self._txn.homeWithResourceID(self._homeType, ownerHomeID)
        returnValue((ownerHome, ownerName))



class _SharedSyncLogic(object):
    """
    Logic for maintaining sync-token shared between notification collections and
    shared collections.
    """

    @classproperty
    def _childSyncTokenQuery(cls):
        """
        DAL query for retrieving the sync token of a L{CommonHomeChild} based on
        its resource ID.
        """
        rev = cls._revisionsSchema
        return Select([Max(rev.REVISION)], From=rev,
                      Where=rev.RESOURCE_ID == Parameter("resourceID"))


    def revisionFromToken(self, token):
        if token is None:
            return 0
        elif isinstance(token, str) or isinstance(token, unicode):
            _ignore_uuid, revision = token.split("_", 1)
            return int(revision)
        else:
            return token


    @inlineCallbacks
    def syncToken(self):
        if self._syncTokenRevision is None:
            self._syncTokenRevision = (yield self._childSyncTokenQuery.on(
                self._txn, resourceID=self._resourceID))[0][0]
            if self._syncTokenRevision is None:
                self._syncTokenRevision = int((yield self._txn.calendarserverValue("MIN-VALID-REVISION")))
        returnValue(("%s_%s" % (self._resourceID, self._syncTokenRevision,)))


    def objectResourcesSinceToken(self, token):
        raise NotImplementedError()


    @classmethod
    def _objectNamesSinceRevisionQuery(cls, deleted=True):
        """
        DAL query for (resource, deleted-flag)
        """
        rev = cls._revisionsSchema
        where = (rev.REVISION > Parameter("revision")).And(rev.RESOURCE_ID == Parameter("resourceID"))
        if not deleted:
            where = where.And(rev.DELETED == False)
        return Select(
            [rev.RESOURCE_NAME, rev.DELETED],
            From=rev,
            Where=where,
        )


    def resourceNamesSinceToken(self, token):
        """
        Return the changed and deleted resources since a particular sync-token. This simply extracts
        the revision from from the token then calls L{resourceNamesSinceRevision}.

        @param revision: the revision to determine changes since
        @type revision: C{int}
        """

        return self.resourceNamesSinceRevision(self.revisionFromToken(token))


    @inlineCallbacks
    def resourceNamesSinceRevision(self, revision):
        """
        Return the changed and deleted resources since a particular revision.

        @param revision: the revision to determine changes since
        @type revision: C{int}
        """
        changed = []
        deleted = []
        invalid = []
        if revision:
            minValidRevision = yield self._txn.calendarserverValue("MIN-VALID-REVISION")
            if revision < int(minValidRevision):
                raise SyncTokenValidException

            results = [
                (name if name else "", removed) for name, removed in
                    (yield self._objectNamesSinceRevisionQuery().on(
                        self._txn, revision=revision, resourceID=self._resourceID)
                    )
            ]
            results.sort(key=lambda x: x[1])

            for name, wasdeleted in results:
                if name:
                    if wasdeleted:
                        deleted.append(name)
                    else:
                        changed.append(name)
        else:
            changed = yield self.listObjectResources()

        returnValue((changed, deleted, invalid))


    @classproperty
    def _removeDeletedRevision(cls):
        rev = cls._revisionsSchema
        return Delete(From=rev,
                      Where=(rev.HOME_RESOURCE_ID == Parameter("homeID")).And(
                          rev.COLLECTION_NAME == Parameter("collectionName")))


    @classproperty
    def _addNewRevision(cls):
        rev = cls._revisionsSchema
        return Insert({rev.HOME_RESOURCE_ID: Parameter("homeID"),
                       rev.RESOURCE_ID: Parameter("resourceID"),
                       rev.COLLECTION_NAME: Parameter("collectionName"),
                       rev.RESOURCE_NAME: None,
                       # Always starts false; may be updated to be a tombstone
                       # later.
                       rev.DELETED: False},
                     Return=[rev.REVISION])


    @inlineCallbacks
    def _initSyncToken(self):
        yield self._removeDeletedRevision.on(
            self._txn, homeID=self._home._resourceID, collectionName=self._name
        )
        self._syncTokenRevision = (yield (
            self._addNewRevision.on(self._txn, homeID=self._home._resourceID,
                                    resourceID=self._resourceID,
                                    collectionName=self._name)))[0][0]
        self._txn.bumpRevisionForObject(self)


    @classproperty
    def _renameSyncTokenQuery(cls):
        """
        DAL query to change sync token for a rename (increment and adjust
        resource name).
        """
        rev = cls._revisionsSchema
        return Update(
            {
                rev.REVISION: schema.REVISION_SEQ,
                rev.COLLECTION_NAME: Parameter("name")
            },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And
                  (rev.RESOURCE_NAME == None),
            Return=rev.REVISION
        )


    @inlineCallbacks
    def _renameSyncToken(self):
        self._syncTokenRevision = (yield self._renameSyncTokenQuery.on(
            self._txn, name=self._name, resourceID=self._resourceID))[0][0]
        self._txn.bumpRevisionForObject(self)


    @classproperty
    def _bumpSyncTokenQuery(cls):
        """
        DAL query to change collection sync token. Note this can impact multiple rows if the
        collection is shared.
        """
        rev = cls._revisionsSchema
        return Update(
            {rev.REVISION: schema.REVISION_SEQ, },
            Where=(rev.RESOURCE_ID == Parameter("resourceID")).And
                  (rev.RESOURCE_NAME == None)
        )


    @inlineCallbacks
    def _bumpSyncToken(self):

        if not self._txn.isRevisionBumpedAlready(self):
            self._txn.bumpRevisionForObject(self)
            yield self._bumpSyncTokenQuery.on(
                self._txn,
                resourceID=self._resourceID,
            )
            self._syncTokenRevision = None


    @classproperty
    def _deleteSyncTokenQuery(cls):
        """
        DAL query to remove all child revision information. The revision for the collection
        itself is not touched.
        """
        rev = cls._revisionsSchema
        return Delete(
            From=rev,
            Where=(rev.HOME_RESOURCE_ID == Parameter("homeID")).And
                  (rev.RESOURCE_ID == Parameter("resourceID")).And
                  (rev.COLLECTION_NAME == None)
        )


    @classproperty
    def _sharedRemovalQuery(cls):
        """
        DAL query to indicate a shared collection has been deleted.
        """
        rev = cls._revisionsSchema
        return Update({rev.RESOURCE_ID: None,
                       rev.REVISION: schema.REVISION_SEQ,
                       rev.DELETED: True},
                      Where=(rev.HOME_RESOURCE_ID == Parameter("homeID")).And(
                          rev.RESOURCE_ID == Parameter("resourceID")).And(
                              rev.RESOURCE_NAME == None)
                     )


    @classproperty
    def _unsharedRemovalQuery(cls):
        """
        DAL query to indicate an owned collection has been deleted.
        """
        rev = cls._revisionsSchema
        return Update({rev.RESOURCE_ID: None,
                       rev.REVISION: schema.REVISION_SEQ,
                       rev.DELETED: True},
                      Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                          rev.RESOURCE_NAME == None),
                     )


    @inlineCallbacks
    def _deletedSyncToken(self, sharedRemoval=False):
        """
        When a collection is deleted we remove all the revision information for its child resources.
        We update the collection's sync token to indicate it has been deleted - that way a sync on
        the home collection can report the deletion of the collection.

        @param sharedRemoval: indicates whether the collection being removed is shared
        @type sharedRemoval: L{bool}
        """
        # Remove all child entries
        yield self._deleteSyncTokenQuery.on(self._txn,
                                            homeID=self._home._resourceID,
                                            resourceID=self._resourceID)

        # If this is a share being removed then we only mark this one specific
        # home/resource-id as being deleted.  On the other hand, if it is a
        # non-shared collection, then we need to mark all collections
        # with the resource-id as being deleted to account for direct shares.
        if sharedRemoval:
            yield self._sharedRemovalQuery.on(self._txn,
                                              homeID=self._home._resourceID,
                                              resourceID=self._resourceID)
        else:
            yield self._unsharedRemovalQuery.on(self._txn,
                                                resourceID=self._resourceID)
        self._syncTokenRevision = None


    def _insertRevision(self, name):
        return self._changeRevision("insert", name)


    def _updateRevision(self, name):
        return self._changeRevision("update", name)


    def _deleteRevision(self, name):
        return self._changeRevision("delete", name)


    @classproperty
    def _deleteBumpTokenQuery(cls):
        rev = cls._revisionsSchema
        return Update({rev.REVISION: schema.REVISION_SEQ,
                       rev.DELETED: True},
                      Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                           rev.RESOURCE_NAME == Parameter("name")),
                      Return=rev.REVISION)


    @classproperty
    def _updateBumpTokenQuery(cls):
        rev = cls._revisionsSchema
        return Update({rev.REVISION: schema.REVISION_SEQ},
                      Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                           rev.RESOURCE_NAME == Parameter("name")),
                      Return=rev.REVISION)


    @classproperty
    def _insertFindPreviouslyNamedQuery(cls):
        rev = cls._revisionsSchema
        return Select([rev.RESOURCE_ID], From=rev,
                      Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                           rev.RESOURCE_NAME == Parameter("name")))


    @classproperty
    def _updatePreviouslyNamedQuery(cls):
        rev = cls._revisionsSchema
        return Update({rev.REVISION: schema.REVISION_SEQ,
                       rev.DELETED: False},
                      Where=(rev.RESOURCE_ID == Parameter("resourceID")).And(
                           rev.RESOURCE_NAME == Parameter("name")),
                      Return=rev.REVISION)


    @classproperty
    def _completelyNewRevisionQuery(cls):
        rev = cls._revisionsSchema
        return Insert({rev.HOME_RESOURCE_ID: Parameter("homeID"),
                       rev.RESOURCE_ID: Parameter("resourceID"),
                       rev.RESOURCE_NAME: Parameter("name"),
                       rev.REVISION: schema.REVISION_SEQ,
                       rev.DELETED: False},
                      Return=rev.REVISION)


    @inlineCallbacks
    def _changeRevision(self, action, name):

        # Need to handle the case where for some reason the revision entry is
        # actually missing. For a "delete" we don't care, for an "update" we
        # will turn it into an "insert".
        if action == "delete":
            rows = (
                yield self._deleteBumpTokenQuery.on(
                    self._txn, resourceID=self._resourceID, name=name))
            if rows:
                self._syncTokenRevision = rows[0][0]
        elif action == "update":
            rows = (
                yield self._updateBumpTokenQuery.on(
                    self._txn, resourceID=self._resourceID, name=name))
            if rows:
                self._syncTokenRevision = rows[0][0]
            else:
                action = "insert"

        if action == "insert":
            # Note that an "insert" may happen for a resource that previously
            # existed and then was deleted. In that case an entry in the
            # REVISIONS table still exists so we have to detect that and do db
            # INSERT or UPDATE as appropriate

            found = bool((
                yield self._insertFindPreviouslyNamedQuery.on(
                    self._txn, resourceID=self._resourceID, name=name)))
            if found:
                self._syncTokenRevision = (
                    yield self._updatePreviouslyNamedQuery.on(
                        self._txn, resourceID=self._resourceID, name=name)
                )[0][0]
            else:
                self._syncTokenRevision = (
                    yield self._completelyNewRevisionQuery.on(
                        self._txn, homeID=self.ownerHome()._resourceID,
                        resourceID=self._resourceID, name=name)
                )[0][0]
        yield self._maybeNotify()
        returnValue(self._syncTokenRevision)


    def _maybeNotify(self):
        """
        Maybe notify changed.  (Overridden in NotificationCollection.)
        """
        return succeed(None)



SharingInvitation = namedtuple(
    "SharingInvitation",
    ["uid", "ownerUID", "ownerHomeID", "shareeUID", "shareeHomeID", "mode", "status", "summary"]
)



class SharingMixIn(object):
    """
    Common class for CommonHomeChild and AddressBookObject
    """

    @classproperty
    def _bindInsertQuery(cls, **kw):
        """
        DAL statement to create a bind entry that connects a collection to its
        home.
        """
        bind = cls._bindSchema
        return Insert({
            bind.HOME_RESOURCE_ID: Parameter("homeID"),
            bind.RESOURCE_ID: Parameter("resourceID"),
            bind.EXTERNAL_ID: Parameter("externalID"),
            bind.RESOURCE_NAME: Parameter("name"),
            bind.BIND_MODE: Parameter("mode"),
            bind.BIND_STATUS: Parameter("bindStatus"),
            bind.MESSAGE: Parameter("message"),
        })


    @classmethod
    def _updateBindColumnsQuery(cls, columnMap):
        bind = cls._bindSchema
        return Update(
            columnMap,
            Where=(bind.RESOURCE_ID == Parameter("resourceID"))
                   .And(bind.HOME_RESOURCE_ID == Parameter("homeID")),
        )


    @classproperty
    def _deleteBindForResourceIDAndHomeID(cls):
        bind = cls._bindSchema
        return Delete(
            From=bind,
            Where=(bind.RESOURCE_ID == Parameter("resourceID"))
                  .And(bind.HOME_RESOURCE_ID == Parameter("homeID")),
        )


    @classmethod
    def _bindFor(cls, condition):
        bind = cls._bindSchema
        columns = cls.bindColumns() + cls.additionalBindColumns()
        return Select(
            columns,
            From=bind,
            Where=condition
        )


    @classmethod
    def _bindInviteFor(cls, condition):
        home = cls._homeSchema
        bind = cls._bindSchema
        return Select(
            [
                home.OWNER_UID,
                bind.HOME_RESOURCE_ID,
                bind.RESOURCE_ID,
                bind.RESOURCE_NAME,
                bind.BIND_MODE,
                bind.BIND_STATUS,
                bind.MESSAGE,
            ],
            From=bind.join(home, on=(bind.HOME_RESOURCE_ID == home.RESOURCE_ID)),
            Where=condition
        )


    @classproperty
    def _sharedInvitationBindForResourceID(cls):
        bind = cls._bindSchema
        return cls._bindInviteFor(
            (bind.RESOURCE_ID == Parameter("resourceID")).And
            (bind.BIND_MODE != _BIND_MODE_OWN)
        )


    @classproperty
    def _acceptedBindForHomeID(cls):
        bind = cls._bindSchema
        return cls._bindFor((bind.HOME_RESOURCE_ID == Parameter("homeID"))
                            .And(bind.BIND_STATUS == _BIND_STATUS_ACCEPTED))


    @classproperty
    def _bindForResourceIDAndHomeID(cls):
        """
        DAL query that looks up home bind rows by home child
        resource ID and home resource ID.
        """
        bind = cls._bindSchema
        return cls._bindFor((bind.RESOURCE_ID == Parameter("resourceID"))
                            .And(bind.HOME_RESOURCE_ID == Parameter("homeID")))


    @classproperty
    def _bindForExternalIDAndHomeID(cls):
        """
        DAL query that looks up home bind rows by home child
        resource ID and home resource ID.
        """
        bind = cls._bindSchema
        return cls._bindFor((bind.EXTERNAL_ID == Parameter("externalID"))
                            .And(bind.HOME_RESOURCE_ID == Parameter("homeID")))


    @classproperty
    def _bindForNameAndHomeID(cls):
        """
        DAL query that looks up any bind rows by home child
        resource ID and home resource ID.
        """
        bind = cls._bindSchema
        return cls._bindFor((bind.RESOURCE_NAME == Parameter("name"))
                            .And(bind.HOME_RESOURCE_ID == Parameter("homeID")))


    #
    # Higher level API
    #
    @inlineCallbacks
    def inviteUIDToShare(self, shareeUID, mode, summary=None, shareName=None):
        """
        Invite a user to share this collection - either create the share if it does not exist, or
        update the existing share with new values. Make sure a notification is sent as well.

        @param shareeUID: UID of the sharee
        @type shareeUID: C{str}
        @param mode: access mode
        @type mode: C{int}
        @param summary: share message
        @type summary: C{str}
        """

        # Look for existing invite and update its fields or create new one
        shareeView = yield self.shareeView(shareeUID)
        if shareeView is not None:
            status = _BIND_STATUS_INVITED if shareeView.shareStatus() in (_BIND_STATUS_DECLINED, _BIND_STATUS_INVALID) else None
            yield self.updateShare(shareeView, mode=mode, status=status, summary=summary)
        else:
            shareeView = yield self.createShare(shareeUID=shareeUID, mode=mode, summary=summary, shareName=shareName)

        # Check for external
        if shareeView.viewerHome().external():
            yield self._sendExternalInvite(shareeView)
        else:
            # Send invite notification
            yield self._sendInviteNotification(shareeView)
        returnValue(shareeView)


    @inlineCallbacks
    def directShareWithUser(self, shareeUID, shareName=None):
        """
        Create a direct share with the specified user. Note it is currently up to the app layer
        to enforce access control - this is not ideal as we really should have control of that in
        the store. Once we do, this api will need to verify that access is allowed for a direct share.

        NB no invitations are used with direct sharing.

        @param shareeUID: UID of the sharee
        @type shareeUID: C{str}
        """

        # Ignore if it already exists
        shareeView = yield self.shareeView(shareeUID)
        if shareeView is None:
            shareeView = yield self.createShare(shareeUID=shareeUID, mode=_BIND_MODE_DIRECT, shareName=shareName)
            yield shareeView.newShare()

            # Check for external
            if shareeView.viewerHome().external():
                yield self._sendExternalInvite(shareeView)

        returnValue(shareeView)


    @inlineCallbacks
    def uninviteUIDFromShare(self, shareeUID):
        """
        Remove a user from a share. Make sure a notification is sent as well.

        @param shareeUID: UID of the sharee
        @type shareeUID: C{str}
        """
        # Cancel invites - we'll just use whatever userid we are given

        shareeView = yield self.shareeView(shareeUID)
        if shareeView is not None:
            if shareeView.viewerHome().external():
                yield self._sendExternalUninvite(shareeView)
            else:
                # If current user state is accepted then we send an invite with the new state, otherwise
                # we cancel any existing invites for the user
                if not shareeView.direct():
                    if shareeView.shareStatus() != _BIND_STATUS_ACCEPTED:
                        yield self._removeInviteNotification(shareeView)
                    else:
                        yield self._sendInviteNotification(shareeView, notificationState=_BIND_STATUS_DELETED)

            # Remove the bind
            yield self.removeShare(shareeView)


    @inlineCallbacks
    def acceptShare(self, summary=None):
        """
        This share is being accepted.
        """

        if not self.direct() and self.shareStatus() != _BIND_STATUS_ACCEPTED:
            if self.external():
                yield self._replyExternalInvite(_BIND_STATUS_ACCEPTED, summary)
            ownerView = yield self.ownerView()
            yield ownerView.updateShare(self, status=_BIND_STATUS_ACCEPTED)
            yield self.newShare(displayname=summary)
            if not ownerView.external():
                yield self._sendReplyNotification(ownerView, summary)


    @inlineCallbacks
    def declineShare(self):
        """
        This share is being declined.
        """

        if not self.direct() and self.shareStatus() != _BIND_STATUS_DECLINED:
            if self.external():
                yield self._replyExternalInvite(_BIND_STATUS_DECLINED)
            ownerView = yield self.ownerView()
            yield ownerView.updateShare(self, status=_BIND_STATUS_DECLINED)
            if not ownerView.external():
                yield self._sendReplyNotification(ownerView)


    @inlineCallbacks
    def deleteShare(self):
        """
        This share is being deleted (by the sharee) - either decline or remove (for direct shares).
        """

        ownerView = yield self.ownerView()
        if self.direct():
            yield ownerView.removeShare(self)
            if ownerView.external():
                yield self._replyExternalInvite(_BIND_STATUS_DECLINED)
        else:
            yield self.declineShare()


    @inlineCallbacks
    def ownerDeleteShare(self):
        """
        This share is being deleted (by the owner) - either decline or remove (for direct shares).
        """

        # Change status on store object
        yield self.setShared(False)

        # Remove all sharees (direct and invited)
        for invitation in (yield self.sharingInvites()):
            yield self.uninviteUIDFromShare(invitation.shareeUID)


    def newShare(self, displayname=None):
        """
        Override in derived classes to do any specific operations needed when a share
        is first accepted.
        """
        return succeed(None)


    @inlineCallbacks
    def allInvitations(self):
        """
        Get list of all invitations (non-direct) to this object.
        """
        invitations = yield self.sharingInvites()

        # remove direct shares as those are not "real" invitations
        invitations = filter(lambda x: x.mode != _BIND_MODE_DIRECT, invitations)
        invitations.sort(key=lambda invitation: invitation.shareeUID)
        returnValue(invitations)


    @inlineCallbacks
    def _sendInviteNotification(self, shareeView, notificationState=None):
        """
        Called on the owner's resource.
        """
        # When deleting the message is the sharee's display name
        displayname = shareeView.shareMessage()
        if notificationState == _BIND_STATUS_DELETED:
            displayname = str(shareeView.properties().get(PropertyName.fromElement(element.DisplayName), displayname))

        notificationtype = {
            "notification-type": "invite-notification",
            "shared-type": shareeView.sharedResourceType(),
        }
        notificationdata = {
            "notification-type": "invite-notification",
            "shared-type": shareeView.sharedResourceType(),
            "dtstamp": DateTime.getNowUTC().getText(),
            "owner": shareeView.ownerHome().uid(),
            "sharee": shareeView.viewerHome().uid(),
            "uid": shareeView.shareUID(),
            "status": shareeView.shareStatus() if notificationState is None else notificationState,
            "access": (yield shareeView.effectiveShareMode()),
            "ownerName": self.shareName(),
            "summary": displayname,
        }
        if hasattr(self, "getSupportedComponents"):
            notificationdata["supported-components"] = self.getSupportedComponents()

        # Add to sharee's collection
        notifications = yield self._txn.notificationsWithUID(shareeView.viewerHome().uid())
        yield notifications.writeNotificationObject(shareeView.shareUID(), notificationtype, notificationdata)


    @inlineCallbacks
    def _sendReplyNotification(self, ownerView, summary=None):
        """
        Create a reply notification based on the current state of this shared resource.
        """

        # Generate invite XML
        notificationUID = "%s-reply" % (self.shareUID(),)

        notificationtype = {
            "notification-type": "invite-reply",
            "shared-type": self.sharedResourceType(),
        }

        notificationdata = {
            "notification-type": "invite-reply",
            "shared-type": self.sharedResourceType(),
            "dtstamp": DateTime.getNowUTC().getText(),
            "owner": self.ownerHome().uid(),
            "sharee": self.viewerHome().uid(),
            "status": self.shareStatus(),
            "ownerName": ownerView.shareName(),
            "in-reply-to": self.shareUID(),
            "summary": summary,
        }

        # Add to owner notification collection
        notifications = yield self._txn.notificationsWithUID(self.ownerHome().uid())
        yield notifications.writeNotificationObject(notificationUID, notificationtype, notificationdata)


    @inlineCallbacks
    def _removeInviteNotification(self, shareeView):
        """
        Called on the owner's resource.
        """

        # Remove from sharee's collection
        notifications = yield self._txn.notificationsWithUID(shareeView.viewerHome().uid())
        yield notifications.removeNotificationObjectWithUID(shareeView.shareUID())


    #
    # External/cross-pod API
    #
    @inlineCallbacks
    def _sendExternalInvite(self, shareeView):

        yield self._txn.store().conduit.send_shareinvite(
            self._txn,
            shareeView.ownerHome()._homeType,
            shareeView.ownerHome().uid(),
            self.id(),
            self.shareName(),
            shareeView.viewerHome().uid(),
            shareeView.shareUID(),
            shareeView.shareMode(),
            shareeView.shareMessage(),
            self.getInviteCopyProperties(),
            supported_components=self.getSupportedComponents() if hasattr(self, "getSupportedComponents") else None,
        )


    @inlineCallbacks
    def _sendExternalUninvite(self, shareeView):

        yield self._txn.store().conduit.send_shareuninvite(
            self._txn,
            shareeView.ownerHome()._homeType,
            shareeView.ownerHome().uid(),
            self.id(),
            shareeView.viewerHome().uid(),
            shareeView.shareUID(),
        )


    @inlineCallbacks
    def _replyExternalInvite(self, status, summary=None):

        yield self._txn.store().conduit.send_sharereply(
            self._txn,
            self.viewerHome()._homeType,
            self.ownerHome().uid(),
            self.viewerHome().uid(),
            self.shareUID(),
            status,
            summary,
        )


    #
    # Lower level API
    #
    @inlineCallbacks
    def ownerView(self):
        """
        Return the owner resource counterpart of this shared resource.

        Note we have to play a trick with the property store to coerce it to match
        the per-user properties for the owner.
        """
        # Get the child of the owner home that has the same resource id as the owned one
        ownerView = yield self.ownerHome().childWithID(self.id())
        returnValue(ownerView)


    @inlineCallbacks
    def shareeView(self, shareeUID):
        """
        Return the shared resource counterpart of this owned resource for the specified sharee.

        Note we have to play a trick with the property store to coerce it to match
        the per-user properties for the sharee.
        """

        # Get the child of the sharee home that has the same resource id as the owned one
        shareeHome = yield self._txn.homeWithUID(self._home._homeType, shareeUID, authzUID=shareeUID)
        shareeView = (yield shareeHome.allChildWithID(self.id())) if shareeHome is not None else None
        returnValue(shareeView)


    @inlineCallbacks
    def shareWithUID(self, shareeUID, mode, status=None, summary=None, shareName=None):
        """
        Share this (owned) L{CommonHomeChild} with another principal.

        @param shareeUID: The UID of the sharee.
        @type: L{str}

        @param mode: The sharing mode; L{_BIND_MODE_READ} or
            L{_BIND_MODE_WRITE} or L{_BIND_MODE_DIRECT}
        @type mode: L{str}

        @param status: The sharing status; L{_BIND_STATUS_INVITED} or
            L{_BIND_STATUS_ACCEPTED}
        @type: L{str}

        @param summary: The proposed message to go along with the share, which
            will be used as the default display name.
        @type: L{str}

        @return: the name of the shared calendar in the new calendar home.
        @rtype: L{str}
        """
        shareeHome = yield self._txn.calendarHomeWithUID(shareeUID, create=True)
        returnValue(
            (yield self.shareWith(shareeHome, mode, status, summary, shareName))
        )


    @inlineCallbacks
    def shareWith(self, shareeHome, mode, status=None, summary=None, shareName=None):
        """
        Share this (owned) L{CommonHomeChild} with another home.

        @param shareeHome: The home of the sharee.
        @type: L{CommonHome}

        @param mode: The sharing mode; L{_BIND_MODE_READ} or
            L{_BIND_MODE_WRITE} or L{_BIND_MODE_DIRECT}
        @type: L{str}

        @param status: The sharing status; L{_BIND_STATUS_INVITED} or
            L{_BIND_STATUS_ACCEPTED}
        @type: L{str}

        @param summary: The proposed message to go along with the share, which
            will be used as the default display name.
        @type: L{str}

        @param shareName: The proposed name of the new share.
        @type: L{str}

        @return: the name of the shared calendar in the new calendar home.
        @rtype: L{str}
        """

        if status is None:
            status = _BIND_STATUS_ACCEPTED

        @inlineCallbacks
        def doInsert(subt):
            newName = shareName if shareName is not None else self.newShareName()
            yield self._bindInsertQuery.on(
                subt,
                homeID=shareeHome._resourceID,
                resourceID=self._resourceID,
                externalID=self._externalID,
                name=newName,
                mode=mode,
                bindStatus=status,
                message=summary
            )
            returnValue(newName)
        try:
            bindName = yield self._txn.subtransaction(doInsert)
        except AllRetriesFailed:
            # FIXME: catch more specific exception
            child = yield shareeHome.allChildWithID(self._resourceID)
            yield self.updateShare(
                child, mode=mode, status=status,
                summary=summary
            )
            bindName = child._name
        else:
            if status == _BIND_STATUS_ACCEPTED:
                shareeView = yield shareeHome.anyObjectWithShareUID(bindName)
                yield shareeView._initSyncToken()
                yield shareeView._initBindRevision()

        # Mark this as shared
        yield self.setShared(True)

        # Must send notification to ensure cache invalidation occurs
        yield self.notifyPropertyChanged()
        yield shareeHome.notifyChanged()

        returnValue(bindName)


    @inlineCallbacks
    def createShare(self, shareeUID, mode, summary=None, shareName=None):
        """
        Create a new shared resource. If the mode is direct, the share is created in accepted state,
        otherwise the share is created in invited state.
        """
        shareeHome = yield self._txn.homeWithUID(self.ownerHome()._homeType, shareeUID, create=True)

        yield self.shareWith(
            shareeHome,
            mode=mode,
            status=_BIND_STATUS_INVITED if mode != _BIND_MODE_DIRECT else _BIND_STATUS_ACCEPTED,
            summary=summary,
            shareName=shareName,
        )
        shareeView = yield self.shareeView(shareeUID)
        returnValue(shareeView)


    @inlineCallbacks
    def updateShare(self, shareeView, mode=None, status=None, summary=None):
        """
        Update share mode, status, and message for a home child shared with
        this (owned) L{CommonHomeChild}.

        @param shareeView: The sharee home child that shares this.
        @type shareeView: L{CommonHomeChild}

        @param mode: The sharing mode; L{_BIND_MODE_READ} or
            L{_BIND_MODE_WRITE} or None to not update
        @type mode: L{str}

        @param status: The sharing status; L{_BIND_STATUS_INVITED} or
            L{_BIND_STATUS_ACCEPTED} or L{_BIND_STATUS_DECLINED} or
            L{_BIND_STATUS_INVALID}  or None to not update
        @type status: L{str}

        @param summary: The proposed message to go along with the share, which
            will be used as the default display name, or None to not update
        @type summary: L{str}
        """
        # TODO: raise a nice exception if shareeView is not, in fact, a shared
        # version of this same L{CommonHomeChild}

        #remove None parameters, and substitute None for empty string
        bind = self._bindSchema
        columnMap = {}
        if mode != None and mode != self._bindMode:
            columnMap[bind.BIND_MODE] = mode
        if status != None:# and status != self._bindStatus:  # FIXME:
            columnMap[bind.BIND_STATUS] = status
        if summary != None and summary and summary != self._bindMessage:
            columnMap[bind.MESSAGE] = summary

        if columnMap:

            # Count accepted
            if bind.BIND_STATUS in columnMap:
                previouslyAcceptedCount = yield shareeView._previousAcceptCount()

            yield self._updateBindColumnsQuery(columnMap).on(
                self._txn,
                resourceID=self._resourceID, homeID=shareeView._home._resourceID
            )

            # Update affected attributes
            if bind.BIND_MODE in columnMap:
                shareeView._bindMode = columnMap[bind.BIND_MODE]

            if bind.BIND_STATUS in columnMap:
                shareeView._bindStatus = columnMap[bind.BIND_STATUS]
                yield shareeView._changedStatus(previouslyAcceptedCount)

            if summary is not None:
                shareeView._bindMessage = columnMap[bind.MESSAGE]

            yield shareeView.invalidateQueryCache()

            # Must send notification to ensure cache invalidation occurs
            yield self.notifyPropertyChanged()
            yield shareeView.viewerHome().notifyChanged()


    def _previousAcceptCount(self):
        return succeed(1)


    @inlineCallbacks
    def _changedStatus(self, previouslyAcceptedCount):
        if self._bindStatus == _BIND_STATUS_ACCEPTED:
            yield self._initSyncToken()
            yield self._initBindRevision()
            self._home._children[self._name] = self
            self._home._children[self._resourceID] = self
        elif self._bindStatus in (_BIND_STATUS_INVITED, _BIND_STATUS_DECLINED):
            yield self._deletedSyncToken(sharedRemoval=True)
            self._home._children.pop(self._name, None)
            self._home._children.pop(self._resourceID, None)


    @inlineCallbacks
    def removeShare(self, shareeView):
        """
        Remove the shared version of this (owned) L{CommonHomeChild} from the
        referenced L{CommonHome}.

        @see: L{CommonHomeChild.shareWith}

        @param shareeView: The shared resource being removed.

        @return: a L{Deferred} which will fire with the previous shareUID
        """

        # remove sync tokens
        shareeHome = shareeView.viewerHome()
        yield shareeView._deletedSyncToken(sharedRemoval=True)
        shareeHome._children.pop(shareeView._name, None)
        shareeHome._children.pop(shareeView._resourceID, None)

        # Must send notification to ensure cache invalidation occurs
        yield self.notifyPropertyChanged()
        yield shareeHome.notifyChanged()

        # delete binds including invites
        yield self._deleteBindForResourceIDAndHomeID.on(
            self._txn,
            resourceID=self._resourceID,
            homeID=shareeHome._resourceID,
        )

        yield shareeView.invalidateQueryCache()


    @inlineCallbacks
    def unshare(self):
        """
        Unshares a collection, regardless of which "direction" it was shared.
        """
        if self.owned():
            # This collection may be shared to others
            invites = yield self.sharingInvites()
            for invite in invites:
                shareeView = yield self.shareeView(invite.shareeUID)
                yield self.removeShare(shareeView)
        else:
            # This collection is shared to me
            ownerView = yield self.ownerView()
            yield ownerView.removeShare(self)


    @inlineCallbacks
    def sharingInvites(self):
        """
        Retrieve the list of all L{SharingInvitation}'s for this L{CommonHomeChild}, irrespective of mode.

        @return: L{SharingInvitation} objects
        @rtype: a L{Deferred} which fires with a L{list} of L{SharingInvitation}s.
        """
        if not self.owned():
            returnValue([])

        # get all accepted binds
        invitedRows = yield self._sharedInvitationBindForResourceID.on(
            self._txn, resourceID=self._resourceID, homeID=self._home._resourceID
        )

        result = []
        for homeUID, homeRID, _ignore_resourceID, resourceName, bindMode, bindStatus, bindMessage in invitedRows:
            invite = SharingInvitation(
                resourceName,
                self.ownerHome().name(),
                self.ownerHome().id(),
                homeUID,
                homeRID,
                bindMode,
                bindStatus,
                bindMessage,
            )
            result.append(invite)
        returnValue(result)


    @inlineCallbacks
    def _initBindRevision(self):
        yield self.syncToken() # init self._syncTokenRevision if None
        self._bindRevision = self._syncTokenRevision

        bind = self._bindSchema
        yield self._updateBindColumnsQuery(
            {bind.BIND_REVISION : Parameter("revision"), }
        ).on(
            self._txn,
            revision=self._bindRevision,
            resourceID=self._resourceID,
            homeID=self.viewerHome()._resourceID,
        )
        yield self.invalidateQueryCache()


    def sharedResourceType(self):
        """
        The sharing resource type. Needs to be overridden by each type of resource that can be shared.

        @return: an identifier for the type of the share.
        @rtype: C{str}
        """
        return ""


    def newShareName(self):
        """
        Name used when creating a new share. By default this is a UUID.
        """
        return str(uuid4())


    def owned(self):
        """
        @see: L{ICalendar.owned}
        """
        return self._bindMode == _BIND_MODE_OWN


    def isShared(self):
        """
        For an owned collection indicate whether it is shared.

        @return: C{True} if shared, C{False} otherwise
        @rtype: C{bool}
        """
        return self.owned() and self._bindMessage == "shared"


    @inlineCallbacks
    def setShared(self, shared):
        """
        Set an owned collection to shared or unshared state. Technically this is not useful as "shared"
        really means it has invitees, but the current sharing spec supports a notion of a shared collection
        that has not yet had invitees added. For the time being we will support that option by using a new
        MESSAGE value to indicate an owned collection that is "shared".

        @param shared: whether or not the owned collection is "shared"
        @type shared: C{bool}
        """
        assert self.owned(), "Cannot change share mode on a shared collection"

        # Only if change is needed
        newMessage = "shared" if shared else None
        if self._bindMessage == newMessage:
            returnValue(None)

        self._bindMessage = newMessage

        bind = self._bindSchema
        yield Update(
            {bind.MESSAGE: self._bindMessage},
            Where=(bind.RESOURCE_ID == Parameter("resourceID"))
                  .And(bind.HOME_RESOURCE_ID == Parameter("homeID")),
        ).on(self._txn, resourceID=self._resourceID, homeID=self.viewerHome()._resourceID)

        yield self.invalidateQueryCache()
        yield self.notifyPropertyChanged()


    def direct(self):
        """
        Is this a "direct" share?

        @return: a boolean indicating whether it's direct.
        """
        return self._bindMode == _BIND_MODE_DIRECT


    def indirect(self):
        """
        Is this an "indirect" share?

        @return: a boolean indicating whether it's indirect.
        """
        return self._bindMode == _BIND_MODE_INDIRECT


    def shareUID(self):
        """
        @see: L{ICalendar.shareUID}
        """
        return self.name()


    def shareMode(self):
        """
        @see: L{ICalendar.shareMode}
        """
        return self._bindMode


    def effectiveShareMode(self):
        """
        @see: L{ICalendar.shareMode}
        """
        return self._bindMode


    def shareName(self):
        """
        This is a path like name for the resource within the home being shared. For object resource
        shares this will be a combination of the L{CommonHomeChild} name and the L{CommonObjecrResource}
        name. Otherwise it is just the L{CommonHomeChild} name. This is needed to expose a value to the
        app-layer such that it can construct a URI for the actual WebDAV resource being shared.
        """
        name = self.name()
        if self.sharedResourceType() == "group":
            name = self.parentCollection().name() + "/" + name
        return name


    def shareStatus(self):
        """
        @see: L{ICalendar.shareStatus}
        """
        return self._bindStatus


    def accepted(self):
        """
        @see: L{ICalendar.shareStatus}
        """
        return self._bindStatus == _BIND_STATUS_ACCEPTED


    def shareMessage(self):
        """
        @see: L{ICalendar.shareMessage}
        """
        return self._bindMessage


    def getInviteCopyProperties(self):
        """
        Get a dictionary of property name/values (as strings) for properties that are shadowable and
        need to be copied to a sharee's collection when an external (cross-pod) share is created.
        Sub-classes should override to expose the properties they care about.
        """
        return {}


    def setInviteCopyProperties(self, props):
        """
        Copy a set of shadowable properties (as name/value strings) onto this shared resource when
        a cross-pod invite is processed. Sub-classes should override to expose the properties they
        care about.
        """
        pass


    @classmethod
    def metadataColumns(cls):
        """
        Return a list of column name for retrieval of metadata. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        # Common behavior is to have created and modified

        return (
            cls._homeChildMetaDataSchema.CREATED,
            cls._homeChildMetaDataSchema.MODIFIED,
        )


    @classmethod
    def metadataAttributes(cls):
        """
        Return a list of attribute names for retrieval of metadata. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        # Common behavior is to have created and modified

        return (
            "_created",
            "_modified",
        )


    @classmethod
    def bindColumns(cls):
        """
        Return a list of column names for retrieval during creation. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        return (
            cls._bindSchema.BIND_MODE,
            cls._bindSchema.HOME_RESOURCE_ID,
            cls._bindSchema.RESOURCE_ID,
            cls._bindSchema.EXTERNAL_ID,
            cls._bindSchema.RESOURCE_NAME,
            cls._bindSchema.BIND_STATUS,
            cls._bindSchema.BIND_REVISION,
            cls._bindSchema.MESSAGE
        )

    bindColumnCount = 8

    @classmethod
    def additionalBindColumns(cls):
        """
        Return a list of column names for retrieval during creation. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        return ()


    @classmethod
    def additionalBindAttributes(cls):
        """
        Return a list of attribute names for retrieval of during creation. This allows
        different child classes to have their own type specific data, but still make use of the
        common base logic.
        """

        return ()


    @classproperty
    def _childrenAndMetadataForHomeID(cls):
        bind = cls._bindSchema
        child = cls._homeChildSchema
        childMetaData = cls._homeChildMetaDataSchema

        columns = cls.bindColumns() + cls.additionalBindColumns() + cls.metadataColumns()
        return Select(columns,
                     From=child.join(
                         bind, child.RESOURCE_ID == bind.RESOURCE_ID,
                         'left outer').join(
                         childMetaData, childMetaData.RESOURCE_ID == bind.RESOURCE_ID,
                         'left outer'),
                     Where=(bind.HOME_RESOURCE_ID == Parameter("homeID")
                           ).And(bind.BIND_STATUS == _BIND_STATUS_ACCEPTED))


    @classmethod
    def _revisionsForResourceIDs(cls, resourceIDs):
        rev = cls._revisionsSchema
        return Select(
            [rev.RESOURCE_ID, Max(rev.REVISION)],
            From=rev,
            Where=rev.RESOURCE_ID.In(Parameter("resourceIDs", len(resourceIDs))).
                    And((rev.RESOURCE_NAME != None).Or(rev.DELETED == False)),
            GroupBy=rev.RESOURCE_ID
        )


    @inlineCallbacks
    def invalidateQueryCache(self):
        queryCacher = self._txn._queryCacher
        if queryCacher is not None:
            yield queryCacher.invalidateAfterCommit(self._txn, queryCacher.keyForHomeChildMetaData(self._resourceID))
            yield queryCacher.invalidateAfterCommit(self._txn, queryCacher.keyForObjectWithName(self._home._resourceID, self._name))
            yield queryCacher.invalidateAfterCommit(self._txn, queryCacher.keyForObjectWithResourceID(self._home._resourceID, self._resourceID))
            yield queryCacher.invalidateAfterCommit(self._txn, queryCacher.keyForObjectWithExternalID(self._home._resourceID, self._externalID))



class CommonHomeChild(FancyEqMixin, Memoizable, _SharedSyncLogic, HomeChildBase, SharingMixIn):
    """
    Common ancestor class of AddressBooks and Calendars.
    """
    log = Logger()

    compareAttributes = (
        "_name",
        "_home",
        "_resourceID",
    )

    _externalClass = None
    _objectResourceClass = None

    _bindSchema = None
    _homeSchema = None
    _homeChildSchema = None
    _homeChildMetaDataSchema = None
    _revisionsSchema = None
    _objectSchema = None


    @classmethod
    @inlineCallbacks
    def makeClass(cls, home, bindData, additionalBindData, metadataData, propstore=None, ownerHome=None):
        """
        Given the various database rows, build the actual class.

        @param home: the parent home object
        @type home: L{CommonHome}
        @param bindData: the standard set of bind columns
        @type bindData: C{list}
        @param additionalBindData: additional bind data specific to sub-classes
        @type additionalBindData: C{list}
        @param metadataData: metadata data
        @type metadataData: C{list}
        @param propstore: a property store to use, or C{None} to load it automatically
        @type propstore: L{PropertyStore}
        @param ownerHome: the home of the owner, or C{None} to figure it out automatically
        @type ownerHome: L{CommonHome}

        @return: the constructed child class
        @rtype: L{CommonHomeChild}
        """

        bindMode, _ignore_homeID, resourceID, externalID, name, bindStatus, bindRevision, bindMessage = bindData

        if ownerHome is None:
            if bindMode == _BIND_MODE_OWN:
                ownerHome = home
                ownerName = name
            else:
                ownerHome, ownerName = yield home.ownerHomeAndChildNameForChildID(resourceID)
        else:
            ownerName = None

        c = cls._externalClass if ownerHome.external() else cls
        child = c(
            home=home,
            name=name,
            resourceID=resourceID,
            mode=bindMode,
            status=bindStatus,
            revision=bindRevision,
            message=bindMessage,
            ownerHome=ownerHome,
            ownerName=ownerName,
            externalID=externalID,
        )

        if additionalBindData:
            for attr, value in zip(child.additionalBindAttributes(), additionalBindData):
                setattr(child, attr, value)

        if metadataData:
            for attr, value in zip(child.metadataAttributes(), metadataData):
                setattr(child, attr, value)

        # We have to re-adjust the property store object to account for possible shared
        # collections as previously we loaded them all as if they were owned
        if propstore and bindMode != _BIND_MODE_OWN:
            propstore._setDefaultUserUID(ownerHome.uid())
        yield child._loadPropertyStore(propstore)

        returnValue(child)


    @classmethod
    @inlineCallbacks
    def _getDBData(cls, home, name, resourceID, externalID):
        """
        Given a set of identifying information, load the data rows for the object. Only one of
        L{name}, L{resourceID} or L{externalID} is specified - others are C{None}.

        @param home: the parent home object
        @type home: L{CommonHome}
        @param name: the resource name
        @type name: C{str}
        @param resourceID: the resource ID
        @type resourceID: C{int}
        @param externalID: the resource ID of the external (cross-pod) referenced item
        @type externalID: C{int}
        """

        # Get the bind row data
        row = None
        queryCacher = home._txn._queryCacher

        if queryCacher:
            # Retrieve data from cache
            if name:
                cacheKey = queryCacher.keyForObjectWithName(home._resourceID, name)
            elif resourceID:
                cacheKey = queryCacher.keyForObjectWithResourceID(home._resourceID, resourceID)
            elif externalID:
                cacheKey = queryCacher.keyForObjectWithExternalID(home._resourceID, externalID)
            row = yield queryCacher.get(cacheKey)

        if row is None:
            # No cached copy
            if name:
                rows = yield cls._bindForNameAndHomeID.on(home._txn, name=name, homeID=home._resourceID)
            elif resourceID:
                rows = yield cls._bindForResourceIDAndHomeID.on(home._txn, resourceID=resourceID, homeID=home._resourceID)
            elif externalID:
                rows = yield cls._bindForExternalIDAndHomeID.on(home._txn, externalID=externalID, homeID=home._resourceID)
            row = rows[0] if rows else None

        if not row:
            returnValue(None)

        if queryCacher:
            # Cache the result
            queryCacher.setAfterCommit(home._txn, queryCacher.keyForObjectWithName(home._resourceID, name), row)
            queryCacher.setAfterCommit(home._txn, queryCacher.keyForObjectWithResourceID(home._resourceID, resourceID), row)
            queryCacher.setAfterCommit(home._txn, queryCacher.keyForObjectWithExternalID(home._resourceID, externalID), row)

        bindData = row[:cls.bindColumnCount]
        additionalBindData = row[cls.bindColumnCount:cls.bindColumnCount + len(cls.additionalBindColumns())]
        resourceID = bindData[cls.bindColumns().index(cls._bindSchema.RESOURCE_ID)]

        # Get the matching metadata data
        metadataData = None
        if queryCacher:
            # Retrieve from cache
            cacheKey = queryCacher.keyForHomeChildMetaData(resourceID)
            metadataData = yield queryCacher.get(cacheKey)

        if metadataData is None:
            # No cached copy
            metadataData = (yield cls._metadataByIDQuery.on(home._txn, resourceID=resourceID))[0]
            if queryCacher:
                # Cache the results
                yield queryCacher.setAfterCommit(home._txn, cacheKey, metadataData)

        returnValue((bindData, additionalBindData, metadataData,))


    def __init__(self, home, name, resourceID, mode, status, revision=0, message=None, ownerHome=None, ownerName=None, externalID=None):

        self._home = home
        self._name = name
        self._resourceID = resourceID
        self._externalID = externalID
        self._bindMode = mode
        self._bindStatus = status
        self._bindRevision = revision
        self._bindMessage = message
        self._ownerHome = home if ownerHome is None else ownerHome
        self._ownerName = name if ownerName is None else ownerName
        self._created = None
        self._modified = None
        self._objects = {}
        self._objectNames = None
        self._syncTokenRevision = None

        # Always use notifiers based off the owner home so that shared collections use tokens common
        # to the owner - and thus will be the same for each sharee. Without that, each sharee would have
        # a different token to subscribe to and thus would each need a separate push - whereas a common
        # token only requires one push (to multiple subscribers).
        if self._ownerHome._notifiers:
            self._notifiers = dict([(factory_name, notifier.clone(self),) for factory_name, notifier in self._ownerHome._notifiers.items()])
        else:
            self._notifiers = None


    def memoMe(self, key, memo):
        """
        Add this object to the memo dictionary in whatever fashion is appropriate.

        @param key: key used for lookup
        @type key: C{object} (typically C{str} or C{int})
        @param memo: the dict to store to
        @type memo: C{dict}
        """
        memo[self._name] = self
        memo[self._resourceID] = self


    @classmethod
    @inlineCallbacks
    def listObjects(cls, home):
        """
        Retrieve the names of the children that exist in the given home.

        @return: an iterable of C{str}s.
        """
        # FIXME: tests don't cover this as directly as they should.
        rows = yield cls._acceptedBindForHomeID.on(
            home._txn, homeID=home._resourceID
        )
        names = [row[cls.bindColumns().index(cls._bindSchema.RESOURCE_NAME)] for row in rows]
        returnValue(names)


    @classmethod
    @inlineCallbacks
    def loadAllObjects(cls, home):
        """
        Load all L{CommonHomeChild} instances which are children of a given
        L{CommonHome} and return a L{Deferred} firing a list of them.  This must
        create the child classes and initialize them using "batched" SQL
        operations to keep this constant wrt the number of children.  This is an
        optimization for Depth:1 operations on the home.
        """
        results = []

        # Load from the main table first
        dataRows = (yield cls._childrenAndMetadataForHomeID.on(home._txn, homeID=home._resourceID))

        if dataRows:
            # Get property stores
            childResourceIDs = [dataRow[2] for dataRow in dataRows]

            propertyStores = yield PropertyStore.forMultipleResourcesWithResourceIDs(
                home.uid(), None, None, home._txn, childResourceIDs
            )

            # Get revisions
            revisions = (yield cls._revisionsForResourceIDs(childResourceIDs).on(home._txn, resourceIDs=childResourceIDs))
            revisions = dict(revisions)

        # Create the actual objects merging in properties
        for dataRow in dataRows:
            bindData = dataRow[:cls.bindColumnCount]
            resourceID = bindData[cls.bindColumns().index(cls._bindSchema.RESOURCE_ID)]
            additionalBindData = dataRow[cls.bindColumnCount:cls.bindColumnCount + len(cls.additionalBindColumns())]
            metadataData = dataRow[cls.bindColumnCount + len(cls.additionalBindColumns()):]
            propstore = propertyStores.get(resourceID, None)

            child = yield cls.makeClass(home, bindData, additionalBindData, metadataData, propstore)
            child._syncTokenRevision = revisions.get(resourceID, 0)
            results.append(child)

        returnValue(results)


    @classmethod
    def objectWithName(cls, home, name, accepted=True):
        return cls.objectWith(home, name=name, accepted=accepted)


    @classmethod
    def objectWithID(cls, home, resourceID, accepted=True):
        return cls.objectWith(home, resourceID=resourceID, accepted=accepted)


    @classmethod
    def objectWithExternalID(cls, home, externalID, accepted=True):
        return cls.objectWith(home, externalID=externalID, accepted=accepted)


    @classmethod
    @inlineCallbacks
    def objectWith(cls, home, name=None, resourceID=None, externalID=None, accepted=True):
        """
        Create the object using one of the specified arguments as the key to load it. One
        and only one of the keyword arguments must be set.

        @param parent: parent collection
        @type parent: L{CommonHomeChild}
        @param name: name of the resource, or C{None}
        @type name: C{str}
        @param uid: resource data UID, or C{None}
        @type uid: C{str}
        @param resourceID: resource id
        @type resourceID: C{int}
        @param accepted: if C{True} only load owned or accepted share items
        @type accepted: C{bool}

        @return: the new object or C{None} if not found
        @rtype: C{CommonHomeChild}
        """

        dbData = yield cls._getDBData(home, name, resourceID, externalID)
        if dbData is None:
            returnValue(None)
        bindData, additionalBindData, metadataData = dbData

        bindStatus = bindData[cls.bindColumns().index(cls._bindSchema.BIND_STATUS)]
        if accepted is not None and (bindStatus == _BIND_STATUS_ACCEPTED) != bool(accepted):
            returnValue(None)

        child = yield cls.makeClass(home, bindData, additionalBindData, metadataData)
        returnValue(child)


    @classproperty
    def _insertHomeChild(cls):
        """
        DAL statement to create a home child with all default values.
        """
        child = cls._homeChildSchema
        return Insert(
            {child.RESOURCE_ID: schema.RESOURCE_ID_SEQ},
            Return=(child.RESOURCE_ID)
        )


    @classproperty
    def _insertHomeChildMetaData(cls):
        """
        DAL statement to create a home child with all default values.
        """
        child = cls._homeChildMetaDataSchema
        return Insert({child.RESOURCE_ID: Parameter("resourceID")},
                      Return=(child.CREATED, child.MODIFIED))


    @classmethod
    @inlineCallbacks
    def create(cls, home, name, externalID=None):

        if (yield cls._bindForNameAndHomeID.on(home._txn, name=name, homeID=home._resourceID)):
            raise HomeChildNameAlreadyExistsError(name)

        if name.startswith("."):
            raise HomeChildNameNotAllowedError(name)

        # Create this object
        resourceID = (yield cls._insertHomeChild.on(home._txn))[0][0]

        # Initialize this object
        _created, _modified = (yield cls._insertHomeChildMetaData.on(home._txn, resourceID=resourceID))[0]
        # Bind table needs entry
        yield cls._bindInsertQuery.on(
            home._txn, homeID=home._resourceID, resourceID=resourceID, externalID=externalID,
            name=name, mode=_BIND_MODE_OWN, bindStatus=_BIND_STATUS_ACCEPTED,
            message=None,
        )

        # Initialize other state
        child = yield cls.objectWithID(home, resourceID)

        yield child._initSyncToken()

        # Change notification for a create is on the home collection
        yield home.notifyChanged()
        yield child.notifyPropertyChanged()
        returnValue(child)


    @classproperty
    def _metadataByIDQuery(cls):
        """
        DAL query to retrieve created/modified dates based on a resource ID.
        """
        child = cls._homeChildMetaDataSchema
        return Select(cls.metadataColumns(),
                      From=child,
                      Where=child.RESOURCE_ID == Parameter("resourceID"))


    def id(self):
        """
        Retrieve the store identifier for this collection.

        @return: store identifier.
        @rtype: C{int}
        """
        return self._resourceID


    def external_id(self):
        """
        Retrieve the external store identifier for this collection.

        @return: a string.
        """
        return self._externalID


    def external(self):
        """
        Is this an external home.

        @return: a string.
        """
        return self.ownerHome().external()


    @property
    def _txn(self):
        return self._home._txn


    def directoryService(self):
        return self._txn.store().directoryService()


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)


    def exists(self):
        """
        An empty resource-id means this object does not yet exist in the DB.
        """
        return self._resourceID is not None


    def name(self):
        return self._name


    @classproperty
    def _renameQuery(cls):
        """
        DAL statement to rename a L{CommonHomeChild}
        """
        bind = cls._bindSchema
        return Update({bind.RESOURCE_NAME: Parameter("name")},
                      Where=(bind.RESOURCE_ID == Parameter("resourceID")).And(
                          bind.HOME_RESOURCE_ID == Parameter("homeID")))


    @inlineCallbacks
    def rename(self, name):
        """
        Change the name of this L{CommonHomeChild} and update its sync token to
        reflect that change.

        @return: a L{Deferred} which fires when the modification is complete.
        """

        if self.isShared() or self.external():
            raise ShareNotAllowed("Cannot rename a shared collection")

        oldName = self._name

        yield self.invalidateQueryCache()

        yield self._renameQuery.on(self._txn, name=name,
                                   resourceID=self._resourceID,
                                   homeID=self._home._resourceID)
        self._name = name
        # update memos
        del self._home._children[oldName]
        self._home._children[name] = self
        yield self._renameSyncToken()

        yield self.notifyPropertyChanged()
        yield self._home.notifyChanged()


    @classproperty
    def _deleteQuery(cls):
        """
        DAL statement to delete a L{CommonHomeChild} by its resource ID.
        """
        child = cls._homeChildSchema
        return Delete(child, Where=child.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def remove(self):

        # Stop sharing first
        yield self.ownerDeleteShare()

        # Do before setting _resourceID making changes
        yield self.notifyPropertyChanged()

        yield self.invalidateQueryCache()

        yield self._deletedSyncToken()
        yield self._deleteQuery.on(self._txn, NoSuchHomeChildError, resourceID=self._resourceID)
        yield self.properties()._removeResource()

        # Set to non-existent state
        self._resourceID = None
        self._created = None
        self._modified = None
        self._objects = {}

        yield self._home.notifyChanged()


    def ownerHome(self):
        """
        @see: L{ICalendar.ownerCalendarHome}
        @see: L{IAddressbook.ownerAddessbookHome}
        """
        return self._ownerHome


    def viewerHome(self):
        """
        @see: L{ICalendar.viewerCalendarHome}
        @see: L{IAddressbook.viewerAddressbookHome}
        """
        return self._home


    @classproperty
    def _ownerHomeWithResourceID(cls):
        """
        DAL query to retrieve the home resource ID and resource name of the owner from the bound
        home-child ID.
        """
        bind = cls._bindSchema
        return Select(
            [bind.HOME_RESOURCE_ID, bind.RESOURCE_NAME, ],
            From=bind,
            Where=(bind.RESOURCE_ID == Parameter("resourceID")).And(
                bind.BIND_MODE == _BIND_MODE_OWN)
        )


    @inlineCallbacks
    def objectResources(self):
        """
        Load and cache all children - Depth:1 optimization
        """
        results = (yield self._objectResourceClass.loadAllObjects(self))
        for result in results:
            self._objects[result.name()] = result
            self._objects[result.uid()] = result
            self._objects[result.id()] = result
        self._objectNames = sorted([result.name() for result in results])
        returnValue(results)


    @inlineCallbacks
    def objectResourcesWithNames(self, names):
        """
        Load and cache all named children - set of names optimization
        """
        results = (yield self._objectResourceClass.loadAllObjectsWithNames(self, names))
        for result in results:
            self._objects[result.name()] = result
            self._objects[result.uid()] = result
            self._objects[result.id()] = result
        self._objectNames = sorted([result.name() for result in results])
        returnValue(results)


    @classproperty
    def _objectResourceNamesQuery(cls):
        """
        DAL query to load all object resource names for a home child.
        """
        obj = cls._objectSchema
        return Select([obj.RESOURCE_NAME], From=obj,
                      Where=obj.PARENT_RESOURCE_ID == Parameter('resourceID'))


    @inlineCallbacks
    def listObjectResources(self):
        if self._objectNames is None:
            rows = yield self._objectResourceNamesQuery.on(
                self._txn, resourceID=self._resourceID)
            self._objectNames = sorted([row[0] for row in rows])
        returnValue(self._objectNames)


    @classproperty
    def _objectCountQuery(cls):
        """
        DAL query to count all object resources for a home child.
        """
        obj = cls._objectSchema
        return Select([Count(ALL_COLUMNS)], From=obj,
                      Where=obj.PARENT_RESOURCE_ID == Parameter('resourceID'))


    @inlineCallbacks
    def countObjectResources(self):
        if self._objectNames is None:
            rows = yield self._objectCountQuery.on(self._txn, resourceID=self._resourceID)
            returnValue(rows[0][0])
        returnValue(len(self._objectNames))


    def objectResourceWithName(self, name):
        if name in self._objects:
            return succeed(self._objects[name])
        else:
            return self._makeObjectResource(name=name)


    def objectResourceWithUID(self, uid):
        if uid in self._objects:
            return succeed(self._objects[uid])
        else:
            return self._makeObjectResource(uid=uid)


    def objectResourceWithID(self, resourceID):
        if resourceID in self._objects:
            return succeed(self._objects[resourceID])
        else:
            return self._makeObjectResource(resourceID=resourceID)


    @inlineCallbacks
    def _makeObjectResource(self, name=None, uid=None, resourceID=None):
        """
        We create the empty object first then have it initialize itself from the
        store.
        """
        objectResource = (
            yield self._objectResourceClass.objectWith(self, name=name, uid=uid, resourceID=resourceID)
        )
        if objectResource:
            self._objects[objectResource.name()] = objectResource
            self._objects[objectResource.uid()] = objectResource
            self._objects[objectResource.id()] = objectResource
        else:
            if resourceID:
                self._objects[resourceID] = None
            else:
                self._objects[name if name else uid] = None
        returnValue(objectResource)


    @classproperty
    def _resourceNameForUIDQuery(cls):
        """
        DAL query to retrieve the resource name for an object resource based on
        its UID column.
        """
        obj = cls._objectSchema
        return Select(
            [obj.RESOURCE_NAME], From=obj,
            Where=(obj.UID == Parameter("uid")
                  ).And(obj.PARENT_RESOURCE_ID == Parameter("resourceID")))


    @inlineCallbacks
    def resourceNameForUID(self, uid):
        try:
            resource = self._objects[uid]
            returnValue(resource.name() if resource else None)
        except KeyError:
            pass
        rows = yield self._resourceNameForUIDQuery.on(
            self._txn, uid=uid, resourceID=self._resourceID)
        if rows:
            returnValue(rows[0][0])
        else:
            self._objects[uid] = None
            returnValue(None)


    @classproperty
    def _resourceUIDForNameQuery(cls):
        """
        DAL query to retrieve the UID for an object resource based on its
        resource name column.
        """
        obj = cls._objectSchema
        return Select(
            [obj.UID], From=obj,
            Where=(obj.RESOURCE_NAME == Parameter("name")
                  ).And(obj.PARENT_RESOURCE_ID == Parameter("resourceID")))


    @inlineCallbacks
    def resourceUIDForName(self, name):
        try:
            resource = self._objects[name]
            returnValue(resource.uid() if resource else None)
        except KeyError:
            pass
        rows = yield self._resourceUIDForNameQuery.on(
            self._txn, name=name, resourceID=self._resourceID)
        if rows:
            returnValue(rows[0][0])
        else:
            self._objects[name] = None
            returnValue(None)


    @inlineCallbacks
    def createObjectResourceWithName(self, name, component, options=None):
        """
        Create a new resource with component data and optional metadata. We
        create the python object using the metadata then create the actual store
        object with setComponent.
        """

        # Create => a new resource name
        if name in self._objects and self._objects[name]:
            raise ObjectResourceNameAlreadyExistsError()

        # Apply check to the size of the collection
        if config.MaxResourcesPerCollection:
            child_count = (yield self.countObjectResources())
            if child_count >= config.MaxResourcesPerCollection:
                raise TooManyObjectResourcesError()

        objectResource = (
            yield self._objectResourceClass.create(self, name, component, options)
        )
        self._objects[objectResource.name()] = objectResource
        self._objects[objectResource.uid()] = objectResource
        self._objects[objectResource.id()] = objectResource

        # Note: create triggers a notification when the component is set, so we
        # don't need to call notify() here like we do for object removal.
        returnValue(objectResource)


    @inlineCallbacks
    def removedObjectResource(self, child):
        self._objects.pop(child.name(), None)
        self._objects.pop(child.uid(), None)
        self._objects.pop(child.id(), None)
        if self._objectNames and child.name() in self._objectNames:
            self._objectNames.remove(child.name())
        yield self._deleteRevision(child.name())
        yield self.notifyChanged(category=child.removeNotifyCategory())


    @classproperty
    def _moveParentUpdateQuery(cls, adjustName=False):
        """
        DAL query to update a child to be in a new parent.
        """
        obj = cls._objectSchema
        cols = {
            obj.PARENT_RESOURCE_ID: Parameter("newParentID")
        }
        if adjustName:
            cols[obj.RESOURCE_NAME] = Parameter("newName")
        return Update(
            cols,
            Where=obj.RESOURCE_ID == Parameter("resourceID")
        )


    def _movedObjectResource(self, child, newparent):
        """
        Method that subclasses can override to do an extra DB adjustments when a resource
        is moved.
        """
        return succeed(True)


    @inlineCallbacks
    def _validObjectResource(self, child, newparent, newname=None):
        """
        Check that the move operation is valid

        TODO: check that the resource name does not exist in the new parent, or that the UID
        does not exist there too.

        @param child: the child resource to move
        @type child: L{CommonObjectResource}
        @param newparent: the parent to move to
        @type newparent: L{CommonHomeChild}
        @param newname: new name to use in new parent
        @type newname: C{str} or C{None} for existing name
        """

        name = child.name()

        if newname is None:
            newname = name

        # Create => a new resource name
        if newname.startswith("."):
            raise ObjectResourceNameNotAllowedError(newname)

        # Make sure name is not already used - i.e., overwrite not allowed
        if (yield newparent.objectResourceWithName(newname)) is not None:
            raise ObjectResourceNameAlreadyExistsError(newname)

        # Apply check to the size of the collection
        if config.MaxResourcesPerCollection:
            child_count = (yield self.countObjectResources())
            if child_count >= config.MaxResourcesPerCollection:
                raise TooManyObjectResourcesError()

        returnValue(newname)


    @inlineCallbacks
    def moveObjectResource(self, child, newparent, newname=None):
        """
        Move a child of this collection into another collection without actually removing/re-inserting the data.
        Make sure sync and cache details for both collections are updated.

        TODO: check that the resource name does not exist in the new parent, or that the UID
        does not exist there too.

        @param child: the child resource to move
        @type child: L{CommonObjectResource}
        @param newparent: the parent to move to
        @type newparent: L{CommonHomeChild}
        @param newname: new name to use in new parent
        @type newname: C{str} or C{None} for existing name
        """

        name = child.name()
        newname = yield self._validObjectResource(child, newparent, newname)
        uid = child.uid()

        # Clean this collections cache and signal sync change
        self._objects.pop(name, None)
        self._objects.pop(uid, None)
        self._objects.pop(child.id(), None)
        yield self._deleteRevision(name)
        yield self.notifyChanged()

        # Handle cases where move is within the same collection or to a different collection
        # with/without a name change
        obj = self._objectSchema
        cols = {}
        if newparent._resourceID != self._resourceID:
            cols[obj.PARENT_RESOURCE_ID] = Parameter("newParentID")
        if newname != name:
            cols[obj.RESOURCE_NAME] = Parameter("newName")
        yield Update(
            cols,
            Where=obj.RESOURCE_ID == Parameter("resourceID")
        ).on(
            self._txn,
            resourceID=child._resourceID,
            newParentID=newparent._resourceID,
            newName=newname,
        )

        # Only signal a move when parent is different
        if newparent._resourceID != self._resourceID:
            yield self._movedObjectResource(child, newparent)

        child._parentCollection = newparent

        # Signal sync change on new collection
        newparent._objects.pop(name, None)
        newparent._objects.pop(uid, None)
        newparent._objects.pop(child.id(), None)
        yield newparent._insertRevision(newname)
        yield newparent.notifyChanged()


    @inlineCallbacks
    def moveObjectResourceCreateDelete(self, child, newparent, newname=None):
        """
        Move a child of this collection into another collection by doing a create/delete.

        TODO: check that the resource name does not exist in the new parent, or that the UID
        does not exist there too.

        @param child: the child resource to move
        @type child: L{CommonObjectResource}
        @param newparent: the parent to move to
        @type newparent: L{CommonHomeChild}
        @param newname: new name to use in new parent
        @type newname: C{str} or C{None} for existing name
        """

        name = child.name()
        newname = yield self._validObjectResource(child, newparent, newname)

        # Do a move as a create/delete
        component = yield child.component()
        yield newparent.moveObjectResourceHere(name, component)
        yield self.moveObjectResourceAway(child.id(), child)


    @inlineCallbacks
    def moveObjectResourceHere(self, name, component):
        """
        Create a new child in this collection as part of a move operation. This needs to be split out because
        behavior differs for sub-classes and cross-pod operations.

        @param name: new name to use in new parent
        @type name: C{str} or C{None} for existing name
        @param component: data for new resource
        @type component: L{Component}
        """

        yield self.createObjectResourceWithName(name, component)


    @inlineCallbacks
    def moveObjectResourceAway(self, rid, child=None):
        """
        Remove the child as the result of a move operation. This needs to be split out because
        behavior differs for sub-classes and cross-pod operations.

        @param rid: the child resource-id to move
        @type rid: C{int}
        @param child: the child resource to move - might be C{None} for cross-pod
        @type child: L{CommonObjectResource}
        """

        if child is None:
            child = yield self.objectResourceWithID(rid)
        yield child.remove()


    def objectResourcesHaveProperties(self):
        return False


    def search(self, filter):
        """
        Do a query of the contents of this collection.

        @param filter: the query filter to use
        @type filter: L{Filter}

        @return: the names of the matching resources
        @rtype: C{list}
        """

        # This implementation raises - sub-classes override to do the actual query
        raise IndexedSearchException()


    @inlineCallbacks
    def sharedChildResourceNamesSinceRevision(self, revision, depth):
        """
        Determine the list of child resources that have changed since the specified sync revision.
        We do the same SQL query for both depth "1" and "infinity", but filter the results for
        "1" to only account for a collection change.

        We need to handle shared collection a little differently from owned ones. When a shared collection
        is bound into a home we record a revision for it using the sharee home id and sharee collection name.
        That revision is the "starting point" for changes: so if sync occurs with a revision earlier than
        that, we return the list of all resources in the shared collection since they are all "new" as far
        as the client is concerned since the shared collection has just appeared. For a later revision, we
        just report the changes since that one. When a shared collection is removed from a home, we again
        record a revision for the sharee home and sharee collection name with the "deleted" flag set. That way
        the shared collection can be reported as removed.

        @param revision: the sync revision to compare to
        @type revision: C{str}
        @param depth: depth for determine what changed
        @type depth: C{str}
        """
        changed = set()
        deleted = set()
        invalid = set()
        if self.external():
            if depth == "1":
                pass
            else:
                invalid.add(self.name() + "/")
        else:
            # If revision is prior to when the share was created, then treat as a full sync of the share
            if revision != 0 and revision < self._bindRevision:
                if depth != "1":
                    # This should never happen unless the client the share existed, was removed and then
                    # re-added and the client has a token from before the remove. In that case the token is no
                    # longer valid - a full sync has to be done.
                    raise SyncTokenValidException
                else:
                    results = yield self.sharedChildResourceNamesSinceRevisionZero(depth)
                    returnValue(results)

            rev = self._revisionsSchema
            results = [
                (
                    self.name(),
                    name if name else "",
                    wasdeleted
                )
                for name, wasdeleted in
                (yield Select(
                    [rev.RESOURCE_NAME, rev.DELETED],
                    From=rev,
                    Where=(rev.REVISION > revision).And(
                    rev.RESOURCE_ID == self._resourceID)
                ).on(self._txn))
                if name
            ]

            for path, name, wasdeleted in results:
                if wasdeleted:
                    if depth == "1":
                        changed.add("%s/" % (path,))
                    else:
                        deleted.add("%s/%s" % (path, name,))

                # Always report collection as changed
                changed.add("%s/" % (path,))

                # Resource changed - for depth "infinity" report resource as changed
                if name and depth != "1":
                    changed.add("%s/%s" % (path, name,))

        returnValue((changed, deleted, invalid,))


    @inlineCallbacks
    def sharedChildResourceNamesSinceRevisionZero(self, depth):
        """
        Revision == 0 specialization of L{sharedChildResourceNamesSinceRevision}. We report on all
        existing resources -= this collection and children (if depth == infinite).

        @param depth: depth for determine what changed
        @type depth: C{str}
        """
        changed = set()
        deleted = set()
        invalid = set()
        path = self.name()
        if self.external():
            if depth == "1":
                changed.add("{}/".format(path))
            else:
                invalid.add("{}/".format(path))
        else:
            path = self.name()
            # Always report collection as changed
            changed.add(path + "/")

            # Resource changed - for depth "infinity" report resource as changed
            if depth != "1":
                for name in (yield self.listObjectResources()):
                    changed.add("%s/%s" % (path, name,))

        returnValue((changed, deleted, invalid,))


    @inlineCallbacks
    def _loadPropertyStore(self, props=None):
        if props is None:
            # Use any authz uid in place of the viewer uid so delegates have their own
            # set of properties
            props = yield PropertyStore.load(
                self.ownerHome().uid(),
                self.viewerHome().uid(),
                self.viewerHome().authzuid(),
                self._txn,
                self._resourceID,
                notifyCallback=self.notifyPropertyChanged
            )
        self.initPropertyStore(props)
        self._properties = props


    def properties(self):
        return self._properties


    def initPropertyStore(self, props):
        """
        A hook for subclasses to override in order to set up their property
        store after it's been created.

        @param props: the L{PropertyStore} from C{properties()}.
        """
        pass


    # IDataStoreObject
    def contentType(self):
        raise NotImplementedError()


    def md5(self):
        return None


    def size(self):
        return 0


    def created(self):
        return datetimeMktime(parseSQLTimestamp(self._created)) if self._created else None


    def modified(self):
        return datetimeMktime(parseSQLTimestamp(self._modified)) if self._modified else None


    def addNotifier(self, factory_name, notifier):
        if self._notifiers is None:
            self._notifiers = {}
        self._notifiers[factory_name] = notifier


    def getNotifier(self, factory_name):
        return self._notifiers.get(factory_name)


    def notifierID(self):
        return (self.ownerHome()._notifierPrefix, "%s/%s" % (self.ownerHome().uid(), self._ownerName,),)


    def parentNotifierID(self):
        return self.ownerHome().notifierID()


    def notifyChanged(self, category=ChangeCategory.default):
        """
        Send notifications when a child resource is changed.
        """
        return self._notifyChanged(property_change=False, category=category)


    def notifyPropertyChanged(self):
        """
        Send notifications when properties on this object change.
        """
        return self._notifyChanged(property_change=True)


    @inlineCallbacks
    def _notifyChanged(self, property_change=False, category=ChangeCategory.default):
        """
        Send notifications, change sync token and bump last modified because
        the resource has changed.  We ensure we only do this once per object
        per transaction.

        Note that we distinguish between property changes and child resource changes. For property
        changes we need to bump the collections revision token, but we must not do that for child
        changes because that can cause a deadlock (plus it is not needed as the overall revision
        token includes the child token via the max() construct in the query).

        @param property_change: indicates whether this is the result of a property change as opposed to
            a child resource being added, changed or removed.
        @type property_change: C{bool}
        """
        if self._txn.isNotifiedAlready(self):
            returnValue(None)
        self._txn.notificationAddedForObject(self)

        # Update modified if object still exists
        if self._resourceID:
            yield self.bumpModified()

            # Bump the collection level sync token only for property change
            if property_change:
                yield self._bumpSyncToken()

        # Send notifications
        if self._notifiers:
            # cache notifiers run in post commit
            notifier = self._notifiers.get("cache", None)
            if notifier:
                self._txn.postCommit(notifier.notify)
            # push notifiers add their work items immediately
            notifier = self._notifiers.get("push", None)
            if notifier:
                yield notifier.notify(self._txn, priority=category.value)


    @classproperty
    def _lockLastModifiedQuery(cls):
        schema = cls._homeChildMetaDataSchema
        return Select(
            From=schema,
            Where=schema.RESOURCE_ID == Parameter("resourceID"),
            ForUpdate=True,
            NoWait=True
        )


    @classproperty
    def _changeLastModifiedQuery(cls):
        schema = cls._homeChildMetaDataSchema
        return Update({schema.MODIFIED: utcNowSQL},
                      Where=schema.RESOURCE_ID == Parameter("resourceID"),
                      Return=schema.MODIFIED)


    @inlineCallbacks
    def bumpModified(self):
        """
        Bump the MODIFIED value. A possible deadlock could happen here if two
        or more simultaneous changes are happening. In that case it is OK for
        the MODIFIED change to fail so long as at least one works. We will use
        SAVEPOINT logic to handle ignoring the deadlock error. We use SELECT
        FOR UPDATE NOWAIT to ensure we do not delay the transaction whilst
        waiting for deadlock detection to kick in.
        """

        @inlineCallbacks
        def _bumpModified(subtxn):
            yield self._lockLastModifiedQuery.on(
                subtxn, resourceID=self._resourceID
            )
            result = yield self._changeLastModifiedQuery.on(
                subtxn, resourceID=self._resourceID
            )
            returnValue(result)

        try:
            self._modified = (
                yield self._txn.subtransaction(
                    _bumpModified, retries=0, failureOK=True
                )
            )[0][0]

            queryCacher = self._txn._queryCacher
            if queryCacher is not None:
                cacheKey = queryCacher.keyForHomeChildMetaData(
                    self._resourceID
                )
                yield queryCacher.invalidateAfterCommit(self._txn, cacheKey)
        except AllRetriesFailed:
            log.debug("CommonHomeChild.bumpModified failed")



class CommonObjectResource(FancyEqMixin, object):
    """
    Base class for object resources.
    """
    log = Logger()

    compareAttributes = (
        "_name",
        "_parentCollection",
    )

    _externalClass = None
    _objectSchema = None
    _componentClass = None

    # Sub-classes must override and set their version number. This is used for
    # on-demand data upgrades - i.e., any time old data is read it will be
    # converted to the latest format and written back.
    _currentDataVersion = 0

    BATCH_LOAD_SIZE = 50


    @classmethod
    @inlineCallbacks
    def makeClass(cls, parent, objectData, propstore=None):
        """
        Given the various database rows, build the actual class.

        @param parent: the parent collection object
        @type parent: L{CommonHomeChild}

        @param objectData: the standard set of object columns
        @type objectData: C{list}

        @param propstore: a property store to use, or C{None} to load it
            automatically
        @type propstore: L{PropertyStore}

        @return: the constructed child class
        @rtype: L{CommonHomeChild}
        """

        c = cls._externalClass if parent.external() else cls
        child = c(
            parent,
            objectData[cls._allColumns().index(cls._objectSchema.RESOURCE_NAME)],
            objectData[cls._allColumns().index(cls._objectSchema.UID)],
        )

        for attr, value in zip(child._rowAttributes(), objectData):
            setattr(child, attr, value)

        yield child._loadPropertyStore(propstore)

        returnValue(child)


    @classmethod
    @inlineCallbacks
    def _getDBData(cls, parent, name, uid, resourceID):
        """
        Given a set of identifying information, load the data rows for the object. Only one of
        L{name}, L{uid} or L{resourceID} is specified - others are C{None}.

        @param parent: the parent collection object
        @type parent: L{CommonHomeChild}
        @param name: the resource name
        @type name: C{str}
        @param uid: the UID of the data
        @type uid: C{str}
        @param resourceID: the resource ID
        @type resourceID: C{int}
        """

        rows = None
        if name:
            rows = yield cls._allColumnsWithParentAndName.on(
                parent._txn,
                name=name,
                parentID=parent._resourceID
            )
        elif uid:
            rows = yield cls._allColumnsWithParentAndUID.on(
                parent._txn,
                uid=uid,
                parentID=parent._resourceID
            )
        elif resourceID:
            rows = yield cls._allColumnsWithParentAndID.on(
                parent._txn,
                resourceID=resourceID,
                parentID=parent._resourceID
            )

        returnValue(rows[0] if rows else None)


    def __init__(self, parent, name, uid, resourceID=None, options=None):
        self._parentCollection = parent
        self._resourceID = resourceID
        self._name = name
        self._uid = uid
        self._md5 = None
        self._size = None
        self._created = None
        self._modified = None
        self._dataversion = None
        self._textData = None
        self._cachedComponent = None

        self._locked = False


    @classproperty
    def _allColumnsWithParentQuery(cls):
        obj = cls._objectSchema
        return Select(cls._allColumns(), From=obj,
                      Where=obj.PARENT_RESOURCE_ID == Parameter("parentID"))


    @classmethod
    @inlineCallbacks
    def _allColumnsWithParent(cls, parent):
        returnValue((yield cls._allColumnsWithParentQuery.on(
            parent._txn, parentID=parent._resourceID)))


    @classmethod
    @inlineCallbacks
    def loadAllObjects(cls, parent):
        """
        Load all child objects and return a list of them. This must create the
        child classes and initialize them using "batched" SQL operations to keep
        this constant wrt the number of children. This is an optimization for
        Depth:1 operations on the collection.
        """

        results = []

        # Load from the main table first
        dataRows = yield cls._allColumnsWithParent(parent)

        if dataRows:
            # Get property stores for all these child resources (if any found)
            if parent.objectResourcesHaveProperties():
                propertyStores = (yield PropertyStore.forMultipleResources(
                    parent._home.uid(),
                    None,
                    None,
                    parent._txn,
                    cls._objectSchema.RESOURCE_ID,
                    cls._objectSchema.PARENT_RESOURCE_ID,
                    parent._resourceID
                ))
            else:
                propertyStores = {}

        # Create the actual objects merging in properties
        for row in dataRows:
            resourceID = row[cls._allColumns().index(cls._objectSchema.RESOURCE_ID)]
            propstore = propertyStores.get(resourceID, None)

            child = yield cls.makeClass(parent, row, propstore=propstore)
            results.append(child)

        returnValue(results)


    @classmethod
    @inlineCallbacks
    def loadAllObjectsWithNames(cls, parent, names):
        """
        Load all child objects with the specified names, doing so in batches (because we need to match
        using SQL "resource_name in (...)" where there might be a character length limit on the number
        of items in the set).
        """
        names = tuple(names)
        results = []
        while(len(names)):
            result_batch = (yield cls._loadAllObjectsWithNames(parent, names[:cls.BATCH_LOAD_SIZE]))
            results.extend(result_batch)
            names = names[cls.BATCH_LOAD_SIZE:]

        returnValue(results)


    @classmethod
    def _allColumnsWithParentAndNamesQuery(cls, names):
        obj = cls._objectSchema
        return Select(cls._allColumns(), From=obj,
                      Where=(obj.PARENT_RESOURCE_ID == Parameter("parentID")).And(
                          obj.RESOURCE_NAME.In(Parameter("names", len(names)))))


    @classmethod
    @inlineCallbacks
    def _allColumnsWithParentAndNames(cls, parent, names):
        returnValue((yield cls._allColumnsWithParentAndNamesQuery(names).on(
            parent._txn, parentID=parent._resourceID, names=names)))


    @classmethod
    @inlineCallbacks
    def _loadAllObjectsWithNames(cls, parent, names):
        """
        Load all child objects with the specified names. This must create the
        child classes and initialize them using "batched" SQL operations to keep
        this constant wrt the number of children. This is an optimization for
        Depth:1 operations on the collection.
        """

        # Optimize case of single name to load
        if len(names) == 1:
            obj = yield cls.objectWithName(parent, names[0])
            returnValue([obj] if obj else [])

        results = []

        # Load from the main table first
        dataRows = yield cls._allColumnsWithParentAndNames(parent, names)

        if dataRows:
            # Get property stores for all these child resources
            if parent.objectResourcesHaveProperties():
                propertyStores = (yield PropertyStore.forMultipleResourcesWithResourceIDs(
                    parent._home.uid(),
                    None,
                    None,
                    parent._txn,
                    tuple([row[0] for row in dataRows]),
                ))
            else:
                propertyStores = {}

        # Create the actual objects merging in properties
        for row in dataRows:
            resourceID = row[cls._allColumns().index(cls._objectSchema.RESOURCE_ID)]
            propstore = propertyStores.get(resourceID, None)

            child = yield cls.makeClass(parent, row, propstore=propstore)
            results.append(child)

        returnValue(results)


    @classmethod
    def objectWithName(cls, parent, name):
        return cls.objectWith(parent, name=name)


    @classmethod
    def objectWithUID(cls, parent, uid):
        return cls.objectWith(parent, uid=uid)


    @classmethod
    def objectWithID(cls, parent, resourceID):
        return cls.objectWith(parent, resourceID=resourceID)


    @classmethod
    @inlineCallbacks
    def objectWith(cls, parent, name=None, uid=None, resourceID=None):
        """
        Create the object using one of the specified arguments as the key to load it. One
        and only one of the keyword arguments must be set.

        @param parent: parent collection
        @type parent: L{CommonHomeChild}
        @param name: name of the resource, or C{None}
        @type name: C{str}
        @param uid: resource data UID, or C{None}
        @type uid: C{str}
        @param resourceID: resource id
        @type resourceID: C{int}

        @return: the new object or C{None} if not found
        @rtype: C{CommonObjectResource}
        """

        row = yield cls._getDBData(parent, name, uid, resourceID)

        if row:
            child = yield cls.makeClass(parent, row)
            returnValue(child)
        else:
            returnValue(None)


    @classmethod
    @inlineCallbacks
    def create(cls, parent, name, component, options=None):

        child = (yield parent.objectResourceWithName(name))
        if child:
            raise ObjectResourceNameAlreadyExistsError(name)

        if name.startswith("."):
            raise ObjectResourceNameNotAllowedError(name)

        c = cls._externalClass if parent.external() else cls
        objectResource = c(parent, name, None, None, options=options)
        yield objectResource.setComponent(component, inserting=True)
        yield objectResource._loadPropertyStore(created=True)

        # Note: setComponent triggers a notification, so we don't need to
        # call notify( ) here like we do for object removal.
        returnValue(objectResource)


    @classmethod
    def _allColumnsWithParentAnd(cls, column, paramName):
        """
        DAL query for all columns where PARENT_RESOURCE_ID matches a parentID
        parameter and a given instance column matches a given parameter name.
        """
        return Select(
            cls._allColumns(), From=cls._objectSchema,
            Where=(column == Parameter(paramName)).And(
                cls._objectSchema.PARENT_RESOURCE_ID == Parameter("parentID"))
        )


    @classproperty
    def _allColumnsWithParentAndName(cls):
        return cls._allColumnsWithParentAnd(cls._objectSchema.RESOURCE_NAME, "name")


    @classproperty
    def _allColumnsWithParentAndUID(cls):
        return cls._allColumnsWithParentAnd(cls._objectSchema.UID, "uid")


    @classproperty
    def _allColumnsWithParentAndID(cls):
        return cls._allColumnsWithParentAnd(cls._objectSchema.RESOURCE_ID, "resourceID")


    @classmethod
    def _allColumns(cls):
        """
        Full set of columns in the object table that need to be loaded to
        initialize the object resource state.
        """
        obj = cls._objectSchema
        return [
            obj.RESOURCE_ID,
            obj.RESOURCE_NAME,
            obj.UID,
            obj.MD5,
            Len(obj.TEXT),
            obj.CREATED,
            obj.MODIFIED,
            obj.DATAVERSION,
        ]


    @classmethod
    def _rowAttributes(cls):
        return (
            "_resourceID",
            "_name",
            "_uid",
            "_md5",
            "_size",
            "_created",
            "_modified",
            "_dataversion",
        )


    @classmethod
    def _otherSerializedAttributes(cls):
        return (
            "_componentChanged",
        )


    def externalize(self):
        """
        Create a dictionary mapping key attributes so this object can be sent over a cross-pod call
        and reconstituted at the other end. Note that the other end may have a different schema so
        the attributes may not match exactly and will need to be processed accordingly.
        """
        return dict([(attr[1:], getattr(self, attr, None)) for attr in itertools.chain(self._rowAttributes(), self._otherSerializedAttributes())])


    @classmethod
    @inlineCallbacks
    def internalize(cls, parent, mapping):
        """
        Given a mapping generated by L{externalize}, convert the values into an array of database
        like items that conforms to the ordering of L{_allColumns} so it can be fed into L{makeClass}.
        Note that there may be a schema mismatch with the external data, so treat missing items as
        C{None} and ignore extra items.
        """

        child = yield cls.makeClass(parent, [mapping.get(row[1:]) for row in cls._rowAttributes()])
        for attr in cls._otherSerializedAttributes():
            setattr(child, attr, mapping.get(attr[1:]))
        returnValue(child)


    @inlineCallbacks
    def _loadPropertyStore(self, props=None, created=False):
        if props is None:
            if self._parentCollection.objectResourcesHaveProperties():
                props = yield PropertyStore.load(
                    self._parentCollection.ownerHome().uid(),
                    self._parentCollection.viewerHome().uid(),
                    self._parentCollection.viewerHome().authzuid(),
                    self._txn,
                    self._resourceID,
                    created=created
                )
            else:
                props = NonePropertyStore(self._parentCollection.ownerHome().uid())
        self.initPropertyStore(props)
        self._propertyStore = props


    def properties(self):
        return self._propertyStore


    def initPropertyStore(self, props):
        """
        A hook for subclasses to override in order to set up their property
        store after it's been created.

        @param props: the L{PropertyStore} from C{properties()}.
        """
        pass


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)


    def id(self):
        """
        Retrieve the store identifier for this object resource.

        @return: store identifier.
        @rtype: C{int}
        """
        return self._resourceID


    @property
    def _txn(self):
        return self._parentCollection._txn


    @property
    def _home(self):
        return self._parentCollection._home


    def transaction(self):
        return self._parentCollection._txn


    def directoryService(self):
        return self._txn.store().directoryService()


    def parentCollection(self):
        return self._parentCollection


    def owned(self):
        return self._parentCollection.owned()


    def ownerHome(self):
        return self._parentCollection.ownerHome()


    def viewerHome(self):
        return self._parentCollection.viewerHome()


    @classmethod
    def _selectForUpdateQuery(cls, nowait):
        """
        DAL statement to lock a L{CommonObjectResource} by its resource ID.
        """
        return Select(From=cls._objectSchema, ForUpdate=True, NoWait=nowait, Where=cls._objectSchema.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def lock(self, wait=True, txn=None):
        """
        Attempt to obtain a row lock on the object resource. 'wait' determines whether the DB call will
        block on any existing lock held by someone else. Lock will remain until
        transaction is complete, or fail if resource is missing, or it is already locked
        and wait=False is used. Occasionally we need to lock via a separate transaction so we
        pass that in too.

        @param wait: whether or not to wait on someone else's lock
        @type wait: C{bool}
        @param txn: alternative transaction to use
        @type txn: L{CommonStoreTransaction}

        @raise: L{NoSuchObjectResourceError} if resource does not exist, other L{Exception}
                if already locked and NOWAIT is used.
        """

        txn = txn if txn is not None else self._txn
        yield self._selectForUpdateQuery(not wait).on(txn, NoSuchObjectResourceError, resourceID=self._resourceID)
        self._locked = True


    def setComponent(self, component, inserting=False):
        raise NotImplementedError


    def component(self):
        raise NotImplementedError


    @inlineCallbacks
    def componentType(self):
        returnValue((yield self.component()).mainType())


    @classproperty
    def _deleteQuery(cls):
        """
        DAL statement to delete a L{CommonObjectResource} by its resource ID.
        """
        return Delete(cls._objectSchema, Where=cls._objectSchema.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def moveTo(self, destination, name=None):
        """
        Move object to another collection.

        @param destination: parent collection to move to
        @type destination: L{CommonHomeChild}
        @param name: new name in destination
        @type name: C{str} or C{None} to use existing name
        """

        yield self.moveValidation(destination, name)

        # If possible we do a "fast" move by simply fixing up the database information directly rather than
        # re-writing any data. That is only possible when the source and destination are on this pod.
        if not self._parentCollection.external() and not destination.external():
            yield self._parentCollection.moveObjectResource(self, destination, name)
        else:
            yield self._parentCollection.moveObjectResourceCreateDelete(self, destination, name)


    def moveValidation(self, destination, name):
        raise NotImplementedError


    @inlineCallbacks
    def remove(self):
        yield self._deleteQuery.on(self._txn, NoSuchObjectResourceError,
                                   resourceID=self._resourceID)
        yield self.properties()._removeResource()

        yield self._parentCollection.removedObjectResource(self)

        # Set to non-existent state
        self._resourceID = None
        self._name = None
        self._uid = None
        self._md5 = None
        self._size = None
        self._created = None
        self._modified = None
        self._textData = None
        self._cachedComponent = None


    def removeNotifyCategory(self):
        """
        Indicates what category to use when determining the priority of push
        notifications when this object is removed.

        @returns: The "default" category (but should be overridden to return
            values such as "inbox")
        @rtype: L{ChangeCategory}
        """
        return ChangeCategory.default


    def uid(self):
        return self._uid


    def name(self):
        return self._name


    # IDataStoreObject
    def contentType(self):
        raise NotImplementedError()


    def md5(self):
        return self._md5


    def size(self):
        return self._size


    def created(self):
        return datetimeMktime(parseSQLTimestamp(self._created))


    def modified(self):
        return datetimeMktime(parseSQLTimestamp(self._modified))


    @classproperty
    def _textByIDQuery(cls):
        """
        DAL query to load iCalendar/vCard text via an object's resource ID.
        """
        obj = cls._objectSchema
        return Select([obj.TEXT], From=obj,
                      Where=obj.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def _text(self):
        if self._textData is None:
            texts = (
                yield self._textByIDQuery.on(self._txn,
                                             resourceID=self._resourceID)
            )
            if texts:
                text = texts[0][0]
                self._textData = text
                returnValue(text)
            else:
                raise ConcurrentModification()
        else:
            returnValue(self._textData)



class NotificationCollection(FancyEqMixin, _SharedSyncLogic):
    log = Logger()

    implements(INotificationCollection)

    compareAttributes = (
        "_uid",
        "_resourceID",
    )

    _revisionsSchema = schema.NOTIFICATION_OBJECT_REVISIONS
    _homeSchema = schema.NOTIFICATION_HOME


    def __init__(self, txn, uid, resourceID):

        self._txn = txn
        self._uid = uid
        self._resourceID = resourceID
        self._dataVersion = None
        self._notifications = {}
        self._notificationNames = None
        self._syncTokenRevision = None

        # Make sure we have push notifications setup to push on this collection
        # as well as the home it is in
        self._notifiers = dict([(factory_name, factory.newNotifier(self),) for factory_name, factory in txn._notifierFactories.items()])

    _resourceIDFromUIDQuery = Select(
        [_homeSchema.RESOURCE_ID], From=_homeSchema,
        Where=_homeSchema.OWNER_UID == Parameter("uid"))

    _UIDFromResourceIDQuery = Select(
        [_homeSchema.OWNER_UID], From=_homeSchema,
        Where=_homeSchema.RESOURCE_ID == Parameter("rid"))

    _provisionNewNotificationsQuery = Insert(
        {_homeSchema.OWNER_UID: Parameter("uid")},
        Return=_homeSchema.RESOURCE_ID
    )


    @property
    def _home(self):
        """
        L{NotificationCollection} serves as its own C{_home} for the purposes of
        working with L{_SharedSyncLogic}.
        """
        return self


    @classmethod
    @inlineCallbacks
    def notificationsWithUID(cls, txn, uid, create):
        """
        @param uid: I'm going to assume uid is utf-8 encoded bytes
        """
        rows = yield cls._resourceIDFromUIDQuery.on(txn, uid=uid)

        if rows:
            resourceID = rows[0][0]
            created = False
        elif create:
            # Determine if the user is local or external
            record = yield txn.directoryService().recordWithUID(uid.decode("utf-8"))
            if record is None:
                raise DirectoryRecordNotFoundError("Cannot create home for UID since no directory record exists: {}".format(uid))

            state = _HOME_STATUS_NORMAL if record.thisServer() else _HOME_STATUS_EXTERNAL
            if state == _HOME_STATUS_EXTERNAL:
                raise RecordNotAllowedError("Cannot store notifications for external user: {}".format(uid))

            # Use savepoint so we can do a partial rollback if there is a race
            # condition where this row has already been inserted
            savepoint = SavepointAction("notificationsWithUID")
            yield savepoint.acquire(txn)

            try:
                resourceID = str((
                    yield cls._provisionNewNotificationsQuery.on(txn, uid=uid)
                )[0][0])
            except Exception:
                # FIXME: Really want to trap the pg.DatabaseError but in a non-
                # DB specific manner
                yield savepoint.rollback(txn)

                # Retry the query - row may exist now, if not re-raise
                rows = yield cls._resourceIDFromUIDQuery.on(txn, uid=uid)
                if rows:
                    resourceID = rows[0][0]
                    created = False
                else:
                    raise
            else:
                created = True
                yield savepoint.release(txn)
        else:
            returnValue(None)
        collection = cls(txn, uid, resourceID)
        yield collection._loadPropertyStore()
        if created:
            yield collection._initSyncToken()
            yield collection.notifyChanged()
        returnValue(collection)


    @classmethod
    @inlineCallbacks
    def notificationsWithResourceID(cls, txn, rid):
        rows = yield cls._UIDFromResourceIDQuery.on(txn, rid=rid)

        if rows:
            uid = rows[0][0]
            result = (yield cls.notificationsWithUID(txn, uid, create=False))
            returnValue(result)
        else:
            returnValue(None)


    @inlineCallbacks
    def _loadPropertyStore(self):
        self._propertyStore = yield PropertyStore.load(
            self._uid,
            self._uid,
            None,
            self._txn,
            self._resourceID,
            notifyCallback=self.notifyChanged
        )


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)


    def id(self):
        """
        Retrieve the store identifier for this collection.

        @return: store identifier.
        @rtype: C{int}
        """
        return self._resourceID


    @classproperty
    def _dataVersionQuery(cls):
        nh = cls._homeSchema
        return Select(
            [nh.DATAVERSION], From=nh,
            Where=nh.RESOURCE_ID == Parameter("resourceID")
        )


    @inlineCallbacks
    def dataVersion(self):
        if self._dataVersion is None:
            self._dataVersion = (yield self._dataVersionQuery.on(
                self._txn, resourceID=self._resourceID))[0][0]
        returnValue(self._dataVersion)


    def name(self):
        return "notification"


    def uid(self):
        return self._uid


    def owned(self):
        return True


    def ownerHome(self):
        return self._home


    def viewerHome(self):
        return self._home


    @inlineCallbacks
    def notificationObjects(self):
        results = (yield NotificationObject.loadAllObjects(self))
        for result in results:
            self._notifications[result.uid()] = result
        self._notificationNames = sorted([result.name() for result in results])
        returnValue(results)

    _notificationUIDsForHomeQuery = Select(
        [schema.NOTIFICATION.NOTIFICATION_UID], From=schema.NOTIFICATION,
        Where=schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID ==
        Parameter("resourceID"))


    @inlineCallbacks
    def listNotificationObjects(self):
        if self._notificationNames is None:
            rows = yield self._notificationUIDsForHomeQuery.on(
                self._txn, resourceID=self._resourceID)
            self._notificationNames = sorted([row[0] for row in rows])
        returnValue(self._notificationNames)


    # used by _SharedSyncLogic.resourceNamesSinceRevision()
    def listObjectResources(self):
        return self.listNotificationObjects()


    def _nameToUID(self, name):
        """
        Based on the file-backed implementation, the 'name' is just uid +
        ".xml".
        """
        return name.rsplit(".", 1)[0]


    def notificationObjectWithName(self, name):
        return self.notificationObjectWithUID(self._nameToUID(name))


    @memoizedKey("uid", "_notifications")
    @inlineCallbacks
    def notificationObjectWithUID(self, uid):
        """
        Create an empty notification object first then have it initialize itself
        from the store.
        """
        no = NotificationObject(self, uid)
        no = (yield no.initFromStore())
        returnValue(no)


    @inlineCallbacks
    def writeNotificationObject(self, uid, notificationtype, notificationdata):

        inserting = False
        notificationObject = yield self.notificationObjectWithUID(uid)
        if notificationObject is None:
            notificationObject = NotificationObject(self, uid)
            inserting = True
        yield notificationObject.setData(uid, notificationtype, notificationdata, inserting=inserting)
        if inserting:
            yield self._insertRevision("%s.xml" % (uid,))
            if self._notificationNames is not None:
                self._notificationNames.append(notificationObject.uid())
        else:
            yield self._updateRevision("%s.xml" % (uid,))
        yield self.notifyChanged()


    def removeNotificationObjectWithName(self, name):
        if self._notificationNames is not None:
            self._notificationNames.remove(self._nameToUID(name))
        return self.removeNotificationObjectWithUID(self._nameToUID(name))

    _removeByUIDQuery = Delete(
        From=schema.NOTIFICATION,
        Where=(schema.NOTIFICATION.NOTIFICATION_UID == Parameter("uid")).And(
            schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID
            == Parameter("resourceID")))


    @inlineCallbacks
    def removeNotificationObjectWithUID(self, uid):
        yield self._removeByUIDQuery.on(
            self._txn, uid=uid, resourceID=self._resourceID)
        self._notifications.pop(uid, None)
        yield self._deleteRevision("%s.xml" % (uid,))
        yield self.notifyChanged()

    _initSyncTokenQuery = Insert(
        {
            _revisionsSchema.HOME_RESOURCE_ID : Parameter("resourceID"),
            _revisionsSchema.RESOURCE_NAME    : None,
            _revisionsSchema.REVISION         : schema.REVISION_SEQ,
            _revisionsSchema.DELETED          : False
        }, Return=_revisionsSchema.REVISION
    )


    @inlineCallbacks
    def _initSyncToken(self):
        self._syncTokenRevision = (yield self._initSyncTokenQuery.on(
            self._txn, resourceID=self._resourceID))[0][0]

    _syncTokenQuery = Select(
        [Max(_revisionsSchema.REVISION)], From=_revisionsSchema,
        Where=_revisionsSchema.HOME_RESOURCE_ID == Parameter("resourceID")
    )


    @inlineCallbacks
    def syncToken(self):
        if self._syncTokenRevision is None:
            self._syncTokenRevision = (
                yield self._syncTokenQuery.on(
                    self._txn, resourceID=self._resourceID)
            )[0][0]
            if self._syncTokenRevision is None:
                self._syncTokenRevision = int((yield self._txn.calendarserverValue("MIN-VALID-REVISION")))
        returnValue("%s_%s" % (self._resourceID, self._syncTokenRevision))


    def properties(self):
        return self._propertyStore


    def addNotifier(self, factory_name, notifier):
        if self._notifiers is None:
            self._notifiers = {}
        self._notifiers[factory_name] = notifier


    def getNotifier(self, factory_name):
        return self._notifiers.get(factory_name)


    def notifierID(self):
        return (self._txn._homeClass[self._txn._primaryHomeType]._notifierPrefix, "%s/notification" % (self.ownerHome().uid(),),)


    def parentNotifierID(self):
        return (self._txn._homeClass[self._txn._primaryHomeType]._notifierPrefix, "%s" % (self.ownerHome().uid(),),)


    @inlineCallbacks
    def notifyChanged(self, category=ChangeCategory.default):
        """
        Send notifications, change sync token and bump last modified because
        the resource has changed.  We ensure we only do this once per object
        per transaction.
        """
        if self._txn.isNotifiedAlready(self):
            returnValue(None)
        self._txn.notificationAddedForObject(self)

        # Send notifications
        if self._notifiers:
            # cache notifiers run in post commit
            notifier = self._notifiers.get("cache", None)
            if notifier:
                self._txn.postCommit(notifier.notify)
            # push notifiers add their work items immediately
            notifier = self._notifiers.get("push", None)
            if notifier:
                yield notifier.notify(self._txn, priority=category.value)

        returnValue(None)


    @classproperty
    def _completelyNewRevisionQuery(cls):
        rev = cls._revisionsSchema
        return Insert({rev.HOME_RESOURCE_ID: Parameter("homeID"),
                       # rev.RESOURCE_ID: Parameter("resourceID"),
                       rev.RESOURCE_NAME: Parameter("name"),
                       rev.REVISION: schema.REVISION_SEQ,
                       rev.DELETED: False},
                      Return=rev.REVISION)


    def _maybeNotify(self):
        """
        Emit a push notification after C{_changeRevision}.
        """
        return self.notifyChanged()


    @inlineCallbacks
    def remove(self):
        """
        Remove DB rows corresponding to this notification home.
        """
        # Delete NOTIFICATION rows
        no = schema.NOTIFICATION
        kwds = {"ResourceID": self._resourceID}
        yield Delete(
            From=no,
            Where=(
                no.NOTIFICATION_HOME_RESOURCE_ID == Parameter("ResourceID")
            ),
        ).on(self._txn, **kwds)

        # Delete NOTIFICATION_HOME (will cascade to NOTIFICATION_OBJECT_REVISIONS)
        nh = schema.NOTIFICATION_HOME
        yield Delete(
            From=nh,
            Where=(
                nh.RESOURCE_ID == Parameter("ResourceID")
            ),
        ).on(self._txn, **kwds)



class NotificationObject(FancyEqMixin, object):
    """
    This used to store XML data and an XML element for the type. But we are now switching it
    to use JSON internally. The app layer will convert that to XML and fill in the "blanks" as
    needed for the app.
    """
    log = Logger()

    implements(INotificationObject)

    compareAttributes = (
        "_resourceID",
        "_home",
    )

    _objectSchema = schema.NOTIFICATION

    def __init__(self, home, uid):
        self._home = home
        self._resourceID = None
        self._uid = uid
        self._md5 = None
        self._size = None
        self._created = None
        self._modified = None
        self._notificationType = None
        self._notificationData = None


    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self._resourceID)


    @classproperty
    def _allColumnsByHomeIDQuery(cls):
        """
        DAL query to load all columns by home ID.
        """
        obj = cls._objectSchema
        return Select(
            [obj.RESOURCE_ID, obj.NOTIFICATION_UID, obj.MD5,
             Len(obj.NOTIFICATION_DATA), obj.NOTIFICATION_TYPE, obj.CREATED, obj.MODIFIED],
            From=obj,
            Where=(obj.NOTIFICATION_HOME_RESOURCE_ID == Parameter("homeID"))
        )


    @classmethod
    @inlineCallbacks
    def loadAllObjects(cls, parent):
        """
        Load all child objects and return a list of them. This must create the
        child classes and initialize them using "batched" SQL operations to keep
        this constant wrt the number of children. This is an optimization for
        Depth:1 operations on the collection.
        """

        results = []

        # Load from the main table first
        dataRows = (
            yield cls._allColumnsByHomeIDQuery.on(parent._txn,
                                                  homeID=parent._resourceID))

        if dataRows:
            # Get property stores for all these child resources (if any found)
            propertyStores = (yield PropertyStore.forMultipleResources(
                parent.uid(),
                None,
                None,
                parent._txn,
                schema.NOTIFICATION.RESOURCE_ID,
                schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID,
                parent._resourceID,
            ))

        # Create the actual objects merging in properties
        for row in dataRows:
            child = cls(parent, None)
            (child._resourceID,
             child._uid,
             child._md5,
             child._size,
             child._notificationType,
             child._created,
             child._modified,) = tuple(row)
            try:
                child._notificationType = json.loads(child._notificationType)
            except ValueError:
                pass
            if isinstance(child._notificationType, unicode):
                child._notificationType = child._notificationType.encode("utf-8")
            child._loadPropertyStore(
                props=propertyStores.get(child._resourceID, None)
            )
            results.append(child)

        returnValue(results)


    @classproperty
    def _oneNotificationQuery(cls):
        no = cls._objectSchema
        return Select(
            [
                no.RESOURCE_ID,
                no.MD5,
                Len(no.NOTIFICATION_DATA),
                no.NOTIFICATION_TYPE,
                no.CREATED,
                no.MODIFIED
            ],
            From=no,
            Where=(no.NOTIFICATION_UID ==
                   Parameter("uid")).And(no.NOTIFICATION_HOME_RESOURCE_ID ==
                                         Parameter("homeID")))


    @inlineCallbacks
    def initFromStore(self):
        """
        Initialise this object from the store, based on its UID and home
        resource ID. We read in and cache all the extra metadata from the DB to
        avoid having to do DB queries for those individually later.

        @return: L{self} if object exists in the DB, else C{None}
        """
        rows = (yield self._oneNotificationQuery.on(
            self._txn, uid=self._uid, homeID=self._home._resourceID))
        if rows:
            (self._resourceID,
             self._md5,
             self._size,
             self._notificationType,
             self._created,
             self._modified,) = tuple(rows[0])
            try:
                self._notificationType = json.loads(self._notificationType)
            except ValueError:
                pass
            if isinstance(self._notificationType, unicode):
                self._notificationType = self._notificationType.encode("utf-8")
            self._loadPropertyStore()
            returnValue(self)
        else:
            returnValue(None)


    def _loadPropertyStore(self, props=None, created=False):
        if props is None:
            props = NonePropertyStore(self._home.uid())
        self._propertyStore = props


    def properties(self):
        return self._propertyStore


    def id(self):
        """
        Retrieve the store identifier for this object.

        @return: store identifier.
        @rtype: C{int}
        """
        return self._resourceID


    @property
    def _txn(self):
        return self._home._txn


    def notificationCollection(self):
        return self._home


    def uid(self):
        return self._uid


    def name(self):
        return self.uid() + ".xml"


    @classproperty
    def _newNotificationQuery(cls):
        no = cls._objectSchema
        return Insert(
            {
                no.NOTIFICATION_HOME_RESOURCE_ID: Parameter("homeID"),
                no.NOTIFICATION_UID: Parameter("uid"),
                no.NOTIFICATION_TYPE: Parameter("notificationType"),
                no.NOTIFICATION_DATA: Parameter("notificationData"),
                no.MD5: Parameter("md5"),
            },
            Return=[no.RESOURCE_ID, no.CREATED, no.MODIFIED]
        )


    @classproperty
    def _updateNotificationQuery(cls):
        no = cls._objectSchema
        return Update(
            {
                no.NOTIFICATION_TYPE: Parameter("notificationType"),
                no.NOTIFICATION_DATA: Parameter("notificationData"),
                no.MD5: Parameter("md5"),
            },
            Where=(no.NOTIFICATION_HOME_RESOURCE_ID == Parameter("homeID")).And(
                no.NOTIFICATION_UID == Parameter("uid")),
            Return=no.MODIFIED
        )


    @inlineCallbacks
    def setData(self, uid, notificationtype, notificationdata, inserting=False):
        """
        Set the object resource data and update and cached metadata.
        """

        notificationtext = json.dumps(notificationdata)
        self._notificationType = notificationtype
        self._md5 = hashlib.md5(notificationtext).hexdigest()
        self._size = len(notificationtext)
        if inserting:
            rows = yield self._newNotificationQuery.on(
                self._txn, homeID=self._home._resourceID, uid=uid,
                notificationType=json.dumps(self._notificationType),
                notificationData=notificationtext, md5=self._md5
            )
            self._resourceID, self._created, self._modified = rows[0]
            self._loadPropertyStore()
        else:
            rows = yield self._updateNotificationQuery.on(
                self._txn, homeID=self._home._resourceID, uid=uid,
                notificationType=json.dumps(self._notificationType),
                notificationData=notificationtext, md5=self._md5
            )
            self._modified = rows[0][0]
        self._notificationData = notificationdata

    _notificationDataFromID = Select(
        [_objectSchema.NOTIFICATION_DATA], From=_objectSchema,
        Where=_objectSchema.RESOURCE_ID == Parameter("resourceID"))


    @inlineCallbacks
    def notificationData(self):
        if self._notificationData is None:
            self._notificationData = (yield self._notificationDataFromID.on(self._txn, resourceID=self._resourceID))[0][0]
            try:
                self._notificationData = json.loads(self._notificationData)
            except ValueError:
                pass
            if isinstance(self._notificationData, unicode):
                self._notificationData = self._notificationData.encode("utf-8")
        returnValue(self._notificationData)


    def contentType(self):
        """
        The content type of NotificationObjects is text/xml.
        """
        return MimeType.fromString("text/xml")


    def md5(self):
        return self._md5


    def size(self):
        return self._size


    def notificationType(self):
        return self._notificationType


    def created(self):
        return datetimeMktime(parseSQLTimestamp(self._created))


    def modified(self):
        return datetimeMktime(parseSQLTimestamp(self._modified))



def determineNewest(uid, homeType):
    """
    Construct a query to determine the modification time of the newest object
    in a given home.

    @param uid: the UID of the home to scan.
    @type uid: C{str}

    @param homeType: The type of home to scan; C{ECALENDARTYPE},
        C{ENOTIFICATIONTYPE}, or C{EADDRESSBOOKTYPE}.
    @type homeType: C{int}

    @return: A select query that will return a single row containing a single
        column which is the maximum value.
    @rtype: L{Select}
    """
    if homeType == ENOTIFICATIONTYPE:
        return Select(
            [Max(schema.NOTIFICATION.MODIFIED)],
            From=schema.NOTIFICATION_HOME.join(
                schema.NOTIFICATION,
                on=schema.NOTIFICATION_HOME.RESOURCE_ID ==
                    schema.NOTIFICATION.NOTIFICATION_HOME_RESOURCE_ID),
            Where=schema.NOTIFICATION_HOME.OWNER_UID == uid
        )
    homeTypeName = {ECALENDARTYPE: "CALENDAR",
                    EADDRESSBOOKTYPE: "ADDRESSBOOK"}[homeType]
    home = getattr(schema, homeTypeName + "_HOME")
    bind = getattr(schema, homeTypeName + "_BIND")
    child = getattr(schema, homeTypeName)
    obj = getattr(schema, homeTypeName + "_OBJECT")
    return Select(
        [Max(obj.MODIFIED)],
        From=home.join(bind, on=bind.HOME_RESOURCE_ID == home.RESOURCE_ID)
           .join(child, on=child.RESOURCE_ID == bind.RESOURCE_ID)
           .join(obj, on=obj.PARENT_RESOURCE_ID == child.RESOURCE_ID),
        Where=(bind.BIND_MODE == 0).And(home.OWNER_UID == uid)
    )



@inlineCallbacks
def mergeHomes(sqlTxn, one, other, homeType):
    """
    Merge two homes together.  This determines which of C{one} or C{two} is
    newer - that is, has been modified more recently - and pulls all the data
    from the older into the newer home.  Then, it changes the UID of the old
    home to its UID, normalized and prefixed with "old.", and then re-names the
    new home to its name, normalized.

    Because the UIDs of both homes have changed, B{both one and two will be
    invalid to all other callers from the start of the invocation of this
    function}.

    @param sqlTxn: the transaction to use
    @type sqlTxn: A L{CommonTransaction}

    @param one: A calendar home.
    @type one: L{ICalendarHome}

    @param two: Another, different calendar home.
    @type two: L{ICalendarHome}

    @param homeType: The type of home to scan; L{ECALENDARTYPE} or
        L{EADDRESSBOOKTYPE}.
    @type homeType: C{int}

    @return: a L{Deferred} which fires with with the newer of C{one} or C{two},
        into which the data from the other home has been merged, when the merge
        is complete.
    """
    from txdav.caldav.datastore.util import migrateHome as migrateCalendarHome
    from txdav.carddav.datastore.util import migrateHome as migrateABHome
    migrateHome = {EADDRESSBOOKTYPE: migrateABHome,
                   ECALENDARTYPE: migrateCalendarHome,
                   ENOTIFICATIONTYPE: _dontBotherWithNotifications}[homeType]
    homeTable = {EADDRESSBOOKTYPE: schema.ADDRESSBOOK_HOME,
                 ECALENDARTYPE: schema.CALENDAR_HOME,
                 ENOTIFICATIONTYPE: schema.NOTIFICATION_HOME}[homeType]
    both = []
    both.append([one,
                 (yield determineNewest(one.uid(), homeType).on(sqlTxn))])
    both.append([other,
                 (yield determineNewest(other.uid(), homeType).on(sqlTxn))])
    both.sort(key=lambda x: x[1])

    older = both[0][0]
    newer = both[1][0]
    yield migrateHome(older, newer, merge=True)
    # Rename the old one to 'old.<correct-guid>'
    newNormalized = normalizeUUIDOrNot(newer.uid())
    oldNormalized = normalizeUUIDOrNot(older.uid())
    yield _renameHome(sqlTxn, homeTable, older.uid(), "old." + oldNormalized)
    # Rename the new one to '<correct-guid>'
    if newer.uid() != newNormalized:
        yield _renameHome(sqlTxn, homeTable, newer.uid(), newNormalized)
    yield returnValue(newer)



def _renameHome(txn, table, oldUID, newUID):
    """
    Rename a calendar, addressbook, or notification home.  Note that this
    function is only safe in transactions that have had caching disabled, and
    more specifically should only ever be used during upgrades.  Running this
    in a normal transaction will have unpredictable consequences, especially
    with respect to memcache.

    @param txn: an SQL transaction to use for this update
    @type txn: L{twext.enterprise.ienterprise.IAsyncTransaction}

    @param table: the storage table of the desired home type
    @type table: L{TableSyntax}

    @param oldUID: the old UID, the existing home's UID
    @type oldUID: L{str}

    @param newUID: the new UID, to change the UID to
    @type newUID: L{str}

    @return: a L{Deferred} which fires when the home is renamed.
    """
    return Update({table.OWNER_UID: newUID},
                  Where=table.OWNER_UID == oldUID).on(txn)



def _dontBotherWithNotifications(older, newer, merge):
    """
    Notifications are more transient and can be easily worked around; don't
    bother to migrate all of them when there is a UUID case mismatch.
    """
    pass



@inlineCallbacks
def _normalizeHomeUUIDsIn(t, homeType):
    """
    Normalize the UUIDs in the given L{txdav.common.datastore.CommonStore}.

    This changes the case of the UUIDs in the calendar home.

    @param t: the transaction to normalize all the UUIDs in.
    @type t: L{CommonStoreTransaction}

    @param homeType: The type of home to scan, L{ECALENDARTYPE},
        L{EADDRESSBOOKTYPE}, or L{ENOTIFICATIONTYPE}.
    @type homeType: C{int}

    @return: a L{Deferred} which fires with C{None} when the UUID normalization
        is complete.
    """
    from txdav.caldav.datastore.util import fixOneCalendarHome
    homeTable = {EADDRESSBOOKTYPE: schema.ADDRESSBOOK_HOME,
                 ECALENDARTYPE: schema.CALENDAR_HOME,
                 ENOTIFICATIONTYPE: schema.NOTIFICATION_HOME}[homeType]
    homeTypeName = homeTable.model.name.split("_")[0]

    allUIDs = yield Select([homeTable.OWNER_UID],
                           From=homeTable,
                           OrderBy=homeTable.OWNER_UID).on(t)
    total = len(allUIDs)
    allElapsed = []
    for n, [UID] in enumerate(allUIDs):
        start = time.time()
        if allElapsed:
            estimate = "%0.3d" % ((sum(allElapsed) / len(allElapsed)) *
                                  total - n)
        else:
            estimate = "unknown"
        log.info(
            "Scanning UID {uid} [{homeType}] "
            "({pct!0.2d}%, {estimate} seconds remaining)...",
            uid=UID, pct=(n / float(total)) * 100, estimate=estimate,
            homeType=homeTypeName
        )
        other = None
        this = yield _getHome(t, homeType, UID)
        if homeType == ECALENDARTYPE:
            fixedThisHome = yield fixOneCalendarHome(this)
        else:
            fixedThisHome = 0
        fixedOtherHome = 0
        if this is None:
            log.info(
                "{uid!r} appears to be missing, already processed", uid=UID
            )
        try:
            uuidobj = UUID(UID)
        except ValueError:
            pass
        else:
            newname = str(uuidobj).upper()
            if UID != newname:
                log.info(
                    "Detected case variance: {uid} {newuid}[{homeType}]",
                    uid=UID, newuid=newname, homeType=homeTypeName
                )
                other = yield _getHome(t, homeType, newname)
                if other is None:
                    # No duplicate: just fix the name.
                    yield _renameHome(t, homeTable, UID, newname)
                else:
                    if homeType == ECALENDARTYPE:
                        fixedOtherHome = yield fixOneCalendarHome(other)
                    this = yield mergeHomes(t, this, other, homeType)
                # NOTE: WE MUST NOT TOUCH EITHER HOME OBJECT AFTER THIS POINT.
                # THE UIDS HAVE CHANGED AND ALL OPERATIONS WILL FAIL.

        end = time.time()
        elapsed = end - start
        allElapsed.append(elapsed)
        log.info(
            "Scanned UID {uid}; {elapsed} seconds elapsed,"
            " {fixes} properties fixed ({duplicate} fixes in duplicate).",
            uid=UID, elapsed=elapsed, fixes=fixedThisHome,
            duplicate=fixedOtherHome
        )
    returnValue(None)



def _getHome(txn, homeType, uid):
    """
    Like L{CommonHome.homeWithUID} but also honoring ENOTIFICATIONTYPE which
    isn't I{really} a type of home.

    @param txn: the transaction to retrieve the home from
    @type txn: L{CommonStoreTransaction}

    @param homeType: L{ENOTIFICATIONTYPE}, L{ECALENDARTYPE}, or
        L{EADDRESSBOOKTYPE}.

    @param uid: the UID of the home to retrieve.
    @type uid: L{str}

    @return: a L{Deferred} that fires with the L{CommonHome} or
        L{NotificationHome} when it has been retrieved.
    """
    if homeType == ENOTIFICATIONTYPE:
        return txn.notificationsWithUID(uid, create=False)
    else:
        return txn.homeWithUID(homeType, uid)



@inlineCallbacks
def _normalizeColumnUUIDs(txn, column):
    """
    Upper-case the UUIDs in the given SQL DAL column.

    @param txn: The transaction.
    @type txn: L{CommonStoreTransaction}

    @param column: the column, which may contain UIDs, to normalize.
    @type column: L{ColumnSyntax}

    @return: A L{Deferred} that will fire when the UUID normalization of the
        given column has completed.
    """
    tableModel = column.model.table
    # Get a primary key made of column syntax objects for querying and
    # comparison later.
    pkey = [ColumnSyntax(columnModel)
            for columnModel in tableModel.primaryKey]
    for row in (yield Select([column] + pkey,
                             From=TableSyntax(tableModel)).on(txn)):
        before = row[0]
        pkeyparts = row[1:]
        after = normalizeUUIDOrNot(before)
        if after != before:
            where = _AndNothing
            # Build a where clause out of the primary key and the parts of the
            # primary key that were found.
            for pkeycol, pkeypart in zip(pkeyparts, pkey):
                where = where.And(pkeycol == pkeypart)
            yield Update({column: after}, Where=where).on(txn)



class _AndNothing(object):
    """
    Simple placeholder for iteratively generating a 'Where' clause; the 'And'
    just returns its argument, so it can be used at the start of the loop.
    """
    @staticmethod
    def And(self):
        """
        Return the argument.
        """
        return self



@inlineCallbacks
def _needsNormalizationUpgrade(txn):
    """
    Determine whether a given store requires a UUID normalization data upgrade.

    @param txn: the transaction to use
    @type txn: L{CommonStoreTransaction}

    @return: a L{Deferred} that fires with C{True} or C{False} depending on
        whether we need the normalization upgrade or not.
    """
    for x in [schema.CALENDAR_HOME, schema.ADDRESSBOOK_HOME,
              schema.NOTIFICATION_HOME]:
        slct = Select([x.OWNER_UID], From=x,
                      Where=x.OWNER_UID != Upper(x.OWNER_UID))
        rows = yield slct.on(txn)
        if rows:
            for [uid] in rows:
                if normalizeUUIDOrNot(uid) != uid:
                    returnValue(True)
    returnValue(False)



@inlineCallbacks
def fixUUIDNormalization(store):
    """
    Fix all UUIDs in the given SQL store to be in a canonical form;
    00000000-0000-0000-0000-000000000000 format and upper-case.
    """
    t = store.newTransaction(disableCache=True)

    # First, let's see if there are any calendar, addressbook, or notification
    # homes that have a de-normalized OWNER_UID.  If there are none, then we can
    # early-out and avoid the tedious and potentially expensive inspection of
    # oodles of calendar data.
    if not (yield _needsNormalizationUpgrade(t)):
        log.info("No potentially denormalized UUIDs detected, "
                 "skipping normalization upgrade.")
        yield t.abort()
        returnValue(None)
    try:
        yield _normalizeHomeUUIDsIn(t, ECALENDARTYPE)
        yield _normalizeHomeUUIDsIn(t, EADDRESSBOOKTYPE)
        yield _normalizeHomeUUIDsIn(t, ENOTIFICATIONTYPE)
        yield _normalizeColumnUUIDs(t, schema.RESOURCE_PROPERTY.VIEWER_UID)
        yield _normalizeColumnUUIDs(t, schema.APN_SUBSCRIPTIONS.SUBSCRIBER_GUID)
    except:
        log.failure("Unable to normalize UUIDs")
        yield t.abort()
        # There's a lot of possible problems here which are very hard to test
        # for individually; unexpected data that might cause constraint
        # violations under one of the manipulations done by
        # normalizeHomeUUIDsIn. Since this upgrade does not come along with a
        # schema version bump and may be re- attempted at any time, just raise
        # the exception and log it so that we can try again later, and the
        # service will survive for everyone _not_ affected by this somewhat
        # obscure bug.
    else:
        yield t.commit()
