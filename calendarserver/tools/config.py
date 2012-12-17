#!/usr/bin/env python

##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
This tool reads the Calendar Server configuration file and emits the
requested value.
"""

import os, sys
from getopt import getopt, GetoptError

from twistedcaldav.config import config, ConfigurationError
from twistedcaldav.stdconfig import DEFAULT_CONFIG_FILE

def usage(e=None):
    if e:
        print e
        print ""

    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] config_key" % (name,)
    print ""
    print "Print the value of the given config key."
    print "options:"
    print "  -h --help: print this help and exit"
    print "  -f --config: Specify caldavd.plist configuration path"

    if e:
        sys.exit(64)
    else:
        sys.exit(0)

def main():
    try:
        (optargs, args) = getopt(
            sys.argv[1:], "hf:w:", [
                "help",
                "config=",
                "write=",
            ],
        )
    except GetoptError, e:
        usage(e)

    configFileName = DEFAULT_CONFIG_FILE
    writeConfigFileName = DEFAULT_CONFIG_FILE

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        elif opt in ("-w", "--write"):
            writeConfigFileName = arg

    try:
        config = loadConfig(configFileName)
    except ConfigurationError, e:
        sys.stdout.write("%s\n" % (e,))
        sys.exit(1)

    for configKey in args:
        c = config
        for subKey in configKey.split("."):
            c = c.get(subKey, None)
            if c is None:
                sys.stderr.write("No such config key: %s\n" % configKey)
                break
        else:
            sys.stdout.write("%s\n" % c)
