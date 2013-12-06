##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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

__import__("twext") # install patches before doing anything

from zope.interface import implements
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker

from twisted.python import reflect

from twisted.internet.protocol import Factory
Factory.noisy = False

def serviceMakerProperty(propname):
    def getProperty(self):
        return getattr(reflect.namedClass(self.serviceMakerClass), propname)

    return property(getProperty)



class TAP(object):
    implements(IPlugin, IServiceMaker)

    def __init__(self, serviceMakerClass):
        self.serviceMakerClass = serviceMakerClass
        self._serviceMaker = None

    options = serviceMakerProperty("options")
    tapname = serviceMakerProperty("tapname")
    description = serviceMakerProperty("description")

    def makeService(self, options):
        if self._serviceMaker is None:
            self._serviceMaker = reflect.namedClass(self.serviceMakerClass)()

        return self._serviceMaker.makeService(options)


TwistedCalDAV = TAP("calendarserver.tap.caldav.CalDAVServiceMaker")
