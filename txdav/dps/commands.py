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
    ]
    response = [
        ('fields', amp.String()),
    ]



class RecordWithUIDCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
    ]
    response = [
        ('fields', amp.String()),
    ]



class RecordWithGUIDCommand(amp.Command):
    arguments = [
        ('guid', amp.String()),
    ]
    response = [
        ('fields', amp.String()),
    ]



class RecordsWithRecordTypeCommand(amp.Command):
    arguments = [
        ('recordType', amp.String()),
    ]
    response = [
        ('fieldsList', amp.String()),
    ]



class RecordsWithEmailAddressCommand(amp.Command):
    arguments = [
        ('emailAddress', amp.String()),
    ]
    response = [
        ('fieldsList', amp.String()),
    ]



class UpdateRecordsCommand(amp.Command):
    arguments = [
        ('fieldsList', amp.String()),
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
        ('fieldsList', amp.String()),
    ]


class GroupsCommand(amp.Command):
    arguments = [
        ('uid', amp.String()),
    ]
    response = [
        ('fieldsList', amp.String()),
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
