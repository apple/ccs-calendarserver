##
# Copyright (c) 2011-2015 Apple Inc. All rights reserved.
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
##
import json
import collections
import os
import sys
from datetime import datetime

from urlparse import urlparse, urlunparse

from contrib.performance.stats import mean, median, stddev, mad

class TerminalColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    LIGHTBLUE = '\033[36m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class SummarizingMixin(object):

    def printHeader(self, output, fields):
        """
        Print a header for the summarization data which will be reported.

        @param fields: A C{list} of two-tuples.  Each tuple describes one
            column in the summary.  The first element gives a label to appear
            at the top of the column.  The second element gives the width of
            the column.
        """
        format = []
        labels = []
        for (label, width) in fields:
            format.append('%%%ds' % (width,))
            labels.append(label)
        header = ' '.join(format) % tuple(labels)
        output.write("%s\n" % header)
        output.write("%s\n" % ("-" * len(header),))


    def _summarizeData(self, operation, data):
        failed = 0
        thresholds = [0] * len(self._thresholds)
        durations = []
        for (success, duration) in data:
            if not success:
                failed += 1
            for ctr, item in enumerate(self._thresholds):
                threshold, _ignore_fail_at = item
                if duration > threshold:
                    thresholds[ctr] += 1
            durations.append(duration)

        # Determine PASS/FAIL
        failure = False
        count = len(data)

        if failed * 100.0 / count > self._fail_cut_off:
            failure = True

        for ctr, item in enumerate(self._thresholds):
            _ignore_threshold, fail_at = item
            fail_at = fail_at.get(operation, fail_at["default"])
            if thresholds[ctr] * 100.0 / count > fail_at:
                failure = True

        return (operation, count, failed,) + \
            tuple(thresholds) + \
            (mean(durations), median(durations), stddev(durations), "FAIL" if failure else "")


    def _printRow(self, output, formats, values):
        format = ' '.join(formats)
        output.write("%s\n" % format % values)


    def printData(self, output, formats, perOperationTimes):
        """
        Print one or more rows of data with the given formatting.

        @param formats: A C{list} of C{str} giving formats into which each
            data field will be interpolated.

        @param perOperationTimes: A C{list} of all of the data to summarize.
            Each element is a two-tuple of whether the operation succeeded
            (C{True} if so, C{False} if not) and how long the operation took.
        """
        for method, data in perOperationTimes:
            self._printRow(output, formats, self._summarizeData(method, data))


class MessageLogger(object):
    def observe(self, event):
        if event.get("type") == "log":
            import random
            identifier = random.random()
            print(TerminalColors.WARNING + str(identifier) + '/' + event.get('val') + ':' + event.get('text') + TerminalColors.ENDC)

    def report(self, output):
        pass


    def failures(self):
        return []


class EverythingLogger(object):
    def observe(self, event):
        # if event.get("type") == "response":
        #     from pprint import pprint
        #     pprint(event)
        pass

    def report(self, output):
        pass


    def failures(self):
        return []


class RequestLogger(object):
    format = u"%(user)s request %(code)s%(success)s[%(duration)5.2f s] %(method)8s %(url)s"
    success = u"\N{CHECK MARK}"
    failure = u"\N{BALLOT X}"

    def observe(self, event):
        if event.get("type") == "response":
            formatArgs = dict(
                user=event['user'],
                method=event['method'],
                url=urlunparse(('', '') + urlparse(event['url'])[2:]),
                code=event['code'],
                duration=event['duration'],
            )

            if event['success']:
                formatArgs['success'] = self.success
                start = TerminalColors.OKGREEN
            else:
                formatArgs['success'] = self.failure
                start = TerminalColors.FAIL
            print(start + (self.format % formatArgs).encode('utf-8') + "from Logger w/ id: " + str(id(self)) + TerminalColors.ENDC)


    def report(self, output):
        pass


    def failures(self):
        return []



class OperationLogger(SummarizingMixin):
    """
    Profiles will initiate operations which may span multiple requests.  Start
    and stop log messages are emitted for these operations and logged by this
    logger.
    """
    formats = {
        u"start" : u"%(user)s - - - - - - - - - - - %(label)8s BEGIN %(lag)s",
        u"end"   : u"%(user)s - - - - - - - - - - - %(label)8s END [%(duration)5.2f s]",
        u"failed": u"%(user)s x x x x x x x x x x x %(label)8s FAILED %(reason)s",
    }

    lagFormat = u'{lag %5.2f ms}'

    # the response time thresholds to display together with failing % count threshold
    _thresholds_default = {
        "operations": {
            "limits": [0.1, 0.5, 1.0, 3.0, 5.0, 10.0, 30.0],
            "thresholds": {
                "default": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
            }
        }
    }
    _lag_cut_off = 1.0      # Maximum allowed median scheduling latency, seconds
    _fail_cut_off = 1.0     # % of total count at which failed requests will cause a failure

    _fields_init = [
        ('operation', -25, '%-25s'),
        ('count', 8, '%8s'),
        ('failed', 8, '%8s'),
    ]

    _fields_extend = [
        ('mean', 8, '%8.4f'),
        ('median', 8, '%8.4f'),
        ('stddev', 8, '%8.4f'),
        ('avglag (ms)', 12, '%12.4f'),
        ('STATUS', 8, '%8s'),
    ]

    def __init__(self, outfile=None, **params):
        self._perOperationTimes = {}
        self._perOperationLags = {}
        if outfile is None:
            outfile = sys.stdout
        self._outfile = outfile

        # Load parameters from config
        if "thresholdsPath" in params:
            jsondata = json.load(open(params["thresholdsPath"]))
        elif "thresholds" in params:
            jsondata = params["thresholds"]
        else:
            jsondata = self._thresholds_default
        self._thresholds = [[limit, {}] for limit in jsondata["operations"]["limits"]]
        for ctr, item in enumerate(self._thresholds):
            for k, v in jsondata["operations"]["thresholds"].items():
                item[1][k] = v[ctr]

        self._fields = self._fields_init[:]
        for threshold, _ignore_fail_at in self._thresholds:
            self._fields.append(('>%g sec' % (threshold,), 10, '%10s'))
        self._fields.extend(self._fields_extend)

        if "lagCutoff" in params:
            self._lag_cut_off = params["lagCutoff"]

        if "failCutoff" in params:
            self._fail_cut_off = params["failCutoff"]


    def observe(self, event):
        if event.get("type") == "operation":
            event = event.copy()
            lag = event.get('lag')
            if lag is None:
                event['lag'] = ''
            else:
                event['lag'] = self.lagFormat % (lag * 1000.0,)

            self._outfile.write(
                TerminalColors.LIGHTBLUE +
                (self.formats[event[u'phase']] % event).encode('utf-8') + TerminalColors.ENDC + '\n')

            if event[u'phase'] == u'end':
                dataset = self._perOperationTimes.setdefault(event[u'label'], [])
                dataset.append((event[u'success'], event[u'duration']))
            elif lag is not None:
                dataset = self._perOperationLags.setdefault(event[u'label'], [])
                dataset.append(lag)


    def _summarizeData(self, operation, data):
        avglag = mean(self._perOperationLags.get(operation, [0.0])) * 1000.0
        data = SummarizingMixin._summarizeData(self, operation, data)
        return data[:-1] + (avglag,) + data[-1:]


    def report(self, output):
        output.write("\n")
        self.printHeader(output, [
            (label, width)
            for (label, width, _ignore_fmt) in self._fields
        ])
        self.printData(
            output,
            [fmt for (label, width, fmt) in self._fields],
            sorted(self._perOperationTimes.items())
        )

    _LATENCY_REASON = "Median %(operation)s scheduling lag greater than %(cutoff)sms"
    _FAILED_REASON = "Greater than %(cutoff).0f%% %(operation)s failed"

    def failures(self):
        reasons = []

        for operation, lags in self._perOperationLags.iteritems():
            if median(lags) > self._lag_cut_off:
                reasons.append(self._LATENCY_REASON % dict(
                    operation=operation.upper(), cutoff=self._lag_cut_off * 1000))

        for operation, times in self._perOperationTimes.iteritems():
            failures = len([success for (success, _ignore_duration) in times if not success])
            if failures * 100.0 / len(times) > self._fail_cut_off:
                reasons.append(self._FAILED_REASON % dict(
                    operation=operation.upper(), cutoff=self._fail_cut_off))

        return reasons



class StatisticsBase(object):
    def observe(self, event):
        if event.get('type') == 'response':
            self.eventReceived(event)
        elif event.get('type') == 'client-failure':
            self.clientFailure(event)
        elif event.get('type') == 'sim-failure':
            self.simFailure(event)


    def report(self, output):
        pass


    def failures(self):
        return []



class SimpleStatistics(StatisticsBase):
    def __init__(self):
        self._times = []
        self._failures = collections.defaultdict(int)
        self._simFailures = collections.defaultdict(int)


    def eventReceived(self, event):
        self._times.append(event['duration'])
        if len(self._times) == 200:
            print('mean:', mean(self._times))
            print('median:', median(self._times))
            print('stddev:', stddev(self._times))
            print('mad:', mad(self._times))
            del self._times[:100]


    def clientFailure(self, event):
        self._failures[event] += 1


    def simFailure(self, event):
        self._simFailures[event] += 1



class ReportStatistics(StatisticsBase, SummarizingMixin):
    """

    @ivar _users: A C{set} containing all user UIDs which have been observed in
        events.  When generating the final report, the size of this set is
        reported as the number of users in the simulation.

    """

    # the response time thresholds to display together with failing % count threshold
    _thresholds_default = {
        "requests": {
            "limits": [0.1, 0.5, 1.0, 3.0, 5.0, 10.0, 30.0],
            "thresholds": {
                "default": [100.0, 100.0, 100.0, 5.0, 1.0, 0.5, 0.0],
            }
        }
    }
    _fail_cut_off = 1.0     # % of total count at which failed requests will cause a failure

    _fields_init = [
        ('request', -25, '%-25s'),
        ('count', 8, '%8s'),
        ('failed', 8, '%8s'),
    ]

    _fields_extend = [
        ('mean', 8, '%8.4f'),
        ('median', 8, '%8.4f'),
        ('stddev', 8, '%8.4f'),
        ('QoS', 8, '%8.4f'),
        ('STATUS', 8, '%8s'),
    ]

    def __init__(self, **params):
        self._perMethodTimes = {}
        self._users = set()
        self._clients = set()
        self._failed_clients = []
        self._failed_sim = collections.defaultdict(int)
        self._startTime = datetime.now()
        self._expired_data = None

        # Load parameters from config
        if "thresholdsPath" in params:
            jsondata = json.load(open(params["thresholdsPath"]))
        elif "thresholds" in params:
            jsondata = params["thresholds"]
        else:
            jsondata = self._thresholds_default
        self._thresholds = [[limit, {}] for limit in jsondata["requests"]["limits"]]
        for ctr, item in enumerate(self._thresholds):
            for k, v in jsondata["requests"]["thresholds"].items():
                item[1][k] = v[ctr]

        self._fields = self._fields_init[:]
        for threshold, _ignore_fail_at in self._thresholds:
            self._fields.append(('>%g sec' % (threshold,), 10, '%10s'))
        self._fields.extend(self._fields_extend)

        if "benchmarksPath" in params:
            self.benchmarks = json.load(open(params["benchmarksPath"]))
        else:
            self.benchmarks = {}

        if "failCutoff" in params:
            self._fail_cut_off = params["failCutoff"]


    def observe(self, event):
        if event.get('type') == 'sim-expired':
            self.simExpired(event)
        else:
            super(ReportStatistics, self).observe(event)


    def countUsers(self):
        return len(self._users)


    def countClients(self):
        return len(self._clients)


    def countClientFailures(self):
        return len(self._failed_clients)


    def countSimFailures(self):
        return len(self._failed_sim)


    def eventReceived(self, event):
        dataset = self._perMethodTimes.setdefault(event['method'], [])
        dataset.append((event['success'], event['duration']))
        self._users.add(event['user'])
        self._clients.add(event['client_id'])


    def clientFailure(self, event):
        self._failed_clients.append(event['reason'])


    def simFailure(self, event):
        self._failed_sim[event['reason']] += 1


    def simExpired(self, event):
        self._expired_data = event['reason']


    def printMiscellaneous(self, output, items):
        maxColumnWidth = str(len(max(items.iterkeys(), key=len)))
        fmt = "%" + maxColumnWidth + "s : %-s\n"
        for k in sorted(items.iterkeys()):
            output.write(fmt % (k.title(), items[k],))


    def qos(self):
        """
        Determine a "quality of service" value that can be used for comparisons between runs. This value
        is based on the percentage deviation of means of each request from a set of "benchmarks" for each
        type of request.
        """

        # Get means for each type of method
        means = {}
        for method, results in self._perMethodTimes.items():
            means[method] = mean([duration for success, duration in results if success])

        # Determine percentage differences with weighting
        differences = []
        for method, value in means.items():
            result = self.qos_value(method, value)
            if result is not None:
                differences.append(result)

        return ("%-8.4f" % mean(differences)) if differences else "None"


    def qos_value(self, method, value):
        benchmark = self.benchmarks.get(method)
        if benchmark is None:
            return None
        test_mean, weight = (benchmark["mean"], benchmark["weight"],)
        return ((value / test_mean) - 1.0) * weight + 1.0


    def _summarizeData(self, operation, data):
        data = SummarizingMixin._summarizeData(self, operation, data)
        value = self.qos_value(operation, data[-4])
        if value is None:
            value = 0.0
        return data[:-1] + (value,) + data[-1:]


    def report(self, output):
        output.write("\n")
        output.write("** REPORT **\n")
        output.write("\n")
        runtime = datetime.now() - self._startTime
        cpu = os.times()
        cpuUser = cpu[0] + cpu[2]
        cpuSys = cpu[1] + cpu[3]
        cpuTotal = cpuUser + cpuSys
        runHours, remainder = divmod(runtime.seconds, 3600)
        runMinutes, runSeconds = divmod(remainder, 60)
        cpuHours, remainder = divmod(cpuTotal, 3600)
        cpuMinutes, cpuSeconds = divmod(remainder, 60)
        items = {
            'Users': self.countUsers(),
            'Clients': self.countClients(),
            'Start time': self._startTime.strftime('%m/%d %H:%M:%S'),
            'Run time': "%02d:%02d:%02d" % (runHours, runMinutes, runSeconds),
            'CPU Time': "user %-5.2f sys %-5.2f total %02d:%02d:%02d" % (cpuUser, cpuSys, cpuHours, cpuMinutes, cpuSeconds,),
            'QoS': self.qos(),
        }
        if self.countClientFailures() > 0:
            items['Failed clients'] = self.countClientFailures()
            for ctr, reason in enumerate(self._failed_clients, 1):
                items['Failure #%d' % (ctr,)] = reason
        if self.countSimFailures() > 0:
            for reason, count in self._failed_sim.items():
                items['Failed operation'] = "%s : %d times" % (reason, count,)
        output.write("* Client\n")
        self.printMiscellaneous(output, items)
        output.write("\n")

        if self._expired_data is not None:
            items = {
                "Req/sec" : "%.1f" % (self._expired_data[0],),
                "Response": "%.1f (ms)" % (self._expired_data[1],),
                "Slots": "%.2f" % (self._expired_data[2],),
                "CPU": "%.1f%%" % (self._expired_data[3],),
            }
            output.write("* Server (Last 5 minutes)\n")
            self.printMiscellaneous(output, items)
            output.write("\n")
        output.write("* Details\n")

        self.printHeader(output, [
            (label, width)
            for (label, width, _ignore_fmt)
            in self._fields
        ])
        self.printData(
            output,
            [fmt for (label, width, fmt) in self._fields],
            sorted(self._perMethodTimes.items())
        )

    _FAILED_REASON = "Greater than %(cutoff)g%% %(method)s failed"

    _REASON_1 = "Greater than %(cutoff)g%% %(method)s exceeded "
    _REASON_2 = "%g second response time"

    def failures(self):
        # TODO
        reasons = []

        for (method, times) in self._perMethodTimes.iteritems():
            failures = 0
            overDurations = [0] * len(self._thresholds)

            for success, duration in times:
                if not success:
                    failures += 1
                for ctr, item in enumerate(self._thresholds):
                    threshold, _ignore_fail_at = item
                    if duration > threshold:
                        overDurations[ctr] += 1

            checks = [
                (failures, self._fail_cut_off, self._FAILED_REASON),
            ]

            for ctr, item in enumerate(self._thresholds):
                threshold, fail_at = item
                fail_at = fail_at.get(method, fail_at["default"])
                checks.append(
                    (overDurations[ctr], fail_at, self._REASON_1 + self._REASON_2 % (threshold,))
                )

            for count, cutoff, reason in checks:
                if count * 100.0 / len(times) > cutoff:
                    reasons.append(reason % dict(method=method, cutoff=cutoff))

        if self.countClientFailures() != 0:
            reasons.append("Client failures: %d" % (self.countClientFailures(),))
        if self.countSimFailures() != 0:
            reasons.append("Overall failures: %d" % (self.countSimFailures(),))
        return reasons
