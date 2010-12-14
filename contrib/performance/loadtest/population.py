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


    
def main():
    import random

    from twisted.internet import reactor
    from twisted.internet.task import LoopingCall

    r = random.Random()
    r.seed(100)
    populator = Populator(r)
    parameters = PopulationParameters()
    simulator = CalendarClientSimulator(
        populator, parameters, reactor, '127.0.0.1', 8008)

    # Uh yea let's see
    LoopingCall(simulator.add, 1).start(1)

    reactor.run()

if __name__ == '__main__':
    main()
