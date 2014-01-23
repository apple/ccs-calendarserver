##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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

from contrib.performance.stats import mean, median, stddev

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
