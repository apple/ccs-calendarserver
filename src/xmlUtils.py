##
# Copyright (c) 2007-2013 Apple Inc. All rights reserved.
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
XML processing utilities.
"""

import src.xmlDefs

def readStringElementList(node, ename):

    results = []
    for child in node.getchildren():
        if child.tag == ename:
            results.append(child.text.decode("utf-8"))
    return results



def getYesNoAttributeValue(node, attr):
    return node.get(attr, src.xmlDefs.ATTR_VALUE_NO) == src.xmlDefs.ATTR_VALUE_YES



def getDefaultAttributeValue(node, attr, default):
    result = node.getAttribute(attr)
    if result:
        return result
    else:
        return default



def readOneStringElement(node, ename):

    for child in node.getchildren():
        if child.tag == ename:
            return child.text.decode("utf-8")
    return ""



def nodeForPath(root, path):
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
    else:
        results = nodes

    return results



def xmlPathSplit(xpath):

    pos = xpath.find("}")
    if pos == -1:
        return xpath, ""
    pos = xpath[pos:].find("/") + pos
    if pos == -1:
        return xpath, ""
    else:
        return xpath[:pos], xpath[pos + 1:]
