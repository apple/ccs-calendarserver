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
Verifier that matches JSON content using extended JSON pointer syntax.

JSON pointer syntax is extended as follows:

1) A ~$xxx at the end will result in a test for the string "xxx" in the matching JSON object.
2) A "." as a path segment will match any JSON object member or array item.
"""

import json
from src.jsonPointer import JSONMatcher, JSONPointerMatchError

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # Get arguments
        statusCodes = args.get("status", ["200", ])
        exists = args.get("exists", [])
        notexists = args.get("notexists", [])

        # status code must match
        if str(response.status) not in statusCodes:
            return False, "        HTTP Status Code Wrong: %d" % (response.status,)

        # look for response data
        if not respdata:
            return False, "        No response body"

        # Must be application/json
        ct = response.msg.getheaders("content-type")
        if ct[0].split(";")[0] != "application/json":
            return False, "        Wrong Content-Type: %s" % (ct,)

        # Read in json
        try:
            j = json.loads(respdata)
        except Exception, e:
            return False, "        Response data is not JSON data: %s" % (e,)

        def _splitPathTests(path):
            if '[' in path:
                return path.split('[', 1)
            else:
                return path, None

        result = True
        resulttxt = ""
        for jpath in exists:
            if jpath.find("~$") != -1:
                path, value = jpath.split("~$")
            else:
                path, value = jpath, None
            try:
                jp = JSONMatcher(path)
            except Exception:
                result = False
                resulttxt += "        Invalid JSON pointer for %s\n" % (path,)
            else:
                try:
                    jobjs = jp.match(j)
                    if not jobjs:
                        result = False
                        resulttxt += "        Items not returned in JSON for %s\n" % (path,)
                    if value and value not in map(str, jobjs):
                        result = False
                        resulttxt += "        Item values not returned in JSON for %s\n" % (jpath,)
                except JSONPointerMatchError:
                    result = False
                    resulttxt += "        Items not returned in JSON for %s\n" % (path,)

        for jpath in notexists:
            try:
                jp = JSONMatcher(jpath)
            except Exception:
                result = False
                resulttxt += "        Invalid JSON pointer for %s\n" % (jpath,)
            else:
                try:
                    jp.match(j)
                except JSONPointerMatchError:
                    pass
                else:
                    resulttxt += "        Items returned in JSON for %s\n" % (jpath,)
                    result = False

        return result, resulttxt
