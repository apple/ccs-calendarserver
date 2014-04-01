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

"""
Verifier that checks the response body for an exact match to data in a file.
"""

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # Get arguments
        contains = args.get("contains", [])
        notcontains = args.get("notcontains", [])
        unwrap = args.get("unwrap")
        empty = args.get("empty")

        # Test empty
        if empty:
            if respdata:
                return False, "        Response data has a body"
            else:
                return True, ""

        # look for response data
        if not respdata:
            return False, "        No response body"

        # Un wrap if required
        if unwrap is not None:
            newrespdata = respdata.replace("\r\n ", "")
        else:
            newrespdata = respdata
        # Check each contains and not-contains (AND operation)
        for item in contains:
            item = manager.server_info.subs(item)
            if newrespdata.find(item.replace("\n", "\r\n")) == -1 and newrespdata.find(item) == -1:
                return False, "        Response data does not contain \"%s\"" % (item,)
        for item in notcontains:
            item = manager.server_info.subs(item)
            if newrespdata.find(item.replace("\n", "\r\n")) != -1 or newrespdata.find(item) != -1:
                return False, "        Response data incorrectly contains \"%s\"" % (item,)

        return True, ""
