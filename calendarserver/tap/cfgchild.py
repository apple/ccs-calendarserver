##
# Copyright (c) 2005-2011 Apple Inc. All rights reserved.
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
Tools for spawning general-purpose child processes that have a store devrived
from a .
"""

__all__ = [
    # Only the spawner service is really interesting; the other parts are
    # internal implementation details which shouldn't be needed outside this
    # file.
    'ConfiguredChildSpawner',
]

from twisted.python.reflect import namedAny, qual
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.protocols.amp import AMP, Command, String, Integer#, ListOf
from txdav.common.datastore.upgrade.migrate import (
    StoreSpawnerService, swapAMP
)

from calendarserver.tap.util import getDBPool, storeFromConfig

class ConfigureChild(Command):
    """
    Configure a child process, most especially with all the information that it
    needs in order to construct a data store.
    """

    arguments = [
        # The name of the class to delegate to once configuration is complete.
        ("delegateTo", String()),
        ("pidFile", String()),
        ("logID", String()),
        ("configFile", String()),

        # computed value determined only in master, so needs to be propagated
        # to be correct.
        ("processCount", Integer()),

        ## only needed for request processing, and we're not using this
        ## facility for that work (yet)
        # ("inheritFDs", ListOf(Integer())),
        # ("inheritSSLFDs", ListOf(Integer())),
        # ("metaFD", String(optional=True)),

        ## shared connection pool!
        ("connectionPoolFD", Integer(optional=True)),
    ]



class ChildConfigurator(AMP):
    """
    Protocol which can configure a child process.
    """

    def __init__(self, config=None):
        """
        Optionally accept a configuration for testing, but normally created in
        the subprocess configuration-free.
        """
        super(AMP, self).__init__()
        if config is None:
            from twistedcaldav.config import config
        self.config = config


    @ConfigureChild.responder
    def conf(self, delegateTo, pidFile, logID, configFile, processCount,
             connectionPoolFD=None):
        """
        Load the current config file into this child process, create a store
        based on it, and delegate to the upgrade logic.
        """
        # Load the configuration file.
        self.config.load(configFile)

        # Adjust the child's configuration to add all the relevant options for
        # the store that won't be mentioned in the config file.
        changedConfig = dict(
            LogID            = logID,
            PIDFile          = pidFile,
            MultiProcess     = dict(
                ProcessCount = processCount
            )
        )
        if connectionPoolFD is not None:
            changedConfig.update(DBAMPFD=connectionPoolFD)
        self.config.updateDefaults(changedConfig)

        # Construct and start database pool and store.
        pool, txnf = getDBPool(self.config)
        if pool is not None:
            from twisted.internet import reactor
            pool.startService()
            reactor.addSystemEventTrigger(
                "before", "shutdown", pool.stopService
            )
        dbstore = storeFromConfig(self.config, txnf)

        # Finally, construct the class we're supposed to delegate to.
        delegateClass = namedAny(delegateTo)
        swapAMP(self, delegateClass(dbstore))
        return {}



class ConfiguredChildSpawner(StoreSpawnerService):
    """
    L{StoreSpawnerService} that will load a full configuration into each child.
    """

    def __init__(self, maker, dispenser, config):
        """
        Create a L{ConfiguredChildSpawner}.

        @param maker: a L{CalDAVServiceMaker} instance that supplies the
            configuration.

        @param dispenser: a L{calendarserver.tap.ConnectionDispenser} or C{None}.

        @param config: the L{twistedcaldav.config.Config} to use to configure
            the subprocess.
        """
        self.nextID = 0
        self.maker = maker
        self.dispenser = dispenser
        self.config = config


    @inlineCallbacks
    def spawnWithStore(self, here, there):
        """
        Spawn the child with a store based on a configuration.
        """
        thisID = self.nextID
        self.nextID += 1
        if self.dispenser is not None:
            poolfd = self.dispenser.dispense()
            childFDs = {poolfd: poolfd}
        else:
            childFDs = None
        controller = yield self.spawn(
            AMP(), ChildConfigurator, childFDs=childFDs
        )
        yield controller.callRemote(
            ConfigureChild,
            delegateTo=qual(there),
            pidfile="%s-migrator-%s" % (self.maker.tapname, thisID),
            logID="migrator-%s" % (thisID,),
            configFile=self.config.getProvider().getConfigFileName(),
            processCount=self.config.MultiProcess.processCount,
        )
        returnValue(swapAMP(controller, here))



