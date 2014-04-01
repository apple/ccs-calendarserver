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
Verifier that checks a multistatus response to make sure that the specified hrefs
are returned with appropriate status codes.
"""

from xml.etree.cElementTree import ElementTree
from StringIO import StringIO

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args):

        # If no hrefs requested, then assume none should come back
        okhrefs = args.get("okhrefs", [])
        nohrefs = args.get("nohrefs", [])
        badhrefs = args.get("badhrefs", [])
        statushrefs = {}
        for arg in args.keys():
            try:
                code = int(arg)
                statushrefs.setdefault(code, []).append(args[arg])
            except ValueError:
                pass
        count = args.get("count", [])
        totalcount = args.get("totalcount", [])
        responsecount = args.get("responsecount", [])
        prefix = args.get("prefix", [])
        ignoremissing = args.get("ignoremissing", None)
        if len(prefix):
            prefix = prefix[0] if prefix[0] != "-" else ""
        else:
            prefix = uri
        okhrefs = [(prefix + i).rstrip("/") for i in okhrefs]
        nohrefs = [(prefix + i).rstrip("/") for i in nohrefs]
        badhrefs = [(prefix + i).rstrip("/") for i in badhrefs]
        for k, v in args.items():
            v = [prefix + i for i in v]
            args[k] = v
        count = [int(eval(i)) for i in count]
        totalcount = [int(eval(i)) for i in totalcount]
        responsecount = [int(eval(i)) for i in responsecount]

        if "okhrefs" in args or "nohrefs" in args or "badhrefs" in args:
            doOKBad = True
        elif statushrefs:
            doOKBad = False
        else:
            doOKBad = None

        # Process the multistatus response, extracting all hrefs
        # and comparing with the set defined for this test. Report any
        # mismatches.

        # Must have MULTISTATUS response code
        if response.status != 207:
            return False, "           HTTP Status for Request: %d\n" % (response.status,)

        try:
            tree = ElementTree(file=StringIO(respdata))
        except Exception:
            return False, "           HTTP response is not valid XML: %s\n" % (respdata,)

        ok_status_hrefs = []
        bad_status_hrefs = []
        status_code_hrefs = {}
        for response in tree.findall("{DAV:}response"):

            # Get href for this response
            href = response.findall("{DAV:}href")
            if href is None or len(href) != 1:
                return False, "        Incorrect/missing DAV:Href element in response"
            href = urllib.unquote(href[0].text).rstrip("/")

            # Verify status
            status = response.findall("{DAV:}status")
            if len(status) == 1:
                statustxt = status[0].text
                status = False
                if statustxt.startswith("HTTP/1.1 ") and (len(statustxt) >= 10):
                    status = (statustxt[9] == "2")
                    try:
                        code = int(statustxt[9:12])
                    except ValueError:
                        code = 0
            else:
                propstatus = response.findall("{DAV:}propstat")
                if len(propstatus) > 0:
                    statustxt = "OK"
                    status = True
                else:
                    status = False
                code = 0

            if status:
                ok_status_hrefs.append(href)
            else:
                bad_status_hrefs.append(href)
            status_code_hrefs.setdefault(code, set()).add(href)
        ok_result_set = set(ok_status_hrefs)
        ok_test_set = set(okhrefs)
        no_test_set = set(nohrefs)
        bad_result_set = set(bad_status_hrefs)
        bad_test_set = set(badhrefs)

        result = True
        resulttxt = ""

        # Check for count
        if len(count) == 1:
            if len(ok_result_set) != count[0] + 1:
                result = False
                resulttxt += "        %d items returned, but %d items expected" % (len(ok_result_set) - 1, count[0],)
            return result, resulttxt

        # Check for total count
        if len(totalcount) == 1:
            if len(ok_result_set) != totalcount[0]:
                result = False
                resulttxt += "        %d items returned, but %d items expected" % (len(ok_result_set), totalcount[0],)
            return result, resulttxt

        # Check for response count
        if len(responsecount) == 1:
            responses = len(ok_result_set) + len(bad_result_set)
            if responses != responsecount[0]:
                result = False
                resulttxt += "        %d responses returned, but %d responses expected" % (responses, responsecount[0],)
            return result, resulttxt

        if doOKBad:
            # Now do set difference
            ok_missing = ok_test_set.difference(ok_result_set)
            ok_extras = ok_result_set.difference(ok_test_set) if ignoremissing is None else set()
            no_extras = ok_result_set.intersection(no_test_set)
            bad_missing = bad_test_set.difference(bad_result_set)
            bad_extras = bad_result_set.difference(bad_test_set) if ignoremissing is None else set()

            if len(ok_missing) + len(ok_extras) + len(no_extras) + len(bad_missing) + len(bad_extras) != 0:
                if len(ok_missing) != 0:
                    l = list(ok_missing)
                    resulttxt += "        %d Items not returned in report (OK):" % (len(ok_missing),)
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(ok_extras) != 0:
                    l = list(ok_extras)
                    resulttxt += "        %d Unexpected items returned in report (OK):" % (len(ok_extras),)
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(no_extras) != 0:
                    l = list(no_extras)
                    resulttxt += "        %d Unwanted items returned in report (OK):" % (len(no_extras),)
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(bad_missing) != 0:
                    l = list(bad_missing)
                    resulttxt += "        %d Items not returned in report (BAD):" % (len(bad_missing),)
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(bad_extras) != 0:
                    l = list(bad_extras)
                    resulttxt += "        %d Unexpected items returned in report (BAD):" % (len(bad_extras),)
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                result = False

        if not doOKBad:
            l = list(set(statushrefs.keys()) - set(status_code_hrefs.keys()))
            if l:
                resulttxt += "        %d Status Codes not returned in report:" % (len(l),)
                for i in l:
                    resulttxt += " " + str(i)
                resulttxt += "\n"
                result = False

            l = list(set(status_code_hrefs.keys()) - set(statushrefs.keys()))
            if l:
                resulttxt += "        %d Unexpected Status Codes returned in report:" % (len(l),)
                for i in l:
                    resulttxt += " " + str(i)
                resulttxt += "\n"
                result = False

            for code in set(statushrefs.keys()) & set(status_code_hrefs.keys()):
                l = list(set(*statushrefs[code]) - status_code_hrefs[code])
                if l:
                    resulttxt += "        %d Items not returned in report for %d:" % (len(l), code,)
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                    result = False

                l = list(status_code_hrefs[code] - set(*statushrefs[code]))
                if l:
                    resulttxt += "        %d Unexpected items returned in report for %d:" % (len(l), code,)
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                    result = False

        return result, resulttxt
