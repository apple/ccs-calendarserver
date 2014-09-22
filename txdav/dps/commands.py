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

from twisted.protocols import amp


class RecordWithShortNameCommand(amp.Command):
    arguments = [
        ('recordType', amp.String()),
        ('shortName', amp.String()),
        ('timeoutSeconds', amp.Integer(optional=True)),
    ]
    response = [
        ('fields', amp.String()),
    ]



class RecordWithUIDCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
        ('timeoutSeconds', amp.Integer(optional=True)),
    ]
    response = [
        ('fields', amp.String()),
    ]



class RecordWithGUIDCommand(amp.Command):
    arguments = [
        ('guid', amp.String()),
        ('timeoutSeconds', amp.Integer(optional=True)),
    ]
    response = [
        ('fields', amp.String()),
    ]



class RecordsWithRecordTypeCommand(amp.Command):
    arguments = [
        ('recordType', amp.String()),
        ('limitResults', amp.Integer(optional=True)),
        ('timeoutSeconds', amp.Integer(optional=True)),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class RecordsWithEmailAddressCommand(amp.Command):
    arguments = [
        ('emailAddress', amp.String()),
        ('limitResults', amp.Integer(optional=True)),
        ('timeoutSeconds', amp.Integer(optional=True)),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class ContinuationCommand(amp.Command):
    arguments = [
        ('continuation', amp.String(optional=True)),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class RecordsMatchingTokensCommand(amp.Command):
    arguments = [
        ('tokens', amp.ListOf(amp.String())),
        ('context', amp.String(optional=True)),
        ('limitResults', amp.Integer(optional=True)),
        ('timeoutSeconds', amp.Integer(optional=True)),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class RecordsMatchingFieldsCommand(amp.Command):
    arguments = [
        ('fields', amp.ListOf(amp.ListOf(amp.String()))),
        ('operand', amp.String()),
        ('recordType', amp.String(optional=True)),
        ('limitResults', amp.Integer(optional=True)),
        ('timeoutSeconds', amp.Integer(optional=True)),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class UpdateRecordsCommand(amp.Command):
    arguments = [
        ('uids', amp.ListOf(amp.String())),
        ('create', amp.Boolean(optional=True)),
    ]
    response = [
        ('success', amp.Boolean()),
    ]



class RemoveRecordsCommand(amp.Command):
    arguments = [
        ('uids', amp.ListOf(amp.String())),
    ]
    response = [
        ('success', amp.Boolean()),
    ]



class MembersCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class GroupsCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class AddMembersCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
        ('memberUIDs', amp.ListOf(amp.String())),
    ]
    response = [
        ('success', amp.Boolean()),
    ]



class RemoveMembersCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
        ('memberUIDs', amp.ListOf(amp.String())),
    ]
    response = [
        ('success', amp.Boolean()),
    ]



class SetMembersCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
        ('memberUIDs', amp.ListOf(amp.String())),
    ]
    response = [
        ('success', amp.Boolean()),
    ]



class ExpandedMemberUIDsCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
    ]
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class VerifyPlaintextPasswordCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
        ('password', amp.String()),
    ]
    response = [
        ('authenticated', amp.Boolean()),
    ]



class VerifyHTTPDigestCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
        ('username', amp.String()),
        ('realm', amp.String()),
        ('uri', amp.String()),
        ('nonce', amp.String()),
        ('cnonce', amp.String()),
        ('algorithm', amp.String()),
        ('nc', amp.String()),
        ('qop', amp.String()),
        ('response', amp.String()),
        ('method', amp.String()),
    ]
    response = [
        ('authenticated', amp.Boolean()),
    ]



class WikiAccessForUIDCommand(amp.Command):
    arguments = [
        ('wikiUID', amp.String()),
        ('uid', amp.String()),
    ]
    response = [
        ('access', amp.String()),
    ]



class ExternalDelegatesCommand(amp.Command):
    arguments = []
    response = [
        ('items', amp.ListOf(amp.String())),
        ('continuation', amp.String(optional=True)),
    ]



class StatsCommand(amp.Command):
    arguments = []
    response = [
        ('stats', amp.String()),
    ]
