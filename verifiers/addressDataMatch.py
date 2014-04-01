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

from difflib import unified_diff
from pycalendar.vcard.card import Card

"""
Verifier that checks the response body for a semantic match to data in a file.
"""

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # Get arguments
        files = args.get("filepath", [])
        carddata = args.get("data", [])
        filters = args.get("filter", [])

        # Always remove these
        filters.append("PRODID")
        filters.append("REV")

        # status code must be 200, 201, 207
        if response.status not in (200, 201, 207):
            return False, "        HTTP Status Code Wrong: %d" % (response.status,)

        # look for response data
        if not respdata:
            return False, "        No response body"

        # look for one file
        if len(files) != 1 and len(carddata) != 1:
            return False, "        No file to compare response to"

        # read in all data from specified file or use provided data
        if len(files):
            fd = open(files[0], "r")
            try:
                try:
                    data = fd.read()
                finally:
                    fd.close()
            except:
                data = None
        else:
            data = carddata[0] if len(carddata) else None

        if data is None:
            return False, "        Could not read data file"

        data = manager.server_info.subs(data)

        def removePropertiesParameters(component):

            allProps = []
            for properties in component.getProperties().itervalues():
                allProps.extend(properties)
            for property in allProps:
                for filter in filters:
                    if ":" in filter:
                        propname, parameter = filter.split(":")
                        if property.getName() == propname:
                            if property.hasParameter(parameter):
                                property.removeParameters(parameter)
                    else:
                        if property.getName() == filter:
                            component.removeProperty(property)

        try:
            resp_adbk = Card.parseText(respdata)
            removePropertiesParameters(resp_adbk)
            respdata = resp_adbk.getText()

            data_adbk = Card.parseText(data)
            removePropertiesParameters(data_adbk)
            data = data_adbk.getText()

            result = respdata == data

            if result:
                return True, ""
            else:
                error_diff = "\n".join([line for line in unified_diff(data.split("\n"), respdata.split("\n"))])
                return False, "        Response data does not exactly match file data%s" % (error_diff,)
        except Exception, e:
            return False, "        Response data is not address data: %s" % (e,)
