from contrib.performance.loadtest.settings.defaults import arrival, requestLogger, operationLogger, statisticsReporter, accounts

from contrib.performance.loadtest.logger import EverythingLogger, MessageLogger

config = {
    "server": 'https://127.0.0.1:8443',
    "webadminPort": 8080,
    "serverStatsPort": {'server': 'localhost', 'Port': 8100},
    "serializationPath": '/tmp/sim',
    "arrival": arrival,
    "observers": [requestLogger, operationLogger, statisticsReporter, EverythingLogger(), MessageLogger()],
    "records": accounts
}
