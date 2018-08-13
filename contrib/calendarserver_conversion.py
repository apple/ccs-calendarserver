#!/usr/bin/env python

import grp
import plistlib
import pwd
import os
import subprocess
import sys

USER_NAME = "calendarserver"
GROUP_NAME = "staff"
USER_DIRECTORY = os.path.join("/Users", USER_NAME)
SOURCE_DIRECTORY = os.path.join(USER_DIRECTORY, "ccs-calendarserver")
CONTRIB_DIRECTORY = os.path.join(SOURCE_DIRECTORY, "contrib")
CONF_DIRECTORY = os.path.join(CONTRIB_DIRECTORY, "conf")
BIN_DIRECTORY = os.path.join(SOURCE_DIRECTORY, "bin")
INSTALL_DIRECTORY = os.path.join(USER_DIRECTORY, "CalendarServer")
PREFS_FILE = "/Library/Server/Preferences/Calendar.plist"
LAUNCHD_DIRECTORY = "/Library/LaunchDaemons"

"""
This script is intended to assist with converting a CalendarServer instance 
created and managed by macOS Server to an 'open source' configuration,
effectively cutting ties with macOS Server as a result of the changes
described in "Prepare for changes to macOS Server":
    https://support.apple.com/en-us/HT208312
    https://web.archive.org/web/20180624040241/https://support.apple.com/en-us/HT208312

Additional detailed documentation about the conversion is available, and
includes a set of manual steps that can be performed as an alternative to
running this script, and may be found in a PDF document called
"macOS Server - Service Migration Guide" (v1.2 as of this writing):
    https://developer.apple.com/support/macos-server/macOS-Server-Service-Migration-Guide.pdf
    https://web.archive.org/web/20180813185235/https://developer.apple.com/support/macos-server/macOS-Server-Service-Migration-Guide.pdf
"""

def main():

    if os.getuid() != 0:
        exit("Must be run as root")

    userID = getUserID(USER_NAME)
    if userID is None:
        exit("The {} user does not exist".format(USER_NAME))
    groupID = getGroupID(GROUP_NAME)
    if groupID is None:
        exit("The {} group does not exist".format(GROUP_NAME))

    if not os.path.exists(USER_DIRECTORY):
        exit("The home directory for the Calendar Server user does not exist: {}".format(USER_DIRECTORY))

    serverRoot = "/Library/Server/Calendar and Contacts"
    if os.path.exists(PREFS_FILE):
        prefs = plistlib.readPlist(PREFS_FILE)
        serverRoot = prefs["ServerRoot"]
        if isinstance(serverRoot, unicode):
            serverRoot = serverRoot.encode("utf-8")

    if os.path.exists(serverRoot):
        print("Calendar and Contacts data detected at: {}".format(serverRoot))
    else:
        exit("Calendar and Contacts data not found at: {}".format(serverRoot))

    # Tasks performed as root:
    changeOwnership(serverRoot)
    installLaunchdPlist()

    # Drop privileges:
    os.setgroups([])
    os.setgid(groupID)
    os.setuid(userID)

    # Tasks performed as user 'calendarserver':
    modifyProfile(os.path.join(USER_DIRECTORY, ".profile"))
    install()
    resetPostgresConf(serverRoot)
    for dirName in ("certs", "conf", "run", "logs"):
        fullDirName = os.path.join(INSTALL_DIRECTORY, dirName)
        if not os.path.exists(fullDirName):
            os.mkdir(fullDirName)
    installConfPlist()


def getUserID(username):
    try:
        return pwd.getpwnam(username).pw_uid
    except:
        return None


def getGroupID(groupname):
    try:
        return grp.getgrnam(groupname).gr_gid
    except:
        return None


def modifyProfile(fileName):
    with open(fileName, "a") as f:
        f.write("source CalendarServer/environment.sh\n")


def changeOwnership(directoryName):
    args = [
        "/usr/sbin/chown", "-R", "{}:{}".format(USER_NAME, GROUP_NAME),
        directoryName
    ]
    subprocess.call(args, stdout=sys.stdout, stderr=sys.stderr)


def installLaunchdPlist():
    subprocess.call([
        "/bin/cp",
        os.path.join(CONF_DIRECTORY, "org.calendarserver.plist"),
        LAUNCHD_DIRECTORY
    ], stdout=sys.stdout, stderr=sys.stderr)


def installConfPlist():
    subprocess.call([
        "/bin/cp",
        os.path.join(CONF_DIRECTORY, "calendarserver.plist"),
        os.path.join(INSTALL_DIRECTORY, "conf")
    ], stdout=sys.stdout, stderr=sys.stderr)


def install():
    env = os.environ.copy()
    env["USE_OPENSSL"] = "1"
    subprocess.call([
        os.path.join(BIN_DIRECTORY, "package"),
        INSTALL_DIRECTORY
    ], stdout=sys.stdout, stderr=sys.stderr, cwd=SOURCE_DIRECTORY, env=env)


def resetPostgresConf(serverRoot):
    clusterDir = os.path.join(serverRoot, "Data/Database.xpg/cluster.pg")
    confFile = os.path.join(clusterDir, "postgresql.conf")
    if os.path.exists(confFile):
        os.remove(confFile)
    subprocess.call([
        "/usr/bin/touch", confFile
    ], stdout=sys.stdout, stderr=sys.stderr)


def exit(msg):
    print(msg)
    sys.exit(1)


if __name__ == '__main__':
    main()
