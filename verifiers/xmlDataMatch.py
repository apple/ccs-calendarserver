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

from difflib import unified_diff
from xml.etree.cElementTree import ElementTree, tostring
import StringIO

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # Get arguments
        files = args.get("filepath", [])
        filters = args.get("filter", [])

        # status code must be 200, 207
        if response.status not in (200, 207):
            return False, "        HTTP Status Code Wrong: %d" % (response.status,)

        # look for response data
        if not respdata:
            return False, "        No response body"

        # look for one file
        if len(files) != 1:
            return False, "        No file to compare response to"

        # read in all data from specified file
        fd = open(files[0], "r")
        try:
            try:
                data = fd.read()
            finally:
                fd.close()
        except:
            data = None

        if data is None:
            return False, "        Could not read data file"

        data = manager.server_info.subs(data)
        data = manager.server_info.extrasubs(data)

        def normalizeXMLData(data):
            # Read in XML
            try:
                tree = ElementTree(file=StringIO.StringIO(data))
            except Exception:
                raise ValueError("Could not parse XML data")

            # Apply filters
            for filter in filters:
                for node in tree.getiterator(filter):
                    node.clear()
            return tostring(tree.getroot())

        try:
            respdata = normalizeXMLData(respdata)
            data = normalizeXMLData(data)

            result = respdata == data

            if result:
                return True, ""
            else:
                error_diff = "\n".join([line for line in unified_diff(data.split("\n"), respdata.split("\n"))])
                return False, "        Response data does not exactly match file data %s" % (error_diff,)
        except Exception, e:
            return False, "        Response data is not xml data: %s" % (e,)
