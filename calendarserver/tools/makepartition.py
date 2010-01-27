#!/usr/bin/env python
##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

from optparse import OptionParser
from twext.python.plistlib import readPlist, writePlist
import os
import sys
from twistedcaldav.config import ConfigurationError, Config
from twistedcaldav.stdconfig import PListConfigProvider, DEFAULT_CONFIG
from urlparse import urlparse

def error(s):
    print s
    sys.exit(1)

def createPrimary(options):
    _createNode(options, True)
    print "Created primary partition with node id '%s' and uri '%s'" % (options.nodeid, options.nodeurl,)

def createSecondary(options):
    _createNode(options, False)
    print "Created secondary partition with node id '%s' and uri '%s'" % (options.nodeid, options.nodeurl,)

def _createNode(options, isPrimary):

    # Read in main plist
    try:
        dataDict = readPlist(options.conf)
    except (IOError, OSError):                                    
        raise RuntimeError("Main plist file does not exist or is inaccessible: %s" % (options.conf,))
    
    # Look for includes
    includes = dataDict.setdefault("Includes", [])
    
    # Make sure partitioning plist is included
    primaryPlist = "caldavd-partitioning-primary.plist"
    secondaryPlist = "caldavd-partitioning-secondary.plist"
    partitioningPlistAdd = os.path.join(
        os.path.dirname(options.conf),
        primaryPlist if isPrimary else secondaryPlist,
    )
    partitioningPlistRemove = os.path.join(
        os.path.dirname(options.conf),
        secondaryPlist if isPrimary else primaryPlist,
    )
    if partitioningPlistAdd not in includes:
        includes.append(partitioningPlistAdd)
    if partitioningPlistRemove in includes:
        includes.remove(partitioningPlistRemove)
    
    # Push out main plist change
    try:
        writePlist(dataDict, options.conf)
    except (IOError, OSError):                                    
        raise RuntimeError("Could not write main plist file: %s" % (options.conf,))

    # Now edit partitioning plist
    try:
        dataDict = readPlist(partitioningPlistAdd)
    except (IOError, OSError):                                    
        raise RuntimeError("Partitioning plist file does not exist or is inaccessible: %s" % (partitioningPlistAdd,))
    
    # Need to adjust the node id, and host names
    dataDict["Partitioning"]["ServerPartitionID"] = options.nodeid
    
    if not isPrimary:
        _ignore_scheme, netloc, _ignore_path, _ignore_params, _ignore_query, _ignore_fragment = urlparse(options.primaryurl)
        if ':' in netloc:
            host = netloc.split(':')[0]
        else:
            host = netloc
        dataDict["ProxyDBService"]["params"]["host"] = host
        dataDict["Memcached"]["Pools"]["CommonToAllNodes"]["BindAddress"] = host
    
    # Push out partitioning plist change
    try:
        writePlist(dataDict, partitioningPlistAdd)
    except (IOError, OSError):                                    
        raise RuntimeError("Could not write partitioning plist file: %s" % (partitioningPlistAdd,))

def addOther(options):
    _addOther(options.conf, options.nodeid, options.nodeurl)
    print "Added partition with node id '%s' and uri '%s' to partitions plist" % (options.nodeid, options.nodeurl,)
    
def _addOther(conf, nodeid, nodeurl):
    
    # Read main plist
    try:
        cfg = Config(PListConfigProvider(DEFAULT_CONFIG))
        cfg.load(conf)
    except ConfigurationError:
        raise RuntimeError("Could not parse as plist: '%s'" % (conf,))

    # Read in the partitions plist
    partitionsPlist = cfg.Partitioning.PartitionConfigFile
    try:
        dataDict = readPlist(partitionsPlist)
    except (IOError, OSError):                                    
        raise RuntimeError("Partitions plist file does not exist or is inaccessible: %s" % (partitionsPlist,))

    # See if node id already exists
    if nodeid in [partition.get("uid", None) for partition in dataDict.get("partitions", ())]:
        raise RuntimeError("Node '%s' already in partitions plist '%s'" % (nodeid, partitionsPlist,))
    
    # Add new information and write it out
    dataDict.setdefault("partitions", []).append(
        {
            "uid": nodeid,
            "url": nodeurl,
        }
    )
    try:
        writePlist(dataDict, partitionsPlist)
    except (IOError, OSError):                                    
        raise RuntimeError("Could not write partitions plist: %s" % (partitionsPlist,))

def main():

    usage = "%prog [options] MODE"
    epilog = """
MODE is one of primary|secondary|add

  primary:   Create a new primary node (manages main DBs)
  secondary: Create a new secondary node
  add:       Add information for a new partition node on another machine
"""
    description = "Tool to setup CalendarServer partition node configuration files"
    version = "%prog v1.0"
    parser = OptionParser(usage=usage, description=description, version=version)
    parser.epilog = epilog
    parser.format_epilog = lambda _:epilog

    parser.add_option("-c", "--conf", dest="conf",
                      help="Directory where .plist files are stored", metavar="CONF")
    parser.add_option("-n", "--nodeid", dest="nodeid",
                      help="Node ID for this node", metavar="NODEID")
    parser.add_option("-u", "--url", dest="nodeurl",
                      help="URL of node being added", metavar="NODEURL")
    parser.add_option("-p", "--primary", dest="primaryurl",
                      help="URL of primary node", metavar="PRIMARYURL")

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("incorrect number of arguments")

    # Make sure conf dir has the needed .plist files
    if not os.path.exists(options.conf):
        parser.error("Could not find '%s'" % (options.conf,))
    confdir = os.path.dirname(options.conf)
    if not os.path.exists(os.path.join(confdir, "caldavd-partitioning-primary.plist")):
        parser.error("Could not find caldavd-partitioning-primary.plist in '%s'" % (confdir,))
    if not os.path.exists(os.path.join(confdir, "caldavd-partitioning-secondary.plist")):
        parser.error("Could not find caldavd-partitioning-secondary.plist in '%s'" % (confdir,))

    # Handle each action
    {
        "primary"  : createPrimary,
        "secondary": createSecondary,
        "add"      : addOther,
    }[args[0]](options)

if __name__ == '__main__':
    main()
