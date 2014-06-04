##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

import cPickle as pickle
import datetime
import uuid

from twext.python.log import Logger
from twext.who.expression import MatchType, MatchFlags, Operand
from twisted.application import service
from twisted.application.strports import service as strPortsService
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import Factory
from twisted.plugin import IPlugin
from twisted.protocols import amp
from twisted.python.constants import Names, NamedConstant
from twisted.python.usage import Options, UsageError
from twistedcaldav.config import config
from twistedcaldav.stdconfig import DEFAULT_CONFIG, DEFAULT_CONFIG_FILE
from txdav.dps.commands import (
    RecordWithShortNameCommand, RecordWithUIDCommand, RecordWithGUIDCommand,
    RecordsWithRecordTypeCommand, RecordsWithEmailAddressCommand,
    RecordsMatchingTokensCommand, RecordsMatchingFieldsCommand,
    MembersCommand, GroupsCommand, SetMembersCommand,
    VerifyPlaintextPasswordCommand, VerifyHTTPDigestCommand,
    WikiAccessForUID, ContinuationCommand
    # UpdateRecordsCommand, RemoveRecordsCommand
)
from txdav.who.util import directoryFromConfig
from txdav.who.wiki import WikiAccessLevel
from zope.interface import implementer


log = Logger()


##
## Server implementation of Directory Proxy Service
##


class DirectoryProxyAMPProtocol(amp.AMP):
    """
    Server side of directory proxy
    """

    def __init__(self, directory):
        """
        """
        amp.AMP.__init__(self)
        self._directory = directory

        # How to large we let an AMP response get before breaking it up
        self._maxSize = 60000

        # The cache of results we have not fully responded with.  A dictionary
        # whose keys are "continuation tokens" and whose values are tuples of
        # (timestamp, list-of-records).  When a response does not fit within
        # AMP size limits, the remaining records are stored in this dictionary
        # keyed by an opaque token we generate to return to the client so that
        # it can ask for the remaining results later.
        self._continuations = {}


    def _storeContinuation(self, records):
        """
        Store an iterable of records and generate an opaque token we can
        give back to the client so they can later retrieve these remaining
        results that did not fit in the previous AMP response.

        @param records: an iterable of records
        @return: a C{str} token
        """
        token = str(uuid.uuid4())
        # FIXME: I included a timestamp just in case we want to have code that
        # looks for stale continuations to expire them.
        self._continuations[token] = (datetime.datetime.now(), records)
        return token


    def _retrieveContinuation(self, token):
        """
        Retrieve the previously stored iterable of records associated with
        the token, and remove the token.

        @param token: a C{str} token previously returned by _storeContinuation
        @return: an iterable of records, or None if the token does not exist
        """
        if token in self._continuations:
            timestamp, records = self._continuations[token]
            del self._continuations[token]
        else:
            records = None
        return records


    @ContinuationCommand.responder
    def continuation(self, continuation):
        """
        The client calls this command in order to retrieve records that did
        not fit into an earlier response.

        @param continuation: the token returned via the "continuation" key
            in the previous response.
        """
        log.debug("Continuation: {c}", c=continuation)
        records = self._retrieveContinuation(continuation)
        response = self._recordsToResponse(records)
        log.debug("Responding with: {response}", response=response)
        return response


    def _recordsToResponse(self, records):
        """
        Craft an AMP response containing as many records as will fit within
        the size limit.  Remaining records are stored as a "continuation",
        identified by a token that is returned to the client to fetch later
        via the ContinuationCommand.

        @param records: an iterable of records
        @return: the response dictionary, with a list of pickled records
            stored in the "fieldsList" key, and if there are leftover
            records that did not fit, there will be a "continuation" key
            containing the token the client must send via ContinuationCommand.
        """
        fieldsList = []
        count = 0
        if records:
            size = 0
            while size < self._maxSize:
                try:
                    record = records.pop()
                except (KeyError, IndexError):
                    # We're done.
                    # Note: because records is an iterable (list or set)
                    # we're catching both KeyError and IndexError.
                    break
                pickled = pickle.dumps(self.recordToDict(record))
                size = size + len(pickled)
                fieldsList.append(pickled)
                count += 1

        response = {"fieldsList": fieldsList}

        if records:
            response["continuation"] = self._storeContinuation(records)

        return response


    def recordToDict(self, record):
        """
        Turn a record in a dictionary of fields which can be reconstituted
        within the client
        """
        fields = {}
        if record is not None:
            for field, value in record.fields.iteritems():
                valueType = record.service.fieldName.valueType(field)
                # print("%s: %s (%s)" % (field.name, value, valueType))
                if valueType in (unicode, bool):
                    fields[field.name] = value
                elif valueType is uuid.UUID:
                    fields[field.name] = str(value)
                elif issubclass(valueType, (Names, NamedConstant)):
                    fields[field.name] = value.name if value else None
        # print("Server side fields", fields)
        return fields


    @RecordWithShortNameCommand.responder
    @inlineCallbacks
    def recordWithShortName(self, recordType, shortName):
        recordType = recordType  # keep as bytes
        shortName = shortName.decode("utf-8")
        log.debug("RecordWithShortName: {r} {n}", r=recordType, n=shortName)
        record = (yield self._directory.recordWithShortName(
            self._directory.recordType.lookupByName(recordType), shortName)
        )
        fields = self.recordToDict(record)
        response = {
            "fields": pickle.dumps(fields),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordWithUIDCommand.responder
    @inlineCallbacks
    def recordWithUID(self, uid):
        uid = uid.decode("utf-8")
        log.debug("RecordWithUID: {u}", u=uid)
        try:
            record = (yield self._directory.recordWithUID(uid))
        except Exception as e:
            log.error("Failed in recordWithUID", error=e)
            record = None
        fields = self.recordToDict(record)
        response = {
            "fields": pickle.dumps(fields),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordWithGUIDCommand.responder
    @inlineCallbacks
    def recordWithGUID(self, guid):
        guid = uuid.UUID(guid)
        log.debug("RecordWithGUID: {g}", g=guid)
        record = (yield self._directory.recordWithGUID(guid))
        fields = self.recordToDict(record)
        response = {
            "fields": pickle.dumps(fields),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordsWithRecordTypeCommand.responder
    @inlineCallbacks
    def recordsWithRecordType(self, recordType):
        recordType = recordType  # as bytes
        log.debug("RecordsWithRecordType: {r}", r=recordType)
        records = (yield self._directory.recordsWithRecordType(
            self._directory.recordType.lookupByName(recordType))
        )
        response = self._recordsToResponse(records)
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordsWithEmailAddressCommand.responder
    @inlineCallbacks
    def recordsWithEmailAddress(self, emailAddress):
        emailAddress = emailAddress.decode("utf-8")
        log.debug("RecordsWithEmailAddress: {e}", e=emailAddress)
        records = (yield self._directory.recordsWithEmailAddress(emailAddress))
        response = self._recordsToResponse(records)
        log.debug("Responding with: {response}", response=response)
        returnValue(response)




    @RecordsMatchingTokensCommand.responder
    @inlineCallbacks
    def recordsMatchingTokens(self, tokens, context=None):
        tokens = [t.decode("utf-8") for t in tokens]
        log.debug("RecordsMatchingTokens: {t}", t=(", ".join(tokens)))
        records = yield self._directory.recordsMatchingTokens(
            tokens, context=context
        )
        response = self._recordsToResponse(records)
        log.debug("Responding with: {response}", response=response)
        returnValue(response)



    @RecordsMatchingFieldsCommand.responder
    @inlineCallbacks
    def recordsMatchingFields(self, fields, operand="OR", recordType=None):
        log.debug("RecordsMatchingFields")
        newFields = []
        for fieldName, searchTerm, matchFlags, matchType in fields:
            fieldName = fieldName.decode("utf-8")
            searchTerm = searchTerm.decode("utf-8")
            try:
                field = self._directory.fieldName.lookupByName(fieldName)
            except ValueError:
                field = None
            if field:
                valueType = self._directory.fieldName.valueType(field)
                if valueType is uuid.UUID:
                    searchTerm = uuid.UUID(searchTerm)

            matchFlags = matchFlags.decode("utf-8")
            if matchFlags.startswith("{") and matchFlags.endswith("}"):
                flags = MatchFlags.none
                for flag in matchFlags[1:-1].split(","):
                    flags |= MatchFlags.lookupByName(flag)
                matchFlags = flags
            else:
                matchFlags = MatchFlags.lookupByName(matchFlags)

            matchType = MatchType.lookupByName(matchType.decode("utf-8"))

            newFields.append((fieldName, searchTerm, matchFlags, matchType))
        operand = Operand.lookupByName(operand)
        if recordType:
            recordType = self._directory.recordType.lookupByName(recordType)
        records = yield self._directory.recordsMatchingFields(
            newFields, operand=operand, recordType=recordType
        )
        response = self._recordsToResponse(records)
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @MembersCommand.responder
    @inlineCallbacks
    def members(self, uid):
        uid = uid.decode("utf-8")
        log.debug("Members: {u}", u=uid)
        try:
            record = (yield self._directory.recordWithUID(uid))
        except Exception as e:
            log.error("Failed in members", error=e)
            record = None

        records = []
        if record is not None:
            for member in (yield record.members()):
                records.append(member)

        response = self._recordsToResponse(records)
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @SetMembersCommand.responder
    @inlineCallbacks
    def setMembers(self, uid, memberUIDs):
        uid = uid.decode("utf-8")
        memberUIDs = [m.decode("utf-8") for m in memberUIDs]
        log.debug("Set Members: {u} -> {m}", u=uid, m=memberUIDs)
        try:
            record = (yield self._directory.recordWithUID(uid))
        except Exception as e:
            log.error("Failed in setMembers", error=e)
            record = None

        if record is not None:
            memberRecords = []
            for memberUID in memberUIDs:
                memberRecord = yield self._directory.recordWithUID(memberUID)
                if memberRecord is not None:
                    memberRecords.append(memberRecord)
            yield record.setMembers(memberRecords)
            success = True
        else:
            success = False

        response = {
            "success": success,
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @GroupsCommand.responder
    @inlineCallbacks
    def groups(self, uid):
        uid = uid.decode("utf-8")
        log.debug("Groups: {u}", u=uid)
        try:
            record = (yield self._directory.recordWithUID(uid))
        except Exception as e:
            log.error("Failed in groups", error=e)
            record = None

        records = []
        for group in (yield record.groups()):
            records.append(group)
        response = self._recordsToResponse(records)
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @VerifyPlaintextPasswordCommand.responder
    @inlineCallbacks
    def verifyPlaintextPassword(self, uid, password):
        uid = uid.decode("utf-8")
        log.debug("VerifyPlaintextPassword: {u}", u=uid)
        record = (yield self._directory.recordWithUID(uid))
        authenticated = False
        if record is not None:
            authenticated = (yield record.verifyPlaintextPassword(password))
        response = {
            "authenticated": authenticated,
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @VerifyHTTPDigestCommand.responder
    @inlineCallbacks
    def verifyHTTPDigest(
        self, uid, username, realm, uri, nonce, cnonce,
        algorithm, nc, qop, response, method,
    ):
        uid = uid.decode("utf-8")
        username = username.decode("utf-8")
        realm = realm.decode("utf-8")
        uri = uri.decode("utf-8")
        nonce = nonce.decode("utf-8")
        cnonce = cnonce.decode("utf-8")
        algorithm = algorithm.decode("utf-8")
        nc = nc.decode("utf-8")
        qop = qop.decode("utf-8")
        response = response.decode("utf-8")
        method = method.decode("utf-8")
        log.debug("VerifyHTTPDigest: {u}", u=username)
        record = (yield self._directory.recordWithUID(uid))
        authenticated = False
        if record is not None:
            authenticated = (
                yield record.verifyHTTPDigest(
                    username, realm, uri, nonce, cnonce,
                    algorithm, nc, qop, response, method,
                )
            )
        response = {
            "authenticated": authenticated,
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @WikiAccessForUID.responder
    @inlineCallbacks
    def wikiAccessForUID(self, wikiUID, uid):
        wikiUID = wikiUID.decode("utf-8")
        uid = uid.decode("utf-8")
        log.debug("WikiAccessForUID: {w} {u}", w=wikiUID, u=uid)
        access = WikiAccessLevel.none
        wikiRecord = (yield self._directory.recordWithUID(wikiUID))
        userRecord = (yield self._directory.recordWithUID(uid))
        if wikiRecord is not None and userRecord is not None:
            access = (yield wikiRecord.accessForRecord(userRecord))
        response = {
            "access": access.name.encode("utf-8"),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


class DirectoryProxyAMPFactory(Factory):
    """
    """
    protocol = DirectoryProxyAMPProtocol


    def __init__(self, directory):
        self._directory = directory


    def buildProtocol(self, addr):
        return DirectoryProxyAMPProtocol(self._directory)



class DirectoryProxyOptions(Options):
    optParameters = [[
        "config", "f", DEFAULT_CONFIG_FILE, "Path to configuration file."
    ]]


    def __init__(self, *args, **kwargs):
        super(DirectoryProxyOptions, self).__init__(*args, **kwargs)

        self.overrides = {}


    def _coerceOption(self, configDict, key, value):
        """
        Coerce the given C{val} to type of C{configDict[key]}
        """
        if key in configDict:
            if isinstance(configDict[key], bool):
                value = value == "True"

            elif isinstance(configDict[key], (int, float, long)):
                value = type(configDict[key])(value)

            elif isinstance(configDict[key], (list, tuple)):
                value = value.split(',')

            elif isinstance(configDict[key], dict):
                raise UsageError(
                    "Dict options not supported on the command line"
                )

            elif value == 'None':
                value = None

        return value


    def _setOverride(self, configDict, path, value, overrideDict):
        """
        Set the value at path in configDict
        """
        key = path[0]

        if len(path) == 1:
            overrideDict[key] = self._coerceOption(configDict, key, value)
            return

        if key in configDict:
            if not isinstance(configDict[key], dict):
                raise UsageError(
                    "Found intermediate path element that is not a dictionary"
                )

            if key not in overrideDict:
                overrideDict[key] = {}

            self._setOverride(
                configDict[key], path[1:],
                value, overrideDict[key]
            )


    def opt_option(self, option):
        """
        Set an option to override a value in the config file. True, False, int,
        and float options are supported, as well as comma separated lists. Only
        one option may be given for each --option flag, however multiple
        --option flags may be specified.
        """

        if "=" in option:
            path, value = option.split('=')
            self._setOverride(
                DEFAULT_CONFIG,
                path.split('/'),
                value,
                self.overrides
            )
        else:
            self.opt_option('%s=True' % (option,))

    opt_o = opt_option

    def postOptions(self):
        config.load(self['config'])
        config.updateDefaults(self.overrides)
        self.parent['pidfile'] = None



@implementer(IPlugin, service.IServiceMaker)
class DirectoryProxyServiceMaker(object):

    tapname = "caldav_directoryproxy"
    description = "Directory Proxy Service"
    options = DirectoryProxyOptions


    def makeService(self, options):
        """
        Return a service
        """
        try:
            from setproctitle import setproctitle
        except ImportError:
            pass
        else:
            setproctitle("CalendarServer Directory Proxy Service")

        try:
            directory = directoryFromConfig(config)
        except Exception as e:
            log.error("Failed to create directory service", error=e)
            raise

        log.info("Created directory service")

        return strPortsService(
            "unix:{path}:mode=660".format(
                path=config.DirectoryProxy.SocketPath
            ),
            DirectoryProxyAMPFactory(directory)
        )
