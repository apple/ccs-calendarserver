##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
Mac OS X Server Wiki directory service.
"""

__all__ = [
    "DirectoryService",
    "WikiAccessLevel",
]

from twisted.python.constants import Names, NamedConstant
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.web.error import Error as WebError

from twext.python.log import Logger
from twext.internet.gaiendpoint import MultiFailure
from .idirectory import FieldName
from twext.who.directory import (
    DirectoryService as BaseDirectoryService,
    DirectoryRecord as BaseDirectoryRecord
)
from txweb2 import responsecode

from calendarserver.platform.darwin.wiki import accessForUserToWiki



# FIXME: Should this be Flags?
class WikiAccessLevel(Names):
    none  = NamedConstant()
    read  = NamedConstant()
    write = NamedConstant()



class RecordType(Names):
    macOSXServerWiki = NamedConstant()
    macOSXServerWiki.description = u"Mac OS X Server Wiki"



class DirectoryService(BaseDirectoryService):
    """
    Mac OS X Server Wiki directory service.
    """

    uidPrefix = "[wiki]"

    recordType = RecordType


    def __init__(self):
        BaseDirectoryService.__init__(self)
        self._recordsByName = {}


    # This directory service is rather limited in its skills.
    # We don't attempt to implement any expression handling (ie.
    # recordsFromNonCompoundExpression), and only support a couple of the
    # recordWith* convenience methods.

    def _recordWithName(self, name):
        record = self._recordsByName.get(name)

        if record is not None:
            return succeed(record)

        # FIXME: RPC to the wiki and check for existance of a wiki with the
        # given name...
        #
        # NOTE: Don't use the config module here; pass whatever info we need to
        # __init__().
        wikiExists = True

        if wikiExists:
            record = DirectoryRecord(
                self,
                {
                    FieldName.uid: "{}{}".format(self.uidPrefix, name),
                    FieldName.recordType: RecordType.macOSXServerWiki,
                    FieldName.shortNames: [name],
                }
            )
            self._recordsByName[name] = record
            return succeed(record)

        return succeed(None)


    def recordWithUID(self, uid):
        if uid.startswith(self.uidPrefix):
            return self._recordWithName(uid[len(self.uidPrefix):])
        return succeed(None)


    def recordWithShortName(self, recordType, shortName):
        if recordType is RecordType.macOSXServerWiki:
            return self._recordWithName(shortName)
        return succeed(None)



class DirectoryRecord(BaseDirectoryRecord):
    """
    Mac OS X Server Wiki directory record.
    """

    log = Logger()


    @property
    def name(self):
        return self.shortNames[0]


    @inlineCallbacks
    def accessForRecord(self, record):
        """
        Look up the access level for a record in this wiki.

        @param user: The record to check access for.
        """
        guid = record.guid

        try:
            # FIXME: accessForUserToWiki() API is lame.
            # There are no other callers except the old directory API, so
            # nuke it from the originating module and move that logic here
            # once the old API is removed.
            # When we do that note: isn't there a getPage() in twisted.web?

            access = yield accessForUserToWiki(
                guid, self.shortNames[0],
                host=self.service.wikiHost,
                port=self.service.wikiPort,
            )

        except MultiFailure as e:
            self.log.error(
                "Unable to look up access for record {record} "
                "in wiki {log_source}: {error}",
                record=record, error=e
            )

        except WebError as e:
            status = int(e.status)

            if status == responsecode.FORBIDDEN:  # Unknown user
                self.log.debug(
                    "No such record (according to wiki): {record}",
                    record=record, error=e
                )
                returnValue(WikiAccessLevel.none)

            if status == responsecode.NOT_FOUND:  # Unknown wiki
                self.log.error(
                    "No such wiki: {log_source.name}",
                    record=record, error=e
                )
                returnValue(WikiAccessLevel.none)

            self.log.error(
                "Unable to look up wiki access: {error}",
                record=record, error=e
            )

        try:
            returnValue({
                "no-access": WikiAccessLevel.none,
                "read": WikiAccessLevel.read,
                "write": WikiAccessLevel.write,
                "admin": WikiAccessLevel.write,
            }[access])

        except KeyError:
            self.log.error("Unknown wiki access level: {level}", level=access)
            return WikiAccessLevel.none
