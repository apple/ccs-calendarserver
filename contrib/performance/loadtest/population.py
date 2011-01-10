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

from itertools import izip

from stats import mean, median, stddev, mad
from loadtest.ical import SnowLeopard


class PopulationParameters(object):
    """
    Descriptive statistics about a population of Calendar Server users.
    """
    def clientTypes(self):
        """
        Return a list of two-tuples giving the weights and types of
        clients in the population.
        """
        return [(1, SnowLeopard)]



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
        @rtype: generator of L{ICalendarClient} providers
        """
        for (clientType,) in izip(self._cycle(parameters.clientTypes())):
            yield clientType



class CalendarClientSimulator(object):
    def __init__(self, populator, parameters, reactor, host, port):
        self.populator = populator
        self.reactor = reactor
        self.host = host
        self.port = port
        self._pop = self.populator.populate(parameters)
        self._user = 1


    def _nextUser(self):
        from urllib2 import HTTPDigestAuthHandler
        user = "user%02d" % (self._user,)
        self._user += 1
        auth = HTTPDigestAuthHandler()
        auth.add_password(
            realm="Test Realm",
            uri="http://127.0.0.1:8008/",
            user=user,
            passwd=user)
        return user, auth


    def add(self, numClients):
        for n in range(numClients):
            user, auth = self._nextUser()
            client = self._pop.next()(self.reactor, self.host, self.port, user, auth)
            client.run()
        print 'Now running', self._user, 'clients.'



class StatisticsBase(object):
    def observe(self, event):
        if event.get('type') == 'request':
            self.eventReceived(event)



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



class ReportStatistics(StatisticsBase):
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


    def eventReceived(self, event):
        dataset = self._perMethodTimes.setdefault(event['method'], [])
        dataset.append((event['success'], event['duration']))


    def _printHeader(self):
        format = []
        labels = []
        for (label, width, fmt) in self._fields:
            format.append('%%%ds' % (width,))
            labels.append(label)
        print ''.join(format) % tuple(labels)


    def _summarizeData(self, method, data):
        failed = 0
        threesec = 0
        durations = []
        for (success, duration) in data:
            if not success:
                failed += 1
            if duration > 3:
                threesec += 1
            durations.append(duration)

        return method, len(data), failed, threesec, mean(durations), median(durations)


    def _printData(self, *values):
        format = ''.join(fmt for (label, width, fmt) in self._fields)
        print format % values


    def summarize(self):
        print
        self._printHeader()
        for method, data in self._perMethodTimes.iteritems():
            self._printData(*self._summarizeData(method, data))

    
def main():
    import random

    from twisted.internet import reactor
    from twisted.internet.task import LoopingCall
    from twisted.python.log import addObserver

    report = ReportStatistics()
    addObserver(SimpleStatistics().observe)
    addObserver(report.observe)

    r = random.Random()
    r.seed(100)
    populator = Populator(r)
    parameters = PopulationParameters()
    simulator = CalendarClientSimulator(
        populator, parameters, reactor, '127.0.0.1', 8008)

    # Add some clients.
    call = LoopingCall(simulator.add, 1)
    call.start(3)
    reactor.callLater(3 * 90, call.stop)

    reactor.run()
    report.summarize()

if __name__ == '__main__':
    main()
