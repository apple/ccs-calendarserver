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

from twisted.runner import procmon

from twistedcaldav.config import config

serviceTemplate = """
    <service name="%(name)s">
	<listen ip="%(bindAddress)s:%(port)s" />
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

hostTemplate = '<host name="%(name)s" ip="%(bindAddress)s:%(port)s" />'


class TwistdSlaveProcess(object):
    prefix = "caldav"

    def __init__(self, twistdLocation, configFile, interfaces, port, sslPort):
        self.twistd = twistdLocation

        self.configFile = configFile

        self.port = port
        self.sslPort = sslPort

        self.pidFile = os.path.join(
            os.path.dirname(config.PIDFile),
            '%s.pid' % (self.getName(),))

        self.interfaces = interfaces

    def getName(self):
        return '%s-%s' % (self.prefix, self.port)
    
    def getSSLName(self):
        return '%s-%s' % (self.prefix, self.sslPort)

    def getCommandLine(self):
        return [
            sys.executable,
            self.twistd, '-n', 'caldav', 
            '-f', self.configFile,
            '-o', 'ServerType=singleprocess',
            '-o', 'BindAddress=%s' % (','.join(self.interfaces),),
            '-o', 'Port=%s' % (self.port,),
            '-o', 'SSLPort=%s' % (self.sslPort,),
            '-o', 'PIDFile=%s' % (self.pidFile,)]
    
    def getHostLine(self, ssl=None):
        name = self.getName()
        port = self.port

        if ssl:
            name = self.getSSLName()
            port = self.sslPort

        return hostTemplate % {'name': name,
                               'port': port,
                               'bindAddress': '127.0.0.1'}

def makeService_multiprocess(self, options):
    service = procmon.ProcessMonitor()
    
    parentEnv = {'PYTHONPATH': os.environ.get('PYTHONPATH', ''),}

    hosts = []
    sslHosts = []

    port = config.Port
    sslport = config.SSLPort

    bindAddress = ['127.0.0.1']

    if not config.MultiProcess['LoadBalancer']['Enabled']:
        bindAddress = config.BindAddress

    for p in xrange(0, config.MultiProcess['NumProcesses']):
        port += 1
        sslport += 1

        process = TwistdSlaveProcess(config.twistdLocation,
                                     options['config'],
                                     bindAddress,
                                     port, sslport)

        service.addProcess(process.getName(),
                           process.getCommandLine(),
                           uid=options.parent['uid'],
                           gid=options.parent['gid'],
                           env=parentEnv)
        
        if not config.SSLOnly:
            hosts.append(process.getHostLine())

        if config.SSLEnable:
            sslHosts.append(process.getHostLine(ssl=True))

    if config.MultiProcess['LoadBalancer']['Enabled']: 
        services = []

        if not config.BindAddress:
            config.BindAddress = ['']

        for bindAddress in config.BindAddress:
            if not config.SSLOnly:
                services.append(serviceTemplate % {
                        'name': 'http',
                        'bindAddress': bindAddress,
                        'port': config.Port,
                        'scheduler': 
                        config.MultiProcess['LoadBalancer']['Scheduler'],
                        'hosts': '\n'.join(hosts)
                        })
            
            if config.SSLEnable:
                services.append(serviceTemplate % {
                        'name': 'https',
                        'bindAddress': bindAddress,
                        'port': config.SSLPort,
                        'scheduler': 
                        config.MultiProcess['LoadBalancer']['Scheduler'],
                        'hosts': '\n'.join(sslHosts),
                        })

        pdconfig = configTemplate % {
            'services': '\n'.join(services),
            }
                
        fd, fname = tempfile.mkstemp(prefix='pydir')
        os.write(fd, pdconfig)
        os.close(fd)
        
        service.addProcess('pydir', [sys.executable,
                                     config.pydirLocation,
                                     fname])
    
    return service

def makeService_pydir(self, options):
    service = procmon.ProcessMonitor()

    service.addProcess('pydir', [sys.executable,
                                 config.pydirLocation,
                                 config.pydirConfig])

    return service
