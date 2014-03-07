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
import os
import uuid

from calendarserver.tap.util import getDBPool, storeFromConfig
from twext.python.log import Logger
from twext.who.aggregate import DirectoryService as AggregateDirectoryService
from twext.who.expression import (
    MatchType, Operand, MatchExpression, CompoundExpression, MatchFlags
)
from twext.who.idirectory import RecordType
from twext.who.ldap import DirectoryService as LDAPDirectoryService
from twisted.application import service
from twisted.application.strports import service as strPortsService
from twisted.cred.credentials import UsernamePassword
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.protocol import Factory
from twisted.plugin import IPlugin
from twisted.protocols import amp
from twisted.python.constants import Names, NamedConstant
from twisted.python.filepath import FilePath
from twisted.python.reflect import namedClass
from twisted.python.usage import Options, UsageError
from twistedcaldav.config import config
from twistedcaldav.stdconfig import DEFAULT_CONFIG, DEFAULT_CONFIG_FILE
from txdav.dps.commands import (
    RecordWithShortNameCommand, RecordWithUIDCommand, RecordWithGUIDCommand,
    RecordsWithRecordTypeCommand, RecordsWithEmailAddressCommand,
    RecordsMatchingTokensCommand,
    MembersCommand, GroupsCommand, SetMembersCommand,
    VerifyPlaintextPasswordCommand, VerifyHTTPDigestCommand,
    # UpdateRecordsCommand, RemoveRecordsCommand
)
from txdav.who.augment import AugmentedDirectoryService
from txdav.who.delegates import DirectoryService as DelegateDirectoryService
from txdav.who.xml import DirectoryService as XMLDirectoryService
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
            RecordType.lookupByName(recordType))
        )
        fieldsList = []
        for record in records:
            fieldsList.append(self.recordToDict(record))
        response = {
            "fieldsList": pickle.dumps(fieldsList),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordsWithEmailAddressCommand.responder
    @inlineCallbacks
    def recordsWithEmailAddress(self, emailAddress):
        emailAddress = emailAddress.decode("utf-8")
        log.debug("RecordsWithEmailAddress: {e}", e=emailAddress)
        records = (yield self._directory.recordsWithEmailAddress(emailAddress))
        fieldsList = []
        for record in records:
            fieldsList.append(self.recordToDict(record))
        response = {
            "fieldsList": pickle.dumps(fieldsList),
        }
        log.debug("Responding with: {response}", response=response)
        returnValue(response)


    @RecordsMatchingTokensCommand.responder
    @inlineCallbacks
    def recordsMatchingTokens(self, tokens, context=None):
        tokens = [t.decode("utf-8") for t in tokens]

        log.debug("RecordsMatchingTokens: {t}", t=(", ".join(tokens)))

        fields = [
            ("fullNames", MatchType.contains),
            ("emailAddresses", MatchType.startsWith),
        ]
        outer = []
        for token in tokens:
            inner = []
            for name, matchType in fields:
                inner.append(
                    MatchExpression(
                        self._directory.fieldName.lookupByName(name),
                        token,
                        matchType,
                        MatchFlags.caseInsensitive
                    )
                )
            outer.append(
                CompoundExpression(
                    inner,
                    Operand.OR
                )
            )
        expression = CompoundExpression(outer, Operand.AND)
        records = yield self._directory.recordsFromExpression(expression)

        fieldsList = []
        for record in records:
            fieldsList.append(self.recordToDict(record))
        response = {
            "fieldsList": pickle.dumps(fieldsList),
        }
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

        fieldsList = []
        if record is not None:
            for member in (yield record.members()):
                fieldsList.append(self.recordToDict(member))
        response = {
            "fieldsList": pickle.dumps(fieldsList),
        }
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

        fieldsList = []
        for group in (yield record.groups()):
            fieldsList.append(self.recordToDict(group))
        response = {
            "fieldsList": pickle.dumps(fieldsList),
        }
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



def directoryFromConfig(config, store=None):
    """
    Return a directory service based on the config
    """
    directoryType = config.DirectoryProxy.DirectoryType
    args = config.DirectoryProxy.Arguments
    kwds = config.DirectoryProxy.Keywords

    # FIXME: this needs to talk to its own separate database
    pool, txnFactory = getDBPool(config)
    if store is None:
        store = storeFromConfig(config, txnFactory, None)

    if directoryType == "OD":
        from twext.who.opendirectory import DirectoryService as ODDirectoryService
        primaryDirectory = ODDirectoryService(*args, **kwds)

    elif directoryType == "LDAP":
        authDN = kwds.pop("authDN", "")
        password = kwds.pop("password", "")
        if authDN and password:
            creds = UsernamePassword(authDN, password)
        else:
            creds = None
        kwds["credentials"] = creds
        debug = kwds.pop("debug", "")
        primaryDirectory = LDAPDirectoryService(
            *args, _debug=debug, **kwds
        )

    elif directoryType == "XML":
        path = kwds.pop("path", "")
        if not path or not os.path.exists(path):
            log.error("Path not found for XML directory: {p}", p=path)
        fp = FilePath(path)
        primaryDirectory = XMLDirectoryService(fp, *args, **kwds)

    else:
        log.error("Invalid DirectoryType: {dt}", dt=directoryType)

    #
    # Setup the Augment Service
    #
    if config.AugmentService.type:
        augmentClass = namedClass(config.AugmentService.type)
        log.info(
            "Configuring augment service of type: {augmentClass}",
            augmentClass=augmentClass
        )
        try:
            augmentService = augmentClass(**config.AugmentService.params)
        except IOError:
            log.error("Could not start augment service")
            raise
    else:
        augmentService = None

    delegateDirectory = DelegateDirectoryService(
        primaryDirectory.realmName,
        store
    )

    aggregateDirectory = AggregateDirectoryService(
        primaryDirectory.realmName,
        (primaryDirectory, delegateDirectory)
    )
    try:
        augmented = AugmentedDirectoryService(
            aggregateDirectory, store, augmentService
        )

        # The delegate directory needs a way to look up user/group records
        # so hand it a reference to the augmented directory.
        # FIXME: is there a better pattern to use here?
        delegateDirectory.setMasterDirectory(augmented)

    except Exception as e:
        log.error("Could not create directory service", error=e)
        raise

    return augmented


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
            print("XZZZY AAA")
            directory = directoryFromConfig(config)
            print("XZZZY BBB")
        except Exception as e:
            log.error("Failed to create directory service", error=e)
            raise

        log.info("Created directory service")
        print("XZZZY CCCC")

        return strPortsService(
            "unix:{path}:mode=660".format(
                path=config.DirectoryProxy.SocketPath
            ),
            DirectoryProxyAMPFactory(directory)
        )
