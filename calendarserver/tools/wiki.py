#!/usr/bin/env python

##
# Copyright (c) 2006-2017 Apple Inc. All rights reserved.
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

__all__ = [
    "migrateWiki",
]

from getopt import getopt, GetoptError
import os
import sys

from calendarserver.tools.cmdline import utilityMain, WorkerService
from twext.enterprise.dal.syntax import Select
from twext.python.log import Logger
from twext.who.directory import DirectoryRecord
from twisted.internet.defer import inlineCallbacks
from txdav.common.datastore.sql_tables import schema
from txdav.who.idirectory import RecordType as CalRecordType
from txdav.who.wiki import DirectoryService as WikiDirectoryService

log = Logger()


class WikiMigrationService(WorkerService):

    @inlineCallbacks
    def doWork(self):
        yield migrateWiki(self.store)


def usage():

    name = os.path.basename(sys.argv[0])
    print("usage: %s [options] " % (name,))
    print("")
    print("  Migrates Wiki principals into Calendar Server resources")
    print("")
    print("options:")
    print("  -h --help: print this help and exit")
    print("  -f --config <path>: Specify caldavd.plist configuration path")
    print("")

    sys.exit(0)


def main():
    try:
        (optargs, _ignore_args) = getopt(
            sys.argv[1:], "hf:", [
                "help",
                "config=",
            ],
        )
    except GetoptError, e:
        usage(e)

    #
    # Get configuration
    #
    configFileName = None

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

        elif opt in ("-f", "--config"):
            configFileName = arg

        else:
            raise NotImplementedError(opt)

    def _patchConfig(config):
        # Disable Wiki DirectoryService so when we look up uids we don't get
        # the synthesized ones.
        config.Authentication.Wiki.Enabled = False

    utilityMain(configFileName, WikiMigrationService, patchConfig=_patchConfig)


@inlineCallbacks
def migrateWiki(store):
    """
    Iterate calendar homes looking for wiki principals; create resources
    for each.
    """

    directory = store.directoryService()
    recordType = CalRecordType.resource
    prefix = WikiDirectoryService.uidPrefix
    ch = schema.CALENDAR_HOME

    # Look up in the DB all the uids starting with the wiki prefix
    txn = store.newTransaction()
    rows = (yield Select(
        [ch.OWNER_UID, ],
        From=ch,
        Where=(ch.OWNER_UID.StartsWith(prefix)),
    ).on(txn))
    yield txn.commit()

    # For each wiki uid, if the resource record does not already exist,
    # create a record
    for uid in [row[0] for row in rows]:
        uid = uid.decode("utf-8")
        record = yield directory.recordWithUID(uid)
        if record is None:
            name = uid[len(prefix):]
            fields = {
                directory.fieldName.recordType: recordType,
                directory.fieldName.uid: uid,
                directory.fieldName.shortNames: [name],
                directory.fieldName.fullNames: [name],
                directory.fieldName.hasCalendars: True,
                directory.fieldName.hasContacts: False,
            }
            record = DirectoryRecord(directory, fields)
            yield record.service.updateRecords([record], create=True)
            print("Added '{}'".format(name))


if __name__ == "__main__":
    main()
