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
#
##

"""
Tools for generating a population of CalendarServer users based on
certain usage parameters.
"""

from __future__ import division

from tempfile import mkdtemp
from itertools import izip

from twisted.python.filepath import FilePath
from twisted.python.util import FancyEqMixin
from twisted.python.log import msg, err

from stats import mean, median, stddev, mad
from loadtest.trafficlogger import loggedReactor
from loadtest.logger import SummarizingMixin
from loadtest.ical import SnowLeopard, RequestLogger
from loadtest.profiles import Eventer, Inviter, Accepter


class ProfileType(object, FancyEqMixin):
    """
    @ivar profileType: A L{ProfileBase} subclass, or an L{ICalendarUserProfile}
        implementation.

    @ivar params: A C{dict} which will be passed to C{profileType} as keyword
        arguments to create a new profile instance.
    """
    compareAttributes = ("profileType", "params")

    def __init__(self, profileType, params):
        self.profileType = profileType
        self.params = params


    def __call__(self, reactor, simulator, client, number):
        return self.profileType(reactor, simulator, client, number, **self.params)



class ClientType(object, FancyEqMixin):
    """
    @ivar clientType: An L{ICalendarClient} implementation
    @ivar profileTypes: A list of L{ProfileType} instances
    """
    compareAttributes = ("clientType", "profileTypes")

    def __init__(self, clientType, clientParams, profileTypes):
        self.clientType = clientType
        self.clientParams = clientParams
        self.profileTypes = profileTypes


    def new(self, reactor, serverAddress, userRecord, authInfo):
        """
        Create a new instance of this client type.
        """
        return self.clientType(
            reactor, serverAddress, userRecord, authInfo, **self.clientParams)



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


    def clientTypes(self):
        """
        Return a list of two-tuples giving the weights and types of
        clients in the population.
        """
        return self.clients



class Populator(object):
    """
    @ivar userPattern: A C{str} giving a formatting pattern to use to
        construct usernames.  The string will be interpolated with a
        single integer, the incrementing counter of how many users
        have thus far been "used".

    @ivar passwordPattern: Similar to C{userPattern}, but for
        passwords.
    """
    def __init__(self, random):
        self._random = random


    def _cycle(self, elements):
        while True:
            for (weight, value) in elements:
                for i in range(weight):
                    yield value


    def populate(self, parameters):
        """
        Generate individuals such as might be randomly selected from a
        population with the given parameters.
        
        @type parameters: L{PopulationParameters}
        @rtype: generator of L{ClientType} instances
        """
        for (clientType,) in izip(self._cycle(parameters.clientTypes())):
            yield clientType



class CalendarClientSimulator(object):
    def __init__(self, records, populator, parameters, reactor, server):
        self._records = records
        self.populator = populator
        self.reactor = reactor
        self.server = server
        self._pop = self.populator.populate(parameters)
        self._user = 0


    def getUserRecord(self, index):
        return self._records[index]


    def _nextUserNumber(self):
        result = self._user
        self._user += 1
        return result


    def _createUser(self, number):
        from urllib2 import HTTPDigestAuthHandler
        record = self._records[number]
        user = record.uid
        auth = HTTPDigestAuthHandler()
        auth.add_password(
            realm="Test Realm",
            uri=self.server,
            user=user.encode('utf-8'),
            passwd=record.password.encode('utf-8'))
        return user, auth


    def add(self, numClients):
        for n in range(numClients):
            number = self._nextUserNumber()
            user, auth = self._createUser(number)

            clientType = self._pop.next()
            reactor = loggedReactor(self.reactor)
            client = clientType.new(
                reactor, self.server, self.getUserRecord(number), auth)
            d = client.run()
            d.addErrback(self._clientFailure, reactor)

            for profileType in clientType.profileTypes:
                d = profileType(reactor, self, client, number).run()
                d.addErrback(self._profileFailure, profileType, reactor)
        msg(type="status", clientCount=self._user - 1)


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


    def _clientFailure(self, reason, reactor):
        where = self._dumpLogs(reactor, reason)
        err(reason, "Client stopped with error; recent traffic in %r" % (
                where.path,))


    def _profileFailure(self, reason, profileType, reactor):
        where = self._dumpLogs(reactor, reason)
        err(reason, "Profile stopped with error; recent traffic in %r" % (
                where.path,))



class SmoothRampUp(object):
    def __init__(self, reactor, groups, groupSize, interval):
        self.reactor = reactor
        self.groups = groups
        self.groupSize = groupSize
        self.interval = interval


    def run(self, simulator):
        for i in range(self.groups):
            self.reactor.callLater(
                self.interval * i, simulator.add, self.groupSize)



class StatisticsBase(object):
    def observe(self, event):
        if event.get('type') == 'response':
            self.eventReceived(event)


    def report(self):
        pass


    def failures(self):
        return []



class SimpleStatistics(StatisticsBase):
    def __init__(self):
        self._times = []


    def eventReceived(self, event):
        self._times.append(event['duration'])
        if len(self._times) == 200:
            print 'mean:', mean(self._times)
            print 'median:', median(self._times)
            print 'stddev:', stddev(self._times)
            print 'mad:', mad(self._times)
            del self._times[:100]



class ReportStatistics(StatisticsBase, SummarizingMixin):
    """

    @ivar _users: A C{set} containing all user UIDs which have been observed in
        events.  When generating the final report, the size of this set is
        reported as the number of users in the simulation.

    """
    _fields = [
        ('operation', 10, '%10s'),
        ('count', 8, '%8s'),
        ('failed', 8, '%8s'),
        ('>3sec', 8, '%8s'),
        ('mean', 8, '%8.4f'),
        ('median', 8, '%8.4f'),
        ]

    def __init__(self):
        self._perMethodTimes = {}
        self._users = set()


    def countUsers(self):
        return len(self._users)


    def eventReceived(self, event):
        dataset = self._perMethodTimes.setdefault(event['method'], [])
        dataset.append((event['success'], event['duration']))
        self._users.add(event['user'])


    def printMiscellaneous(self, items):
        for k, v in sorted(items.iteritems()):
            print k.title(), ':', v


    def report(self):
        print
        self.printMiscellaneous({'users': self.countUsers()})
        self.printHeader([
                (label, width)
                for (label, width, fmt)
                in self._fields])
        self.printData(
            [fmt for (label, width, fmt) in self._fields],
            sorted(self._perMethodTimes.items()))

    _FAILED_REASON = "Greater than %(cutoff)0.f%% %(method)s failed"
    _THREESEC_REASON = "Greater than %(cutoff)0.f%% %(method)s exceeded 3 second response time"
    _FIVESEC_REASON = "Greater than %(cutoff)0.f%% %(method)s exceeded 5 second response time"

    def failures(self):
        # TODO
        reasons = []

        # Upper limit on ratio of failed requests to total requests
        failCutoff = 0.01

        # Upper limit on ratio of >3sec requests to total requests
        threeSecCutoff = 0.05

        # Upper limit on ratio of >5sec requests to total requests
        fiveSecCutoff = 0.01

        for (method, times) in self._perMethodTimes.iteritems():
            failures = 0
            threeSec = 0
            fiveSec = 0

            for success, duration in times:
                if not success:
                    failures += 1
                if duration > 5:
                    fiveSec += 1
                elif duration > 3:
                    threeSec += 1

            checks = [
                (failures, failCutoff, self._FAILED_REASON),
                (threeSec, threeSecCutoff, self._THREESEC_REASON),
                (fiveSec, fiveSecCutoff, self._FIVESEC_REASON),
                ]

            for count, cutoff, reason in checks:
                if count / len(times) > cutoff:
                    reasons.append(reason % dict(
                            method=method, cutoff=cutoff * 100))

        return reasons



def main():
    import random

    from twisted.internet import reactor
    from twisted.python.log import addObserver

    from twisted.python.failure import startDebugMode
    startDebugMode()

    report = ReportStatistics()
    addObserver(SimpleStatistics().observe)
    addObserver(report.observe)
    addObserver(RequestLogger().observe)

    r = random.Random()
    r.seed(100)
    populator = Populator(r)
    parameters = PopulationParameters()
    parameters.addClient(
        1, ClientType(SnowLeopard, [Eventer, Inviter, Accepter]))
    simulator = CalendarClientSimulator(
        populator, parameters, reactor, '127.0.0.1', 8008)

    arrivalPolicy = SmoothRampUp(groups=10, groupSize=1, interval=3)
    arrivalPolicy.run(reactor, simulator)

    reactor.run()
    report.report()

if __name__ == '__main__':
    main()
