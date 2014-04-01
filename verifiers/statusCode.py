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
Verifier that chec ks the response status code for a specific value.
"""

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # If no status verification requested, then assume all 2xx codes are OK
        teststatus = args.get("status", ["2xx"])

        for test in teststatus:
            if test[1:3] == "xx":
                test = int(test[0])
            else:
                test = int(test)
            if test < 100:
                result = ((response.status / 100) == test)
            else:
                result = (response.status == test)
            if result:
                return True, ""

        return False, "        HTTP Status Code Wrong: %d" % (response.status,)
