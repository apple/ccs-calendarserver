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
Verifier that checks a propfind response to make sure that the specified ACL privileges
are available for the currently authenticated user.
"""

from xml.etree.cElementTree import ElementTree
from StringIO import StringIO

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable

        granted = args.get("granted", [])
        denied = args.get("denied", [])

        # Process the multistatus response, extracting all current-user-privilege-set elements
        # and check to see that each required privilege is present, or that denied ones are not.

        # Must have MULTISTATUS response code
        if response.status != 207:
            return False, "           HTTP Status for Request: %d\n" % (response.status,)

        try:
            tree = ElementTree(file=StringIO(respdata))
        except Exception:
            return False, "           HTTP response is not valid XML: %d\n" % (respdata,)

        result = True
        resulttxt = ""
        for response in tree.findall("{DAV:}response"):

            # Get href for this response
            href = response.findall("{DAV:}href")
            if len(href) != 1:
                return False, "           Wrong number of DAV:href elements\n"
            href = urllib.unquote(href[0].text)

            # Get all privileges
            granted_privs = []
            privset = response.getiterator("{DAV:}current-user-privilege-set")
            for props in privset:
                # Determine status for this propstat
                privileges = props.findall("{DAV:}privilege")
                for privilege in privileges:
                    for child in privilege.getchildren():
                        granted_privs.append(child.tag)

            granted_result_set = set(granted_privs)
            granted_test_set = set(granted)
            denied_test_set = set(denied)

            # Now do set difference
            granted_missing = granted_test_set.difference(granted_result_set)
            denied_present = granted_result_set.intersection(denied_test_set)

            if len(granted_missing) + len(denied_present) != 0:
                if len(granted_missing) != 0:
                    l = list(granted_missing)
                    resulttxt += "        Missing privileges not granted for %s:" % href
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                if len(denied_present) != 0:
                    l = list(denied_present)
                    resulttxt += "        Available privileges that should be denied for %s:" % href
                    for i in l:
                        resulttxt += " " + str(i)
                    resulttxt += "\n"
                result = False

        return result, resulttxt
