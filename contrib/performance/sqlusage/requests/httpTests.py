##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
##

"""
Defines a set of HTTP requests to execute and return results.
"""

class HTTPTestBase(object):
    """
    Base class for an HTTP request that executes and results are returned for.
    """

    class SQLResults(object):
        
        def __init__(self, count, rows, timing):
            self.count = count
            self.rows = rows
            self.timing = timing
        
    def __init__(self, label, session, href, logFilePath):
        """
        @param label: label used to identify the test
        @type label: C{str}
        """
        self.label = label
        self.session = session
        self.baseHref = href
        self.logFilePath = logFilePath
        self.result = None

    def execute(self):
        """
        Execute the HTTP request and read the results.
        """
        
        self.prepare()
        self.clearLog()
        self.doRequest()
        self.collectResults()
        self.cleanup()
        return self.result

    def prepare(self):
        """
        Do some setup prior to the real request.
        """
        pass

    def clearLog(self):
        """
        Clear the server's SQL log file.
        """
        open(self.logFilePath, "w").write("")

    def doRequest(self):
        """
        Execute the actual HTTP request. Sub-classes override.
        """
        raise NotImplementedError

    def collectResults(self):
        """
        Parse the server log file to extract the details we need.
        """
        
        def extractInt(line):
            pos = line.find(": ")
            return int(line[pos+2:])

        def extractFloat(line):
            pos = line.find(": ")
            return float(line[pos+2:])

        data = open(self.logFilePath).read()
        lines = data.splitlines()
        count = extractInt(lines[4])
        rows = extractInt(lines[5])
        timing = extractFloat(lines[6])
        self.result = HTTPTestBase.SQLResults(count, rows, timing)

    def cleanup(self):
        """
        Do some cleanup after the real request.
        """
        pass
