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
#
# DRI: David Reid, dreid@apple.com
##

import os
import sys
import tempfile

from twisted.python import log

from twisted.runner import procmon
from twisted.scripts.mktap import getid
from twistedcaldav.config import config

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
</pdconfig>
"""

listenTemplate = '<listen ip="%(bindAddress)s:%(port)s" />'

hostTemplate = '<host name="%(name)s" ip="%(bindAddress)s:%(port)s" />'


class TwistdSlaveProcess(object):
    prefix = "caldav"

    def __init__(self, twistd, tapname, configFile, interfaces, port, sslPort):
        self.twistd = twistd

        self.tapname = tapname

        self.configFile = configFile

        self.port = port
        self.sslPort = sslPort

        self.interfaces = interfaces

    def getName(self):
        return '%s-%s' % (self.prefix, self.port)

    def getSSLName(self):
        return '%s-%s' % (self.prefix, self.sslPort)

    def getCommandLine(self):
        return [
            sys.executable,
            self.twistd,
            '-u', config.UserName,
            '-g', config.GroupName,
            '-n', self.tapname,
            '-f', self.configFile,
            '-o', 'ProcessType=Slave',
            '-o', 'BindAddresses=%s' % (','.join(self.interfaces),),
            '-o', 'BindHTTPPorts=%s' % (self.port,),
            '-o', 'BindSSLPorts=%s' % (self.sslPort,),
            '-o', 'PIDFile=None',
            '-o', 'ErrorLogFile=None']

    def getHostLine(self, ssl=None):
        name = self.getName()
        port = self.port

        if ssl:
            name = self.getSSLName()
            port = self.sslPort

        return hostTemplate % {'name': name,
                               'port': port,
                               'bindAddress': '127.0.0.1'}

def makeService_Combined(self, options):
    service = procmon.ProcessMonitor()

    parentEnv = {'PYTHONPATH': os.environ.get('PYTHONPATH', ''),}

    hosts = []
    sslHosts = []

    port = config.HTTPPort
    sslport = config.SSLPort

    bindAddress = ['127.0.0.1']

    if not config.MultiProcess['LoadBalancer']['Enabled']:
        bindAddress = config.BindAddresses

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

    for p in xrange(0, config.MultiProcess['ProcessCount']):
        if int(config.MultiProcess['ProcessCount']) > 1:
            port += 1
            sslport += 1

        process = TwistdSlaveProcess(config.Twisted['twistd'],
                                     self.tapname,
                                     options['config'],
                                     bindAddress,
                                     port, sslport)

        service.addProcess(process.getName(),
                           process.getCommandLine(),
                           env=parentEnv)

        if config.HTTPPort:
            hosts.append(process.getHostLine())

        if config.SSLPort:
            sslHosts.append(process.getHostLine(ssl=True))

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
                httpPorts = (config.HTTPPort,)

            sslPorts = config.BindSSLPorts
            if not sslPorts:
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
            }

        fd, fname = tempfile.mkstemp(prefix='pydir')
        os.write(fd, pdconfig)
        os.close(fd)

        log.msg("Adding pydirector service with configuration: %s" % (fname,))

        service.addProcess('pydir', [sys.executable,
                                     config.PythonDirector['pydir'],
                                     fname],
                           env=parentEnv)

    return service

def makeService_Master(self, options):
    service = procmon.ProcessMonitor()

    parentEnv = {'PYTHONPATH': os.environ.get('PYTHONPATH', ''),}

    log.msg("Adding pydirector service with configuration: %s" % (config.PythonDirector['ConfigFile'],))

    service.addProcess('pydir', [sys.executable,
                                 config.PythonDirector['pydir'],
                                 config.PythonDirector['ConfigFile']],
                       env=parentEnv)

    return service
