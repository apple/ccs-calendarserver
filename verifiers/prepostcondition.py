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
Verifier that checks the response for a pre/post-condition <DAV:error> result.
"""

from xml.etree.cElementTree import ElementTree
from StringIO import StringIO

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # If no status verification requested, then assume all 2xx codes are OK
        teststatus = args.get("error", [])
        statusCode = args.get("status", ["403", "409", "507"])
        ignoreextras = args.get("ignoreextras", None)

        # status code could be anything, but typically 403, 409 or 507
        if str(response.status) not in statusCode:
            return False, "        HTTP Status Code Wrong: %d" % (response.status,)

        # look for pre-condition data
        if not respdata:
            return False, "        No pre/post condition response body"

        try:
            tree = ElementTree(file=StringIO(respdata))
        except Exception, ex:
            return False, "        Could not parse XML: %s" % (ex,)

        if tree.getroot().tag != "{DAV:}error":
            return False, "        Missing <DAV:error> element in response"

        # Make a set of expected pre/post condition elements
        expected = set(teststatus)
        got = set()
        for child in tree.getroot().getchildren():
            if child.tag != "{http://twistedmatrix.com/xml_namespace/dav/}error-description":
                got.add(child.tag)

        missing = expected.difference(got)
        extras = got.difference(expected)

        err_txt = ""
        if len(missing):
            err_txt += "        Items not returned in error: element %s" % str(missing)
        if len(extras) and not ignoreextras:
            if len(err_txt):
                err_txt += "\n"
            err_txt += "        Unexpected items returned in error element: %s" % str(extras)
        if len(missing) or len(extras) and not ignoreextras:
            return False, err_txt

        return True, ""
