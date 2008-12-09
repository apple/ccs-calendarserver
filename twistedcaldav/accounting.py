##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
Extended account-specific logging.
Allows different sub-systems to log data on a per-principal basis.
"""

__all__ = [
    "accountingEnabled",
    "emitAccounting",
]

import datetime
import os

from twistedcaldav.config import config
from twistedcaldav.log import Logger

log = Logger()

def accountingEnabled(category, principal):
    """
    Determine if accounting is enabled for the given category and principal.
    """
    return (
        accountingEnabledForCategory(category) and
        accountingEnabledForPrincipal(principal)
    )

def accountingEnabledForCategory(category):
    """
    Determine if accounting is enabled for the given category.
    """
    return config.AccountingCategories.get(category, False)

def accountingEnabledForPrincipal(principal):
    """
    Determine if accounting is enabled for the given principal.
    """
    enabledPrincipalURIs = config.AccountingPrincipals

    if "*" in enabledPrincipalURIs:
        return True

    if principal.principalURL() in enabledPrincipalURIs:
        return True

    for principal in principal.alternateURIs():
        if principal in enabledPrincipalURIs:
            return True

    return False

def emitAccounting(category, principal, data):
    """
    Write the supplied data to the appropriate location for the given
    category and principal.

    @param principal: the principal for whom a log entry is to be created.
    @type principal: L{DirectoryPrincipalResource}
    @param category: accounting category
    @type category: C{tuple}
    @param data: data to write.
    @type data: C{str}
    """    
    if not accountingEnabled(category, principal):
        return

    try:
        #
        # Obtain the accounting log file name
        #
        logRoot = config.AccountingLogRoot
        logDirectory = os.path.join(
            logRoot,
            principal.record.guid[0:2],
            principal.record.guid[2:4],
            principal.record.guid,
            category
        )
        logFilename = os.path.join(logDirectory, datetime.datetime.now().isoformat())
    
        if not os.path.isdir(logDirectory):
            os.makedirs(logDirectory)
            logFilename = "%s-01" % (logFilename,)
        else:
            index = 1
            while True:
                path = "%s-%02d" % (logFilename, index)
                if not os.path.isfile(path):
                    logFilename = path
                    break
                if index == 1000:
                    log.error("Too many %s accounting files for %s" % (category, principal))
                    return
    
        #
        # Now write out the data to the log file
        #
        logFile = open(logFilename, "a")
        try:
            logFile.write(data)
        finally:
            logFile.close()
    except OSError, e:
        # No failures in accounting should propagate out
        log.error("Failed to write accounting data due to: %s" % (str(e),))
