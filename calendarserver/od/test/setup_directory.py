##
# Copyright (c) 2010 Apple Inc. All rights reserved.
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

import os
import sys
import OpenDirectory
from getopt import getopt, GetoptError

# TODO: Nested groups
# TODO: GroupMembership

masterNodeName = "/LDAPv3/127.0.0.1"
localNodeName = "/Local/Default"

masterUsers = [
    (
        "odtestamanda",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["Amanda"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeFullName : ["Amanda Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["amanda@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a70-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33300"],
        },
    ),
    (
        "odtestbetty",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["Betty"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeFullName : ["Betty Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["betty@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a71-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33301"],
        },
    ),
    (
        "odtestcarlene",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["Carlene"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["carlene@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a72-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33302"],
        },
    ),
    (
        "odtestdenise",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["Denise"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["denise@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a73-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33303"],
        },
    ),
]

masterGroups = [
    (
        "odtestgrouptop",
        {
            OpenDirectory.kODAttributeTypeGUID : ["6c6cd280-e6e3-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeFullName : ["OD Test Group Top"],
            OpenDirectory.kODAttributeTypeGroupMembers : ["9dc04a70-e6dd-11df-9492-0800200c9a66", "9dc04a71-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypePrimaryGroupID : ["33400"],
        },
    ),
]

localUsers = [
    (
        "odtestalbert",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["Albert"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeFullName : ["Albert Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["albert@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a74-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33350"],
        },
    ),
    (
        "odtestbill",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["Bill"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeFullName : ["Bill Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["bill@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a75-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33351"],
        },
    ),
    (
        "odtestcarl",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["Carl"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["carl@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a76-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33352"],
        },
    ),
    (
        "odtestdavid",
        {
            OpenDirectory.kODAttributeTypePassword : ["password"],
            OpenDirectory.kODAttributeTypeFirstName : ["David"],
            OpenDirectory.kODAttributeTypeLastName  : ["Test"],
            OpenDirectory.kODAttributeTypeEMailAddress : ["david@example.com"],
            OpenDirectory.kODAttributeTypeGUID : ["9dc04a77-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeUniqueID : ["33353"],
        },
    ),
]

localGroups = [
    (
        "odtestsubgroupa",
        {
            OpenDirectory.kODAttributeTypeGUID : ["6c6cd281-e6e3-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypeFullName : ["OD Test Subgroup A"],
            OpenDirectory.kODAttributeTypeGroupMembers : ["9dc04a74-e6dd-11df-9492-0800200c9a66", "9dc04a75-e6dd-11df-9492-0800200c9a66"],
            OpenDirectory.kODAttributeTypePrimaryGroupID : ["33400"],
        },
    ),
]


def usage(e=None):
    name = os.path.basename(sys.argv[0])
    print "usage: %s [options] local_user local_password odmaster_user odmaster_password" % (name,)
    print ""
    print " Configures local and OD master directories for testing"
    print ""
    print "options:"
    print " -h --help: print this help and exit"
    if e:
        sys.exit(1)
    else:
        sys.exit(0)


def lookupRecordName(node, recordType, name):
    query, error = OpenDirectory.ODQuery.queryWithNode_forRecordTypes_attribute_matchType_queryValues_returnAttributes_maximumResults_error_(
        node,
        recordType,
        OpenDirectory.kODAttributeTypeRecordName,
        OpenDirectory.kODMatchEqualTo,
        name,
        None,
        0,
        None)
    if error:
        raise ODError(error)
    records, error = query.resultsAllowingPartial_error_(False, None)
    if error:
        raise ODError(error)

    if len(records) < 1:
        return None
    if len(records) > 1:
        raise ODError("Multiple records for '%s' were found" % (name,))

    return records[0]

def createRecord(node, recordType, recordName, attrs):
    record, error = node.createRecordWithRecordType_name_attributes_error_(
        recordType,
        recordName,
        attrs,
        None)
    if error:
        print error
        raise ODError(error)
    return record

def main():

    try:
        (optargs, args) = getopt(sys.argv[1:], "h", ["help"])
    except GetoptError, e:
        usage(e)

    for opt, arg in optargs:
        if opt in ("-h", "--help"):
            usage()

    if len(args) != 4:
        usage()

    localUser, localPassword, masterUser, masterPassword = args

    userInfo = {
        masterNodeName : {
            "user" : masterUser,
            "password" : masterPassword,
            "users" : masterUsers,
            "groups" : masterGroups,
        },
        localNodeName : {
            "user" : localUser,
            "password" : localPassword,
            "users" : localUsers,
            "groups" : localGroups,
        },
    }


    session = OpenDirectory.ODSession.defaultSession()

    for nodeName, info in userInfo.iteritems():

        userName = info["user"]
        password = info["password"]
        users = info["users"]
        groups = info["groups"]

        node, error = OpenDirectory.ODNode.nodeWithSession_name_error_(session, nodeName, None)
        if error:
            print error
            raise ODError(error)

        result, error = node.setCredentialsWithRecordType_recordName_password_error_(
            OpenDirectory.kODRecordTypeUsers,
            userName,
            password,
            None
        )
        if error:
            print "Unable to authenticate with directory %s: %s" % (nodeName, error)
            raise ODError(error)

        print "Successfully authenticated with directory %s" % (nodeName,)

        print "Creating users within %s:" % (nodeName,)
        for recordName, attrs in users:
            record = lookupRecordName(node, OpenDirectory.kODRecordTypeUsers, recordName)
            if record is None:
                print "Creating user %s" % (recordName,)
                try:
                    record = createRecord(node, OpenDirectory.kODRecordTypeUsers, recordName, attrs)
                    print "Successfully created user %s" % (recordName,)
                except ODError, e:
                    print "Failed to create user %s: %s" % (recordName, e)
            else:
                print "User %s already exists" % (recordName,)

        print "Creating groups within %s:" % (nodeName,)
        for recordName, attrs in groups:
            record = lookupRecordName(node, OpenDirectory.kODRecordTypeGroups, recordName)
            if record is None:
                print "Creating group %s" % (recordName,)
                try:
                    record = createRecord(node, OpenDirectory.kODRecordTypeGroups, recordName, attrs)
                    print "Successfully created group %s" % (recordName,)
                except ODError, e:
                    print "Failed to create group %s: %s" % (recordName, e)
            else:
                print "Group %s already exists" % (recordName,)

        print



class ODError(Exception):
    def __init__(self, error):
        self.message = (str(error), error.code())

if __name__ == "__main__":
    main()
