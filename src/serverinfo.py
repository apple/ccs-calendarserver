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
Class that encapsulates the server information for a CalDAV test run.
"""

import datetime
import re
import src.xmlDefs


class serverinfo(object):
    """
    Maintains information about the server being targeted.
    """

    # RegEx pattern to match substitution variables
    subspattern = re.compile("(?P<name>\\$[_a-zA-Z][_a-zA-Z0-9\\-]*\\:)")

    def __init__(self):
        self.host = ""
        self.nonsslport = 80
        self.sslport = 443
        self.host2 = ""
        self.nonsslport2 = 80
        self.sslport2 = 443
        self.authtype = "basic"
        self.features = set()
        self.user = ""
        self.pswd = ""
        self.waitcount = 120
        self.waitdelay = 0.25
        self.waitsuccess = 10
        self.subsdict = {}
        self.extrasubsdict = {}

        # dtnow needs to be fixed to a single date at the start of the tests just in case the tests
        # run over a day boundary.
        self.dtnow = datetime.date.today()


    def _re_subs(self, sub, mapping):
        """
        Do a regex substitution via the supplied mapping, only if the mapping exists.

        @param sub: string to do substitution in
        @type sub: L{str}
        @param mapping: mapping of substitution name to value
        @type mapping: L{dict}
        """
        # Helper function for .sub()
        def convert(mo):
            named = mo.group('name')
            if named is not None and named in mapping:
                return mapping[named]
            else:
                return named
        return self.subspattern.sub(convert, sub)


    def subs(self, sub, db=None):

        # Special handling for relative date-times
        pos = sub.find("$now.")
        while pos != -1:
            endpos = pos + sub[pos:].find(":")
            if sub[pos:].startswith("$now.year."):
                yearoffset = int(sub[pos + 10:endpos])
                value = "%d" % (self.dtnow.year + yearoffset,)
            elif sub[pos:].startswith("$now.month."):
                monthoffset = int(sub[pos + 11:endpos])
                month = self.dtnow.month + monthoffset
                year = self.dtnow.year + divmod(month - 1, 12)[0]
                month = divmod(month - 1, 12)[1] + 1
                value = "%d%02d" % (year, month,)
            elif sub[pos:].startswith("$now.week."):
                weekoffset = int(sub[pos + 10:endpos])
                dtoffset = self.dtnow + datetime.timedelta(days=7 * weekoffset)
                value = "%d%02d%02d" % (dtoffset.year, dtoffset.month, dtoffset.day,)
            else:
                dayoffset = int(sub[pos + 5:endpos])
                dtoffset = self.dtnow + datetime.timedelta(days=dayoffset)
                value = "%d%02d%02d" % (dtoffset.year, dtoffset.month, dtoffset.day,)
            sub = "%s%s%s" % (sub[:pos], value, sub[endpos + 1:])
            pos = sub.find("$now.")

        if db is None:
            db = self.subsdict
        while '$' in sub:
            newstr = self._re_subs(sub, db)
            if newstr == sub:
                break
            sub = newstr
        return sub


    def addsubs(self, items, db=None):
        if db is None:
            db_actual = self.subsdict
        else:
            db_actual = db
        for key, value in items.iteritems():
            db_actual[key] = value

        if db is None:
            self.updateParams()


    def hasextrasubs(self):
        return len(self.extrasubsdict) > 0


    def extrasubs(self, str):
        return self.subs(str, self.extrasubsdict)


    def addextrasubs(self, items):
        processed = {}

        # Various "functions" might be applied to a variable name to cause the value to
        # be changed in various ways
        for variable, value in items.items():

            # basename() - extract just the URL last path segment from the value
            if variable.startswith("basename("):
                variable = variable[len("basename("):-1]
                value = value.rstrip("/").split("/")[-1]
            processed[variable] = value

        self.addsubs(processed, self.extrasubsdict)


    def parseXML(self, node):
        for child in node.getchildren():
            if child.tag == src.xmlDefs.ELEMENT_HOST:
                try:
                    self.host = child.text.encode("utf-8")
                except:
                    self.host = "localhost"
            elif child.tag == src.xmlDefs.ELEMENT_NONSSLPORT:
                self.nonsslport = int(child.text)
            elif child.tag == src.xmlDefs.ELEMENT_SSLPORT:
                self.sslport = int(child.text)
            elif child.tag == src.xmlDefs.ELEMENT_HOST2:
                try:
                    self.host2 = child.text.encode("utf-8")
                except:
                    self.host2 = "localhost"
            elif child.tag == src.xmlDefs.ELEMENT_NONSSLPORT2:
                self.nonsslport2 = int(child.text)
            elif child.tag == src.xmlDefs.ELEMENT_SSLPORT2:
                self.sslport2 = int(child.text)
            elif child.tag == src.xmlDefs.ELEMENT_AUTHTYPE:
                self.authtype = child.text.encode("utf-8")
            elif child.tag == src.xmlDefs.ELEMENT_WAITCOUNT:
                self.waitcount = int(child.text.encode("utf-8"))
            elif child.tag == src.xmlDefs.ELEMENT_WAITDELAY:
                self.waitdelay = float(child.text.encode("utf-8"))
            elif child.tag == src.xmlDefs.ELEMENT_WAITSUCCESS:
                self.waitsuccess = int(child.text.encode("utf-8"))
            elif child.tag == src.xmlDefs.ELEMENT_FEATURES:
                self.parseFeatures(child)
            elif child.tag == src.xmlDefs.ELEMENT_SUBSTITUTIONS:
                self.parseSubstitutionsXML(child)

        self.updateParams()


    def parseFeatures(self, node):
        for child in node.getchildren():
            if child.tag == src.xmlDefs.ELEMENT_FEATURE:
                self.features.add(child.text.encode("utf-8"))


    def updateParams(self):

        # Expand substitutions fully at this point
        for k, v in self.subsdict.items():
            while '$' in v:
                v = self._re_subs(v, self.subsdict)
            self.subsdict[k] = v

        # Now cache some useful substitutions
        if "$userid1:" not in self.subsdict:
            raise ValueError("Must have $userid1: substitution")
        self.user = self.subsdict["$userid1:"]
        if "$pswd1:" not in self.subsdict:
            raise ValueError("Must have $pswd1: substitution")
        self.pswd = self.subsdict["$pswd1:"]


    def parseRepeatXML(self, node):
        # Look for count
        count = node.get(src.xmlDefs.ATTR_COUNT)

        for child in node.getchildren():
            self.parseSubstitutionXML(child, count)


    def parseSubstitutionsXML(self, node):
        for child in node.getchildren():
            if child.tag == src.xmlDefs.ELEMENT_SUBSTITUTION:
                self.parseSubstitutionXML(child)
            elif child.tag == src.xmlDefs.ELEMENT_REPEAT:
                self.parseRepeatXML(child)


    def parseSubstitutionXML(self, node, repeat=None):
        if node.tag == src.xmlDefs.ELEMENT_SUBSTITUTION:
            key = None
            value = None
            for schild in node.getchildren():
                if schild.tag == src.xmlDefs.ELEMENT_KEY:
                    key = schild.text.encode("utf-8")
                elif schild.tag == src.xmlDefs.ELEMENT_VALUE:
                    value = schild.text.encode("utf-8") if schild.text else ""

            if key and value:
                if repeat:
                    for count in range(1, int(repeat) + 1):
                        self.subsdict[key % (count,)] = (value % (count,)) if "%" in value else value
                else:
                    self.subsdict[key] = value
