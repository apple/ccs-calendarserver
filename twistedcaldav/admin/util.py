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
#
# DRI: David Reid, dreid@apple.com
##

import xattr

import commands

from twisted.web import microdom

from twistedcaldav import ical
 
def prepareByteValue(config, value):
    if config.get('human', None):
        KB = value/1024.0
        if KB < 1:
            return '%d' % (value,)

        MB = KB/1024.0
        if MB < 1:
            return '%5.2fKB' % (KB,)

        GB = MB/1024.0
        if GB < 1:
            return '%5.2fMB' % (MB,)

        return '%5.2fGB' % (GB,)

    elif config.get('gigabytes', None):
        G = value/1024.0/1024.0/1024.0

        return '%5.2fGB' % (G,)

    elif config.get('megabytes', None):
        M = value/1024.0/1024.0

        return '%5.2fMB' % (M,)

    elif config.get('kilobytes', None):
        K = value/1024.0
        return '%5.2fKB' % (K,)

    return value


def getPrincipalList(principalCollection, type, disabled=False):
    typeRoot = principalCollection.child(type)

    pl = []
    
    for child in typeRoot.listdir():
        if child not in ['.db.sqlite']:
            p = typeRoot.child(child)

            if disabled:
                if isPrincipalDisabled(p):
                    pl.append(p)
            else:
                pl.append(p)

    return pl


def getDiskUsage(config, fp):
    status, output = commands.getstatusoutput(
        ' '.join(['/usr/bin/du', '-s', fp.path]))
    
    if status != 0:
        return 0

    return prepareByteValue(config, int(output.split()[0]))


def getResourceType(fp):
    rt = 'WebDAV:{DAV:}resourcetype'
    x = xattr.xattr(fp.path)
    if not x.has_key(rt):
        return None
    
    collection = False

    type = None

    dom = microdom.parseString(x[rt])
    rt = microdom.getElementsByTagName(dom, 'resourcetype')

    for child in rt[0].childNodes:
        if child.tagName == 'collection':
            collection = True
        else:
            type = child.tagName

    return (collection, type)


def getCalendarDataCounts(calendarCollection):
    calCount = 0
    eventCount = 0
    todoCount = 0

    for child in calendarCollection.walk():
        if child.isdir():
            if getResourceType(child) == (True, 'calendar'):
                calCount += 1

        elif child.isfile():
            try:
                component = ical.Component.fromStream(child.open())
            except ValueError:
                # not a calendar file
                continue
            
            if component.resourceType() == 'VEVENT':
                eventCount += 1
                
            elif component.resourceType() == 'VTODO':
                todoCount += 1

    return {'calendarCount': calCount, 
            'eventCount': eventCount,
            'todoCount': todoCount}


def isPrincipalDisabled(principal):
    return False


from twisted.web2.dav.resource import TwistedQuotaRootProperty, TwistedQuotaUsedProperty

quotaRoot = "WebDAV:" + TwistedQuotaRootProperty.sname().replace("/", "%2F")
quotaUsed = "WebDAV:" + TwistedQuotaUsedProperty.sname().replace("/", "%2F")

def getQuotaRoot(fp):
    x = xattr.xattr(fp.path)
    if not x.has_key(quotaRoot):
        return None

    dom = microdom.parseString(x[quotaRoot])

    qr = microdom.getElementsByTagName(dom, 'quota-root')[0]

    return int(qr.firstChild().value)


def getQuotaUsed(fp):
    x = xattr.xattr(fp.path)
    if not x.has_key(quotaUsed):
        return None

    dom = microdom.parseString(x[quotaUsed])

    qu = microdom.getElementsByTagName(dom, 'quota-used')[0]

    return int(qu.firstChild().value)


def getQuotaStatsForPrincipal(config, principal, defaultQuota=None, depth=2):
    quotaRoot = principal

    principalQuota = getQuotaRoot(quotaRoot)

    while not principalQuota and depth > 0:
        depth -= 1
        quotaRoot = quotaRoot.parent()
        principalQuota = getQuotaRoot(quotaRoot)

    if not principalQuota:
        principalQuota = defaultQuota

    principalUsed = getQuotaUsed(principal)
    if not principalUsed:
        principalUsed = 0
        
    principalAvail = principalQuota - principalUsed
    principalFree = (float(principalAvail)/principalQuota)*100

    return {'quotaRoot': prepareByteValue(config, principalQuota), 
            'quotaUsed': prepareByteValue(config, principalUsed),
            'quotaAvail': prepareByteValue(config, principalAvail),
            'quotaFree': principalFree}
