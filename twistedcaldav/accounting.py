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
Extended account-specific logging.
Allows different sub-systems to log data on a per-principal basis.
"""

__all__ = [
    "accountingEnabled",
    "emitAccounting",
]

import datetime
import os

from twext.python.log import Logger

from twistedcaldav.config import config

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
    AccountingCategories = getattr(config, "AccountingCategories", None)
    if AccountingCategories is None:
        return False
    return AccountingCategories.get(category, False)

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

def emitAccounting(category, principal, data, tag=None):
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
    if isinstance(principal, str):
        principalLogPath = principal
    elif accountingEnabled(category, principal):
        principalLogPath = os.path.join(
            principal.record.guid[0:2],
            principal.record.guid[2:4],
            principal.record.guid
        )
    else:
        return None

    try:
        #
        # Obtain the accounting log file name
        #
        logRoot = config.AccountingLogRoot
        logDirectory = category
        if principalLogPath:
            logDirectory = os.path.join(
                logDirectory,
                principalLogPath,
            )
        logFilename = os.path.join(
            logDirectory,
            datetime.datetime.now().isoformat()
        )
    
        if not os.path.isdir(os.path.join(logRoot, logDirectory)):
            os.makedirs(os.path.join(logRoot, logDirectory))
            logFilename = "%s-01" % (logFilename,)
            if tag:
                logFilename += " (%s)" % (tag,)
            logFilename += ".txt"
        else:
            index = 1
            while True:
                path = "%s-%02d" % (logFilename, index)
                if tag:
                    path += " (%s)" % (tag,)
                path += ".txt"
                if not os.path.isfile(os.path.join(logRoot, path)):
                    logFilename = path
                    break
                if index == 1000:
                    log.error("Too many %s accounting files for %s" % (category, principal))
                    return None
                index += 1
    
        #
        # Now write out the data to the log file
        #
        logFile = open(os.path.join(logRoot, logFilename), "a")
        try:
            logFile.write(data)
        finally:
            logFile.close()
            
        return logFilename

    except OSError, e:
        # No failures in accounting should propagate out
        log.error("Failed to write accounting data due to: %s" % (str(e),))
        return None
