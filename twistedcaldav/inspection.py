##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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
Inspection framework for Calendar Server
"""

from twisted.internet.protocol import ServerFactory
from twisted.protocols.basic import LineReceiver
from twistedcaldav.log import LoggingMixIn
import datetime
import time

__all__ = [
    "Inspector",
    "InspectionFactory",
]


class Inspector(object):

    _inspector = None

    @classmethod
    def getInspector(klass):
        if klass._inspector is None:
            klass._inspector = klass()
        return klass._inspector

    @classmethod
    def getInspection(klass, id, emit=True):
        if klass.isInspecting():
            return Inspection(id, emit=emit)
        else:
            return None

    @classmethod
    def isInspecting(klass):
        return klass._inspector is not None and len(klass._inspector.observers) > 0

    def __init__(self):
        self.observers = set()

    def addObserver(self, observer):
        self.observers.add(observer)

    def removeObserver(self, observer):
        try:
            self.observers.remove(observer)
        except KeyError:
            pass

    def hasObservers(self):
        return len(self.observers) > 0

    def emit(self, msg):
        if self.observers:
            now = datetime.datetime.now()
            msg = "%s | %s" % (now, msg)
            for observer in self.observers:
                observer.emit(msg)


class Inspection(object):

    def __init__(self, id, event="init", emit=True):
        self.id = id
        self.timeline = []
        self.add(event, emit=emit)

    def add(self, event, emit=True):
        self.timeline.append((time.time(), event))
        if emit:
            if len(self.timeline) > 1:
                Inspector.getInspector().emit("%d | %s=%.3f" %
                    (self.id, event, self.timeline[-1][0] - self.timeline[-2][0]))
            else:
                Inspector.getInspector().emit("%d | %s" % (self.id, event))

    def complete(self):
        timestrings = []
        starttime, event = self.timeline[0]
        basetime = starttime
        for timestamp, event in self.timeline[1:]:
            delta = timestamp - basetime
            timestrings.append("%s=%.3f" % (event, delta))
            basetime = timestamp
        Inspector.getInspector().emit("%d | duration=%.3f | %s" %
            (self.id, timestamp - starttime, " ".join(timestrings)))

class InspectionProtocol(LineReceiver, LoggingMixIn):

    def connectionMade(self):
        Inspector.getInspector().addObserver(self)

    def connectionLost(self, reason):
        Inspector.getInspector().removeObserver(self)

    def lineReceived(self, line):
        line = line.strip()
        if line == "ping":
            self.sendLine("pong")
        else:
            self.sendLine("???")

    def emit(self, msg):
        self.sendLine(msg)


class InspectionFactory(ServerFactory):

    protocol = InspectionProtocol
