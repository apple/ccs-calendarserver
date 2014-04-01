##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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

from verifiers.calendarDataMatch import Verifier as CalVerifier

"""
Verifier that checks the response body for a semantic match to data in a file.
"""

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args):

        # Just hand this off to the calendarDataMatch verifier which knows all about
        # proper calendar normalization rules.
        verifier = CalVerifier()
        return verifier.verify(manager, uri, response, respdata, args, is_json=True)
