##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
import urllib

"""
Verifier that checks a propfind response for regex matches to property values.
"""

from xml.etree.cElementTree import ElementTree, tostring
from StringIO import StringIO
import re

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable

        # If no status verification requested, then assume all 2xx codes are OK
        ignores = args.get("ignore", [])
        only = args.get("only", [])

        def normalizeXML(value):

            if value[0] == '<':
                try:
                    tree = ElementTree(file=StringIO(value))
                except Exception:
                    return False, "           Could not parse XML value: %s\n" % (value,)
                value = tostring(tree.getroot())
            return value

        # Get property arguments and split on $ delimited for name, value tuples
        testprops = args.get("props", [])
        props_match = []
        for i in range(len(testprops)):
            p = testprops[i]
            if (p.find("$") != -1):
                if p.find("$") != len(p) - 1:
                    props_match.append((p.split("$")[0], normalizeXML(p.split("$")[1]), True))
                else:
                    props_match.append((p.split("$")[0], "", True))
            elif (p.find("!") != -1):
                if  p.find("!") != len(p) - 1:
                    props_match.append((p.split("!")[0], normalizeXML(p.split("!")[1]), False))
                else:
                    props_match.append((p.split("!")[0], "", False))

        # Process the multistatus response, extracting all hrefs
        # and comparing with the properties defined for this test. Report any
        # mismatches.

        # Must have MULTISTATUS response code
        if response.status != 207:
            return False, "           HTTP Status for Request: %d\n" % (response.status,)

        try:
            tree = ElementTree(file=StringIO(respdata))
        except Exception:
            return False, "           Could not parse proper XML response\n"

        result = True
        resulttxt = ""
        for response in tree.findall("{DAV:}response"):

            # Get href for this response
            href = response.findall("{DAV:}href")
            if len(href) != 1:
                return False, "           Wrong number of DAV:href elements\n"
            href = urllib.unquote(href[0].text)
            if href in ignores:
                continue
            if only and href not in only:
                continue

            # Get all property status
            ok_status_props = {}
            propstatus = response.findall("{DAV:}propstat")
            for props in propstatus:
                # Determine status for this propstat
                status = props.findall("{DAV:}status")
                if len(status) == 1:
                    statustxt = status[0].text
                    status = False
                    if statustxt.startswith("HTTP/1.1 ") and (len(statustxt) >= 10):
                        status = (statustxt[9] == "2")
                else:
                    status = False

                # Get properties for this propstat
                prop = props.findall("{DAV:}prop")
                if len(prop) != 1:
                    return False, "           Wrong number of DAV:prop elements\n"

                def _removeWhitespace(node):

                    for child in node.getchildren():
                        child.text = child.text.strip() if child.text else child.text
                        child.tail = child.tail.strip() if child.tail else child.tail
                        _removeWhitespace(child)

                for child in prop[0].getchildren():
                    fqname = child.tag
                    if len(child):
                        value = ""
                        _removeWhitespace(child)
                        for p in child.getchildren():
                            value += tostring(p)
                    elif child.text:
                        value = child.text
                    else:
                        value = None

                    if status:
                        ok_status_props[fqname] = value

            # Look at each property we want to test and see if present
            for propname, value, match in props_match:
                if propname not in ok_status_props:
                    resulttxt += "        Items not returned in report (OK) for %s: %s\n" % (href, propname,)
                    result = False
                    continue
                matched = re.match(value, ok_status_props[propname])
                if match and not matched:
                    resulttxt += "        Items not matching for %s: %s %s\n" % (href, propname, ok_status_props[propname])
                    result = False
                elif not match and matched:
                    resulttxt += "        Items incorrectly match for %s: %s %s\n" % (href, propname, ok_status_props[propname])
                    result = False

        return result, resulttxt
