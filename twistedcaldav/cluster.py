##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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

import os
import sys
import tempfile

from twisted.python import log

from twisted.runner import procmon
from twisted.application import internet, service

from twistedcaldav import logging
from twistedcaldav.config import config, ConfigurationError

from twistedcaldav.util import getNCPU

serviceTemplate = """
    <service name="%(name)s">
        %(listeningInterfaces)s
    <group name="main" scheduler="%(scheduler)s">
        %(hosts)s
        </group>
        <enable group="main" />
    </service>
"""

configTemplate = """
<pdconfig>
    %(services)s
    <control socket="%(controlSocket)s" />
</pdconfig>
"""

listenTemplate = '<listen ip="%(bindAddress)s:%(port)s" />'

hostTemplate = '<host name="%(name)s" ip="%(bindAddress)s:%(port)s" />'


class TwistdSlaveProcess(object):
    prefix = "caldav"

    def __init__(self, twistd, tapname, configFile,
                 interfaces, port, sslPort):
        self.twistd = twistd

        self.tapname = tapname

        self.configFile = configFile

        self.ports = port
        self.sslPorts = sslPort

        self.interfaces = interfaces

    def getName(self):
        if self.ports is not None:
            return '%s-%s' % (self.prefix, self.ports[0])
        elif self.sslPorts is not None:
            return '%s-%s' % (self.prefix, self.sslPorts[0])

        raise ConfigurationError(
            "Can't create TwistdSlaveProcess without a TCP Port")

    def getCommandLine(self):
        args = [
            sys.executable,
            self.twistd]

        if config.UserName:
            args.extend(('-u', config.UserName))

        if config.GroupName:
            args.extend(('-g', config.GroupName))

        args.extend(
            ['-n', self.tapname,
             '-f', self.configFile,
             '-o', 'ProcessType=Slave',
             '-o', 'BindAddresses=%s' % (','.join(self.interfaces),),
             '-o', 'PIDFile=None',
             '-o', 'ErrorLogFile=None',
             '-o', 'MultiProcess/ProcessCount=%d' % (
                    config.MultiProcess['ProcessCount'],)])

        if self.ports:
            args.extend([
                    '-o',
                    'BindHTTPPorts=%s' % (','.join(map(str, self.ports)),)])

        if self.sslPorts:
            args.extend([
                    '-o',
                    'BindSSLPorts=%s' % (','.join(map(str, self.sslPorts)),)])




        return args

    def getHostLine(self, ssl=False):
        name = self.getName()
        port = None

        if self.ports is not None:
            port = self.ports

        if ssl and self.sslPorts is not None:
            port = self.sslPorts

        if port is None:
            raise ConfigurationError(
                "Can not add a host without a port")

        return hostTemplate % {'name': name,
                               'port': port[0],
                               'bindAddress': '127.0.0.1'}


def makeService_Combined(self, options):
    s = service.MultiService()
    monitor = procmon.ProcessMonitor()
    monitor.setServiceParent(s)

    parentEnv = {'PYTHONPATH': os.environ.get('PYTHONPATH', ''),}

    hosts = []
    sslHosts = []

    port = [config.HTTPPort,]
    sslPort = [config.SSLPort,]

    bindAddress = ['127.0.0.1']

    # Attempt to calculate the number of processes to use
    # 1 per processor

    if config.MultiProcess['ProcessCount'] == 0:
        try:
            config.MultiProcess['ProcessCount'] = getNCPU()
            log.msg("%d processors found, configuring %d processes." % (
                    config.MultiProcess['ProcessCount'],
                    config.MultiProcess['ProcessCount']))

        except NotImplementedError, err:
            log.msg('Could not autodetect number of CPUs:')
            log.msg(err)
            config.MultiProcess['ProcessCount'] = 1

    if config.MultiProcess['ProcessCount'] > 1:
        if config.BindHTTPPorts:
            port = [list(reversed(config.BindHTTPPorts))[0]]

        if config.BindSSLPorts:
            sslPort = [list(reversed(config.BindSSLPorts))[0]]

    elif config.MultiProcess['ProcessCount'] == 1:
        if config.BindHTTPPorts:
            port = config.BindHTTPPorts

        if config.BindSSLPorts:
            sslPort = config.BindSSLPorts

    if port[0] == 0:
        port = None

    if sslPort[0] == 0:
        sslPort = None

    # If the load balancer isn't enabled, or if we only have one process
    # We listen directly on the interfaces.

    if ((not config.MultiProcess['LoadBalancer']['Enabled']) or
        (config.MultiProcess['ProcessCount'] == 1)):
        bindAddress = config.BindAddresses

    for p in xrange(0, config.MultiProcess['ProcessCount']):
        if config.MultiProcess['ProcessCount'] > 1:
            if port is not None:
                port = [port[0] + 1]

            if sslPort is not None:
                sslPort = [sslPort[0] + 1]

        process = TwistdSlaveProcess(config.Twisted['twistd'],
                                     self.tapname,
                                     options['config'],
                                     bindAddress,
                                     port, sslPort)

        monitor.addProcess(process.getName(),
                           process.getCommandLine(),
                           env=parentEnv)

        if config.HTTPPort:
            hosts.append(process.getHostLine())

        if config.SSLPort:
            sslHosts.append(process.getHostLine(ssl=True))

    # Set up pydirector config file.

    if (config.MultiProcess['LoadBalancer']['Enabled'] and
        config.MultiProcess['ProcessCount'] > 1):
        services = []

        if not config.BindAddresses:
            config.BindAddresses = ['']

        scheduler_map = {
            "LeastConnections": "leastconns",
            "RoundRobin": "roundrobin",
            "LeastConnectionsAndRoundRobin": "leastconnsrr",
        }

        for bindAddress in config.BindAddresses:
            httpListeners = []
            sslListeners = []

            httpPorts = config.BindHTTPPorts
            if not httpPorts:
                if config.HTTPPort != 0:
                    httpPorts = (config.HTTPPort,)

            sslPorts = config.BindSSLPorts
            if not sslPorts:
                if config.SSLPort != 0:
                    sslPorts = (config.SSLPort,)

            for ports, listeners in ((httpPorts, httpListeners),
                                     (sslPorts, sslListeners)):
                for port in ports:
                    listeners.append(listenTemplate % {
                            'bindAddress': bindAddress,
                            'port': port})

            if httpPorts:
                services.append(serviceTemplate % {
                        'name': 'http',
                        'listeningInterfaces': '\n'.join(httpListeners),
                        'bindAddress': bindAddress,
                        'scheduler': scheduler_map[config.MultiProcess['LoadBalancer']['Scheduler']],
                        'hosts': '\n'.join(hosts)
                        })

            if sslPorts:
                services.append(serviceTemplate % {
                        'name': 'https',
                        'listeningInterfaces': '\n'.join(sslListeners),
                        'bindAddress': bindAddress,
                        'scheduler': scheduler_map[config.MultiProcess['LoadBalancer']['Scheduler']],
                        'hosts': '\n'.join(sslHosts),
                        })

        pdconfig = configTemplate % {
            'services': '\n'.join(services),
            'controlSocket': config.PythonDirector["ControlSocket"],
            }

        fd, fname = tempfile.mkstemp(prefix='pydir')
        os.write(fd, pdconfig)
        os.close(fd)

        log.msg("Adding pydirector service with configuration: %s" % (fname,))

        monitor.addProcess('pydir', [sys.executable,
                                     config.PythonDirector['pydir'],
                                     fname],
                           env=parentEnv)

    logger = logging.AMPLoggingFactory(
        logging.RotatingFileAccessLoggingObserver(config.AccessLogFile))

    loggingService = internet.UNIXServer(config.ControlSocket, logger)

    loggingService.setServiceParent(s)

    return s

def makeService_Master(self, options):
    service = procmon.ProcessMonitor()

    parentEnv = {'PYTHONPATH': os.environ.get('PYTHONPATH', ''),}

    log.msg("Adding pydirector service with configuration: %s" % (config.PythonDirector['ConfigFile'],))

    service.addProcess('pydir', [sys.executable,
                                 config.PythonDirector['pydir'],
                                 config.PythonDirector['ConfigFile']],
                       env=parentEnv)

    return service
