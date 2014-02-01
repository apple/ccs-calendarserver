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
import sys

log = Logger()



def makeBetterRequest():

    shortName = sys.argv[1]

    ds = DirectoryService(None)
    d = ds.recordWithShortName(RecordType.user, shortName)

    def gotResults(record):
        print('Done: %s' % (record,))
        reactor.stop()

    def gotError(failure):
        print("Failure: %s" % (failure,))
        reactor.stop()

    d.addCallbacks(gotResults, gotError)
    reactor.run()

if __name__ == '__main__':
    makeBetterRequest()
