#!/usr/bin/env python
# -*- test-case-name: calendarserver.tools.test.test_trash -*-
##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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
from __future__ import print_function

import collections
import datetime
from getopt import getopt, GetoptError
import os
import sys

from calendarserver.tools import tables
from calendarserver.tools.cmdline import utilityMain, WorkerService

from pycalendar.datetime import DateTime

from twext.enterprise.dal.record import fromTable
from twext.enterprise.dal.syntax import Delete, Select, Union
from twext.enterprise.jobqueue import WorkItem, RegeneratingWorkItem
from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twistedcaldav import caldavxml
from twistedcaldav.config import config

from txdav.caldav.datastore.query.filter import Filter
from txdav.common.datastore.sql_tables import schema, _HOME_STATUS_NORMAL
from txdav.caldav.datastore.sql import CalendarStoreFeatures

from argparse import ArgumentParser


log = Logger()



class TrashRestorationService(WorkerService):

    principals = []

    def doWork(self):
        rootResource = self.rootResource()
        directory = rootResource.getDirectory()
        return restoreFromTrash(
            self.store, directory, rootResource, self.principals
        )



def main():

    parser = ArgumentParser(description='Restore events from trash')
    parser.add_argument('-f', '--config', dest='configFileName', metavar='CONFIGFILE', help='caldavd.plist configuration file path')
    parser.add_argument('-d', '--debug', action='store_true', help='show debug logging')
    parser.add_argument('principal', help='one or more principals to restore', nargs='+')  # Required
    args = parser.parse_args()

    TrashRestorationService.principals = args.principal

    utilityMain(
        args.configFileName,
        TrashRestorationService,
        verbose=args.debug,
    )



@inlineCallbacks
def restoreFromTrash(store, directory, root, principals):

    for principalUID in principals:
        txn = store.newTransaction(label="Restore trashed events")
        home = yield txn.calendarHomeWithUID(principalUID)
        if home is None:
            continue
        trash = yield home.childWithName("trash")
        names = yield trash.listObjectResources()
        for name in names:
            cobj = yield trash.calendarObjectWithName(name)
            print(name, cobj)

            if cobj is not None:
                # If it's still in the trash, restore it from trash
                if (yield cobj.isTrash()):
                    print("Restoring:", name)
                    yield cobj.fromTrash()

        yield txn.commit()


if __name__ == "__main__":
    main()
