# -*- test-case-name: twistedcaldav.test.test_upgrade -*-
##
# Copyright (c) 2008-2010 Apple Inc. All rights reserved.
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

from __future__ import with_statement

import xattr, os, zlib, hashlib, datetime, pwd, grp, shutil
from zlib import compress
from cPickle import loads as unpickle, UnpicklingError

from twext.web2.dav.fileop import rmdir
from twext.web2.dav import davxml

from twext.python.log import Logger

from twistedcaldav.directory.directory import DirectoryService
#from twistedcaldav.directory.resourceinfo import ResourceInfoDatabase
from twistedcaldav.mail import MailGatewayTokensDatabase
from twistedcaldav.ical import Component
from twistedcaldav import caldavxml

from calendarserver.tools.util import getDirectory

log = Logger()

def getCalendarServerIDs(config):

    # Determine uid/gid for ownership of directories we create here
    uid = -1
    if config.UserName:
        try:
            uid = pwd.getpwnam(config.UserName).pw_uid
        except KeyError:
            log.error("User not found: %s" % (config.UserName,))

    gid = -1
    if config.GroupName:
        try:
            gid = grp.getgrnam(config.GroupName).gr_gid
        except KeyError:
            log.error("Group not found: %s" % (config.GroupName,))

    return uid, gid

#
# upgrade_to_1
#
# Upconverts data from any calendar server version prior to data format 1
#

def upgrade_to_1(config):

    errorOccurred = False

    def fixBadQuotes(data):
        if (
            data.find('\\"') != -1 or
            data.find('\\\r\n "') != -1 or
            data.find('\r\n \r\n "') != -1
        ):
            # Fix by continuously replacing \" with " until no more
            # replacements occur
            while True:
                newData = data.replace('\\"', '"').replace('\\\r\n "', '\r\n "').replace('\r\n \r\n "', '\r\n "')
                if newData == data:
                    break
                else:
                    data = newData

            return data, True
        else:
            return data, False



    def normalizeCUAddrs(data, directory):
        cal = Component.fromString(data)

        def lookupFunction(cuaddr):
            try:
                principal = directory.principalForCalendarUserAddress(cuaddr)
            except Exception, e:
                log.debug("Lookup of %s failed: %s" % (cuaddr, e))
                principal = None

            if principal is None:
                return (None, None, None)
            else:
                return (principal.record.fullName.decode("utf-8"),
                    principal.record.guid,
                    principal.record.calendarUserAddresses)

        cal.normalizeCalendarUserAddresses(lookupFunction)

        newData = str(cal)
        return newData, not newData == data


    def upgradeCalendarCollection(calPath, directory):

        errorOccurred = False
        collectionUpdated = False

        for resource in os.listdir(calPath):

            if resource.startswith("."):
                continue

            resPath = os.path.join(calPath, resource)

            if os.path.isdir(resPath):
                # Skip directories
                continue

            log.debug("Processing: %s" % (resPath,))
            needsRewrite = False
            with open(resPath) as res:
                data = res.read()

                try:
                    data, fixed = fixBadQuotes(data)
                    if fixed:
                        log.warn("Fixing bad quotes in %s" % (resPath,))
                        needsRewrite = True
                except Exception, e:
                    log.error("Error while fixing bad quotes in %s: %s" %
                        (resPath, e))
                    errorOccurred = True
                    continue

                try:
                    data, fixed = normalizeCUAddrs(data, directory)
                    if fixed:
                        log.debug("Normalized CUAddrs in %s" % (resPath,))
                        needsRewrite = True
                except Exception, e:
                    log.error("Error while normalizing %s: %s" %
                        (resPath, e))
                    errorOccurred = True
                    continue

            if needsRewrite:
                with open(resPath, "w") as res:
                    res.write(data)

                md5value = "<?xml version='1.0' encoding='UTF-8'?>\r\n<getcontentmd5 xmlns='http://twistedmatrix.com/xml_namespace/dav/'>%s</getcontentmd5>\r\n" % (hashlib.md5(data).hexdigest(),)
                md5value = zlib.compress(md5value)
                xattr.setxattr(resPath, "WebDAV:{http:%2F%2Ftwistedmatrix.com%2Fxml_namespace%2Fdav%2F}getcontentmd5", md5value)

                collectionUpdated = True


        if collectionUpdated:
            ctagValue = "<?xml version='1.0' encoding='UTF-8'?>\r\n<getctag xmlns='http://calendarserver.org/ns/'>%s</getctag>\r\n" % (str(datetime.datetime.now()),)
            ctagValue = zlib.compress(ctagValue)
            xattr.setxattr(calPath, "WebDAV:{http:%2F%2Fcalendarserver.org%2Fns%2F}getctag", ctagValue)

        return errorOccurred


    def upgradeCalendarHome(homePath, directory):

        errorOccurred = False

        log.debug("Upgrading calendar home: %s" % (homePath,))

        try:
            for cal in os.listdir(homePath):
                calPath = os.path.join(homePath, cal)
                if not os.path.isdir(calPath):
                    # Skip non-directories; these might have been uploaded by a
                    # random DAV client, they can't be calendar collections.
                    continue
                if cal == 'notifications':
                    # Delete the old, now obsolete, notifications directory.
                    rmdir(calPath)
                    continue
                log.debug("Upgrading calendar: %s" % (calPath,))
                if not upgradeCalendarCollection(calPath, directory):
                    errorOccurred = True

                # Change the calendar-free-busy-set xattrs of the inbox to the
                # __uids__/<guid> form
                if cal == "inbox":
                    for attr, value in xattr.xattr(calPath).iteritems():
                        if attr == "WebDAV:{urn:ietf:params:xml:ns:caldav}calendar-free-busy-set":
                            value = updateFreeBusySet(value, directory)
                            if value is not None:
                                # Need to write the xattr back to disk
                                xattr.setxattr(calPath, attr, value)

        except Exception, e:
            log.error("Failed to upgrade calendar home %s: %s" % (homePath, e))
            raise

        return errorOccurred


    def doProxyDatabaseMoveUpgrade(config, uid=-1, gid=-1):
        pass
#        # See if the new one is already present
#        newDbPath = os.path.join(config.DataRoot,
#            CalendarUserProxyDatabase.dbFilename)
#        if os.path.exists(newDbPath):
#            # Nothing to be done, it's already in the new location
#            return
#
#        # See if the old DB is present
#        oldDbPath = os.path.join(config.DocumentRoot, "principals",
#            CalendarUserProxyDatabase.dbOldFilename)
#        if not os.path.exists(oldDbPath):
#            # Nothing to be moved
#            return
#
#        # Now move the old one to the new location
#        try:
#            if not os.path.exists(config.DataRoot):
#                makeDirsUserGroup(config.DataRoot, uid=uid, gid=gid)
#            try:
#                os.rename(oldDbPath, newDbPath)
#            except OSError:
#                # Can't rename, must copy/delete
#                shutil.copy2(oldDbPath, newDbPath)
#                os.remove(oldDbPath)
#
#        except Exception, e:
#            raise UpgradeError(
#                "Upgrade Error: unable to move the old calendar user proxy database at '%s' to '%s' due to %s."
#                % (oldDbPath, newDbPath, str(e))
#            )
#
#        log.debug(
#            "Moved the calendar user proxy database from '%s' to '%s'."
#            % (oldDbPath, newDbPath,)
#        )


    def moveCalendarHome(oldHome, newHome, uid=-1, gid=-1):
        if os.path.exists(newHome):
            # Both old and new homes exist; stop immediately to let the
            # administrator fix it
            raise UpgradeError(
                "Upgrade Error: calendar home is in two places: %s and %s.  Please remove one of them and restart calendar server."
                % (oldHome, newHome)
            )

        makeDirsUserGroup(os.path.dirname(newHome.rstrip("/")), uid=uid,
            gid=gid)
        os.rename(oldHome, newHome)


    def migrateResourceInfo(config, directory, uid, gid):
        # TODO: we need to account for the new augments database. This means migrating from the pre-resource info
        # implementation and the resource-info implementation
        pass

#        log.info("Fetching delegate assignments and auto-schedule settings from directory")
#        resourceInfoDatabase = ResourceInfoDatabase(config.DataRoot)
#        calendarUserProxyDatabase = CalendarUserProxyDatabase(config.DataRoot)
#        resourceInfo = directory.getResourceInfo()
#        for guid, autoSchedule, proxy, readOnlyProxy in resourceInfo:
#            resourceInfoDatabase.setAutoScheduleInDatabase(guid, autoSchedule)
#            if proxy:
#                calendarUserProxyDatabase.setGroupMembersInDatabase(
#                    "%s#calendar-proxy-write" % (guid,),
#                    [proxy]
#                )
#            if readOnlyProxy:
#                calendarUserProxyDatabase.setGroupMembersInDatabase(
#                    "%s#calendar-proxy-read" % (guid,),
#                    [readOnlyProxy]
#                )
#
#        dbPath = os.path.join(config.DataRoot, ResourceInfoDatabase.dbFilename)
#        if os.path.exists(dbPath):
#            os.chown(dbPath, uid, gid)
#
#        dbPath = os.path.join(config.DataRoot, CalendarUserProxyDatabase.dbFilename)
#        if os.path.exists(dbPath):
#            os.chown(dbPath, uid, gid)

    def createMailTokensDatabase(config, uid, gid):
        # Cause the tokens db to be created on disk so we can set the
        # permissions on it now
        MailGatewayTokensDatabase(config.DataRoot).lookupByToken("")

        dbPath = os.path.join(config.DataRoot, MailGatewayTokensDatabase.dbFilename)
        if os.path.exists(dbPath):
            os.chown(dbPath, uid, gid)

    def createTaskServiceDirectory(config, uid, gid):

        taskDir = os.path.join(config.DataRoot, "tasks")
        if not os.path.exists(taskDir):
            os.mkdir(taskDir)
        os.chown(taskDir, uid, gid)

        incomingDir = os.path.join(taskDir, "incoming")
        if not os.path.exists(incomingDir):
            os.mkdir(incomingDir)
        os.chown(incomingDir, uid, gid)

        return incomingDir



    directory = getDirectory()

    docRoot = config.DocumentRoot

    uid, gid = getCalendarServerIDs(config)

    if not os.path.exists(config.DataRoot):
        makeDirsUserGroup(config.DataRoot, uid=uid, gid=gid)

    if os.path.exists(docRoot):

        # Look for the /principals/ directory on disk
        oldPrincipals = os.path.join(docRoot, "principals")
        if os.path.exists(oldPrincipals):
            # First move the proxy database and rename it
            doProxyDatabaseMoveUpgrade(config, uid=uid, gid=gid)

            # Now delete the on disk representation of principals
            rmdir(oldPrincipals)
            log.debug(
                "Removed the old principal directory at '%s'."
                % (oldPrincipals,)
            )

        calRoot = os.path.join(docRoot, "calendars")
        if os.path.exists(calRoot):

            uidHomes = os.path.join(calRoot, "__uids__")

            # Move calendar homes to new location:

            log.warn("Moving calendar homes to %s" % (uidHomes,))

            if os.path.exists(uidHomes):
                for home in os.listdir(uidHomes):

                    # MOR: This assumes no UID is going to be 2 chars or less
                    if len(home) <= 2:
                        continue

                    oldHome = os.path.join(uidHomes, home)
                    if not os.path.isdir(oldHome):
                        # Skip non-directories
                        continue

                    newHome = os.path.join(uidHomes, home[0:2], home[2:4], home)
                    moveCalendarHome(oldHome, newHome, uid=uid, gid=gid)

            else:
                os.mkdir(uidHomes)
                os.chown(uidHomes, uid, gid)

            for recordType, dirName in (
                (DirectoryService.recordType_users, "users"),
                (DirectoryService.recordType_groups, "groups"),
                (DirectoryService.recordType_locations, "locations"),
                (DirectoryService.recordType_resources, "resources"),
            ):
                dirPath = os.path.join(calRoot, dirName)
                if os.path.exists(dirPath):
                    for shortName in os.listdir(dirPath):
                        record = directory.recordWithShortName(recordType,
                            shortName)
                        oldHome = os.path.join(dirPath, shortName)
                        if record is not None:
                            newHome = os.path.join(uidHomes, record.uid[0:2],
                                record.uid[2:4], record.uid)
                            moveCalendarHome(oldHome, newHome, uid=uid, gid=gid)
                        else:
                            # an orphaned calendar home (principal no longer
                            # exists in the directory)
                            archive(config, oldHome, uid, gid)

                    os.rmdir(dirPath)


            # Count how many calendar homes we'll be processing, and build
            # list of pending inbox items
            total = 0
            inboxItems = set()
            for first in os.listdir(uidHomes):
                if len(first) == 2:
                    firstPath = os.path.join(uidHomes, first)
                    for second in os.listdir(firstPath):
                        if len(second) == 2:
                            secondPath = os.path.join(firstPath, second)
                            for home in os.listdir(secondPath):
                                total += 1
                                homePath = os.path.join(secondPath, home)
                                inboxPath = os.path.join(homePath, "inbox")
                                if os.path.exists(inboxPath):
                                    for inboxItem in os.listdir(inboxPath):
                                        if not inboxItem.startswith("."):
                                            inboxItems.add(os.path.join(inboxPath, inboxItem))

            incomingDir = createTaskServiceDirectory(config, uid, gid)
            if inboxItems:
                taskFile = os.path.join(incomingDir, "scheduleinboxes.task")
                with open(taskFile, "w") as out:
                    for item in inboxItems:
                        out.write("%s\n" % (item))
                os.chown(taskFile, uid, gid)

            if total:
                log.warn("Processing %d calendar homes in %s" % (total, uidHomes))

                # Upgrade calendar homes in the new location:
                count = 0
                for first in os.listdir(uidHomes):
                    if len(first) == 2:
                        firstPath = os.path.join(uidHomes, first)
                        for second in os.listdir(firstPath):
                            if len(second) == 2:
                                secondPath = os.path.join(firstPath, second)
                                for home in os.listdir(secondPath):
                                    homePath = os.path.join(secondPath, home)


                                    if not upgradeCalendarHome(homePath,
                                        directory):
                                        errorOccurred = True

                                    count += 1
                                    if count % 10 == 0:
                                        log.warn("Processed calendar home %d of %d"
                                            % (count, total))

                log.warn("Done processing calendar homes")

    migrateResourceInfo(config, directory, uid, gid)
    createMailTokensDatabase(config, uid, gid)

    if errorOccurred:
        raise UpgradeError("Data upgrade failed, see error.log for details")


# The on-disk version number (which defaults to zero if .calendarserver_version
# doesn't exist), is compared with each of the numbers in the upgradeMethods
# array.  If it is less than the number, the associated method is called.

upgradeMethods = [
    (1, upgrade_to_1),
]

def upgradeData(config):

    docRoot = config.DocumentRoot

    versionFilePath = os.path.join(docRoot, ".calendarserver_version")

    onDiskVersion = 0
    if os.path.exists(versionFilePath):
        try:
            with open(versionFilePath) as versionFile:
                onDiskVersion = int(versionFile.read().strip())
        except IOError:
            log.error("Cannot open %s; skipping migration" %
                (versionFilePath,))
        except ValueError:
            log.error("Invalid version number in %s; skipping migration" %
                (versionFilePath,))

    uid, gid = getCalendarServerIDs(config)

    for version, method in upgradeMethods:
        if onDiskVersion < version:
            log.warn("Upgrading to version %d" % (version,))
            method(config)
            with open(versionFilePath, "w") as verFile:
                verFile.write(str(version))
            os.chown(versionFilePath, uid, gid)


class UpgradeError(RuntimeError):
    """
    Generic upgrade error.
    """
    pass


#
# Utility functions
#
def updateFreeBusyHref(href, directory):
    pieces = href.split("/")
    if pieces[2] == "__uids__":
        # Already updated
        return None

    recordType = pieces[2]
    shortName = pieces[3]
    record = directory.recordWithShortName(recordType, shortName)
    if record is None:
        # We will simply ignore this and not write out an fb-set entry
        log.error("Can't update free-busy href; %s is not in the directory" % shortName)
        return ""

    uid = record.uid
    newHref = "/calendars/__uids__/%s/%s/" % (uid, pieces[4])
    return newHref


def updateFreeBusySet(value, directory):

    try:
        value = zlib.decompress(value)
    except zlib.error:
        # Legacy data - not zlib compressed
        pass

    try:
        doc = davxml.WebDAVDocument.fromString(value)
        freeBusySet = doc.root_element
    except ValueError:
        try:
            freeBusySet = unpickle(value)
        except UnpicklingError:
            log.err("Invalid free/busy property value")
            # MOR: continue on?
            return None

    fbset = set()
    didUpdate = False
    for href in freeBusySet.children:
        href = str(href)
        newHref = updateFreeBusyHref(href, directory)
        if newHref is None:
            fbset.add(href)
        else:
            didUpdate = True
            if newHref != "":
                fbset.add(newHref)

    if didUpdate:
        property = caldavxml.CalendarFreeBusySet(*[davxml.HRef(href)
            for href in fbset])
        value = compress(property.toxml())
        return value

    return None # no update required


def makeDirsUserGroup(path, uid=-1, gid=-1):
    parts = path.split("/")
    if parts[0] == "": # absolute path
        parts[0] = "/"

    path = ""
    for part in parts:
        if not part:
            continue
        path = os.path.join(path, part)
        if not os.path.exists(path):
            os.mkdir(path)
            os.chown(path, uid, gid)


def archive(config, srcPath, uid, gid):
    """
    Move srcPath into dataroot/archived, giving the destination a unique
    (sequentially numbered) name in the case of duplicates.
    """

    archiveDir = os.path.join(config.DataRoot, "archived")

    if not os.path.exists(archiveDir):
        os.mkdir(archiveDir)
    os.chown(archiveDir, uid, gid)

    baseName = os.path.basename(srcPath)
    newName = baseName
    count = 0
    destPath = os.path.join(archiveDir, newName)
    while os.path.exists(destPath):
        count += 1
        newName = "%s.%d" % (baseName, count)
        destPath = os.path.join(archiveDir, newName)

    try:
        os.rename(srcPath, destPath)
    except OSError:
        # Can't rename, must copy/delete
        shutil.copy2(srcPath, destPath)
        os.remove(srcPath)
