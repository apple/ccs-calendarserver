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
import socket
import time
import signal

from twisted.runner import procmon
from twisted.application import internet, service
from twisted.internet import reactor, process
from twisted.internet.threads import deferToThread
from twisted.python.reflect import namedClass

from twistedcaldav.accesslog import AMPLoggingFactory, RotatingFileAccessLoggingObserver
from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.util import getNCPU
from twistedcaldav.log import Logger
from twistedcaldav.directory.appleopendirectory import OpenDirectoryService

log = Logger()

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

    def __init__(self, twistd, tapname, configFile, id,
                 interfaces, port, sslPort,
                 inheritFDs=None, inheritSSLFDs=None):

        self.twistd = twistd

        self.tapname = tapname

        self.configFile = configFile

        self.id = id

        self.ports = port
        self.sslPorts = sslPort

        self.inheritFDs = inheritFDs
        self.inheritSSLFDs = inheritSSLFDs

        self.interfaces = interfaces

    def getName(self):
        if self.ports is not None:
            return '%s-%s' % (self.prefix, self.ports[0])
        elif self.sslPorts is not None:
            return '%s-%s' % (self.prefix, self.sslPorts[0])
        elif self.inheritFDs or self.inheritSSLFDs:
            return '%s-%s' % (self.prefix, self.id)

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

        if config.Profiling['Enabled']:
            args.append('--profile=%s/%s.pstats' % (
                config.Profiling['BaseDirectory'],
                self.getName()))
            args.extend(('--savestats', '--nothotshot'))

        args.extend(
            ['--reactor=%s' % (config.Twisted['reactor'],),
             '-n', self.tapname,
             '-f', self.configFile,
             '-o', 'ProcessType=Slave',
             '-o', 'BindAddresses=%s' % (','.join(self.interfaces),),
             '-o', 'PIDFile=None',
             '-o', 'ErrorLogFile=None',
             '-o', 'LogID=%s' % (self.id,),
             '-o', 'InspectionPort=%s' % (config.BaseInspectionPort + self.id,),
             '-o', 'MultiProcess/ProcessCount=%d' % (
                    config.MultiProcess['ProcessCount'],)])

        if config.Memcached["ServerEnabled"]:
            args.extend(
                ['-o', 'Memcached/ClientEnabled=True'])

        if self.ports:
            args.extend([
                    '-o',
                    'BindHTTPPorts=%s' % (','.join(map(str, self.ports)),)])

        if self.sslPorts:
            args.extend([
                    '-o',
                    'BindSSLPorts=%s' % (','.join(map(str, self.sslPorts)),)])

        if self.inheritFDs:
            args.extend([
                    '-o',
                    'InheritFDs=%s' % (','.join(map(str, self.inheritFDs)),)])

        if self.inheritSSLFDs:
            args.extend([
                    '-o',
                    'InheritSSLFDs=%s' % (','.join(map(str, self.inheritSSLFDs)),)])

        return args

    def getHostLine(self, ssl=False):
        name = self.getName()
        port = None

        if self.ports is not None:
            port = self.ports

        if ssl and self.sslPorts is not None:
            port = self.sslPorts

        if self.inheritFDs or self.inheritSSLFDs:
            port = [self.id]

        if port is None:
            raise ConfigurationError(
                "Can not add a host without a port")

        return hostTemplate % {'name': name,
                               'port': port[0],
                               'bindAddress': '127.0.0.1'}


class DelayedStartupProcessMonitor(procmon.ProcessMonitor):

    def startService(self):
        service.Service.startService(self)
        self.active = 1
        delay = 0
        delay_interval = config.MultiProcess['StaggeredStartup']['Interval'] if config.MultiProcess['StaggeredStartup']['Enabled'] else 0 
        for name in self.processes.keys():
            reactor.callLater(delay if name.startswith("caldav") else 0, self.startProcess, name)
            if name.startswith("caldav"):
                delay += delay_interval
        self.consistency = reactor.callLater(self.consistencyDelay,
                                             self._checkConsistency)

    def signalAll(self, signal, startswithname=None, seconds=0):
        """
        Send a signal to all child processes.

        @param signal: the signal to send
        @type signal: C{int}
        @param startswithname: is set only signal those processes whose name starts with this string
        @type signal: C{str}
        """
        delay = 0
        for name in self.processes.keys():
            if startswithname is None or name.startswith(startswithname):
                reactor.callLater(delay, self.signalProcess, signal, name)
                delay += seconds

    def signalProcess(self, signal, name):
        """
        Send a signal to each monitored process
        
        @param signal: the signal to send
        @type signal: C{int}
        @param startswithname: is set only signal those processes whose name starts with this string
        @type signal: C{str}
        """
        if not self.protocols.has_key(name):
            return
        proc = self.protocols[name].transport
        try:
            proc.signalProcess(signal)
        except process.ProcessExitedAlready:
            pass

    def startProcess(self, name):
        if self.protocols.has_key(name):
            return
        p = self.protocols[name] = procmon.LoggingProtocol()
        p.service = self
        p.name = name
        args, uid, gid, env = self.processes[name]
        self.timeStarted[name] = time.time()

        childFDs = { 0 : "w", 1 : "r", 2 : "r" }

        # Examine args for -o InheritFDs= and -o InheritSSLFDs=
        # Add any file descriptors listed in those args to the childFDs
        # dictionary so those don't get closed across the spawn.
        for i in xrange(len(args)-1):
            if args[i] == "-o" and args[i+1].startswith("Inherit"):
                for fd in map(int, args[i+1].split("=")[1].split(",")):
                    childFDs[fd] = fd

        reactor.spawnProcess(p, args[0], args, uid=uid, gid=gid, env=env,
            childFDs=childFDs)

def makeService_Combined(self, options):


    # Refresh directory information on behalf of the child processes
    directoryClass = namedClass(config.DirectoryService["type"])
    directory = directoryClass(dosetup=True, doreload=False, **config.DirectoryService["params"])
    directory.refresh(master=True)

    # Register USR1 handler
    def sigusr1_handler(num, frame):
        log.warn("SIGUSR1 recieved in master, triggering directory refresh")
        deferToThread(directory.refresh, loop=False, master=True)
        return

    signal.signal(signal.SIGUSR1, sigusr1_handler)

    s = service.MultiService()

    monitor = DelayedStartupProcessMonitor()
    monitor.setServiceParent(s)

    directory.processMonitor = s.processMonitor = monitor

    parentEnv = {
        'PATH': os.environ.get('PATH', ''),
        'PYTHONPATH': os.environ.get('PYTHONPATH', ''),
    }

    hosts = []
    sslHosts = []

    port = [config.HTTPPort,]
    sslPort = [config.SSLPort,]

    bindAddress = ['127.0.0.1']

    inheritFDs = []
    inheritSSLFDs = []

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

    # If we only have one process, disable the software load balancer and
    # listen directly on the interfaces.

    if config.MultiProcess['ProcessCount'] == 1:
        config.MultiProcess['LoadBalancer']['Enabled'] = False
        bindAddress = config.BindAddresses

    elif config.EnableConnectionInheriting:
        # Open the socket(s) to be inherited by the slaves

        config.MultiProcess['LoadBalancer']['Enabled'] = False

        if not config.BindAddresses:
            config.BindAddresses = [""]

        s._inheritedSockets = [] # keep a reference to these so they don't close

        for bindAddress in config.BindAddresses:
            if config.BindHTTPPorts:
                if config.HTTPPort == 0:
                    raise UsageError(
                        "HTTPPort required if BindHTTPPorts is not empty"
                    )
            elif config.HTTPPort != 0:
                config.BindHTTPPorts = [config.HTTPPort]

            if config.BindSSLPorts:
                if config.SSLPort == 0:
                    raise UsageError(
                        "SSLPort required if BindSSLPorts is not empty"
                    )
            elif config.SSLPort != 0:
                config.BindSSLPorts = [config.SSLPort]

            def _openSocket(addr, port):
                log.info("Opening socket for inheritance at %s:%d" % (addr, port))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(0)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((addr, port))
                sock.listen(config.ListenBacklog)
                s._inheritedSockets.append(sock)
                return sock

            for portNum in config.BindHTTPPorts:
                sock = _openSocket(bindAddress, int(portNum))
                inheritFDs.append(sock.fileno())

            for portNum in config.BindSSLPorts:
                sock = _openSocket(bindAddress, int(portNum))
                inheritSSLFDs.append(sock.fileno())

    if not config.MultiProcess['LoadBalancer']['Enabled']:
        bindAddress = config.BindAddresses

    for p in xrange(0, config.MultiProcess['ProcessCount']):
        if config.MultiProcess['ProcessCount'] > 1:
            if port is not None:
                port = [port[0] + 1]

            if sslPort is not None:
                sslPort = [sslPort[0] + 1]

        if inheritFDs:
            port = None

        if inheritSSLFDs:
            sslPort = None

        process = TwistdSlaveProcess(config.Twisted['twistd'],
                                     self.tapname,
                                     options['config'],
                                     p,
                                     bindAddress,
                                     port, sslPort,
                                     inheritFDs=inheritFDs,
                                     inheritSSLFDs=inheritSSLFDs
                                     )

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
    if config.Memcached["ServerEnabled"]:
        log.msg("Adding memcached service")

        memcachedArgv = [
                config.Memcached["memcached"],
                '-p', str(config.Memcached["Port"]),
                '-l', config.Memcached["BindAddress"]]

        if config.Memcached["MaxMemory"] is not 0:
            memcachedArgv.extend([
                    '-m', str(config.Memcached["MaxMemory"])])

        memcachedArgv.extend(config.Memcached["Options"])

        monitor.addProcess('memcached', memcachedArgv, env=parentEnv)

    if (config.Notifications["Enabled"] and
        config.Notifications["InternalNotificationHost"] == "localhost"):
        log.msg("Adding notification service")

        notificationsArgv = [
            config.Twisted['twistd'],
            '-n', 'caldav_notifier',
            '-f', options['config'],
        ]
        monitor.addProcess('notifications', notificationsArgv, env=parentEnv)


    logger = AMPLoggingFactory(
        RotatingFileAccessLoggingObserver(config.AccessLogFile))

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
