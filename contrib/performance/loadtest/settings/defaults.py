from contrib.performance.loadtest.logger import ReportStatistics, RequestLogger, OperationLogger
from contrib.performance.loadtest.records import recordsFromCSVFile
from contrib.performance.loadtest.population import SmoothRampUp

requestLogger = RequestLogger()
operationLogger = OperationLogger(
    thresholdsPath="contrib/performance/loadtest/thresholds.json",
    lagCutoff=1.0,
    failCutoff=1.0
)
statisticsReporter = ReportStatistics(
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

accounts = recordsFromCSVFile("contrib/performance/loadtest/accounts.csv")
