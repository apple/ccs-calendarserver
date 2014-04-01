##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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

import json


class JSONPointerMatchError(Exception):
    """
    Exception for failed pointer matches
    """
    pass



class JSONPointer(object):
    """
    Represents a JSON Pointer that can match a specific JSON object.
    """

    def __init__(self, pointer):

        if not pointer or pointer[0] != "/":
            raise ValueError("Invalid JSON pointer: %s" % (pointer,))
        self.segments = self._splitSegments(pointer)


    def _splitSegments(self, pointer):
        """
        Split a pointer up into segments.

        @param pointer: the pointer
        @type pointer: C{str}

        @return: list of segments
        @rtype C{list}
        """
        splits = pointer[1:].split("/")
        if splits == [""]:
            return None
        if any(map(lambda x: len(x) == 0, splits)):
            raise TypeError("Pointer segment is empty: %s" % (pointer,))
        return map(self._unescape, splits)


    def _unescape(self, segment):
        """
        Unescape ~0 and ~1 in a path segment.

        @param segment: the segment to unescape
        @type segment: C{str}

        @return: the unescaped segment
        @rtype: C{str}
        """
        return segment.replace("~1", "/").replace("~0", "~")


    def matchs(self, s):
        """
        Match this pointer against the string representation of a JSON object.

        @param s: a string representation of a JSON object
        @type s: C{str}
        """

        return self.match(json.loads(s))


    def match(self, j):
        """
        Match this pointer against the JSON object.

        @param j: a JSON object
        @type j: C{dict} or C{list}
        """

        try:
            return self.walk(j, self.segments)
        except Exception:
            raise JSONPointerMatchError


    def walk(self, j, segments):
        """
        Recursively match the next portion of a pointer segment.

        @param j: JSON object to match
        @type j: C{dict} or C{list}
        @param segments: list of pointer segments
        @type segments: C{list}
        """

        if not segments:
            return j

        if isinstance(j, dict):
            return self.walk(j[segments[0]], segments[1:])
        elif isinstance(j, list):
            index = -1 if segments[0] == "-" else int(segments[0])
            return self.walk(j[index], segments[1:])
        else:
            raise JSONPointerMatchError



class JSONMatcher(JSONPointer):
    """
    Represents a JSON pointer with syntax allowing a match against multiple JSON objects. If any
    segment of a path is a single ".", then all object or array members are matched. The result of
    the match is the array of objects that match. Missing keys and index past the end are ignored.
    """

    def __init__(self, pointer):

        if not pointer or pointer[0] != "/":
            raise ValueError("Invalid JSON pointer: %s" % (pointer,))
        self.segments = self._splitSegments(pointer)


    def walk(self, j, segments):
        """
        Recursively match the next portion of a pointer segment, talking wildcard "."
        segment matching into account.

        @param j: JSON object to match
        @type j: C{dict} or C{list}
        @param segments: list of pointer segments
        @type segments: C{list}
        """

        if not segments:
            return [j, ]

        results = []
        if isinstance(j, dict):
            if segments[0] == ".":
                keys = j.keys()
            else:
                keys = [segments[0]]
            for k in keys:
                try:
                    results.extend(self.walk(j[k], segments[1:]))
                except KeyError:
                    pass
        elif isinstance(j, list):
            if segments[0] == ".":
                r = range(len(j))
            else:
                r = [-1 if segments[0] == "-" else int(segments[0])]
            for index in r:
                try:
                    results.extend(self.walk(j[index], segments[1:]))
                except IndexError:
                    pass
        else:
            raise JSONPointerMatchError

        return results
