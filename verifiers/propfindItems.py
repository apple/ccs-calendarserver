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
Verifier that checks a propfind response to make sure that the specified properties
are returned with appropriate status codes.
"""

from xml.etree.cElementTree import ElementTree, tostring
from StringIO import StringIO

class Verifier(object):
    """
    Arguments for verifier:

    ignore: list of hrefs to ignore
    only: list of specific hrefs to test, others ignored
    count: match the number of href elements
    root-element: Qname for the root element of the response
    status: test the overall response status code (default: 207)
    okprops: list of properties with propstat status of 200 to test
    badprops: list of properties with propstat status of 4xx to test
    """

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable

        # If no status verification requested, then assume all 2xx codes are OK
        ignores = args.get("ignore", [])
        only = args.get("only", [])

        # Check how many responses are returned
        counts = args.get("count", [])
        if len(counts) == 1:
            count = int(eval(counts[0]))
        else:
            count = None

        # Check how many responses are returned
        roots = args.get("root-element", [])
        if len(roots) == 1:
            root = roots[0]
        else:
            root = "{DAV:}multistatus"

        # Check how many responses are returned
        status = args.get("status", [])
        if len(status) == 1:
            status = int(status[0])
        else:
            status = 207

        def normalizeXML(value):

            if value[0] == '<':
                try:
                    tree = ElementTree(file=StringIO(value))
                except Exception:
                    return False, "           Could not parse XML value: %s\n" % (value,)
                value = tostring(tree.getroot())
            return value

        # Get property arguments and split on $ delimited for name, value tuples
        okprops = args.get("okprops", [])
        ok_props_match = []
        okprops_nomatch = {}
        for i in range(len(okprops)):
            p = okprops[i]
            if (p.find("$") != -1):
                if  p.find("$") != len(p) - 1:
                    ok_props_match.append((p.split("$")[0], normalizeXML(p.split("$")[1])))
                else:
                    ok_props_match.append((p.split("$")[0], None))
            elif (p.find("!") != -1):
                if  p.find("!") != len(p) - 1:
                    okprops_nomatch[p.split("!")[0]] = normalizeXML(p.split("!")[1])
                else:
                    okprops_nomatch[p.split("!")[0]] = None
            else:
                ok_props_match.append((p, None))
        badprops = args.get("badprops", [])
        for i in range(len(badprops)):
            p = badprops[i]
            if p.find("$") != -1:
                badprops[i] = (p.split("$")[0], normalizeXML(p.split("$")[1]))
            else:
                badprops[i] = (p, None)

        ok_test_set = set(ok_props_match)
        bad_test_set = set(badprops)

        # Process the multistatus response, extracting all hrefs
        # and comparing with the set defined for this test. Report any
        # mismatches.

        # Must have MULTISTATUS response code
        if response.status != status:
            return False, "           HTTP Status for Request: %d\n" % (response.status,)

        # Read in XML
        try:
            tree = ElementTree(file=StringIO(respdata))
        except Exception:
            return False, "           Could not parse proper XML response\n"

        # Test root element
        if tree.getroot().tag != root:
            return False, "           Invalid root-element specified: %s\n" % (root,)

        result = True
        resulttxt = ""
        ctr = 0
        for response in tree.findall("{DAV:}response"):

            # Get href for this response
            href = response.find("{DAV:}href")
            if href is None:
                return False, "           Wrong number of DAV:href elements\n"
            href = urllib.unquote(href.text)
            if href in ignores:
                continue
            if only and href not in only:
                continue

            if count is not None:
                ctr += 1
                continue

            # Get all property status
            ok_status_props = []
            bad_status_props = []
            propstatus = response.findall("{DAV:}propstat")
            for props in propstatus:
                # Determine status for this propstat
                status = props.find("{DAV:}status")
                if status is not None:
                    statustxt = status.text
                    status = False
                    if statustxt.startswith("HTTP/1.1 ") and (len(statustxt) >= 10):
                        status = (statustxt[9] == "2")
                else:
                    status = False

                # Get properties for this propstat
                prop = props.find("{DAV:}prop")

                for child in prop.getchildren():
                    fqname = child.tag
                    if len(child):
                        # Copy sub-element data as text into one long string and strip leading/trailing space
                        value = ""
                        for p in child.getchildren():
                            temp = tostring(p)
                            temp = temp.strip()
                            value += temp
                        if status:
                            if (fqname, None,) in ok_test_set:
                                value = None
                        else:
                            if (fqname, None,) in bad_test_set:
                                value = None
                    elif child.text:
                        value = child.text
                        if status:
                            if (fqname, None,) in ok_test_set:
                                value = None
                        else:
                            if (fqname, None,) in bad_test_set:
                                value = None
                    else:
                        value = None

                    if status:
                        ok_status_props.append((fqname, value,))
                    else:
                        bad_status_props.append((fqname, value,))

            ok_result_set = set(ok_status_props)
            bad_result_set = set(bad_status_props)

            # Now do set difference
            ok_missing = ok_test_set.difference(ok_result_set)
            ok_extras = ok_result_set.difference(ok_test_set)
            bad_missing = bad_test_set.difference(bad_result_set)
            bad_extras = bad_result_set.difference(bad_test_set)

            # Now remove extras that are in the no-match set
            for name, value in [p for p in ok_extras]:
                if name in okprops_nomatch and okprops_nomatch[name] != value:
                    ok_extras.remove((name, value))

            if len(ok_missing) + len(ok_extras) + len(bad_missing) + len(bad_extras) != 0:
                if len(ok_missing) != 0:
                    l = list(ok_missing)
                    resulttxt += "        Items not returned in report (OK) for %s:" % href
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(ok_extras) != 0:
                    l = list(ok_extras)
                    resulttxt += "        Unexpected items returned in report (OK) for %s:" % href
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(bad_missing) != 0:
                    l = list(bad_missing)
                    resulttxt += "        Items not returned in report (BAD) for %s:" % href
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(bad_extras) != 0:
                    l = list(bad_extras)
                    resulttxt += "        Unexpected items returned in report (BAD) for %s:" % href
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                result = False

        if count is not None and count != ctr:
            result = False
            resulttxt = "        Expected %d response items but got %d." % (count, ctr,)

        return result, resulttxt
