##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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
OpenDirectory.framework access via PyObjC
"""

import OpenDirectory
import objc
from twext.python.log import Logger

log = Logger()

# Single-value attributes (must be converted from lists):
SINGLE_VALUE_ATTRIBUTES = [
    OpenDirectory.kODAttributeTypeBirthday,
    OpenDirectory.kODAttributeTypeComment,
    OpenDirectory.kODAttributeTypeCreationTimestamp,
    OpenDirectory.kODAttributeTypeFullName,
    OpenDirectory.kODAttributeTypeFirstName,
    OpenDirectory.kODAttributeTypeGUID,
    OpenDirectory.kODAttributeTypeLastName,
    OpenDirectory.kODAttributeTypeMiddleName,
    OpenDirectory.kODAttributeTypeModificationTimestamp,
    OpenDirectory.kODAttributeTypeNote,
    OpenDirectory.kODAttributeTypeSearchPath,
    OpenDirectory.kODAttributeTypeUserCertificate,
    OpenDirectory.kODAttributeTypeUserPKCS12Data,
    OpenDirectory.kODAttributeTypeUserSMIMECertificate,
    OpenDirectory.kODAttributeTypeWeblogURI,
]


class Directory(object):
    """ Encapsulates OpenDirectory session and node """

    def __init__(self, session, node, nodeName):
        self.session = session
        self.node = node
        self.nodeName = nodeName

    def __str__(self):
        return "OpenDirectory node: %s" % (self.nodeName)


caseInsensitiveEquivalents = {
    OpenDirectory.kODMatchBeginsWith : OpenDirectory.kODMatchInsensitiveBeginsWith,
    OpenDirectory.kODMatchContains : OpenDirectory.kODMatchInsensitiveContains,
    OpenDirectory.kODMatchEndsWith : OpenDirectory.kODMatchInsensitiveEndsWith,
    OpenDirectory.kODMatchEqualTo : OpenDirectory.kODMatchInsensitiveEqualTo,
}

def adjustMatchType(matchType, caseInsensitive):
    """ Return the case-insensitive equivalent matchType """
    return caseInsensitiveEquivalents[matchType] if caseInsensitive else matchType

def recordToResult(record):
    """
    Takes an ODRecord and turns it into a (recordName, attributesDictionary)
    tuple.  Only unicode values are returned. (Not sure what to do with
    non-unicode values)
    """
    details, error = record.recordDetailsForAttributes_error_(None, None)
    if error:
        log.error(error)
        raise ODError(error)
    result = {}
    for key, value in details.iteritems():
        if key in SINGLE_VALUE_ATTRIBUTES:
            if len(value) == 0:
                result[key] = None
            else:
                if isinstance(value[0], objc.pyobjc_unicode):
                    result[key] = unicode(value[0]) # convert from pyobjc
        else:
            result[key] = [unicode(v) for v in value if isinstance(v, objc.pyobjc_unicode)]

    return (details.get(OpenDirectory.kODAttributeTypeRecordName, [None])[0], result)

def odInit(nodeName):
    """
    Create an Open Directory object to operate on the specified directory service node name.

    @param nodeName: C{str} containing the node name.
    @return: C{object} an object to be passed to all subsequent functions on success,
        C{None} on failure.
    """
    session = OpenDirectory.ODSession.defaultSession()
    node, error = OpenDirectory.ODNode.nodeWithSession_name_error_(session,
        nodeName, None)
    if error:
        log.error(error)
        raise ODError(error)

    return Directory(session, node, nodeName)


def getNodeAttributes(directory, nodeName, attributes):
    """
    Return key attributes for the specified directory node. The attributes
    can be a C{str} for the attribute name, or a C{tuple} or C{list} where the first C{str}
    is the attribute name, and the second C{str} is an encoding type, either "str" or "base64".

    @param directory: C{Directory} the object obtained from an odInit call.
    @param nodeName: C{str} containing the OD nodeName to query.
    @param attributes: C{list} or C{tuple} containing the attributes to return for each record.
    @return: C{dict} of attributes found.
    """
    details, error = directory.node.nodeDetailsForKeys_error_(attributes, None)
    if error:
        log.error(error)
        raise ODError(error)
    return details


def listAllRecordsWithAttributes_list(directory, recordType, attributes, count=0):
    """
    List records in Open Directory, and return key attributes for each one.
    The attributes can be a C{str} for the attribute name, or a C{tuple} or C{list} where the first C{str}
    is the attribute name, and the second C{str} is an encoding type, either "str" or "base64".

    @param directory: C{Directory} the object obtained from an odInit call.
    @param recordType: C{str}, C{tuple} or C{list} containing the OD record types to lookup.
    @param attributes: C{list} or C{tuple} containing the attributes to return for each record.
    @param count: C{int} maximum number of records to return (zero returns all).
    @return: C{list} containing a C{list} of C{str} (record name) and C{dict} attributes
        for each record found, or C{None} otherwise.
    """
    query, error = OpenDirectory.ODQuery.queryWithNode_forRecordTypes_attribute_matchType_queryValues_returnAttributes_maximumResults_error_(
        directory.node,
        recordType,
        None,
        OpenDirectory.kODMatchAny,
        None,
        attributes,
        count,
        None)
    if error:
        log.error(error)
        raise ODError(error)
    records, error = query.resultsAllowingPartial_error_(False, None)
    if error:
        log.error(error)
        raise ODError(error)
    for record in records:
        yield recordToResult(record)

def queryRecordsWithAttribute_list(directory, attr, value, matchType, casei, recordType, attributes, count=0):
    """
    List records in Open Directory matching specified attribute/value, and return key attributes for each one.
    The attributes can be a C{str} for the attribute name, or a C{tuple} or C{list} where the first C{str}
    is the attribute name, and the second C{str} is an encoding type, either "str" or "base64".

    @param directory: C{Directory} the object obtained from an odInit call.
    @param attr: C{str} containing the attribute to search.
    @param value: C{str} containing the value to search for.
    @param matchType: C{int} DS match type to use when searching.
    @param casei: C{True} to do case-insensitive match, C{False} otherwise.
    @param recordType: C{str}, C{tuple} or C{list} containing the OD record types to lookup.
    @param attributes: C{list} or C{tuple} containing the attributes to return for each record.
    @param count: C{int} maximum number of records to return (zero returns all).
    @return: C{list} containing a C{list} of C{str} (record name) and C{dict} attributes
        for each record found, or C{None} otherwise.
    """

    query, error = OpenDirectory.ODQuery.queryWithNode_forRecordTypes_attribute_matchType_queryValues_returnAttributes_maximumResults_error_(
        directory.node,
        recordType,
        attr,
        adjustMatchType(matchType, casei),
        value,
        attributes,
        count,
        None)
    if error:
        log.error(error)
        raise ODError(error)
    records, error = query.resultsAllowingPartial_error_(False, None)
    if error:
        log.error(error)
        raise ODError(error)
    for record in records:
        yield recordToResult(record)


def queryRecordsWithAttributes_list(directory, compound, casei, recordType, attributes, count=0):
    """
    List records in Open Directory matching specified criteria, and return key attributes for each one.
    The attributes can be a C{str} for the attribute name, or a C{tuple} or C{list} where the first C{str}
    is the attribute name, and the second C{str} is an encoding type, either "str" or "base64".

    @param directory: C{Directory} the object obtained from an odInit call.
    @param compound: C{str} containing the compound search query to use.
    @param casei: C{True} to do case-insensitive match, C{False} otherwise.
    @param recordType: C{str}, C{tuple} or C{list} containing the OD record types to lookup.
    @param attributes: C{list} or C{tuple} containing the attributes to return for each record.
    @param count: C{int} maximum number of records to return (zero returns all).
    @return: C{list} containing a C{list} of C{str} (record name) and C{dict} attributes
        for each record found, or C{None} otherwise.
    """
    query, error = OpenDirectory.ODQuery.queryWithNode_forRecordTypes_attribute_matchType_queryValues_returnAttributes_maximumResults_error_(
        directory.node,
        recordType,
        None,
        0x210B, # adjustMatchType(matchType, casei),
        compound,
        attributes,
        count,
        None)
    if error:
        log.error(error)
        raise ODError(error)
    records, error = query.resultsAllowingPartial_error_(False, None)
    if error:
        log.error(error)
        raise ODError(error)
    for record in records:
        yield recordToResult(record)


def getUserRecord(directory, user):
    """
    Look up the record for the given user within the directory's node

    @param directory: C{Directory} the object obtained from an odInit call.
    @param user: C{str} the user identifier/directory record name to fetch.
    @return: OD record if the user was found, None otherwise.
    """
    record, error = directory.node.recordWithRecordType_name_attributes_error_(
        OpenDirectory.kODRecordTypeUsers,
        user,
        None,
        None
    )
    if error:
        log.error(error)
        raise ODError(error)
    return record

def authenticateUserBasic(directory, nodeName, user, password):
    """
    Authenticate a user with a password to Open Directory.

    @param directory: C{Directory} the object obtained from an odInit call.
    @param nodeName: C{str} the directory nodeName for the record to check.
    @param user: C{str} the user identifier/directory record name to check.
    @param pswd: C{str} containing the password to check.
    @return: C{True} if the user was found, C{False} otherwise.
    """
    record = getUserRecord(directory, user)
    if record is None:
        raise ODError("Record not found")

    result, error = record.verifyPassword_error_(password, None)
    if error:
        log.error(error)
        raise ODError(error)
    return result


def authenticateUserDigest(directory, nodeName, user, challenge, response, method):
    """
    Authenticate using HTTP Digest credentials to Open Directory.

    @param directory: C{Directory} the object obtained from an odInit call.
    @param nodeName: C{str} the directory nodeName for the record to check.
    @param user: C{str} the user identifier/directory record name to check.
    @param challenge: C{str} the HTTP challenge sent to the client.
    @param response: C{str} the HTTP response sent from the client.
    @param method: C{str} the HTTP method being used.
    @return: C{True} if the user was found, C{False} otherwise.
    """
    record = getUserRecord(directory, user)
    if record is None:
        raise ODError("Record not found")

    # TODO: what are these other return values?
    result, mystery1, mystery2, error = record.verifyExtendedWithAuthenticationType_authenticationItems_continueItems_context_error_(
        OpenDirectory.kODAuthenticationTypeDIGEST_MD5,
        [user, challenge, response, method],
        None, None, None
    )
    if error:
        log.error(error)
        raise ODError(error)
    return result

class ODError(Exception):
    """
    Exceptions from DirectoryServices errors.
    """
    def __init__(self, error):
        self.message = (str(error), error.code())
