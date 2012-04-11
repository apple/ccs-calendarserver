# -*- test-case-name: contrib.performance.loadtest.test_population -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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

from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.python.util import FancyEqMixin
from twisted.python.log import msg, err

from twistedcaldav.timezones import TimezoneCache

from contrib.performance.stats import mean, median, stddev, mad
from contrib.performance.loadtest.trafficlogger import loggedReactor
from contrib.performance.loadtest.logger import SummarizingMixin
from contrib.performance.loadtest.ical import OS_X_10_6, RequestLogger
from contrib.performance.loadtest.profiles import Eventer, Inviter, Accepter


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
                for _ignore_i in range(weight):
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
    def __init__(self, records, populator, parameters, reactor, server,
                 workerIndex=0, workerCount=1):
        self._records = records
        self.populator = populator
        self.reactor = reactor
        self.server = server
        self._pop = self.populator.populate(parameters)
        self._user = 0
        self._stopped = False
        self.workerIndex = workerIndex
        self.workerCount = workerCount

        TimezoneCache.create()

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


    def stop(self):
        """
        Indicate that the simulation is over.  CalendarClientSimulator doesn't
        actively react to this, but it does cause all future failures to be
        disregarded (as some are expected, as the simulation will always stop
        while some requests are in flight).
        """
        self._stopped = True


    def add(self, numClients, clientsPerUser):
        for _ignore_n in range(numClients):
            number = self._nextUserNumber()
            
            for _ignore_peruser in range(clientsPerUser):
                clientType = self._pop.next()
                if (number % self.workerCount) != self.workerIndex:
                    # If we're in a distributed work scenario and we are worker N,
                    # we have to skip all but every Nth request (since every node
                    # runs the same arrival policy).
                    continue
    
                _ignore_user, auth = self._createUser(number)
    
                reactor = loggedReactor(self.reactor)
                client = clientType.new(
                    reactor, self.server, self.getUserRecord(number), auth)
                d = client.run()
                d.addErrback(self._clientFailure, reactor)
    
                for profileType in clientType.profileTypes:
                    profile = profileType(reactor, self, client, number)
                    if profile.enabled:
                        d = profile.run()
                        d.addErrback(self._profileFailure, profileType, reactor)

        # XXX this status message is prone to be slightly inaccurate, but isn't
        # really used by much anyway.
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
        if not self._stopped:
            where = self._dumpLogs(reactor, reason)
            err(reason, "Client stopped with error; recent traffic in %r" % (
                    where.path,))
            if not isinstance(reason, Failure):
                reason = Failure(reason)
            msg(type="client-failure", reason="%s: %s" % (reason.type, reason.value,))


    def _profileFailure(self, reason, profileType, reactor):
        if not self._stopped:
            where = self._dumpLogs(reactor, reason)
            err(reason, "Profile stopped with error; recent traffic in %r" % (
                    where.path,))



class SmoothRampUp(object):
    def __init__(self, reactor, groups, groupSize, interval, clientsPerUser):
        self.reactor = reactor
        self.groups = groups
        self.groupSize = groupSize
        self.interval = interval
        self.clientsPerUser = clientsPerUser


    def run(self, simulator):
        for i in range(self.groups):
            self.reactor.callLater(
                self.interval * i, simulator.add, self.groupSize, self.clientsPerUser)



class StatisticsBase(object):
    def observe(self, event):
        if event.get('type') == 'response':
            self.eventReceived(event)
        elif event.get('type') == 'client-failure':
            self.clientFailure(event)


    def report(self, output):
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


    def clientFailure(self, event):
        pass


class ReportStatistics(StatisticsBase, SummarizingMixin):
    """

    @ivar _users: A C{set} containing all user UIDs which have been observed in
        events.  When generating the final report, the size of this set is
        reported as the number of users in the simulation.

    """

    # the response time thresholds to display together with failing % count threshold
    _thresholds = (
        (0.5, 100.0),  
        (  1, 100.0),  
        (  3,   5.0),  
        (  5,   1.0),
        ( 10,   0.5),
    )
    _fail_cut_off = 1.0     # % of total count at which failed requests will cause a failure 

    _fields = [
        ('request', -20, '%-20s'),
        ('count', 8, '%8s'),
        ('failed', 8, '%8s'),
    ]
    
    for threshold, _ignore_fail_at in _thresholds:
        _fields.append(('>%g sec' % (threshold,), 10, '%10s'))

    _fields.extend([
        ('mean', 8, '%8.4f'),
        ('median', 8, '%8.4f'),
        ('stddev', 8, '%8.4f'),
        ('STATUS', 8, '%8s'),
    ])

    def __init__(self):
        self._perMethodTimes = {}
        self._users = set()
        self._clients = set()
        self._failed_clients = []


    def countUsers(self):
        return len(self._users)


    def countClients(self):
        return len(self._clients)


    def countClientFailures(self):
        return len(self._failed_clients)


    def eventReceived(self, event):
        dataset = self._perMethodTimes.setdefault(event['method'], [])
        dataset.append((event['success'], event['duration']))
        self._users.add(event['user'])
        self._clients.add(event['client_id'])


    def clientFailure(self, event):
        self._failed_clients.append(event['reason'])


    def printMiscellaneous(self, output, items):
        for k, v in sorted(items.iteritems()):
            output.write("%s:%s\n" % (k.title(), v,))


    def report(self, output):
        output.write("\n")
        output.write("** REPORT **\n")
        output.write("\n")
        self.printMiscellaneous(output, {
            'users': self.countUsers(),
            'clients': self.countClients(),
        })
        if self.countClientFailures() > 0:
            self.printMiscellaneous(output, {
                'Failed clients': self.countClientFailures(),
            })
            for ctr, reason in enumerate(self._failed_clients, 1):
                self.printMiscellaneous(output, {
                    'Failure #%d' % (ctr,): reason,
                })
            
        output.write("\n")
        self.printHeader(output, [
                (label, width)
                for (label, width, _ignore_fmt)
                in self._fields])
        self.printData(output,
            [fmt for (label, width, fmt) in self._fields],
            sorted(self._perMethodTimes.items()))

    _FAILED_REASON = "Greater than %(cutoff)g%% %(method)s failed"

    _REASON_1 = "Greater than %(cutoff)g%% %(method)s exceeded "
    _REASON_2 = "%g second response time"

    def failures(self):
        # TODO
        reasons = []

        for (method, times) in self._perMethodTimes.iteritems():
            failures = 0
            overDurations = [0] * len(self._thresholds)

            for success, duration in times:
                if not success:
                    failures += 1
                for ctr, item in enumerate(self._thresholds):
                    threshold, _ignore_fail_at = item
                    if duration > threshold:
                        overDurations[ctr] += 1

            checks = [
                (failures, self._fail_cut_off, self._FAILED_REASON),
                ]
            
            for ctr, item in enumerate(self._thresholds):
                threshold, fail_at = item
                checks.append(
                    (overDurations[ctr], fail_at, self._REASON_1 + self._REASON_2 % (threshold,))
                )

            for count, cutoff, reason in checks:
                if count * 100.0 / len(times) > cutoff:
                    reasons.append(reason % dict(method=method, cutoff=cutoff))

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
        1, ClientType(OS_X_10_6, [Eventer, Inviter, Accepter]))
    simulator = CalendarClientSimulator(
        populator, parameters, reactor, '127.0.0.1', 8008)

    arrivalPolicy = SmoothRampUp(groups=10, groupSize=1, interval=3)
    arrivalPolicy.run(reactor, simulator)

    reactor.run()
    report.report()

if __name__ == '__main__':
    main()
