##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

from twext.who.xml import DirectoryService as XMLDirectoryService
from twext.who.index import DirectoryService as BaseDirectoryService
from twisted.python.usage import Options, UsageError
from twisted.plugin import IPlugin
from twisted.application import service
from zope.interface import implementer
from twistedcaldav.config import config
from twistedcaldav.stdconfig import DEFAULT_CONFIG, DEFAULT_CONFIG_FILE
from twisted.application.strports import service as strPortsService
from twisted.internet.protocol import Factory
from twext.python.log import Logger
from twisted.python.filepath import FilePath

from .protocol import DirectoryProxyAMPProtocol, RecordWithShortNameCommand

from twisted.internet import reactor
from twisted.internet.protocol import ClientCreator
from twisted.protocols import amp
import cPickle as pickle

log = Logger()


class DirectoryService(BaseDirectoryService):

    def _getConnection(self):
        # path = config.DirectoryProxy.SocketPath
        path = "data/Logs/state/directory-proxy.sock"
        return ClientCreator(reactor, amp.AMP).connectUNIX(path)

    def recordWithShortName(self, recordType, shortName):

        def deserialize(result):
            return pickle.loads(result['record'])

        def call(ampProto):
            return ampProto.callRemote(
                RecordWithShortNameCommand,
                recordType=recordType.description.encode("utf-8"),
                shortName=shortName.encode("utf-8")
            )

        return self._getConnection().addCallback(call).addCallback(deserialize)



class DirectoryProxyAMPFactory(Factory):
    """
    """
    protocol = DirectoryProxyAMPProtocol


    def __init__(self, directory):
        self._directory = directory

    def buildProtocol(self, addr):
        return DirectoryProxyAMPProtocol(self._directory)



class DirectoryProxyOptions(Options):
    optParameters = [[
        "config", "f", DEFAULT_CONFIG_FILE, "Path to configuration file."
    ]]


    def __init__(self, *args, **kwargs):
        super(DirectoryProxyOptions, self).__init__(*args, **kwargs)

        self.overrides = {}


    def _coerceOption(self, configDict, key, value):
        """
        Coerce the given C{val} to type of C{configDict[key]}
        """
        if key in configDict:
            if isinstance(configDict[key], bool):
                value = value == "True"

            elif isinstance(configDict[key], (int, float, long)):
                value = type(configDict[key])(value)

            elif isinstance(configDict[key], (list, tuple)):
                value = value.split(',')

            elif isinstance(configDict[key], dict):
                raise UsageError(
                    "Dict options not supported on the command line"
                )

            elif value == 'None':
                value = None

        return value


    def _setOverride(self, configDict, path, value, overrideDict):
        """
        Set the value at path in configDict
        """
        key = path[0]

        if len(path) == 1:
            overrideDict[key] = self._coerceOption(configDict, key, value)
            return

        if key in configDict:
            if not isinstance(configDict[key], dict):
                raise UsageError(
                    "Found intermediate path element that is not a dictionary"
                )

            if key not in overrideDict:
                overrideDict[key] = {}

            self._setOverride(
                configDict[key], path[1:],
                value, overrideDict[key]
            )


    def opt_option(self, option):
        """
        Set an option to override a value in the config file. True, False, int,
        and float options are supported, as well as comma seperated lists. Only
        one option may be given for each --option flag, however multiple
        --option flags may be specified.
        """

        if "=" in option:
            path, value = option.split('=')
            self._setOverride(
                DEFAULT_CONFIG,
                path.split('/'),
                value,
                self.overrides
            )
        else:
            self.opt_option('%s=True' % (option,))

    opt_o = opt_option

    def postOptions(self):
        config.load(self['config'])
        config.updateDefaults(self.overrides)
        self.parent['pidfile'] = None


@implementer(IPlugin, service.IServiceMaker)
class DirectoryProxyServiceMaker(object):

    tapname = "caldav_directoryproxy"
    description = "Directory Proxy Service"
    options = DirectoryProxyOptions

    def makeService(self, options):
        """
        Return a service
        """
        try:
            from setproctitle import setproctitle
        except ImportError:
            pass
        else:
            setproctitle("CalendarServer Directory Proxy Service")

        directory = XMLDirectoryService(FilePath("foo.xml"))

        desc = "unix:{path}:mode=660".format(
            path=config.DirectoryProxy.SocketPath
        )
        return strPortsService(desc, DirectoryProxyAMPFactory(directory))
