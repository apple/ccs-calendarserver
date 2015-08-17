from importlib import import_module

from contrib.performance.loadtest.logger import ReportStatistics, RequestLogger, OperationLogger
from contrib.performance.loadtest.sim import recordsFromCSVFile

DEFAULTS = {
    server = "https://127.0.0.1:8443"

    accounts = recordsFromCSVFile("contrib/performance/loadtest/accounts.csv")

    _requestLogger = RequestLogger()
    _operationLogger = OperationLogger(
        thresholdsPath="contrib/performance/loadtest/thresholds.json",
        lagCutoff=1.0,
        failCutoff=1.0
    )
    _statisticsReporter = ReportStatistics(
        thresholdsPath="contrib/performance/loadtest/thresholds.json",
        benchmarksPath="contrib/performance/loadtest/benchmarks.json",
        failCutoff=1.0
    )

    arrival = SmoothRampUp(
        groups=2,
        groupSize=1,
        interval=3,
        clientsPerUser=1
    )
}

class Config(object):


    def __init__(self, serverConfigFile, clientConfigFile):
        # These are modules
        serverConfigModule = import_module(serverConfigFile)
        clientConfigModule = import_module(clientConfigFile)

        self.clients = clientConfigModule.clientConfiguration
        self.workers = workers
        self.configTemplate = configTemplate
        self.workerID = workerID
        self.workerCount = workerCount

        self.server = serverConfig.get('server')
        self.webadminPort = serverConfig.get('webadminPort')
        self.serverStats = serverConfig.get('serverStatsPort')
        self.serializationPath = serverConfig.get('serializationPath')
        self.arrival = serverConfig.get('arrival')
        self.observers = serverConfig.get('observers')
        self.records = serverConfig.get('records')
        self.workers = serverConfig.get('workers')

        self.buildParameters()

    def buildParameters(self):
        self.parameters = PopulationParameters()
        for client in self.clients:
            self.parameters.addClient(
                client["weight"],
                ClientType(
                    client["software"],
                    client["params"],
                    client["profiles"]
                )
            )

    def buildSerializationPath(self):
        if self.serializationPath:
            if not isdir(serializationPath):
                try:
                    mkdir(serializationPath)
                except OSError:
                    print("Unable to create client data serialization directory: %s" % (serializationPath))
                    print("Please consult the clientDataSerialization stanza of contrib/performance/loadtest/config.plist")
                    raise

    def get(self, attr):
        if hasattr(self, attr):
            return getattr(self, attr)
        return DEFAULTS.get(attr, None)
