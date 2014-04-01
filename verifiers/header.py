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
Verifier that checks the response headers for a specific value.
"""

import re

class Verifier(object):

    def verify(self, manager, uri, response, respdata, args): #@UnusedVariable
        # Split into header/value tuples
        testheader = args.get("header", [])[:]
        for i in range(len(testheader)):
            p = testheader[i]
            present = "single"
            if p[0] == "!":
                p = p[1:]
                present = "none"
            if p[0] == "*":
                p = p[1:]
                present = "multiple"
            if p.find("$") != -1:
                testheader[i] = (p.split("$", 1)[0], p.split("$", 1)[1], present, True,)
            elif p.find("!") != -1:
                testheader[i] = (p.split("!", 1)[0], p.split("!", 1)[1], present, False,)
            else:
                testheader[i] = (p, None, present, True,)

        result = True
        resulttxt = ""
        for hdrname, hdrvalue, presence, matchvalue in testheader:
            hdrs = response.msg.getheaders(hdrname)
            if (hdrs is None or (len(hdrs) == 0)):
                if presence != "none":
                    result = False
                    if len(resulttxt):
                        resulttxt += "\n"
                    resulttxt += "        Missing Response Header: %s" % (hdrname,)
                    continue
                else:
                    continue

            if (hdrs is not None) and (len(hdrs) != 0) and (presence == "none"):
                result = False
                if len(resulttxt):
                    resulttxt += "\n"
                resulttxt += "        Response Header was present one or more times: %s" % (hdrname,)
                continue

            if (len(hdrs) != 1) and (presence == "single"):
                result = False
                if len(resulttxt):
                    resulttxt += "\n"
                resulttxt += "        Multiple Response Headers: %s" % (hdrname,)
                continue

            if (hdrvalue is not None):
                hdrvalue = hdrvalue.replace(" ", "")
                matched = False
                for hdr in hdrs:
                    hdr = hdr.replace(" ", "")
                    if (re.match(hdrvalue, hdr) is not None):
                        matched = True
                        break

                if matchvalue and not matched or not matchvalue and matched:
                    result = False
                    if len(resulttxt):
                        resulttxt += "\n"
                    resulttxt += "        Wrong Response Header Value: %s: %s" % (hdrname, str(hdrs))

        return result, resulttxt
