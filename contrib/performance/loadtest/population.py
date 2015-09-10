# -*- test-case-name: contrib.performance.loadtest.test_population -*-
##
# Copyright (c) 2010-2015 Apple Inc. All rights reserved.
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
##
from __future__ import print_function
from __future__ import division

"""
Tools for generating a population of CalendarServer users based on
certain usage parameters.
"""

from tempfile import mkdtemp
from itertools import izip

from urllib2 import HTTPBasicAuthHandler
from urllib2 import HTTPDigestAuthHandler
from urllib2 import HTTPPasswordMgrWithDefaultRealm

from twisted.internet.defer import DeferredList
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.python.util import FancyEqMixin
from twisted.python.log import msg, err

from twistedcaldav.timezones import TimezoneCache

from contrib.performance.loadtest.trafficlogger import loggedReactor

from contrib.performance.loadtest.profiles import Eventer, Inviter, Accepter


# class ProfileType(object, FancyEqMixin):
#     """
#     @ivar profileType: A L{ProfileBase} subclass
#     @type profileType: C{type}

#     @ivar params: A C{dict} which will be passed to C{profileType} as keyword
#         arguments to create a new profile instance.
#     """
#     compareAttributes = ("profileType", "params")

#     def __init__(self, profileType, params):
#         self.profileType = profileType
#         self.params = params


#     def __call__(self, reactor, simulator, client, number):
#         base = self.profileType(**self.params)
#         base.setUp(reactor, simulator, client, number)
#         return base


#     def __repr__(self):
#         return "ProfileType(%s, params=%s)" % (self.profileType.__name__, self.params)



class ClientFactory(object, FancyEqMixin):
    """
    @ivar clientType: An L{BaseAppleClient} subclass
    @ivar params: A C{dict} which will be passed to C{clientType} as keyword
        arguements to create a new client
    @ivar profileTypes: A list of L{ProfileType} instances
    """
    compareAttributes = ("clientType", "profileTypes")

    def __init__(self, clientType, clientParams, profiles):
        self.clientType = clientType
        self.clientParams = clientParams
        self.profiles = profiles


    def new(self, reactor, serverAddress, serializationPath, userRecord, authInfo):
        """
        Create a new instance of this client type.
        """
        return self.clientType(
            reactor, serverAddress, serializationPath,
            userRecord, authInfo, **self.clientParams
        )



class PopulationParameters(object, FancyEqMixin):
    """
    Descriptive statistics about a population of Calendar Server users.
    """
    compareAttributes = ("clients",)

    def __init__(self):
        self.clients = []


    def addClient(self, weight, clientType):
        """
        Add another type of client to these parameters.

        @param weight: A C{int} giving the weight of this client type.
            The higher the weight, the more frequently a client of
            this type will show up in the population described by
            these parameters.

        @param clientType: A L{ClientType} instance describing the
            type of client to add.
        """
        self.clients.append((weight, clientType))


    def clientGenerator(self):
        while True:
            for (weight, clientFactory) in self.clients:
                for _ignore_i in xrange(weight):
                    yield clientFactory


    # def clientTypes(self):
    #     """
    #     Return a list of two-tuples giving the weights and types of
    #     clients in the population.
    #     """
    #     return self.clients





# class Populator(object):
#     """
#     """
#     def __init__(self):
#         self._random = random


#     def _cycle(self, elements):
#         while True:
#             for (weight, value) in elements:
#                 for _ignore_i in range(weight):
#                     yield value


#     def populate(self, parameters):
#         """
#         Generate individuals such as might be randomly selected from a
#         population with the given parameters.

#         @type parameters: L{PopulationParameters}
#         @rtype: generator of L{ClientType} instances
#         """
#         for (clientType,) in izip(self._cycle(parameters.clientTypes())):
#             yield clientType



class CalendarClientSimulator(object):
    def __init__(self, records, parameters, reactor, server,
                 serializationPath, workerIndex=0, workerCount=1):
        import random
        # i = random.randint(0, 1000)
        # with open('log%d.txt'.format(i), 'a') as f:
        #     f.write('wtf')
        val = random.random()
        msg(type="log", text="In create client sim", val=str(val))
        # from pprint import pprint
        # pprint(records)
        self._records = records
        self.reactor = reactor
        self.server = server
        self.serializationPath = serializationPath
        self._populator = parameters.clientGenerator()
        self._user = 0
        self._stopped = False
        self.workerIndex = workerIndex
        self.workerCount = workerCount
        self.clients = []

        # TimezoneCache.create()


    def getUserRecord(self, index):
        return self._records[index]


    def _nextUserNumber(self):
        result = self._user
        self._user += 1
        return result


    def _createUser(self, number):
        record = self._records[number]
        user = record.uid
        authBasic = HTTPBasicAuthHandler(password_mgr=HTTPPasswordMgrWithDefaultRealm())
        authBasic.add_password(
            realm=None,
            uri=self.server,
            user=user.encode('utf-8'),
            passwd=record.password.encode('utf-8'))
        authDigest = HTTPDigestAuthHandler(passwd=HTTPPasswordMgrWithDefaultRealm())
        authDigest.add_password(
            realm=None,
            uri=self.server,
            user=user.encode('utf-8'),
            passwd=record.password.encode('utf-8'))
        return user, {"basic": authBasic, "digest": authDigest, }


    def stop(self):
        """
        Indicate that the simulation is over.  CalendarClientSimulator doesn't
        actively react to this, but it does cause all future failures to be
        disregarded (as some are expected, as the simulation will always stop
        while some requests are in flight).
        """

        # Give all the clients a chance to stop (including unsubscribe from push)
        deferreds = []
        for client in self.clients:
            deferreds.append(client.stop())
        self._stopped = True
        return DeferredList(deferreds)


    def add(self, numClients, clientsPerUser):
        # for _ignore_n in range(numClients):
        #     number = self._nextUserNumber()

        #     for _ignore_peruser in range(clientsPerUser):
        #         clientType = self._populator.next()
        #         if (number % self.workerCount) != self.workerIndex:
        #             # If we're in a distributed work scenario and we are worker N,
        #             # we have to skip all but every Nth request (since every node
        #             # runs the same arrival policy).
        #             continue

        #         _ignore_user, auth = self._createUser(number)

        #         reactor = loggedReactor(self.reactor)
        #         client = clientType.new(
        #             reactor,
        #             self.server,
        #             self.serializationPath,
        #             self.getUserRecord(number),
        #             auth,
        #         )
        #         self.clients.append(client)
        #         d = client.run()
        #         d.addErrback(self._clientFailure, reactor)

        #         for profileType in clientType.profileTypes:
        #             print(profileType)
        #             profile = profileType(reactor, self, client, number)
        #             if profile.enabled:
        #                 d = profile.initialize()
        #                 def _run(result):
        #                     d2 = profile.run()
        #                     d2.addErrback(self._profileFailure, profileType, reactor)
        #                     return d2
        #                 d.addCallback(_run)

        for i in range(numClients):
            number = self._nextUserNumber()
            # What user are we representing?
            for j in range(clientsPerUser):
                if (number % self.workerCount) != self.workerIndex:
                    # If we're in a distributed work scenario and we are worker N,
                    # we have to skip all but every Nth request (since every node
                    # runs the same arrival policy).
                    continue
                clientFactory = self._populator.next()

                _ignore_user, auth = self._createUser(number)
                reactor = loggedReactor(self.reactor)

                client = clientFactory.new(
                    self.reactor,
                    self.server,
                    self.serializationPath,
                    self.getUserRecord(number),
                    auth
                )
                self.clients.append(client)
                client.run().addErrback(self._clientFailure, reactor)
                for profileTemplate in clientFactory.profiles:
                    profile = profileTemplate.duplicate()
                    profile.setUp(self.reactor, self, client, number)
                    profile.run().addErrback(self._profileFailure, reactor)


    def _dumpLogs(self, loggingReactor, reason):
        path = FilePath(mkdtemp())
        logstate = loggingReactor.getLogFiles()
        i = 0
        for i, log in enumerate(logstate.finished):
            path.child('%03d.log' % (i,)).setContent(log.getvalue())
        for i, log in enumerate(logstate.active, i):
            path.child('%03d.log' % (i,)).setContent(log.getvalue())
        path.child('reason.log').setContent(reason.getTraceback())
        return path


    def _profileFailure(self, reason, reactor):
        if not self._stopped:
            where = self._dumpLogs(reactor, reason)
            err(reason, "Profile stopped with error; recent traffic in %r" % (
                where.path,))


    def _clientFailure(self, reason, reactor):
        if not self._stopped:
            where = self._dumpLogs(reactor, reason)
            err(reason, "Client stopped with error; recent traffic in %r" % (
                where.path,))
            if not isinstance(reason, Failure):
                reason = Failure(reason)
            msg(type="client-failure", reason="%s: %s" % (reason.type, reason.value,))


    def _simFailure(self, reason, reactor):
        if not self._stopped:
            msg(type="sim-failure", reason=reason)



class SmoothRampUp(object):
    def __init__(self, groups, groupSize, interval, clientsPerUser):
        self.groups = groups
        self.groupSize = groupSize
        self.interval = interval
        self.clientsPerUser = clientsPerUser


    def run(self, reactor, simulator):
        for i in range(self.groups):
            reactor.callLater(
                self.interval * i, simulator.add, self.groupSize, self.clientsPerUser)



def main():
    import random

    from twisted.internet import reactor
    from twisted.python.log import addObserver

    from twisted.python.failure import startDebugMode
    startDebugMode()

    from contrib.performance.loadtest.clients import OS_X_10_6
    from contrib.performance.loadtest.logger import ReportStatistics, SimpleStatistics, RequestLogger

    report = ReportStatistics()
    addObserver(SimpleStatistics().observe)
    addObserver(report.observe)
    addObserver(RequestLogger().observe)

    r = random.Random()
    r.seed(100)
    populator = Populator(r)
    parameters = PopulationParameters()
    parameters.addClient(
        1, ClientType(OS_X_10_6, [Eventer, Inviter, Accepter]))
    simulator = CalendarClientSimulator(
        populator, parameters, reactor, '127.0.0.1', 8008)

    arrivalPolicy = SmoothRampUp(groups=10, groupSize=1, interval=3)
    arrivalPolicy.run(reactor, simulator)

    reactor.run()
    report.report()

if __name__ == '__main__':
    main()
