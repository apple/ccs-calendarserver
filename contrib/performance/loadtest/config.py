from importlib import import_module

from twisted.python.log import msg
from contrib.performance.loadtest.logger import ReportStatistics, RequestLogger, OperationLogger
from contrib.performance.loadtest.records import recordsFromCSVFile
from contrib.performance.loadtest.population import ClientFactory, PopulationParameters

class Config(object):
    def __init__(self):
        pass

    def populateFrom(self, serverConfig, clientConfig, usePlist=False):
        # If there is a list of workers, then this process is *not* a worker
        isManager = serverConfig.get('workers') is not None

        if usePlist:
            # If the supplied files are plists, we need to convert the named objects into real Python objects.
            # The ensuing hacky code is why I recommend we remove support for plist-based configuration
            workers = config['workers']
            if not isManager:
                # Client / place where the simulator actually runs configuration
                workerID = config.get("workerID", 0)
                workerCount = config.get("workerCount", 1)
                configTemplate = None
                server = config.get('server', 'http://127.0.0.1:8008')
                serializationPath = None

                serializationPath = config['serializationPath']

                if 'arrival' in config:
                    arrival = Arrival(
                        namedAny(config['arrival']['factory']),
                        config['arrival']['params'])
                else:
                    arrival = Arrival(
                        SmoothRampUp, dict(groups=10, groupSize=1, interval=3))

                parameters = PopulationParameters()
                if 'clients' in config:
                    for clientConfig in config['clients']:
                        parameters.addClient(
                            clientConfig["weight"],
                            ClientType(
                                clientConfig["software"],
                                clientConfig["params"],
                                clientConfig["profiles"]
                            )
                        )
                            # ClientType(
                            #     namedAny(clientConfig["software"]),
                            #     cls._convertParams(clientConfig["params"]),
                            #     [
                            #         ProfileType(
                            #             namedAny(profile["class"]),
                            #             cls._convertParams(profile["params"])
                            #         ) for profile in clientConfig["profiles"]
                            #     ]))
                if not parameters.clients:
                    parameters.addClient(1,
                                         ClientType(OS_X_10_6, {},
                                                    [Eventer, Inviter, Accepter]))
            else:
                # Manager / observer process.
                server = ''
                serializationPath = None
                arrival = None
                parameters = None
                workerID = 0
                configTemplate = config
                workerCount = 1

            # webadminPort = 
            webadminPort = None
            if 'webadmin' in config:
                if config['webadmin']['enabled']:
                    webadminPort = config['webadmin']['HTTPPort']

            serverStats = None
            if 'serverStats' in config:
                if config['serverStats']['enabled']:
                    serverStats = config['serverStats']
                    serverStats['server'] = config['server'] if 'server' in config else ''

            observers = []
            if 'observers' in config:
                for observer in config['observers']:
                    observerName = observer["type"]
                    observerParams = observer["params"]
                    observers.append(namedAny(observerName)(**observerParams))

            records = []
            if 'accounts' in config:
                loader = config['accounts']['loader']
                params = config['accounts']['params']
                records.extend(namedAny(loader)(**params))
                output.write("Loaded {0} accounts.\n".format(len(records)))

        else:
            # Python configuration - super easy! Look! It's great!
                self.webadminPort = serverConfig.get('webadminPort')
                self.serverStats = serverConfig.get('serverStatsPort')
                self.observers = serverConfig.get('observers') # Workers shouldn't need this
                self.workers = serverConfig.get('workers')

                self.server = serverConfig.get('server')
                self.serializationPath = serverConfig.get('serializationPath')
                self.arrival = serverConfig.get('arrival')
                self.records = serverConfig.get('records')
                self.workerID = serverConfig.get('workerID', 0)
                self.workerCount = serverConfig.get('workerCount', 1)
                self.parameters = self.buildParameters(clientConfig)

    def buildParameters(self, clients):
        parameters = PopulationParameters()
        for client in clients:
            parameters.addClient(
                client["weight"],
                ClientFactory(
                    client["software"],
                    client["params"],
                    client["profiles"]
                )
            )
        return parameters

    def buildSerializationPath(self):
        if self.serializationPath:
            if not isdir(serializationPath):
                try:
                    mkdir(serializationPath)
                except OSError:
                    print("Unable to create client data serialization directory: %s" % (serializationPath))
                    print("Please consult the clientDataSerialization stanza of contrib/performance/loadtest/config.plist")
                    raise

    def serializeForWorker(self, workerID, workerCount):
        if not self.workers: # If we are workers, don't try to be a manager
            return {}
        # print "Trying to serialize for worker #" + str(workerID)
        # print "My info, btw is " + str(self.__dict__)
        info = {
            'webadminPort': '',
            'serverStats': '',
            'workers': [],
            'observers': [],
            'workerID': workerID,
            'workerCount': workerCount,
            # Workers need some information to work correctly
            'server': self.server,
            'serializationPath': self.serializationPath,
            'arrival': self.arrival,
            'records': self.records,
            'parameters': self.parameters
        }
        return info

    @classmethod
    def deserializeFromWorker(cls, info):
        base = cls()
        base.__dict__.update(info)
        return base

    # Goodness, how awkward is this code? If we dropped support for plists, we could do away with it
    @classmethod
    def _convertParams(cls, params):
        """
        Find parameter values which should be more structured than plistlib is
        capable of constructing and replace them with the more structured form.

        Specifically, find keys that end with C{"Distribution"} and convert
        them into some kind of distribution object using the associated
        dictionary of keyword arguments.
        """
        for k, v in params.iteritems():
            if k.endswith('Distribution'): # Goodness how fragile
                params[k] = cls._convertDistribution(v)
        return params


    @classmethod
    def _convertDistribution(cls, value):
        """
        Construct and return a new distribution object using the type and
        params specified by C{value}.
        """
        return namedAny(value['type'])(**value['params'])