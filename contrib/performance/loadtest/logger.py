from stats import mean, median

class SummarizingMixin(object):
    def printHeader(self, fields):
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
        print ' '.join(format) % tuple(labels)


    def _summarizeData(self, operation, data):
        failed = 0
        threesec = 0
        durations = []
        for (success, duration) in data:
            if not success:
                failed += 1
            if duration > 3:
                threesec += 1
            durations.append(duration)

        return operation, len(data), failed, threesec, mean(durations), median(durations)


    def _printRow(self, formats, values):
        format = ' '.join(formats)
        print format % values


    def printData(self, formats, perOperationTimes):
        """
        Print one or more rows of data with the given formatting.

        @param formats: A C{list} of C{str} giving formats into which each
            data field will be interpolated.

        @param perOperationTimes: A C{list} of all of the data to summarize.
            Each element is a two-tuple of whether the operation succeeded
            (C{True} if so, C{False} if not) and how long the operation took.
        """
        for method, data in perOperationTimes:
            self._printRow(formats, self._summarizeData(method, data))
