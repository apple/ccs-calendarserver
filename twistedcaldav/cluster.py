import os
import tempfile
import socket

from twisted.runner import procmon

from twisted.python import usage

from twistedcaldav.config import config
from twistedcaldav.tap import CaldavOptions, CaldavServiceMaker

serviceTemplate = """
    <service name="%(name)s">
	<listen ip="127.0.0.1:%(port)s" />
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
    <logging file="pydir.log"/>
</pdconfig>
"""

hostTemplate = '<host name="%(name)s" ip="127.0.0.1:%(port)s" />'

twistdTemplate = ('%(twistd)s caldav -f %(configFile)s '
                  '-o Port=%(port)s -o SSLPort=%(sslPort)s')

class TwistdSlaveProcess(object):
    prefix = "caldav"

    def __init__(self, twistdLocation, configFile, port, sslPort):
        self.twistd = twistdLocation

        self.configFile = configFile

        self.port = port
        self.sslPort = sslPort

        self.pidFile = os.path.join(
            os.path.dirname(config.PIDFile),
            '%s.pid' % (self.getName(),))

    def getName(self):
        return '%s-%s' % (self.prefix, self.port)
    
    def getSSLName(self):
        return '%s-%s' % (self.prefix, self.sslPort)

    def getCommandLine(self):
        return [self.twistd, '-n', 'caldav', 
                '-f', self.configFile,
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
                               'port': port}


class ClusterServiceMaker(CaldavServiceMaker):
    tapname = "caldavcluster"
    
    description = "A cluster of Calendar Servers"

    def makeService(self, options):
        _twistdTemplate = twistdTemplate % {
            'twistd': config.twistdLocation,
            'configFile': options['config'],
            'port': '%(port)s',
            'sslPort': '%(sslPort)s',
            }
        
        if not config.ClusterEnable:
            raise usage.UsageError(
                ("Clustering is not enabled in the config "
                 "file, use -o ClusterEnable=True to "
                 "override, or use --degrade"))

        service = procmon.ProcessMonitor()

        hosts = []
        sslHosts = []

        port = config.Port
        sslport = config.SSLPort

        for p in xrange(0, config.Cluster['processes']):
            port += 1
            sslport += 1

            process = TwistdSlaveProcess(config.twistdLocation,
                                         options['config'],
                                         port, sslport)

            service.addProcess(process.getName(),
                               process.getCommandLine(),
                               uid=options.parent['uid'],
                               gid=options.parent['gid'])
            
            if not config.SSLOnly:
                hosts.append(process.getHostLine())

            if config.SSLEnable:
                sslHosts.append(process.getHostLine(ssl=True))

        services = []

        services.append(serviceTemplate % {
                'name': 'http',
                'port': config.Port,
                'scheduler': config.Cluster['scheduler'],
                'hosts': '\n'.join(hosts)
                })
                

        if config.SSLEnable:
            services.append(serviceTemplate % {
                    'name': 'https',
                    'port': config.SSLPort,
                    'scheduler': config.Cluster['scheduler'],
                    'hosts': '\n'.join(sslHosts),
                    })
                    
        pdconfig = configTemplate % {
            'services': '\n'.join(services),
            'username': config.Cluster['admin']['username'],
            'password': config.Cluster['admin']['password'],
            }
            
        fd, fname = tempfile.mkstemp(prefix='pydir')
        os.write(fd, pdconfig)
        os.close(fd)

        service.addProcess('pydir', [config.Cluster['pydirLocation'],
                                     fname])

        return service
