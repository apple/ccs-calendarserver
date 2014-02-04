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

from txdav.dps.service import DirectoryService
from twext.who.idirectory import RecordType
from twext.python.log import Logger
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

import sys

log = Logger()


@inlineCallbacks
def makeEvenBetterRequest():
    shortName = sys.argv[1]

    ds = DirectoryService(None)
    record = (yield ds.recordWithShortName(RecordType.user, shortName))
    print("A: {r}".format(r=record))
    record = (yield ds.recordWithShortName(RecordType.user, shortName))
    print("B: {r}".format(r=record))


def succeeded(result):
    print("yay")
    reactor.stop()


def failed(failure):
    print("boo: {f}".format(f=failure))
    reactor.stop()

if __name__ == '__main__':
    d = makeEvenBetterRequest()
    d.addCallbacks(succeeded, failed)
    reactor.run()
