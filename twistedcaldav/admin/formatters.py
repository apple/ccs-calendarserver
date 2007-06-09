##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
# DRI: David Reid, dreid@apple.com
##

import sys

FORMATTERS = {}

def registerFormatter(formatter):
    FORMATTERS[formatter.name] = formatter

def listFormatters():
    return FORMATTERS.keys()

def getFormatter(short):
    return FORMATTERS[short]


class BaseFormatter(object):
    config = None

    def __init__(self, dest=None, options=None):
        self.dest = dest
        
        if not self.dest:
            self.dest = sys.stdout

        self.options = options

        if not options:
            self.options = {}

        self.reportTypes = []

        for attr in self.__dict__:
            if attr.startswith('report_'):
                self.reportTypes.append(attr.split('_', 1)[1])

    def write(self, data):
        self.dest.write(data)
        self.dest.flush()

    def close(self):
        self.dest.close()

    def printReport(self, report):
        reportPrinter = getattr(self, 'report_%s' % (report['type'],), None)

        if reportPrinter:
            reportPrinter(report)

        else:
            print "No report printer found for report type %r" % (report,)
            self.report_default(report)
    
    def report_default(self, report):
        import pprint

        preport = pprint.pformat(report)

        self.write(''.join([preport, '\n']))
        self.close()


class PPrintFormatter(BaseFormatter):
    name = "pprint"

registerFormatter(PPrintFormatter)


class PlainFormatter(BaseFormatter):
    name = "plain"

    def writeLine(self, fields, spacing=None):

        if not spacing:
            spacing = self.options.get('spacing', 16)

        for f in fields:
            if isinstance(f, float):
                p = ("% " + str(spacing - 1) + ".2f") % (f,)
            elif isinstance(f, int) or isinstance(f, long):
                p = ("% " + str(spacing - 1) + "d") % (f,)
            else:
                p = str(f)
            self.write(p)
            self.write(' '*(int(spacing) - len(p)))

        self.write('\n')

    def writeTable(self, report, fields, headings):
        if self.options.has_key('fields'):
            fields = self.options.get('fields', '').split(',')

        self.writeLine((headings[f] for f in fields))

        for record in report['records']:
            self.writeLine((record[f] for f in fields))

    def writeMap(self, reportmap, fields, types, headings):
        self.writeLine((headings[f] for f in fields))
        spacing = self.options.get('spacing', 16)
        self.write(('-' * (spacing - 1) + ' ') * len(fields) + '\n')

        for key, value in reportmap.iteritems():
            values = (key,)
            values += tuple(value[f] for f in fields[1:])
            values = [types[i](value) for i, value in enumerate(values)]
            self.writeLine(values)

    def writeFrequencies(self, frequencies, max_count=None):
        
        width = len(frequencies)
        plot = [[" "] * width for ignore in range(20)]
        plot.append(["|---"] * 24)
        plot.append(["%02d  " % d for d in range(24)])
        
        if max_count is None:
            max_count = 0
            for freq in frequencies:
                max_count = max(freq, max_count)
            
        for column, freq in enumerate(frequencies):
            if freq == 0:
                continue
            scaled = (20 * freq) / max_count
            for row in range(20):
                if row <= scaled:
                    plot[19 - row][column] = "*"
        
        self.write("\n".join(["".join(p) for p in plot]))
        self.write("\n")
        
        return max_count

    def writeReport(self, report, name, fields, headings):
        if self.options.has_key('fields'):
            fields = self.options.get('fields', '').split(',')
        
        if name:
            self.write('%s:\n' % (name,))

        for f in fields:
            self.write('  %s: %s\n' % (headings[f], report['data'][f]))

    def report_principals(self, report):
        fields = ('principalName', 'calendarCount', 'eventCount', 'todoCount',
                  'quotaRoot', 'quotaUsed', 'quotaAvail')

        headings = {
            'principalName': 'Name',
            'calendarCount': '# Calendars',
            'eventCount': '# Events',
            'todoCount': '# Todos',
            'quotaRoot': 'Quota',
            'quotaUsed': 'Used',
            'quotaAvail': 'Available',
            'disabled': 'Disaabled',
            'quotaFree': 'Free %',
            'calendarHome': 'Home',
            }

        self.writeTable(report, fields, headings)

    report_users = report_groups = report_resources = report_locations = report_principals

    def report_stats(self, report):
        fields = ('accountCount', 'groupCount', 'resourceCount', 'locationCount',
                  'calendarCount', 'eventCount', 
                  'todoCount', 'diskUsage')

        headings = {
            'accountCount':  '# Accounts ',
            'groupCount':    '# Groups   ',
            'resourceCount': '# Resources',
            'locationCount': '# Locations',
            'calendarCount': '# Calendars',
            'eventCount':    '# Events   ',
            'todoCount':     '# Todos    ',
            'diskUsage':     'Disk Usage ',
            }

        self.writeReport(report, 'Statistics', fields, headings)

    def report_logs(self, report):
        self.write('Log Statistics:\n\n')

        self.write('  Start Date: %s\n  End Date  : %s\n\n' % report['data']['dateRange'])

        self.write('  Bytes Out: %s (%.2f GB)\n\n' % (report['data']['bytesOut'], report['data']['bytesOut'] / (1024.0 * 1024 * 1024)))
        self.write('  # Requests:\n')

        title_spacing = self.options.get('spacing', 16) - 1

        fields = (
            'method',
            'num',
            'numOK',
            'numBAD',
            'numISE',
            'numOther',
            'minbytes',
            'avbytes',
            'maxbytes',
            'mintime',
            'avtime',
            'maxtime',
        )
        types = (
            str,
            long,
            long,
            long,
            long,
            long,
            long,
            long,
            long,
            float,
            float,
            float,
        )
        headings = {
            'method':        'Method',
            'num':           '# Requests'.rjust(title_spacing),
            'numOK':         '# OK'.rjust(title_spacing),
            'numBAD':        '# BAD'.rjust(title_spacing),
            'numISE':        '# Failed'.rjust(title_spacing),
            'numOther':      '# Other'.rjust(title_spacing),
            'minbytes':      'Min. bytes'.rjust(title_spacing),
            'avbytes':       'Av. bytes'.rjust(title_spacing),
            'maxbytes':      'Max. bytes'.rjust(title_spacing),
            'mintime':       'Min. time (ms)'.rjust(title_spacing),
            'avtime':        'Av. time (ms)'.rjust(title_spacing),
            'maxtime':       'Max. time (ms)'.rjust(title_spacing),
        }
        self.writeMap(report['data']['requestStats'], fields, types, headings)
        self.write('\n')

        self.write('  # Requests by time of day:\n')
        max_count = self.writeFrequencies(report['data']['timeOfDayStats'])
        self.write('\n')
        
        for request, freqs in report['data']['requestByTimeOfDayStats'].iteritems():
            self.write('  # %s requests by time of day:\n' % (request,))
            self.writeFrequencies(freqs)
            self.write('\n')

        self.write('  User Agents:\n')

        for ua, count in report['data']['userAgents'].iteritems():
            self.write('    %s: %s\n' % (ua, count))

registerFormatter(PlainFormatter)


import csv

class CsvFormatter(BaseFormatter):
    name = "csv"

    def writeList(self, fieldnames, l):
        dw = csv.DictWriter(self.dest,
                            **self.options)

        dw.writerow(dict(zip(fieldnames,
                             fieldnames)))

        dw.writerows(l)

    def report_principals(self, report):
        if 'fieldnames' not in self.options:
            self.options['fieldnames'] = [
                'principalName',
                'calendarHome',
                'calendarCount',
                'eventCount',
                'todoCount',
                'disabled',
                'diskUsage',
                'quotaRoot',
                'quotaUsed',
                'quotaAvail',
                'quotaFree']
            
        self.writeDict(self.options['fieldnames'],
                       report['records'])
        
    report_users = report_groups = report_resources = report_locations = report_principals

    def report_stats(self, report):
        if 'fieldnames' not in self.options:
            self.options['fieldnames'] = sorted(report['data'].keys())

        self.writeList(self.options['fieldnames'],
                       [report['data']])
                
    report_logs = report_stats

registerFormatter(CsvFormatter)

import plistlib

class PlistFormatter(BaseFormatter):
    name = "plist"

    def report_principals(self, report):
        plist = plistlib.Dict()

        plist[report['type']] = list(report['records'])

        plistlib.writePlist(plist, self.dest)

    report_users = report_groups = report_resources = report_locations = report_principals

    def report_stats(self, report):
        plist = plistlib.Dict()
        plist[report['type']] = report['data']

        plistlib.writePlist(plist, self.dest)

    report_logs = report_stats

registerFormatter(PlistFormatter)

class HTMLFormatter(BaseFormatter):
    name = "html"

    def writeLine(self, fields, spacing=None):

        if not spacing:
            spacing = self.options.get('spacing', 16)

        for f in fields:
            if isinstance(f, float):
                p = ("% " + str(spacing - 1) + ".2f") % (f,)
            elif isinstance(f, int) or isinstance(f, long):
                p = ("% " + str(spacing - 1) + "d") % (f,)
            else:
                p = str(f)
            self.write(p)
            self.write(' '*(int(spacing) - len(p)))

        self.write('\n')

    def writeTable(self, report, fields, headings):
        if self.options.has_key('fields'):
            fields = self.options.get('fields', '').split(',')

        self.write("<table>\n")

        self.write("  <tr>\n")
        for f in fields:
            self.write("    <td>%s</td>\n" % headings[f])
        self.write("  <tr>\n")

        for record in report['records']:
            self.writeTableRow((record[f] for f in fields))

        self.write("  </tr>\n")
        self.write("</table>\n")

    def writeTableRow(self, fields):

        self.write("  <tr>\n")

        for f in fields:
            align = ""
            if isinstance(f, float):
                p = ("%.2f") % (f,)
                align = " align='right'"
            elif isinstance(f, int) or isinstance(f, long):
                p = ("%d") % (f,)
                align = " align='right'"
            else:
                p = str(f)
            self.write("    <td%s>%s</td>\n" % (align, p,))

        self.write("  </tr>\n")

    def writeMap(self, reportmap, fields, types, headings):

        self.write("<table border='1'>\n")

        self.write("  <tr>\n")
        for f in fields:
            self.write("    <td>%s</td>\n" % headings[f])
        self.write("  <tr>\n")

        for key, value in reportmap.iteritems():
            values = (key,)
            values += tuple(value[f] for f in fields[1:])
            values = [types[i](value) for i, value in enumerate(values)]
            self.writeTableRow(values)

        self.write("  </tr>\n")
        self.write("</table>\n")

    def writeFrequencies(self, frequencies, max_count = None):
        
        if max_count is None:
            max_count = 0
            for freq in frequencies:
                max_count = max(freq, max_count)
            
        self.write("<table>\n")

        for row in range(20):
            self.write("  <tr>\n")
            for freq in frequencies:
                scaled = (20 * freq) / max_count
                if 19 - row <= scaled:
                    self.write("    <td><font size='1'>*</font></td>\n")
                else:
                    self.write("    <td><font size='1'>&nbsp;</font></td>\n")
            self.write("  </tr>\n")

        self.write("  <tr>\n")
        for i in range(len(frequencies) / 4):
            self.write("    <td align='center'><font size='1'>|</font></td>\n")
            self.write("    <td align='center'><font size='1'>-</font></td>\n")
            self.write("    <td align='center'><font size='1'>-</font></td>\n")
            self.write("    <td align='center'><font size='1'>-</font></td>\n")
        self.write("  </tr>\n")
        self.write("  <tr>\n")
        for i in range(len(frequencies) / 4):
            self.write("    <td colspan='4'><font size='1'>%s</font></td>\n" % (i,))
        self.write("  </tr>\n")
        self.write("</table>\n")
        
        return max_count

    def writeReport(self, report, name, fields, headings):
        if self.options.has_key('fields'):
            fields = self.options.get('fields', '').split(',')
        
        if name:
            self.write('<h3>%s:</h3>\n' % (name,))

        for f in fields:
            self.write('&nbsp;&nbsp;%s: %s<br>\n' % (headings[f], report['data'][f]))

    def report_principals(self, report):
        fields = ('principalName', 'calendarCount', 'eventCount', 'todoCount',
                  'quotaRoot', 'quotaUsed', 'quotaAvail')

        headings = {
            'principalName': 'Name',
            'calendarCount': '# Calendars',
            'eventCount': '# Events',
            'todoCount': '# Todos',
            'quotaRoot': 'Quota',
            'quotaUsed': 'Used',
            'quotaAvail': 'Available',
            'disabled': 'Disaabled',
            'quotaFree': 'Free %',
            'calendarHome': 'Home',
            }

        self.writeTable(report, fields, headings)

    report_users = report_groups = report_resources = report_locations = report_principals

    def report_stats(self, report):
        fields = ('accountCount', 'groupCount', 'resourceCount', 'locationCount',
                  'calendarCount', 'eventCount', 
                  'todoCount', 'diskUsage')

        headings = {
            'accountCount':  '# Accounts ',
            'groupCount':    '# Groups   ',
            'resourceCount': '# Resources',
            'locationCount': '# Locations',
            'calendarCount': '# Calendars',
            'eventCount':    '# Events   ',
            'todoCount':     '# Todos    ',
            'diskUsage':     'Disk Usage ',
            }

        self.writeReport(report, 'Statistics', fields, headings)

    def report_logs(self, report):
        
        self.write('<html>\n<body>\n')

        self.write('<h2>Log Statistics:</h2><br>\n<br>\n')

        self.write("<table>\n")
        self.write('<tr><td>Start Date:</td><td>%s</td></tr>\n' % report['data']['dateRange'][0])
        self.write('<tr><td>End Date:</td><td>%s</td></tr>\n' % report['data']['dateRange'][1])
        self.write('<tr><td>&nbsp;</td><td>&nbsp;</td></tr>\n')
        self.write('<tr><td>Bytes Out:</td><td>%s (%.2f GB)</td></tr>\n' % (report['data']['bytesOut'], report['data']['bytesOut'] / (1024.0 * 1024 * 1024)))
        self.write("</table>\n")

        self.write('<h3># Requests:</h3>\n')

        title_spacing = self.options.get('spacing', 16) - 1

        fields = (
            'method',
            'num',
            'numOK',
            'numBAD',
            'numISE',
            'numOther',
            'minbytes',
            'avbytes',
            'maxbytes',
            'mintime',
            'avtime',
            'maxtime',
        )
        types = (
            str,
            long,
            long,
            long,
            long,
            long,
            long,
            long,
            long,
            float,
            float,
            float,
        )
        headings = {
            'method':        'Method',
            'num':           '# Requests'.rjust(title_spacing),
            'numOK':         '# OK'.rjust(title_spacing),
            'numBAD':        '# BAD'.rjust(title_spacing),
            'numISE':        '# Failed'.rjust(title_spacing),
            'numOther':      '# Other'.rjust(title_spacing),
            'minbytes':      'Min. bytes'.rjust(title_spacing),
            'avbytes':       'Av. bytes'.rjust(title_spacing),
            'maxbytes':      'Max. bytes'.rjust(title_spacing),
            'mintime':       'Min. time (ms)'.rjust(title_spacing),
            'avtime':        'Av. time (ms)'.rjust(title_spacing),
            'maxtime':       'Max. time (ms)'.rjust(title_spacing),
        }
        self.writeMap(report['data']['requestStats'], fields, types, headings)
        self.write('<br>\n')

        self.write('<h3># Requests by time of day:</h3>\n')
        max_count = self.writeFrequencies(report['data']['timeOfDayStats'])
        self.write('<br>\n')

        
        for request, freqs in report['data']['requestByTimeOfDayStats'].iteritems():
            self.write('<h3># %s requests by time of day:</h3>\n' % (request,))
            self.writeFrequencies(freqs)
            self.write('<br>\n')

        self.write('<h3>User Agents:</h3>\n')

        self.write("<table border='1'>")
        self.write('  <tr><td>User Agent</td><td># Requests</td></tr>\n')
        for ua, count in report['data']['userAgents'].iteritems():
            self.write('  <tr><td>%s:</td><td align=\'right\'>%s</td></tr>\n' % (ua, count))
        self.write('</table>\n')
        
        self.write('</body>\n</html>\n')

registerFormatter(HTMLFormatter)
