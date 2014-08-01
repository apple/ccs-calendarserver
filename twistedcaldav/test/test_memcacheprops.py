##
# Copyright (c) 2009-2014 Apple Inc. All rights reserved.
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

from txweb2.http import HTTPError

from txdav.xml.base import encodeXMLName

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
        return self.children[childName]


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
        return "%s = %s" % (encodeXMLName(self.ns, self.name), self.value)



class MemcachePropertyCollectionTestCase(TestCase):
    """
    Test MemcacheProprtyCollection
    """

    def getColl(self):
        return StubCollection("calendars", ["a", "b", "c"])


    def test_setget(self):

        child1 = self.getColl().getChild("a")
        child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val1"))

        child2 = self.getColl().getChild("a")
        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop1")).value,
            "val1")

        child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val2"))

        # force memcache to be consulted (once per collection per request)
        child1 = self.getColl().getChild("a")

        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop1")).value,
            "val2")


    def test_merge(self):
        child1 = self.getColl().getChild("a")
        child2 = self.getColl().getChild("a")
        child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val0"))
        child1.deadProperties().set(StubProperty("ns1:", "prop2", value="val0"))
        child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val0"))

        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop1")).value,
            "val0")
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop2")).value,
            "val0")
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop3")).value,
            "val0")

        child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val1"))
        child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val3"))

        # force memcache to be consulted (once per collection per request)
        child2 = self.getColl().getChild("a")

        # verify properties
        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop1")).value,
            "val1")
        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop2")).value,
            "val0")
        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop3")).value,
            "val3")

        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop1")).value,
            "val1")
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop2")).value,
            "val0")
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop3")).value,
            "val3")


    def test_delete(self):
        child1 = self.getColl().getChild("a")
        child2 = self.getColl().getChild("a")
        child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val0"))
        child1.deadProperties().set(StubProperty("ns1:", "prop2", value="val0"))
        child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val0"))

        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop1")).value,
            "val0")
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop2")).value,
            "val0")
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop3")).value,
            "val0")

        child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val1"))
        child1.deadProperties().delete(("ns1:", "prop1"))
        self.assertRaises(HTTPError, child1.deadProperties().get, ("ns1:", "prop1"))

        self.assertFalse(child1.deadProperties().contains(("ns1:", "prop1")))
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop2")).value,
            "val0")
        self.assertEquals(
            child1.deadProperties().get(("ns1:", "prop3")).value,
            "val0")

        # force memcache to be consulted (once per collection per request)
        child2 = self.getColl().getChild("a")

        # verify properties
        self.assertFalse(child2.deadProperties().contains(("ns1:", "prop1")))
        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop2")).value,
            "val0")
        self.assertEquals(
            child2.deadProperties().get(("ns1:", "prop3")).value,
            "val0")


    def test_setget_uids(self):

        for uid in (None, "123", "456"):
            child1 = self.getColl().getChild("a")
            child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val1%s" % (uid if uid else "",)), uid=uid)

            child2 = self.getColl().getChild("a")
            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop1"), uid=uid).value,
                "val1%s" % (uid if uid else "",))

            child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val2%s" % (uid if uid else "",)), uid=uid)

            # force memcache to be consulted (once per collection per request)
            child1 = self.getColl().getChild("a")

            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop1"), uid=uid).value,
                "val2%s" % (uid if uid else "",))


    def test_merge_uids(self):

        for uid in (None, "123", "456"):
            child1 = self.getColl().getChild("a")
            child2 = self.getColl().getChild("a")
            child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val0%s" % (uid if uid else "",)), uid=uid)
            child1.deadProperties().set(StubProperty("ns1:", "prop2", value="val0%s" % (uid if uid else "",)), uid=uid)
            child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val0%s" % (uid if uid else "",)), uid=uid)

            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop1"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop2"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop3"), uid=uid).value,
                "val0%s" % (uid if uid else "",))

            child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val1%s" % (uid if uid else "",)), uid=uid)
            child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val3%s" % (uid if uid else "",)), uid=uid)

            # force memcache to be consulted (once per collection per request)
            child2 = self.getColl().getChild("a")

            # verify properties
            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop1"), uid=uid).value,
                "val1%s" % (uid if uid else "",))
            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop2"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop3"), uid=uid).value,
                "val3%s" % (uid if uid else "",))

            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop1"), uid=uid).value,
                "val1%s" % (uid if uid else "",))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop2"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop3"), uid=uid).value,
                "val3%s" % (uid if uid else "",))


    def test_delete_uids(self):

        for uid in (None, "123", "456"):
            child1 = self.getColl().getChild("a")
            child2 = self.getColl().getChild("a")
            child1.deadProperties().set(StubProperty("ns1:", "prop1", value="val0%s" % (uid if uid else "",)), uid=uid)
            child1.deadProperties().set(StubProperty("ns1:", "prop2", value="val0%s" % (uid if uid else "",)), uid=uid)
            child1.deadProperties().set(StubProperty("ns1:", "prop3", value="val0%s" % (uid if uid else "",)), uid=uid)

            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop1"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop2"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop3"), uid=uid).value,
                "val0%s" % (uid if uid else "",))

            child2.deadProperties().set(StubProperty("ns1:", "prop1", value="val1%s" % (uid if uid else "",)), uid=uid)
            child1.deadProperties().delete(("ns1:", "prop1"), uid=uid)
            self.assertRaises(HTTPError, child1.deadProperties().get, ("ns1:", "prop1"), uid=uid)

            self.assertFalse(child1.deadProperties().contains(("ns1:", "prop1"), uid=uid))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop2"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child1.deadProperties().get(("ns1:", "prop3"), uid=uid).value,
                "val0%s" % (uid if uid else "",))

            # force memcache to be consulted (once per collection per request)
            child2 = self.getColl().getChild("a")

            # verify properties
            self.assertFalse(child2.deadProperties().contains(("ns1:", "prop1"), uid=uid))
            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop2"), uid=uid).value,
                "val0%s" % (uid if uid else "",))
            self.assertEquals(
                child2.deadProperties().get(("ns1:", "prop3"), uid=uid).value,
                "val0%s" % (uid if uid else "",))


    def _stub_set_multi(self, values, time=None):

        self.callCount += 1
        for key, value in values.iteritems():
            self.results[key] = value


    def test_splitSetMulti(self):

        self.callCount = 0
        self.results = {}

        mpc = MemcachePropertyCollection(None)
        values = {}
        for i in xrange(600):
            values["key%d" % (i,)] = "value%d" % (i,)

        mpc._split_set_multi(values, self._stub_set_multi)

        self.assertEquals(self.callCount, 3)
        self.assertEquals(self.results, values)


    def test_splitSetMultiWithChunksize(self):

        self.callCount = 0
        self.results = {}

        mpc = MemcachePropertyCollection(None)
        values = {}
        for i in xrange(13):
            values["key%d" % (i,)] = "value%d" % (i,)

        mpc._split_set_multi(values, self._stub_set_multi, chunksize=3)

        self.assertEquals(self.callCount, 5)
        self.assertEquals(self.results, values)


    def _stub_gets_multi(self, keys):

        self.callCount += 1
        result = {}
        for key in keys:
            result[key] = self.expected[key]
        return result


    def test_splitGetsMulti(self):

        self.callCount = 0
        self.expected = {}
        keys = []
        for i in xrange(600):
            keys.append("key%d" % (i,))
            self.expected["key%d" % (i,)] = "value%d" % (i,)

        mpc = MemcachePropertyCollection(None)
        result = mpc._split_gets_multi(keys, self._stub_gets_multi)

        self.assertEquals(self.callCount, 3)
        self.assertEquals(self.expected, result)


    def test_splitGetsMultiWithChunksize(self):

        self.callCount = 0
        self.expected = {}
        keys = []
        for i in xrange(600):
            keys.append("key%d" % (i,))
            self.expected["key%d" % (i,)] = "value%d" % (i,)

        mpc = MemcachePropertyCollection(None)
        result = mpc._split_gets_multi(keys, self._stub_gets_multi, chunksize=12)

        self.assertEquals(self.callCount, 50)
        self.assertEquals(self.expected, result)
