
"""
This is the logic associated with queueing.
"""

from socket import getfqdn
from functools import wraps
from os import getpid
from datetime import datetime

from twisted.internet.task import LoopingCall
from twisted.application.service import Service
from twisted.internet.protocol import Factory
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.protocols.amp import AMP, Command, Integer, Argument
from twisted.python.reflect import qual

from twext.enterprise.dal.syntax import TableSyntax, SchemaSyntax
from twext.enterprise.dal.model import ProcedureCall
from twext.enterprise.dal.syntax import NamedValue
from twext.enterprise.dal.record import fromTable
from twisted.internet.defer import Deferred
from twext.enterprise.dal.model import Table, Schema, SQLType, Constraint


def makeMasterSchema(inSchema):
    """
    Create a self-contained schema for L{MasterInfo} to use.

    @return: a schema with just the one table.
    """
    # Initializing this duplicate schema avoids a circular dependency, but this
    # should really be accomplished with independent schema objects that the
    # transaction is made aware of somehow.
    masterTable = Table(inSchema, 'MASTER_INFO')
    masterTable.addColumn("HOSTNAME", SQLType("varchar", 255))
    masterTable.addColumn("PID", SQLType("integer", None))
    masterTable.addColumn("PORT", SQLType("integer", None))
    masterTable.addColumn("TIME", SQLType("timestamp", None)).setDefaultValue(
        # Note: in the real data structure, this is actually a not-cleaned-up
        # sqlparse internal data structure, but it *should* look closer to this.
        ProcedureCall("timezone", ["UTC", NamedValue('CURRENT_TIMESTAMP')])
    )
    for column in masterTable.columns:
        masterTable.tableConstraint(Constraint.NOT_NULL, [column.name])
    return inSchema

masterInfoSchema = SchemaSyntax(makeMasterSchema(Schema(__file__)))



class TableSyntaxByName(Argument):
    """
    Serialize and deserialize L{TableSyntax} objects for an AMP protocol with
    an attached schema.
    """

    def fromStringProto(self, inString, proto):
        """
        Convert the name of the table into a table, given a C{proto} with an
        attached C{schema}.

        @param inString: the name of a table, as utf-8 encoded bytes
        @type inString: L{bytes}

        @param proto: an L{SchemaAMP}
        """
        return TableSyntax(proto.schema.tableNamed(inString.decode("UTF-8")))


    def toString(self, inObject):
        """
        Convert a L{TableSyntax} object into just its name for wire transport.

        @param inObject: a table.
        @type inObject: L{TableSyntax}

        @return: the name of that table
        @rtype: L{bytes}
        """
        return inObject.model.name.encode("UTF-8")



class MasterInfo(fromTable(masterInfoSchema.MASTER_INFO)):
    """
    A L{MasterInfo} is information about a currently-active master process.
    """

    def endpoint(self):
        """
        Create an L{IStreamServerEndpoint} that will talk to the master process
        that is described by this L{MasterInfo}.

        @return: an endpoint that will connect to this host.
        @rtype: L{IStreamServerEndpoint}
        """
        return TCP4ClientEndpoint(self.hostname, self.port)


    def updateCurrent(self):
        return self.update(timestamp=datetime.datetime.now())



def abstract(thunk):
    """
    The decorated function is abstract.

    @note: only methods are currently supported.
    """
    @classmethod
    @wraps(thunk)
    def inner(cls, *a, **k):
        raise NotImplementedError(qual(cls) + " does not implement " +
                                  thunk.func_name)
    return inner



class WorkItem(object):
    """
    An item of work.

    @ivar workID: the unique identifier (primary key) for items of this type.
        There must be a corresponding column in the database.
    @type workID: L{int}
    """

    @abstract
    def doWork(self):
        """
        Subclasses must implement this to actually perform the queued work.

        This method will be invoked in a worker process.

        This method does I{not} need to delete the row referencing it; that
        will be taken care of by the job queueing machinery.
        """


    @classmethod
    def forTable(cls, table):
        """
        Look up a work-item class given a particular L{TableSyntax}.  Factoring
        this correctly may place it into L{twext.enterprise.record.Record}
        instead; it is probably generally useful to be able to look up a mapped
        class from a table.

        @param table: the table to look up
        @type table: L{twext.enterprise.dal.model.Table}

        @return: the relevant subclass
        @rtype: L{type}
        """



class PerformWork(Command):
    """
    Notify another process that it must do some work that has been persisted to
    the database, by informing it of the table and the ID where said work has
    been persisted.
    """

    arguments = [
        ("table", TableSyntaxByName()),
        ("workID", Integer()),
    ]
    response = []



class ConnectionFromPeerMaster(AMP):
    """
    A connection to a peer master.  Symmetric; since the 'client' and the
    'server' both serve the same role, the logic is the same in every master.

    This only exists in the master.
    """

    def __init__(self, localWorkerPool, boxReceiver=None, locator=None):
        """
        Initialize this L{ConnectionFromPeerMaster} with a reference to a pool
        of local workers.

        @param localWorkerPool: the pool of local worker procesess that can
            process queue work.
        """
        self.localWorkerPool = localWorkerPool
        super(ConnectionFromPeerMaster, self).__init__(boxReceiver, locator)


    def performWork(self, table, workID):
        """
        A L{local worker connection <ConnectionFromWorker>} is asking this
        specific peer master process to perform some work, having already
        determined that it's appropriate.

        @param table: The table where work is waiting.
        @type table: L{TableSyntax}

        @param workID: The primary key identifier of the given work.
        @type workID: L{int}

        @return: a L{Deferred} firing with an empty dictionary when the work is
            complete.
        @rtype: L{Deferred} firing L{dict}
        """
        return self.callRemote(PerformWork,
                               table=table.model.name, workID=workID)


    @PerformWork.responder
    def dispatchToWorker(self, table, workID):
        """
        A remote peer master has asked this master to do some work; dispatch it
        to a local worker.
        """
        return self.localWorkerPool.performWork(table, workID)



class WorkerConnectionPool(object):
    """
    A pool of L{ConnectionFromWorker}s.

    L{WorkerConnectionPool} also implements the same implicit protocol as a
    L{ConnectionFromPeerMaster}, but one that dispenses work to the local
    worker processes rather than to a remote connection pool.
    """

    def __init__(self):
        self.workers = []


    def addWorker(self, worker):
        self.workers.append(worker)


    def removeWorker(self, worker):
        self.workers.remove(worker)


    def _selectLowestLoadLocalConnection(self):
        """
        Select the local connection with the lowest current load, or C{None} if
        all workers are too busy.

        @return: a worker connection with the lowest current load.
        @rtype: L{ConnectionFromWorker} or L{NoneType}
        """
        return sorted(self.workers[:], key=lambda w: w.currentLoad())[0]


    def performWork(self, table, workID):
        """
        Select a local worker that is idle enough to perform the given work,
        then ask them to perform it.

        @param table: The table where work is waiting.
        @type table: L{TableSyntax}

        @param workID: The primary key identifier of the given work.
        @type workID: L{int}

        @return: a L{Deferred} firing with an empty dictionary when the work is
            complete.
        @rtype: L{Deferred} firing L{dict}
        """
        return self._selectLowestLoadLocalConnection().performWork(table, workID)



class ConnectionFromWorker(AMP):
    """
    An individual connection from a worker, as seem from the master's
    perspective.  L{ConnectionFromWorker}s go into a L{WorkerConnectionPool}.

    @ivar workerPool: The connection pool that this individual connection is
        participating in.
    @type workerPool: L{WorkerConnectionPool}
    """

    def __init__(self, workerPool):
        self.workerPool = workerPool
        super(ConnectionFromWorker, self).__init__()


    @property
    def currentLoad(self):
        """
        What is the current load of this worker?
        """
        # TODO: this needs to be hooked up to something.
        return 0


    def startReceivingBoxes(self, sender):
        """
        Start receiving AMP boxes from the peer.  Initialize all necessary
        state.
        """
        result = super(ConnectionFromWorker, self).startReceivingBoxes(sender)
        self.workerPool.addWorker(self)
        return result


    def stopReceivingBoxes(self, reason):
        """
        AMP boxes will no longer be received.
        """
        result = super(ConnectionFromWorker, self).stopReceivingBoxes(reason)
        self.workerPool.removeWorker(self)
        return result


    def performWork(self, table, workID):
        """
        Dispatch work to this worker.

        @see: The responder for this should always be
            L{ConnectionFromMaster.actuallyReallyExecuteWorkHere}.
        """
        return self.callRemote(PerformWork,
                               table=table.model.name, workID=workID)



class ConnectionFromMaster(AMP):
    """
    A L{ConnectionFromMaster} is the connection to a master process, in a
    worker process.  It processes requests from its own master to do work.  It
    is the opposite end of the connection from L{ConnectionFromWorker}.
    """

    def __init__(self, schemaSyntax):
        """
        @param schemaSyntax: The schema that this connection operates on, which
            contains (at least) all the tables that we may receive requests for
            work in.
        """
        super(ConnectionFromMaster, self).__init__()
        self.schemaSyntax = schemaSyntax


    @PerformWork.responder
    @inlineCallbacks
    def actuallyReallyExecuteWorkHere(self, table, workID):
        """
        This is where it's time to actually do the work.  The master process
        has instructed this worker to do it; so, look up the data in the row,
        and do it.
        """
        workItemClass = WorkItem.forTable(table)
        # TODO: mumble locking something mumble
        # TODO: get a transaction in here.
        workItem = yield workItemClass.load(workID)
        # TODO: verify that workID is the primary key someplace.
        yield workItem.doWork()
        # TODO: what if we fail?  error-handling should be recorded someplace,
        # the row should probably be removed, re-tries should be triggerable.
        yield workItem.delete()
        returnValue({})



class TransactionFailed(Exception):
    """
    A transaction failed.
    """



class PeerConnectionPool(Service, object):
    """
    Each master has a L{PeerConnectionPool} connecting it to all the other
    masters currently active on the same database.

    @ivar hostName: The hostname of this master process, as reported by the
        local host's configuration.  Possibly this should be obtained via
        C{config.ServerHostName} instead of C{socket.getfqdn()}; although hosts
        within a cluster may be configured with the same C{ServerHostName};
        TODO need to confirm.

    @ivar thisProcess: a L{MasterInfo} representing this process, which is
        initialized when this L{PeerConnectionPool} service is started via
        C{startService}.  May be C{None} if this service is not fully started
        up or if it is shutting down.
    """

    getfqdn = staticmethod(getfqdn)
    getpid = staticmethod(getpid)

    def __init__(self, connectionFactory, ampPort):
        """
        Initialize a L{PeerConnectionPool}.

        @param ampPort: The AMP port to listen on for inter-host communication.
            This must be an integer because we need to communicate it to the
            other peers in the cluster.
        @type ampPort: L{int}

        @param connectionFactory: a 0- or 1-argument callable that produces an
            L{IAsyncTransaction}
        """
        self.connectionFactory = connectionFactory
        self.hostName = self.getfqdn()
        self.pid = self.getpid()
        self.ampPort = ampPort
        self.thisProcess = None


    def choosePeer(self):
        """
        Choose a peer to distribute work to based on the current known slot
        occupancy of the other masters.

        @return: a L{Deferred <twisted.internet.defer.Deferred>} which fires
            with the chosen L{ConnectionFromPeerMaster} as soon as one is
            available.  Normally this will be synchronous, but we need to
            account for the possibility that we may need to connect to other
            hosts.
        @rtype: L{Deferred <twisted.internet.defer.Deferred>} firing
            L{ConnectionFromPeerMaster}
        """


    def enqueueWork(self, workItem):
        """
        There is some work to do.  Do it, someplace else, ideally in parallel.
        Later, let the caller know that the work has been completed by firing a
        L{Deferred}.

        @note: The L{Deferred} returned by C{enqueueWork} should be used with
            caution.  If an application decides to do any database-persistent
            work as a result of this L{Deferred} firing, that work I{may be
            lost} as a result of a service being normally shut down between the
            time that the work is scheduled and the time that it is executed.
            So, the only things that should be added as callbacks to this
            L{Deferred} are those which are ephemeral, in memory, and reflect
            only presentation state associated with the user's perception of
            the completion of work, not logical chains of work which need to be
            completed in sequence; those should all be completed within the
            transaction of the L{WorkItem.doWork} that gets executed.

        @param workItem: An item of work to be done in another process.
        @type workItem: A L{WorkItem}

        @return: a L{Deferred} that fires when the work has been completed.
        @rtype: L{Deferred} firing L{None}
        """
        d = Deferred()
        @workItem.__txn__.postCommit
        @inlineCallbacks
        def whenDone():
            peer = yield self.choosePeer()
            peer.performWork(workItem.__tbl__, workItem.workID)
        @workItem.__txn__.postAbort
        def whenFailed():
            d.errback(TransactionFailed)
        return d


    def startService(self):
        """
        Register ourselves with the database and establish all outgoing
        connections to other servers in the cluster.
        """
        self._doStart()


    @inlineCallbacks
    def _doStart(self):
        """
        First, we tell the database that we're an active master so that other
        masters know about us.  This should also give us a
        unique-to-the-whole-database identifier for this process instance.
        """
        txn = self.connectionFactory()
        thisProcess = yield MasterInfo.create(
            txn, hostname=self.hostName, pid=self.pid, port=self.ampPort,
            time=datetime.datetime.now()
        )

        """
        It might be a good idea to update this periodicially in order to give an
        indication that the process isn't dead.  On the other hand maybe there's no
        concrete feature which actually requires this information.
        """
        lc = LoopingCall(thisProcess.updateCurrent, self.connectionFactory)
        lc.start(30.0)

        """
        Now let's find all the other masters.
        """
        masters = self.activeMasters()

        """
        Each other 'master' here is another L{MasterInfo} which tells us where
        to connect.
        """
        f = Factory()
        f.protocol = ConnectionFromPeerMaster
        for master in masters:
            self._startConnectingTo(master)


    def _startConnectingTo(self, master):
        """
        Start an outgoing connection to another master process.

        @param master: a description of the master to connect to.
        @type master: L{MasterInfo}
        """
        f = Factory()
        master.endpoint().connect(f)


