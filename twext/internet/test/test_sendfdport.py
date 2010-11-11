# -*- test-case-name: twext.internet.test.test_sendfdport -*-
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
Tests for L{twext.internet.sendfdport}.
"""

from twisted.trial.unittest import TestCase
from twext.internet.sendfdport import InheritedSocketDispatcher
from twisted.internet.interfaces import IReactorFDSet
from zope.interface.declarations import implements


class ReaderAdder(object):
    implements(IReactorFDSet)

    def __init__(self):
        self.readers = []

    def addReader(self, reader):
        self.readers.append(reader)

    def getReaders(self):
        return self.readers[:]



class InheritedSocketDispatcherTests(TestCase):
    """
    Inherited socket dispatcher tests.
    """

    def test_addAfterStart(self):
        """
        Adding a socket to an L{InheritedSocketDispatcher} after it has already
        been started results in it immediately starting reading.
        """
        reactor = ReaderAdder()
        dispatcher = InheritedSocketDispatcher(None)
        dispatcher.reactor = reactor
        dispatcher.startDispatching()
        dispatcher.addSocket()
        self.assertEquals(reactor.getReaders(), dispatcher._subprocessSockets)
