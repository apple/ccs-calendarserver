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
    <admin listen="localhost:7001">
	<user name="%(username)s" password="%(password)s" access="full"/>
    </admin>
</pdconfig>
"""

hostTemplate = '<host name="%(name)s" ip="%(bindAddress)s:%(port)s" />'


class TwistdSlaveProcess(object):
    prefix = "caldav"

    def __init__(self, twistdLocation, configFile, interface, port, sslPort):
        self.twistd = twistdLocation

        self.configFile = configFile

        self.port = port
        self.sslPort = sslPort

        self.pidFile = os.path.join(
            os.path.dirname(config.PIDFile),
            '%s.pid' % (self.getName(),))

        self.interface = interface

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
            '-o', 'BindAddress=%s' % (self.interface,),
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
                               'bindAddress': self.interface}

def makeService_multiprocess(self, options):
    service = procmon.ProcessMonitor()

    hosts = []
    sslHosts = []

    port = config.Port
    sslport = config.SSLPort

    bindAddress = '127.0.0.1'

    if not config.MultiProcess['PyDirector']['Enabled']:
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
                           gid=options.parent['gid'])
        
        if not config.SSLOnly:
            hosts.append(process.getHostLine())

        if config.SSLEnable:
            sslHosts.append(process.getHostLine(ssl=True))

    if config.MultiProcess['PyDirector']['Enabled']: 
        services = []

        if not config.SSLOnly:
            services.append(serviceTemplate % {
                    'name': 'http',
                    'bindAddress': config.BindAddress,
                    'port': config.Port,
                    'scheduler': 
                        config.MultiProcess['PyDirector']['Scheduler'],
                    'hosts': '\n'.join(hosts)
                    })
            
        if config.SSLEnable:
            services.append(serviceTemplate % {
                    'name': 'https',
                    'bindAddress': config.BindAddress,
                    'port': config.SSLPort,
                    'scheduler': 
                    config.MultiProcess['PyDirector']['Scheduler'],
                        'hosts': '\n'.join(sslHosts),
                    })

        pdconfig = configTemplate % {
            'services': '\n'.join(services),
            'username': 
                config.MultiProcess['PyDirector']['admin']['username'],
            'password': 
                config.MultiProcess['PyDirector']['admin']['password'],
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
