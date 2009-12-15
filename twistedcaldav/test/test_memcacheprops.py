##
# Copyright (c) 2009 Apple Computer, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
##

"""
Test memcacheprops.
"""

import os

from twisted.web2.http import HTTPError
from twisted.internet.defer import succeed, inlineCallbacks, returnValue

from twistedcaldav.memcacheprops import MemcachePropertyCollection
from twistedcaldav.test.util import InMemoryPropertyStore
from twistedcaldav.test.util import TestCase



class StubCollection(object):

    def __init__(self, path, childNames):
        self.path = path
        self.fp = StubFP(path)
        self.children = {}

        for childName in childNames:
            self.children[childName] = StubResource(self, path, childName)

    def listChildren(self):
        return self.children.iterkeys()

    def getChild(self, childName):
        return succeed(self.children[childName])

    def propertyCollection(self):
        if not hasattr(self, "_propertyCollection"):
            self._propertyCollection = MemcachePropertyCollection(self)
        return self._propertyCollection


class StubResource(object):

    def __init__(self, parent, path, name):
        self.parent = parent
        self.fp = StubFP(os.path.join(path, name))

    def deadProperties(self):
        if not hasattr(self, "_dead_properties"):
            self._dead_properties = self.parent.propertyCollection().propertyStoreForChild(self, InMemoryPropertyStore())
        return self._dead_properties

class StubFP(object):

    def __init__(self, path):
        self.path = path

    def child(self, childName):
        class _Child(object):
            def __init__(self, path):
                self.path = path
        return _Child(os.path.join(self.path, childName))

    def basename(self):
        return os.path.basename(self.path)

class StubProperty(object):

    def __init__(self, ns, name, value=None):
        self.ns = ns
        self.name = name
        self.value = value

    def qname(self):
        return self.ns, self.name


    def __repr__(self):
        return "{%s}%s = %s" % (self.ns, self.name, self.value)


class MemcachePropertyCollectionTestCase(TestCase):
    """
    Test MemcachePropertyCollection
    """

    @inlineCallbacks
    def assertRaisesDeferred(self, exception, f, *args, **kwargs):
        try:
            result = (yield f(*args, **kwargs))
        except exception, inst:
            returnValue(inst)
        except:
            raise self.failureException('%s raised instead of %s:\n %s'
                                        % (sys.exc_info()[0],
                                           exception.__name__,
                                           failure.Failure().getTraceback()))
        else:
            raise self.failureException('%s not raised (%r returned)'
                                        % (exception.__name__, result))


    def getColl(self):
        return StubCollection("calendars", ["a", "b", "c"])

    @inlineCallbacks
    def test_setget(self):

        child1 = (yield self.getColl().getChild("a"))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val1")))

        child2 = (yield self.getColl().getChild("a"))
        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop1"))).value,
            "val1")

        (yield child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val2")))

        # force memcache to be consulted (once per collection per request)
        child1 = (yield self.getColl().getChild("a"))

        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop1"))).value,
            "val2")

    @inlineCallbacks
    def test_merge(self):
        child1 = (yield self.getColl().getChild("a"))
        child2 = (yield self.getColl().getChild("a"))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val0")))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop2", value="val0")))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val0")))

        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop1"))).value,
            "val0")
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop2"))).value,
            "val0")
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop3"))).value,
            "val0")

        (yield child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val1")))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val3")))

        # force memcache to be consulted (once per collection per request)
        child2 = (yield self.getColl().getChild("a"))

        # verify properties
        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop1"))).value,
            "val1")
        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop2"))).value,
            "val0")
        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop3"))).value,
            "val3")

        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop1"))).value,
            "val1")
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop2"))).value,
            "val0")
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop3"))).value,
            "val3")

    @inlineCallbacks
    def test_delete(self):
        child1 = (yield self.getColl().getChild("a"))
        child2 = (yield self.getColl().getChild("a"))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val0")))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop2", value="val0")))
        (yield child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val0")))

        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop1"))).value,
            "val0")
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop2"))).value,
            "val0")
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop3"))).value,
            "val0")

        (yield child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val1")))
        (yield child1.deadProperties().delete(("ns1:", "prop1")))
        self.assertRaisesDeferred(HTTPError, child1.deadProperties().get, ("ns1:", "prop1"))

        self.assertFalse((yield child1.deadProperties().contains(("ns1:", "prop1")))) 
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop2"))).value,
            "val0")
        self.assertEquals((yield child1.deadProperties().get(("ns1:", "prop3"))).value,
            "val0")

        # force memcache to be consulted (once per collection per request)
        child2 = (yield self.getColl().getChild("a"))

        # verify properties
        self.assertFalse((yield child2.deadProperties().contains(("ns1:", "prop1")))) 
        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop2"))).value,
            "val0")
        self.assertEquals((yield child2.deadProperties().get(("ns1:", "prop3"))).value,
            "val0")
