#!/usr/bin/env python
##
# Copyright (c) 2009-2012 Apple Inc. All rights reserved.
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
import os
import subprocess
import sys
import time

def error(s):
    print s
    sys.exit(1)

def cmd(s):
    print s
    subprocess.call(s, shell=True)

def doInit(basedir):
    
    cmd("mkdir %s/data" % (basedir,))
    cmd("%s/bin/initdb -D %s/data" % (basedir, basedir,))
    
    # Have the DB listen on all interfaces
    with open("%s/data/postgresql.conf" % (basedir,)) as f:
        conf = f.read()
    conf = conf.replace("#listen_addresses = 'localhost'", "listen_addresses = '*'\t")
    conf = conf.replace("max_connections = 20 ", "max_connections = 500")
    with open("%s/data/postgresql.conf" % (basedir,), "w") as f:
        f.write(conf)
        
    # Allow current user to auth to the DBs
    with open("%s/data/pg_hba.conf" % (basedir,)) as f:
        conf = f.read()
    conf = conf.replace("127.0.0.1/32", "0.0.0.0/0   ")
    with open("%s/data/pg_hba.conf" % (basedir,), "w") as f:
        f.write(conf)

    cmd("%s/bin/pg_ctl -D %s/data -l logfile start" % (basedir, basedir,))
    time.sleep(5)
    cmd("%s/bin/createdb proxies" % (basedir,))
    cmd("%s/bin/createdb augments" % (basedir,))
    cmd("%s/bin/pg_ctl -D %s/data -l logfile stop" % (basedir, basedir,))

def doStart(basedir):
    
    cmd("%s/bin/pg_ctl -D %s/data -l logfile start" % (basedir, basedir,))

def doStop(basedir):
    
    cmd("%s/bin/pg_ctl -D %s/data -l logfile stop" % (basedir, basedir,))

def doRun(basedir, verbose):
    
    cmd("%s/bin/postgres %s -D %s/data" % (basedir, "-d 3" if verbose else "",  basedir,))

def doClean(basedir):
    
    cmd("rm -rf %s/data" % (basedir,))

def main():

    usage = "%prog [options] ACTION"
    epilog = """
ACTION is one of init|start|stop|run

  init:   initialize databases
  start:  start postgres daemon
  stop:   stop postgres daemon
  run:    run postgres (non-daemon)
  clean:  remove databases
  
"""
    description = "Tool to manage PostgreSQL"
    version = "%prog v1.0"
    parser = OptionParser(usage=usage, description=description, version=version)
    parser.epilog = epilog
    parser.format_epilog = lambda _:epilog

    parser.add_option("-v", "--verbose", action="store_true", dest="verbose",
                      default=True, help="Use debug logging for PostgreSQL")
    parser.add_option("-d", "--base-dir", dest="basedir",
                      default="%s/../postgresql-8.4.2/_root" % (os.getcwd(),), help="Base directory for PostgreSQL install")

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("incorrect number of arguments")

    if args[0] == "init":
        doInit(options.basedir)
    elif args[0] == "start":
        doStart(options.basedir)
    elif args[0] == "stop":
        doStop(options.basedir)
    elif args[0] == "run":
        doRun(options.basedir, options.verbose)
    elif args[0] == "clean":
        doClean(options.basedir)
    else:
        parser.error("incorrect argument '%s'" % (args[0],))

if __name__ == '__main__':
    main()
