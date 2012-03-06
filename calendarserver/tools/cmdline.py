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
Shared main-point between utilities.
"""

import os, sys

from calendarserver.tap.caldav import CalDAVServiceMaker, CalDAVOptions
from calendarserver.tools.util import loadConfig, autoDisableMemcached
from twistedcaldav.config import ConfigurationError

# TODO: direct unit tests for this function.

def utilityMain(configFileName, serviceClass, reactor=None, serviceMaker=CalDAVServiceMaker):
    """
    Shared main-point for utilities.

    This function will:

        - Load the configuration file named by C{configFileName},
        - launch a L{CalDAVServiceMaker}'s with the C{ProcessType} of
          C{"Utility"}
        - run the reactor, with start/stop events hooked up to the service's
          C{startService}/C{stopService} methods.

    It is C{serviceClass}'s responsibility to stop the reactor when it's
    complete.

    @param configFileName: the name of the configuration file to load.
    @type configuration: C{str}

    @param serviceClass: a 1-argument callable which takes an object that
        provides L{ICalendarStore} and/or L{IAddressbookStore} and returns an
        L{IService}.

    @param reactor: if specified, the L{IReactorTime} / L{IReactorThreads} /
        L{IReactorTCP} (etc) provider to use.  If C{None}, the default reactor
        will be imported and used.
    """
    if reactor is None:
        from twisted.internet import reactor
    try:
        config = loadConfig(configFileName)

        # If we don't have permission to access the DataRoot directory, we
        # can't proceed.  If this fails it should raise OSError which we
        # catch below.
        os.listdir(config.DataRoot)

        config.ProcessType = "Utility"
        config.UtilityServiceClass = serviceClass

        autoDisableMemcached(config)

        maker = serviceMaker()
        options = CalDAVOptions
        service = maker.makeService(options)

        reactor.addSystemEventTrigger("during", "startup", service.startService)
        reactor.addSystemEventTrigger("before", "shutdown", service.stopService)

    except (ConfigurationError, OSError), e:
        sys.stderr.write("Error: %s\n" % (e,))
        return

    reactor.run()
