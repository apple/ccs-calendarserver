##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
Verifier that checks the response body for an exact match to data in a file.
"""

from pycalendar.icalendar.calendar import Calendar
from xml.etree.cElementTree import ElementTree
import json
import StringIO

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # Get arguments
        parent = args.get("parent", [])
        exists = args.get("exists", [])
        notexists = args.get("notexists", [])

        # status code must be 200, 207
        if response.status not in (200, 207):
            return False, "        HTTP Status Code Wrong: %d" % (response.status,)

        # look for response data
        if not respdata:
            return False, "        No response body"

        # Read in XML
        try:
            tree = ElementTree(file=StringIO.StringIO(respdata))
        except Exception, e:
            return False, "        Response data is not xml data: %s" % (e,)

        def _splitPathTests(path):
            if '[' in path:
                return path.split('[', 1)
            else:
                return path, None

        if parent:
            nodes = self.nodeForPath(tree.getroot(), parent[0])
            if len(nodes) == 0:
                return False, "        Response data is missing parent node: %s" % (parent[0],)
            elif len(nodes) > 1:
                return False, "        Response data has too many parent nodes: %s" % (parent[0],)
            root = nodes[0]
        else:
            root = tree.getroot()

        result = True
        resulttxt = ""
        for path in exists:

            matched, txt = self.matchPath(root, path)
            result &= matched
            resulttxt += txt

        for path in notexists:
            matched, _ignore_txt = self.matchPath(root, path)
            if matched:
                resulttxt += "        Items returned in XML for %s\n" % (path,)
                result = False

        return result, resulttxt


    def nodeForPath(self, root, path):
        if '[' in path:
            actual_path, tests = path.split('[', 1)
        else:
            actual_path = path
            tests = None

        # Handle absolute root element
        if actual_path[0] == '/':
            actual_path = actual_path[1:]
        if '/' in actual_path:
            root_path, child_path = actual_path.split('/', 1)
            if root.tag != root_path:
                return None
            nodes = root.findall(child_path)
        else:
            root_path = actual_path
            child_path = None
            nodes = (root,)

        if len(nodes) == 0:
            return None

        results = []

        if tests:
            tests = [item[:-1] for item in tests.split('[')]
            for test in tests:
                for node in nodes:
                    if test[0] == '@':
                        if '=' in test:
                            attr, value = test[1:].split('=')
                            value = value[1:-1]
                        else:
                            attr = test[1:]
                            value = None
                        if attr in node.keys() and (value is None or node.get(attr) == value):
                            results.append(node)
                    elif test[0] == '=':
                        if node.text == test[1:]:
                            results.append(node)
                    elif test[0] == '!':
                        if node.text != test[1:]:
                            results.append(node)
                    elif test[0] == '*':
                        if node.text is not None and node.text.find(test[1:]) != -1:
                            results.append(node)
                    elif test[0] == '$':
                        if node.text is not None and node.text.find(test[1:]) == -1:
                            results.append(node)
                    elif test[0] == '+':
                        if node.text is not None and node.text.startswith(test[1:]):
                            results.append(node)
                    elif test[0] == '^':
                        if "=" in test:
                            element, value = test[1:].split("=", 1)
                        else:
                            element = test[1:]
                            value = None
                        for child in node.getchildren():
                            if child.tag == element and (value is None or child.text == value):
                                results.append(node)
                    elif test[0] == '|':
                        if node.text is None and len(node.getchildren()) == 0:
                            results.append(node)
        else:
            results = nodes

        return results


    def matchPath(self, root, path):

        result = True
        resulttxt = ""

        if '[' in path:
            actual_path, tests = path.split('[', 1)
        else:
            actual_path = path
            tests = None

        # Handle absolute root element
        if actual_path[0] == '/':
            actual_path = actual_path[1:]
        if '/' in actual_path:
            root_path, child_path = actual_path.split('/', 1)
            if root.tag != root_path:
                resulttxt += "        Items not returned in XML for %s\n" % (path,)
            nodes = root.findall(child_path)
        else:
            nodes = (root,)

        if len(nodes) == 0:
            resulttxt += "        Items not returned in XML for %s\n" % (path,)
            result = False
            return result, resulttxt

        if tests:
            tests = [item[:-1] for item in tests.split('[')]
            for test in tests:
                for node in nodes:

                    def _doTest():
                        result = None
                        if test[0] == '@':
                            if '=' in test:
                                attr, value = test[1:].split('=')
                                value = value[1:-1]
                            else:
                                attr = test[1:]
                                value = None
                            if attr not in node.keys():
                                result = "        Missing attribute returned in XML for %s\n" % (path,)
                            if value is not None and node.get(attr) != value:
                                result = "        Incorrect attribute value returned in XML for %s\n" % (path,)
                        elif test[0] == '=':
                            if node.text != test[1:]:
                                result = "        Incorrect value returned in XML for %s\n" % (path,)
                        elif test[0] == '!':
                            if node.text == test[1:]:
                                result = "        Incorrect value returned in XML for %s\n" % (path,)
                        elif test[0] == '*':
                            if node.text is None or node.text.find(test[1:]) == -1:
                                result = "        Incorrect value returned in XML for %s\n" % (path,)
                        elif test[0] == '$':
                            if node.text is None or node.text.find(test[1:]) != -1:
                                result = "        Incorrect value returned in XML for %s\n" % (path,)
                        elif test[0] == '+':
                            if node.text is None or not node.text.startswith(test[1:]):
                                result = "        Incorrect value returned in XML for %s\n" % (path,)
                        elif test[0] == '^':
                            if "=" in test:
                                element, value = test[1:].split("=", 1)
                            else:
                                element = test[1:]
                                value = None
                            for child in node.getchildren():
                                if child.tag == element and (value is None or child.text == value):
                                    break
                            else:
                                result = "        Missing child returned in XML for %s\n" % (path,)

                        # Try to parse as iCalendar
                        elif test == 'icalendar':
                            try:
                                Calendar.parseText(node.text)
                            except:
                                result = "        Incorrect value returned in iCalendar for %s\n" % (path,)

                        # Try to parse as JSON
                        elif test == 'json':
                            try:
                                json.loads(node.text)
                            except:
                                result = "        Incorrect value returned in XML for %s\n" % (path,)
                        return result

                    testresult = _doTest()
                    if testresult is None:
                        break
                if testresult is not None:
                    resulttxt += testresult
                    result = False
                    break

        return result, resulttxt
