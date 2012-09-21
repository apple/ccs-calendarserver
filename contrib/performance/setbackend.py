##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

"""
Generate a new calendar server configuration file based on an existing
one, with a few values changed to satisfy requirements of the
benchmarking tools.
"""

import sys
from xml.etree import ElementTree

def main():
    conf = ElementTree.parse(file(sys.argv[1]))
    if sys.argv[2] == 'postgresql':
        value = 'true'
    elif sys.argv[2] == 'filesystem':
        value = 'false'
    else:
        raise RuntimeError("Don't know what to do with %r" % (sys.argv[2],))

    # Here are the config changes we make - use the specified backend
    replace(conf.getiterator(), 'UseDatabase', value)
    # - and disable the response cache
    replace(conf.getiterator(), 'EnableResponseCache', 'false')
    conf.write(sys.stdout)


def replace(elements, key, value):
    found = False
    for ele in elements:
        if found:
            ele.tag = value
            return
        if ele.tag == 'key' and ele.text == key:
            found = True
    raise RuntimeError("Failed to find <key>UseDatabase</key>")
