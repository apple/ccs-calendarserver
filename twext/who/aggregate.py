# -*- test-case-name: twext.who.test.test_aggregate -*-
##
# Copyright (c) 2006-2013 Apple Inc. All rights reserved.
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
Directory service which aggregates multiple directory services.
"""

__all__ = [
    "DirectoryService",
    "DirectoryRecord",
]

from itertools import chain

from twisted.internet.defer import gatherResults, FirstError

from twext.who.idirectory import DirectoryConfigurationError
from twext.who.idirectory import IDirectoryService
from twext.who.index import DirectoryService as BaseDirectoryService
from twext.who.index import DirectoryRecord
from twext.who.util import ConstantsContainer


class DirectoryService(BaseDirectoryService):
    """
    Aggregate directory service.
    """

    def __init__(self, realmName, services):
        recordTypes = set()

        for service in services:
            if not IDirectoryService.implementedBy(service.__class__):
                raise ValueError(
                    "Not a directory service: {0}".format(service)
                )

            for recordType in service.recordTypes():
                if recordType in recordTypes:
                    raise DirectoryConfigurationError(
                        "Aggregated services may not vend "
                        "the same record type: {0}"
                        .format(recordType)
                    )
                recordTypes.add(recordType)

        BaseDirectoryService.__init__(self, realmName)

        self._services = tuple(services)


    @property
    def services(self):
        return self._services


    def loadRecords(self):
        pass


    @property
    def recordType(self):
        if not hasattr(self, "_recordType"):
            self._recordType = ConstantsContainer(chain(*tuple(
                s.recordTypes()
                for s in self.services
            )))
        return self._recordType


    def recordsFromExpression(self, expression):
        ds = []
        for service in self.services:
            d = service.recordsFromExpression(expression)
            ds.append(d)

        def unwrapFirstError(f):
            f.trap(FirstError)
            return f.value.subFailure

        d = gatherResults(ds, consumeErrors=True)
        d.addCallback(lambda results: chain(*results))
        d.addErrback(unwrapFirstError)
        return d
