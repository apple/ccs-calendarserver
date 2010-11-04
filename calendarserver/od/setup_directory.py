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
import odframework
import dsattributes
from getopt import getopt, GetoptError

# TODO: Nested groups
# TODO: GroupMembership

masterNodeName = "/LDAPv3/127.0.0.1"
localNodeName = "/Local/Default"

masterUsers = [
    (
        "odtestamanda",
        {
            dsattributes.kDS1AttrFirstName : ["Amanda"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["Amanda Test"],
            dsattributes.kDSNAttrEMailAddress : ["amanda@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a70-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33300"],
        },
    ),
    (
        "odtestbetty",
        {
            dsattributes.kDS1AttrFirstName : ["Betty"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["Betty Test"],
            dsattributes.kDSNAttrEMailAddress : ["betty@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a71-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33301"],
        },
    ),
    (
        "odtestcarlene",
        {
            dsattributes.kDS1AttrFirstName : ["Carlene"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["Carlene Test"],
            dsattributes.kDSNAttrEMailAddress : ["carlene@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a72-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33302"],
        },
    ),
    (
        "odtestdenise",
        {
            dsattributes.kDS1AttrFirstName : ["Denise"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["Denise Test"],
            dsattributes.kDSNAttrEMailAddress : ["denise@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a73-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33303"],
        },
    ),
]

masterGroups = [
    (
        "odtestgrouptop",
        {
            dsattributes.kDS1AttrGeneratedUID : ["6c6cd280-e6e3-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrDistinguishedName : ["OD Test Group Top"],
            dsattributes.kDSNAttrGroupMembers : ["9dc04a70-e6dd-11df-9492-0800200c9a66", "9dc04a71-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrPrimaryGroupID : ["33400"],
        },
    ),
]

localUsers = [
    (
        "odtestalbert",
        {
            dsattributes.kDS1AttrFirstName : ["Albert"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["Albert Test"],
            dsattributes.kDSNAttrEMailAddress : ["albert@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a74-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33350"],
        },
    ),
    (
        "odtestbill",
        {
            dsattributes.kDS1AttrFirstName : ["Bill"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["Bill Test"],
            dsattributes.kDSNAttrEMailAddress : ["bill@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a75-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33351"],
        },
    ),
    (
        "odtestcarl",
        {
            dsattributes.kDS1AttrFirstName : ["Carl"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["Carl Test"],
            dsattributes.kDSNAttrEMailAddress : ["carl@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a76-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33352"],
        },
    ),
    (
        "odtestdavid",
        {
            dsattributes.kDS1AttrFirstName : ["David"],
            dsattributes.kDS1AttrLastName  : ["Test"],
            dsattributes.kDS1AttrDistinguishedName : ["David Test"],
            dsattributes.kDSNAttrEMailAddress : ["david@example.com"],
            dsattributes.kDS1AttrGeneratedUID : ["9dc04a77-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrUniqueID : ["33353"],
        },
    ),
]

localGroups = [
    (
        "odtestsubgroupa",
        {
            dsattributes.kDS1AttrGeneratedUID : ["6c6cd281-e6e3-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrDistinguishedName : ["OD Test Subgroup A"],
            dsattributes.kDSNAttrGroupMembers : ["9dc04a74-e6dd-11df-9492-0800200c9a66", "9dc04a75-e6dd-11df-9492-0800200c9a66"],
            dsattributes.kDS1AttrPrimaryGroupID : ["33400"],
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
    query, error = odframework.ODQuery.queryWithNode_forRecordTypes_attribute_matchType_queryValues_returnAttributes_maximumResults_error_(
        node,
        recordType,
        dsattributes.kDSNAttrRecordName,
        dsattributes.eDSExact,
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


    session = odframework.ODSession.defaultSession()

    for nodeName, info in userInfo.iteritems():

        userName = info["user"]
        password = info["password"]
        users = info["users"]
        groups = info["groups"]

        node, error = odframework.ODNode.nodeWithSession_name_error_(session, nodeName, None)
        if error:
            print error
            raise ODError(error)

        result, error = node.setCredentialsWithRecordType_recordName_password_error_(
            dsattributes.kDSStdRecordTypeUsers,
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
            record = lookupRecordName(node, dsattributes.kDSStdRecordTypeUsers, recordName)
            if record is None:
                print "Creating user %s" % (recordName,)
                try:
                    record = createRecord(node, dsattributes.kDSStdRecordTypeUsers, recordName, attrs)
                    print "Successfully created user %s" % (recordName,)
                    result, error = record.changePassword_toPassword_error_(
                        None, "password", None)
                    if error or not result:
                        print "Failed to set password for %s: %s" % (recordName, error)
                    else:
                        print "Successfully set password for %s" % (recordName,)
                except ODError, e:
                    print "Failed to create user %s: %s" % (recordName, e)
            else:
                print "User %s already exists" % (recordName,)

        print "Creating groups within %s:" % (nodeName,)
        for recordName, attrs in groups:
            record = lookupRecordName(node, dsattributes.kDSStdRecordTypeGroups, recordName)
            if record is None:
                print "Creating group %s" % (recordName,)
                try:
                    record = createRecord(node, dsattributes.kDSStdRecordTypeGroups, recordName, attrs)
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
