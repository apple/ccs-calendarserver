##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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

__all__ = [
    "CardDAVServiceMaker",
]

from zope.interface import implements

from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker

from twistedcaldav.stdconfig import DEFAULT_CARDDAV_CONFIG_FILE
from twext.log import Logger

log = Logger()

from calendarserver.tap.caldav import CalDAVServiceMaker, CalDAVOptions

try:
    from twistedcaldav.authkerb import NegotiateCredentialFactory
except ImportError:
    NegotiateCredentialFactory = None



class CardDAVOptions(CalDAVOptions):
    """
    The same as L{CalDAVOptions}, but with a different default config file.
    """

    optParameters = [[
        "config", "f", DEFAULT_CARDDAV_CONFIG_FILE, "Path to configuration file."
    ]]



class CardDAVServiceMaker (CalDAVServiceMaker):
    implements(IPlugin, IServiceMaker)

    tapname = "carddav"
    description = "Darwin Contacts Server"
    options = CardDAVOptions
