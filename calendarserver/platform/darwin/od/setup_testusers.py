##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
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
from __future__ import print_function

import os
import sys
import odframework
import dsattributes
from getopt import getopt, GetoptError


def usage(e=None):
    name = os.path.basename(sys.argv[0])
    print("usage: %s [options] local_user local_password" % (name,))
    print("")
    print(" Configures local directory for test users")
    print("")
    print("options:")
    print(" -h --help: print this help and exit")
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
        print(error)
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

    if len(args) != 2:
        usage()

    localUser, localPassword = args

    session = odframework.ODSession.defaultSession()

    nodeName = "/Local/Default"
    node, error = odframework.ODNode.nodeWithSession_name_error_(session, nodeName, None)
    if error:
        print(error)
        raise ODError(error)

    result, error = node.setCredentialsWithRecordType_recordName_password_error_(
        dsattributes.kDSStdRecordTypeUsers,
        localUser,
        localPassword,
        None
    )
    if error:
        print("Unable to authenticate with directory %s: %s" % (nodeName, error))
        raise ODError(error)

    print("Successfully authenticated with directory %s" % (nodeName,))

    print("Creating users within %s:" % (nodeName,))
    for i in xrange(99):
        j = i+1
        recordName = "user%02d" % (j,)
        password = "user%02d" % (j,)
        attrs = {
            dsattributes.kDS1AttrFirstName : ["User"],
            dsattributes.kDS1AttrLastName  : ["%02d" % (j,)],
            dsattributes.kDS1AttrDistinguishedName : ["User %02d" % (j,)],
            dsattributes.kDSNAttrEMailAddress : ["user%02d@example.com" % (j,)],
            dsattributes.kDS1AttrGeneratedUID : ["user%02d" % (j,)],
        }

        record = lookupRecordName(node, dsattributes.kDSStdRecordTypeUsers, recordName)
        if record is None:
            print("Creating user %s" % (recordName,))
            try:
                record = createRecord(node, dsattributes.kDSStdRecordTypeUsers, recordName, attrs)
                print("Successfully created user %s" % (recordName,))
                result, error = record.changePassword_toPassword_error_(
                    None, password, None)
                if error or not result:
                    print("Failed to set password for %s: %s" % (recordName, error))
                else:
                    print("Successfully set password for %s" % (recordName,))
            except ODError, e:
                print("Failed to create user %s: %s" % (recordName, e))
        else:
            print("User %s already exists" % (recordName,))


class ODError(Exception):
    def __init__(self, error):
        self.message = (str(error), error.code())

if __name__ == "__main__":
    main()
