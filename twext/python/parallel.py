# -*- test-case-name: twext.python.test.test_parallel -*-
##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
Utilities for parallelizing tasks.
"""

from twisted.internet.defer import inlineCallbacks, DeferredList, returnValue

class Parallelizer(object):
    """
    Do some operation with a degree of parallelism, using a set of resources
    which may each only be used for one task at a time, given some underlying
    API that returns L{Deferreds}.

    @ivar available: A list of available resources from the C{resources}
        constructor parameter.

    @ivar busy: A list of resources which are currently being used by
        operations.
    """

    def __init__(self, resources):
        """
        Initialize a L{Parallelizer} with a list of objects that will be passed
        to the callables sent to L{Parallelizer.do}.

        @param resources: objects which may be of any arbitrary type.
        @type resources: C{list}
        """
        self.available = list(resources)
        self.busy = []
        self.activeDeferreds = []


    @inlineCallbacks
    def do(self, operation):
        """
        Call C{operation} with one of the resources in C{self.available},
        removing that value for use by other callers of C{do} until the task
        performed by C{operation} is complete (in other words, the L{Deferred}
        returned by C{operation} has fired).

        @param operation: a 1-argument callable taking a resource from
            C{self.active} and returning a L{Deferred} when it's done using
            that resource.
        @type operation: C{callable}

        @return: a L{Deferred} that fires as soon as there are resources
            available such that this task can be I{started} - not completed.
        """
        if not self.available:
            yield DeferredList(self.activeDeferreds, fireOnOneCallback=True,
                               fireOnOneErrback=True)
        active = self.available.pop(0)
        self.busy.append(active)
        o = operation(active)
        def andFinally(whatever):
            self.activeDeferreds.remove(o)
            self.busy.remove(active)
            self.available.append(active)
            return whatever
        self.activeDeferreds.append(o)
        o.addBoth(andFinally)
        returnValue(None)


    def done(self):
        """
        Wait until all operations started by L{Parallelizer.do} are completed.

        @return: a L{Deferred} that fires (with C{None}) when all the currently
            pending work on this L{Parallelizer} is completed and C{busy} is
            empty again.
        """
        return (DeferredList(self.activeDeferreds)
                .addCallback(lambda ignored: None))



