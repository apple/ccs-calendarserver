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
DAV Property store using memcache on top of another property store
implementation.
"""

__all__ = ["MemcachePropertyCollection"]

try:
    from hashlib import md5
except ImportError:
    from md5 import new as md5

from memcacheclient import ClientFactory as MemcacheClientFactory, MemcacheError, TokenMismatchError

from twisted.python.filepath import FilePath
from twisted.web2 import responsecode
from twisted.web2.http import HTTPError, StatusResponse

from twistedcaldav.config import config
from twistedcaldav.log import LoggingMixIn, Logger

log = Logger()

NoValue = ""


class MemcachePropertyCollection (LoggingMixIn):
    """
    Manages a single property store for all resources in a collection.
    """
    def __init__(self, collection, cacheTimeout=0):
        self.collection = collection
        self.cacheTimeout = cacheTimeout

    @classmethod
    def memcacheClient(cls, refresh=False):
        if not hasattr(MemcachePropertyCollection, "_memcacheClient"):

            log.info("Instantiating memcache connection for MemcachePropertyCollection")

            MemcachePropertyCollection._memcacheClient = MemcacheClientFactory.getClient(["%s:%s" % (config.Memcached.BindAddress, config.Memcached.Port)],
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
        #          (namespace, name): property,
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
            self.log_debug("No child property cache for %s" % (child,))
            childCache, token = ({}, None)

            #message = "No child property cache for %s" % (child,)
            #log.error(message)
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

        self.log_debug("Loading cache for %s" % (self.collection,))

        client = self.memcacheClient()
        assert client is not None, "OMG no cache!"
        if client is None:
            return None

        keys = tuple((
            (self._keyForPath(self.collection.fp.child(childName).path), childName)
            for childName in childNames
        ))

        result = client.gets_multi((key for key, name in keys))

        if self.logger.willLogAtLevel("debug"):
            if abortIfMissing:
                missing = "missing "
            else:
                missing = ""
            self.log_debug("Loaded keys for %schildren of %s: %s" % (
                missing,
                self.collection,
                [name for key, name in keys],
            ))

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

    def _storeCache(self, cache):
        self.log_debug("Storing cache for %s" % (self.collection,))

        values = dict((
            (self._keyForPath(path), props)
            for path, props
            in cache.iteritems()
        ))

        client = self.memcacheClient()
        if client is not None:
            client.set_multi(values, time=self.cacheTimeout)

    def _buildCache(self, childNames=None):
        if childNames is None:
            childNames = self.collection.listChildren()
        elif not childNames:
            return {}

        self.log_debug("Building cache for %s" % (self.collection,))

        cache = {}

        for childName in childNames:
            child = self.collection.getChild(childName)
            if child is None:
                continue

            propertyStore = child.deadProperties()
            props = {}
            for qname in propertyStore.list(cache=False):
                props[qname] = propertyStore.get(qname, cache=False)

            cache[child.fp.path] = props

        self._storeCache(cache)

        return cache

    def setProperty(self, child, property, delete=False):
        propertyCache, key, childCache, token = self.childCache(child)

        if delete:
            qname = property
            if childCache.has_key(qname):
                del childCache[qname]
        else:
            qname = property.qname()
            childCache[qname] = property

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
                    log.debug("memcacheprops setProperty TokenMismatchError; retrying...")

                finally:
                    # Re-fetch the properties for this child
                    loaded = self._loadCache(childNames=(child.fp.basename(),))
                    propertyCache.update(loaded.iteritems())

                retries -= 1

                propertyCache, key, childCache, token = self.childCache(child)

                if delete:
                    if childCache.has_key(qname):
                        del childCache[qname]
                else:
                    childCache[qname] = property

            else:
                log.error("memcacheprops setProperty had too many failures")
                delattr(self, "_propertyCache")
                raise MemcacheError("Unable to %s property {%s}%s on %s"
                    % ("delete" if delete else "set",
                    qname[0], qname[1], child))

    def deleteProperty(self, child, qname):
        return self.setProperty(child, qname, delete=True)

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

    class ChildPropertyStore (LoggingMixIn):
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

        def get(self, qname, cache=True):
            if cache:
                propertyCache = self.propertyCache()
                if qname in propertyCache:
                    return propertyCache[qname]
                else:
                    raise HTTPError(StatusResponse(
                        responsecode.NOT_FOUND,
                        "No such property: {%s}%s" % qname
                    ))

            self.log_debug("Read for %s on %s"
                           % (qname, self.childPropertyStore.resource.fp.path))
            return self.childPropertyStore.get(qname)

        def set(self, property):
            self.log_debug("Write for %s on %s"
                           % (property.qname(), self.childPropertyStore.resource.fp.path))

            self.parentPropertyCollection.setProperty(self.child, property)
            self.childPropertyStore.set(property)

        def delete(self, qname):
            self.log_debug("Delete for %s on %s"
                           % (qname, self.childPropertyStore.resource.fp.path))

            self.parentPropertyCollection.deleteProperty(self.child, qname)
            self.childPropertyStore.delete(qname)

        def contains(self, qname, cache=True):
            if cache:
                propertyCache = self.propertyCache()
                return qname in propertyCache

            self.log_debug("Contains for %s"
                           % (self.childPropertyStore.resource.fp.path,))
            return self.childPropertyStore.contains(qname)

        def list(self, cache=True):
            if cache:
                propertyCache = self.propertyCache()
                return propertyCache.iterkeys()

            self.log_debug("List for %s"
                           % (self.childPropertyStore.resource.fp.path,))
            return self.childPropertyStore.list()
