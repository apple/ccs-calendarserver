##
# Copyright (c) 2009-2013 Apple Computer, Inc. All rights reserved.
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
DAV Property store using memcache on top of another property store
implementation.
"""

__all__ = ["MemcachePropertyCollection"]

try:
    from hashlib import md5
except ImportError:
    from md5 import new as md5

from twext.python.log import Logger
from twext.python.memcacheclient import ClientFactory
from twext.python.memcacheclient import MemcacheError, TokenMismatchError
from twext.python.filepath import CachingFilePath as FilePath
from txdav.xml.base import encodeXMLName
from twext.web2 import responsecode
from twext.web2.http import HTTPError, StatusResponse

from twistedcaldav.config import config



NoValue = ""



class MemcachePropertyCollection (object):
    """
    Manages a single property store for all resources in a collection.
    """
    log = Logger()

    def __init__(self, collection, cacheTimeout=0):
        self.collection = collection
        self.cacheTimeout = cacheTimeout


    @classmethod
    def memcacheClient(cls, refresh=False):
        if not hasattr(MemcachePropertyCollection, "_memcacheClient"):

            cls.log.info("Instantiating memcache connection for MemcachePropertyCollection")

            MemcachePropertyCollection._memcacheClient = ClientFactory.getClient([
                    "%s:%s" % (config.Memcached.Pools.Default.BindAddress, config.Memcached.Pools.Default.Port)
                ],
                debug=0,
                pickleProtocol=2,
            )
            assert MemcachePropertyCollection._memcacheClient is not None

        return MemcachePropertyCollection._memcacheClient


    def propertyCache(self):
        # The property cache has this format:
        #  {
        #    "/path/to/resource/file":
        #      (
        #        {
        #          (namespace, name, uid): property,
        #          ...,
        #        },
        #        memcache_token,
        #      ),
        #    ...,
        #  }
        if not hasattr(self, "_propertyCache"):
            self._propertyCache = self._loadCache()
        return self._propertyCache


    def childCache(self, child):
        path = child.fp.path
        key = self._keyForPath(path)
        propertyCache = self.propertyCache()

        try:
            childCache, token = propertyCache[key]
        except KeyError:
            self.log.debug("No child property cache for %s" % (child,))
            childCache, token = ({}, None)

            #message = "No child property cache for %s" % (child,)
            #self.log.error(message)
            #raise AssertionError(message)

        return propertyCache, key, childCache, token


    def _keyForPath(self, path):
        key = "|".join((
            self.__class__.__name__,
            path
        ))
        return md5(key).hexdigest()


    def _loadCache(self, childNames=None):
        if childNames is None:
            abortIfMissing = False
            childNames = self.collection.listChildren()
        else:
            if childNames:
                abortIfMissing = True
            else:
                return {}

        self.log.debug("Loading cache for %s" % (self.collection,))

        client = self.memcacheClient()
        assert client is not None, "OMG no cache!"
        if client is None:
            return None

        keys = tuple((
            (self._keyForPath(self.collection.fp.child(childName).path), childName)
            for childName in childNames
        ))

        result = self._split_gets_multi((key for key, _ignore_name in keys),
            client.gets_multi)

        if abortIfMissing:
            missing = "missing "
        else:
            missing = ""
        self.log.debug(
            "Loaded keys for {missing}children of {collection}: {children}",
            missing=missing, collection=self.collection,
            children=[name for _ignore_key, name in keys],
        )
        # FIXME.logging: defer the above list comprehension

        missing = tuple((
            name for key, name in keys
            if key not in result
        ))

        if missing:
            if abortIfMissing:
                raise MemcacheError("Unable to fully load cache for %s" % (self.collection,))

            loaded = self._buildCache(childNames=missing)
            loaded = self._loadCache(childNames=(FilePath(name).basename() for name in loaded.iterkeys()))

            result.update(loaded.iteritems())

        return result


    def _split_gets_multi(self, keys, func, chunksize=250):
        """
        Splits gets_multi into chunks to avoid a memcacheclient timeout due
        of a large number of keys.  Consolidates and returns results.
        Takes a function parameter for easier unit testing.
        """

        results = {}
        count = 0
        subset = []
        for key in keys:
            if count == 0:
                subset = []
            subset.append(key)
            count += 1
            if count == chunksize:
                results.update(func(subset))
                count = 0
        if count:
            results.update(func(subset))
        return results


    def _split_set_multi(self, values, func, time=0, chunksize=250):
        """
        Splits set_multi into chunks to avoid a memcacheclient timeout due
        of a large number of keys.
        Takes a function parameter for easier unit testing.
        """
        count = 0
        subset = {}
        for key, value in values.iteritems():
            if count == 0:
                subset.clear()
            subset[key] = value
            count += 1
            if count == chunksize:
                func(subset, time=time)
                count = 0
        if count:
            func(subset, time=time)


    def _storeCache(self, cache):
        self.log.debug("Storing cache for %s" % (self.collection,))

        values = dict((
            (self._keyForPath(path), props)
            for path, props
            in cache.iteritems()
        ))

        client = self.memcacheClient()
        if client is not None:
            self._split_set_multi(values, client.set_multi,
                time=self.cacheTimeout)


    def _buildCache(self, childNames=None):
        if childNames is None:
            childNames = self.collection.listChildren()
        elif not childNames:
            return {}

        self.log.debug("Building cache for %s" % (self.collection,))

        cache = {}

        for childName in childNames:
            child = self.collection.getChild(childName)
            if child is None:
                continue

            propertyStore = child.deadProperties()
            props = {}
            for pnamespace, pname, puid in propertyStore.list(filterByUID=False, cache=False):
                props[(pnamespace, pname, puid,)] = propertyStore.get((pnamespace, pname,), uid=puid, cache=False)

            cache[child.fp.path] = props

        self._storeCache(cache)

        return cache


    def setProperty(self, child, property, uid, delete=False):
        propertyCache, key, childCache, token = self.childCache(child)

        if delete:
            qname = property
            qnameuid = qname + (uid,)
            if qnameuid in childCache:
                del childCache[qnameuid]
        else:
            qname = property.qname()
            qnameuid = qname + (uid,)
            childCache[qnameuid] = property

        client = self.memcacheClient()

        if client is not None:
            retries = 10
            while retries:
                try:
                    if client.set(key, childCache, time=self.cacheTimeout,
                        token=token):
                        # Success
                        break

                except TokenMismatchError:
                    # The value in memcache has changed since we last
                    # fetched it
                    self.log.debug("memcacheprops setProperty TokenMismatchError; retrying...")

                finally:
                    # Re-fetch the properties for this child
                    loaded = self._loadCache(childNames=(child.fp.basename(),))
                    propertyCache.update(loaded.iteritems())

                retries -= 1

                propertyCache, key, childCache, token = self.childCache(child)

                if delete:
                    if qnameuid in childCache:
                        del childCache[qnameuid]
                else:
                    childCache[qnameuid] = property

            else:
                self.log.error("memcacheprops setProperty had too many failures")
                delattr(self, "_propertyCache")
                raise MemcacheError("Unable to %s property %s%s on %s" % (
                    "delete" if delete else "set",
                    uid if uid else "",
                    encodeXMLName(*qname),
                    child
                ))


    def deleteProperty(self, child, qname, uid):
        return self.setProperty(child, qname, uid, delete=True)


    def flushCache(self, child):
        path = child.fp.path
        key = self._keyForPath(path)
        propertyCache = self.propertyCache()

        if key in propertyCache:
            del propertyCache[key]

        client = self.memcacheClient()
        if client is not None:
            result = client.delete(key)
            if not result:
                raise MemcacheError("Unable to flush cache on %s" % (child,))


    def propertyStoreForChild(self, child, childPropertyStore):
        return self.ChildPropertyStore(self, child, childPropertyStore)


    class ChildPropertyStore (object):
        log = Logger()

        def __init__(self, parentPropertyCollection, child, childPropertyStore):
            self.parentPropertyCollection = parentPropertyCollection
            self.child = child
            self.childPropertyStore = childPropertyStore

        def propertyCache(self):
            path = self.child.fp.path
            key = self.parentPropertyCollection._keyForPath(path)
            parentPropertyCache = self.parentPropertyCollection.propertyCache()
            return parentPropertyCache.get(key, ({}, None))[0]

        def flushCache(self):
            self.parentPropertyCollection.flushCache(self.child)

        def get(self, qname, uid=None, cache=True):
            if cache:
                propertyCache = self.propertyCache()
                qnameuid = qname + (uid,)
                if qnameuid in propertyCache:
                    return propertyCache[qnameuid]
                else:
                    raise HTTPError(StatusResponse(
                        responsecode.NOT_FOUND,
                        "No such property: %s%s" % (uid if uid else "", encodeXMLName(*qname))
                    ))

            self.log.debug("Read for %s%s on %s" % (
                ("{%s}:" % (uid,)) if uid else "",
                qname,
                self.childPropertyStore.resource.fp.path
            ))
            return self.childPropertyStore.get(qname, uid=uid)

        def set(self, property, uid=None):
            self.log.debug("Write for %s%s on %s" % (
                ("{%s}:" % (uid,)) if uid else "",
                property.qname(),
                self.childPropertyStore.resource.fp.path
            ))

            self.parentPropertyCollection.setProperty(self.child, property, uid)
            self.childPropertyStore.set(property, uid=uid)

        def delete(self, qname, uid=None):
            self.log.debug("Delete for %s%s on %s" % (
                ("{%s}:" % (uid,)) if uid else "",
                qname,
                self.childPropertyStore.resource.fp.path
            ))

            self.parentPropertyCollection.deleteProperty(self.child, qname, uid)
            self.childPropertyStore.delete(qname, uid=uid)

        def contains(self, qname, uid=None, cache=True):
            if cache:
                propertyCache = self.propertyCache()
                qnameuid = qname + (uid,)
                return qnameuid in propertyCache

            self.log.debug("Contains for %s%s on %s" % (
                ("{%s}:" % (uid,)) if uid else "",
                qname,
                self.childPropertyStore.resource.fp.path,
            ))
            return self.childPropertyStore.contains(qname, uid=uid)

        def list(self, uid=None, filterByUID=True, cache=True):
            if cache:
                propertyCache = self.propertyCache()
                results = propertyCache.keys()
                if filterByUID:
                    return [
                        (namespace, name)
                        for namespace, name, propuid in results
                        if propuid == uid
                    ]
                else:
                    return results

            self.log.debug("List for %s"
                           % (self.childPropertyStore.resource.fp.path,))
            return self.childPropertyStore.list(uid=uid, filterByUID=filterByUID)
