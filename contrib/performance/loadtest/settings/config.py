# Generally, the defaults are good enough for us.

config = Config(dict(
    server=server,
    webadminPort=8080,
    serverStatsPort=8100,
    serializationPath='/tmp/sim',
    arrival=arrival,
    observers=[_requestLogger, _operationLogger, _statisticsReporter],
    records=accounts
)

config_dist = dict(
    server=server,
    webadminPort=8080,
    serverStatsPort=8100,
    serializationPath='/tmp/sim',
    arrival=arrival,
    observers=[_requestLogger, _operationLogger, _statisticsReporter],
    records=accounts,
    workers=["./bin/python contrib/performance/loadtest/ampsim.py"] * 6,
)

# if __name__ == "__main__":
#     print("Verifying Python games")
