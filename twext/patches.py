##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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
Patches for behavior in Twisted which calendarserver requires to be different.
"""

__all__ = []

import sys

from twisted import version
from twisted.python.versions import Version
from twisted.python.modules import getModule

def _hasIPv6ClientSupport():
    """
    Does the loaded version of Twisted have IPv6 client support?
    """
    lastVersionWithoutIPv6Clients = Version("twisted", 12, 0, 0)
    if version > lastVersionWithoutIPv6Clients:
        return True
    elif version == lastVersionWithoutIPv6Clients:
        # It could be a snapshot of trunk or a branch with this bug fixed. Don't
        # load the module, though, as that would be a bunch of unnecessary work.
        return "_resolveIPv6" in (getModule("twisted.internet.tcp")
                                  .filePath.getContent())
    else:
        return False



def _addBackports():
    """
    We currently require 2 backported bugfixes from a future release of Twisted,
    for IPv6 support:

        - U{IPv6 client support <http://tm.tl/5085>}

        - U{TCP endpoint cancellation <http://tm.tl/4710>}

    This function will activate those backports.  (Note it must be run before
    any of the modules in question are imported or it will raise an exception.)

    This function, L{_hasIPv6ClientSupport}, and all the associated backports
    (i.e., all of C{twext/backport}) should be removed upon upgrading our
    minimum required Twisted version.
    """
    from twext.backport import internet as bpinternet
    from twisted import internet
    internet.__path__[:] = bpinternet.__path__ + internet.__path__

    # Make sure none of the backports are loaded yet.
    backports = getModule("twext.backport.internet")
    for submod in backports.iterModules():
        subname = submod.name.split(".")[-1]
        tiname = 'twisted.internet.' + subname
        if tiname in sys.modules:
            raise RuntimeError(
                tiname + "already loaded, cannot load required backport")



if not _hasIPv6ClientSupport():
    _addBackports()



from twisted.mail.imap4 import Command

Command._1_RESPONSES += tuple(['BYE'])
