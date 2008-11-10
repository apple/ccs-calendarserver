#!/usr/bin/env python

##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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

from __future__ import with_statement
import sys


##
# Convert OSX .strings files to gnu gettext .po format
#
# usage: stringsconverter.py <file1> ...
##

class ParseError(Exception):
    pass

def parseString(text, index=0):

    value = ""

    while index < len(text):
        ch = text[index]

        if ch == '"':
            if text[index-1] != "\\":
                # At unescaped quote
                if value:
                    # ...marking end of string; return it
                    return (value, index+1)
                else:
                    # ...marking beginning of string; skip it
                    index += 1
                continue

        value += text[index]
        index += 1

    # no closing quote "
    raise ParseError("No closing quote")

def parseLine(line):

    key, index = parseString(line)
    remaining = line[index:].strip()
    if remaining[0] != "=":
        raise ParseError("Expected equals sign")
    remaining = remaining[1:].strip()
    value, index = parseString(remaining)
    return (key, value)


def convertFile(fileName):

    with open(fileName) as input:
        lines = input.readlines()

    with open("%s.out" % fileName, "w") as output:
        for line in lines:
            line = line.strip()
            if not line.startswith('"'):
                continue

            key, value = parseLine(line)
            output.write('msgid "%s"\n' % (key,))
            output.write('msgstr "%s"\n' % (value,))
            output.write('\n')


def main():
    for fileName in sys.argv[1:]:
        convertFile(fileName)

if __name__ == '__main__':
    main()
