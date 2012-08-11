
"""
This is the logic associated with queueing.
"""

from twisted.internet.task import LoopingCall
from twisted.application.service import Service
from twisted.internet.protocol import Factory
from twisted.internet.defer import inlineCallbacks#, Deferred
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.protocols.amp import AMP, Command, Integer, String
from twisted.python.reflect import qual

from socket import getfqdn
from functools import wraps

from datetime import datetime
from os import getpid



class MasterInfo(object):
    """
    A L{MasterInfo} is information about a currently-active master process.
    """

    def endpoint(self):
        return TCP4ClientEndpoint(self.host, self.ampPort)


    def representLocalProcess(self):
        """
        Set the flag that says that this L{MasterInfo} is representative of the
        current, local process.
        """



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
        ("table", String()),
        ("workID", Integer()),
    ]
    response = []



class PeerConnection(AMP):
    """
    A connection to a peer master.  Symmetric; since the 'client' and the
    'server' both serve the same role, the logic is the same in every master.
    """
    def performWork(self, table, workID):
        return self.callRemote(PerformWork,
                               table=table.model.name, workID=workID)



class LocalConnection(object):
    """
    Implements the same implicit protocol as a L{PeerConnection}, but one that
    dispenses work to the local worker processes rather than to a remote
    connection pool.
    """

    def performWork(self, table, workID):
        """
        Look up a local worker and delegate .performWork to it.
        """



class ConnectionFromMaster(AMP):
    """
    This is in the child process.  It processes requests from its own master to
    do work.
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
    def perform(self, table, workID):
        """
        This is where it's time to actually do the work.  The master process
        has instructed this worker to do it; so, look up the data in the row,
        and do it.
        """
        tableSyntax = getattr(self.schemaSyntax, table)
        workItemClass = WorkItem.forTable(tableSyntax)
        # TODO: mumble locking something mumble
        workItem = yield workItemClass.load(workID)
        # TODO: verify that workID is the primary key someplace.
        yield workItem.doWork()



class PeerConnectionPool(Service):
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

    def __init__(self, connectionFactory, ampPort):
        """
        @param ampPort: The AMP port to listen on for inter-host communication.
            This must be an integer because we need to communicate it to the
            other peers in the cluster.
        @type ampPort: L{int}

        @param connectionFactory: a 0- or 1-argument callable that produces an
            L{IAsyncTransaction}
        """
        self.connectionFactory = connectionFactory
        self.hostName = getfqdn()
        self.ampPort = ampPort
        self.thisProcess = None


    def choosePeer(self):
        """
        Choose a peer to distribute work to based on the current known slot
        occupancy of the other masters.

        @return: a Deferred which fires with the chosen L{PeerConnection} as
            soon as one is available.  Normally this will be synchronous, but
            we need to account for the possibility that we may need to connect
            to other hosts.
        @rtype: L{twisted.internet.defer.Deferred} firing L{PeerConnection}
        """


    def enqueueWork(self, workItem):
        """
        There is some work to do.  Do it, someplace.

        @type workItem: A L{WorkItem}
        """
        @workItem.transaction.postCommit
        @inlineCallbacks
        def whenDone():
            peer = yield self.choosePeer()
            peer.performWork(workItem.__tbl__, workItem.workID)


    def startService(self):
        """
        Register ourselves with the database and establish all outgoing
        connections to other servers in the cluster.
        """

        """
        First, we tell the database that we're an active master so that other
        masters know about us.  This should also give us a
        unique-to-the-whole-database identifier for this process instance.
        """
        thisProcess = MasterInfo.create(
            host=self.hostName, pid=getpid(), port=self.ampPort,
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
        f.protocol = PeerConnection
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

"""
Notes:

The master process is going to talk to a slave process by signaling via the
logging (e.g.  "control") socket.  But it also needs to have a reference over
to the meta-fd-dispatcher socket so it knows which one to talk to.

Right now all the slave->master connections are established by the slaves
coming in, so we need to work with whatever connections are availble and/or
buffer until the first one comes in.
"""

