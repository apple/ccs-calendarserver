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

from zope.interface import implementer

from twisted.python.reflect import namedClass
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker



@implementer(IPlugin, IServiceMaker)
class ServiceMakerWrapper(object):
    """
    ServiceMaker that instantiates and wraps a ServiceMaker, given a class name
    and arguments.
    """

    def __init__(self, className, *args, **kwargs):
        """
        @param className: The fully qualified name of the
            L{IServiceMaker}-providing class to instiantiate.
        @type className: L{str}

        @param args: Sequential arguments to pass to the class's constructor.
        @type args: arguments L{list}

        @param kwargs: Keyword arguments to pass to the class's constructor.
        @type args: arguments L{dict}
        """
        self.className = className
        self.args = args
        self.kwargs = kwargs


    @property
    def wrappedServiceMaker(self):
        if not hasattr(self, "_wrappedServiceMaker"):
            makerClass = namedClass(self.className)
            maker = makerClass(*self.args, **self.kwargs)
            self._wrappedServiceMaker = maker

        return self._wrappedServiceMaker


    @property
    def tapname(self):
        return self.wrappedServiceMaker.tapname


    @property
    def description(self):
        return self.wrappedServiceMaker.description


    @property
    def options(self):
        return self.wrappedServiceMaker.options


    def makeService(self, options):
        return self.wrappedServiceMaker.makeService(options)



masterServiceMaker = ServiceMakerWrapper(
    "twext.application.masterchild.MasterServiceMaker"
)

childServiceMaker = ServiceMakerWrapper(
    "twext.application.masterchild.ChildServiceMaker"
)
