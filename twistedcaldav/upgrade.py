##
# Copyright (c) 2008 Apple Inc. All rights reserved.
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

from twisted.web2.dav.fileop import rmdir
from twisted.web2.dav import davxml
from twistedcaldav.directory.directory import DirectoryService
from twistedcaldav.directory.calendaruserproxy import CalendarUserProxyDatabase
from twistedcaldav.log import Logger
from twistedcaldav.ical import Component
from twistedcaldav.scheduling.cuaddress import normalizeCUAddr
from twistedcaldav import caldavxml
from calendarserver.tools.util import getDirectory, dummyDirectoryRecord
import xattr, itertools, os, zlib, hashlib, datetime, pwd, grp
from zlib import compress, decompress
from cPickle import loads as unpickle, PicklingError, UnpicklingError


log = Logger()


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

            log.info("Processing: %s" % (resPath,))
            needsRewrite = False
            with open(resPath) as res:
                data = res.read()

                try:
                    data, fixed = fixBadQuotes(data)
                    if fixed:
                        log.info("Fixing bad quotes in %s" % (resPath,))
                        needsRewrite = True
                except Exception, e:
                    log.error("Error while fixing bad quotes in %s: %s" %
                        (resPath, e))
                    errorOccurred = True
                    continue

                try:
                    data, fixed = normalizeCUAddrs(data, directory)
                    if fixed:
                        log.info("Normalized CUAddrs in %s" % (resPath,))
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

        log.info("Upgrading calendar home: %s" % (homePath,))

        for cal in os.listdir(homePath):
            calPath = os.path.join(homePath, cal)
            log.info("Upgrading calendar: %s" % (calPath,))
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

        return errorOccurred


    def doProxyDatabaseMoveUpgrade(config, uid=-1, gid=-1):

        # See if the old DB is present
        oldDbPath = os.path.join(config.DocumentRoot, "principals",
            CalendarUserProxyDatabase.dbOldFilename)
        if not os.path.exists(oldDbPath):
            # Nothing to be done
            return

        # See if the new one is already present
        newDbPath = os.path.join(config.DataRoot,
            CalendarUserProxyDatabase.dbFilename)
        if os.path.exists(newDbPath):
            # We have a problem - both the old and new ones exist. Stop the server
            # from starting up and alert the admin to this condition
            raise UpgradeError(
                "Upgrade Error: unable to move the old calendar user proxy database at '%s' to '%s' because the new database already exists."
                % (oldDbPath, newDbPath,)
            )

        # Now move the old one to the new location
        try:
            if not os.path.exists(config.DataRoot):
                makeDirsUserGroup(config.DataRoot, uid=uid, gid=gid)
            os.rename(oldDbPath, newDbPath)
        except Exception, e:
            raise UpgradeError(
                "Upgrade Error: unable to move the old calendar user proxy database at '%s' to '%s' due to %s."
                % (oldDbPath, newDbPath, str(e))
            )

        log.info(
            "Moved the calendar user proxy database from '%s' to '%s'."
            % (oldDbPath, newDbPath,)
        )


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



    directory = getDirectory()
    docRoot = config.DocumentRoot


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


    if os.path.exists(docRoot):

        # Look for the /principals/ directory on disk
        oldPrincipals = os.path.join(docRoot, "principals")
        if os.path.exists(oldPrincipals):
            # First move the proxy database and rename it
            doProxyDatabaseMoveUpgrade(config, uid=uid, gid=gid)

            # Now delete the on disk representation of principals
            rmdir(oldPrincipals)
            log.info(
                "Removed the old principal directory at '%s'."
                % (oldPrincipals,)
            )

        calRoot = os.path.join(docRoot, "calendars")
        if os.path.exists(calRoot):

            uidHomes = os.path.join(calRoot, "__uids__")

            # Move calendar homes to new location:

            if os.path.exists(uidHomes):
                for home in os.listdir(uidHomes):

                    # MOR: This assumes no UID is going to be 2 chars or less
                    if len(home) <= 2:
                        continue

                    oldHome = os.path.join(uidHomes, home)
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
                        if record is not None:
                            oldHome = os.path.join(dirPath, shortName)
                            newHome = os.path.join(uidHomes, record.uid[0:2],
                                record.uid[2:4], record.uid)
                            moveCalendarHome(oldHome, newHome, uid=uid, gid=gid)
                    os.rmdir(dirPath)

            # Upgrade calendar homes in the new location:
            for first in os.listdir(uidHomes):
                if len(first) == 2:
                    firstPath = os.path.join(uidHomes, first)
                    for second in os.listdir(firstPath):
                        if len(second) == 2:
                            secondPath = os.path.join(firstPath, second)
                            for home in os.listdir(secondPath):
                                homePath = os.path.join(secondPath, home)
                                if not upgradeCalendarHome(homePath, directory):
                                    errorOccurred = True

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
        except IOError, e:
            log.error("Cannot open %s; skipping migration" %
                (versionFilePath,))
        except ValueError, e:
            log.error("Invalid version number in %s; skipping migration" %
                (versionFilePath,))

    for version, method in upgradeMethods:
        if onDiskVersion < version:
            log.info("Upgrading to version %d" % (version,))
            method(config)
            with open(versionFilePath, "w") as verFile:
                verFile.write(str(version))


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
        msg = "Can't update free-busy href; %s is not in the directory" % shortName
        log.error(msg)
        raise UpgradeError(msg)

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
            log.err("Invalid xattr property value for: %s" % attr)
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

