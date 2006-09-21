##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
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
# DRI: Cyrus Daboo, cdaboo@apple.com
##

"""
Principal Index.

Defines an index for use with directory-based principal collections. Its stores information
derived from principal resource dead properties that are used when comparing the directory entries
with those cached locally.

"""

from twistedcaldav import customxml
from twistedcaldav.db import AbstractIndex
from twistedcaldav.db import db_basename

__version__ = "0.0"

__all__ = [
    "UserIndex",
    "GroupIndex",
    "ResourceIndex",
]

schema_version = "1"
collection_types = {
    "Users"    : "User Principals",
    "Groups"   : "Group Principals",
    "Resources": "Resource Principals",
}

class PrincipalIndex(AbstractIndex):
    """
    Principal index - abstract class for indexer that indexes principal objects in a collection.
    """
    
    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index.
        """
        super(PrincipalIndex, self).__init__(resource)

    def check(self):
        """
        Verify that the index is valid.
        """
        
        # Just run a name test - that will force the db to open, be checked etc
        self.hasName("Bogus")

        # Now verify that index entries have a corresponding child
        indexnames = set(self.listNames())
        filenames = set(self.resource.listFileChildren())
        extranames = indexnames.difference(filenames)
        for name in extranames:
            self.deleteName(name)
            
    def commit(self):
        self._db_commit()

    def nameFromGUID(self, guid):
        """
        Looks up the name of the resource with the given GUID.

        @param guid: the guid of the resource to look up.
        @return: C{str} name of the resource if found; C{None} otherwise.
        """
        return self._db_value_for_sql("select NAME from PRINCIPAL where GUID = :1", guid)

    def addPrincipal(self, name, principal, fast=False):
        """
        Adding or updating an existing principal.
        
        @param name: the name of the principal to add.
        @param principal: the L{DirectoryPrincipalFile} to add.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        """
        
        # Need these imports here to avoid circular dependency with twistedcaldav.directory
        if self.hasGUID(principal.getGUID()):
            self._delete_from_db(guid=principal.getGUID())
        self._add_to_db(name,
                        principal.getPropertyValue(customxml.TwistedGUIDProperty),
                        principal.getPropertyValue(customxml.TwistedLastModifiedProperty),
                        principal.getPropertyValue(customxml.TwistedCalendarPrincipalURI))
        if not fast:
            self._db_commit()

    def addName(self, name, guid, lastModified, uri, params=None, fast=False): #@UnusedVariable
        """
        Adding or updating an existing principal.
        
        @param name: the name of the principal to add.
        @param guid: the guid of the principal to add.
        @param lastModified: the last-modified value of the directory entry of the principal to add.
        @param uri: the calendar principal uri of the principal to add.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        """
        if self.hasGUID(guid):
            self._delete_from_db(guid=guid)
        self._add_to_db(name, guid, lastModified, uri)
        if not fast:
            self._db_commit()

    def deleteName(self, name, fast=False):
        """
        Remove this principal from the index.
        
        @param name: the name of the principal to delete.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        """
        if self.hasName(name) is not None:
            self._delete_from_db(name=name)
            if not fast:
                self._db_commit()
    
    def deleteGUID(self, guid, fast=False):
        """
        Remove this principal from the index.
        
        @param guid: the guid of the principal to delete.
        @param fast: if C{True} then final commit is not done, if C{False} commit is done.
        """
        if self.hasGUID(guid) is not None:
            self._delete_from_db(guid=guid)
            if not fast:
                self._db_commit()
    
    def hasName(self, name):
        """
        Determines whether the specified principal name exists in the index.
        
        @param name: the name of the principal to test
        @return: C{True} if the resource exists, C{False} if not
        """
        test = self._db_value_for_sql("select NAME from PRINCIPAL where NAME = :1", name)
        return test is not None
    
    def hasGUID(self, guid):
        """
        Determines whether the specified principal guid exists in the index.
        
        @param guid: the guid of the principal to test
        @return: C{True} if the resource exists, C{False} if not
        """
        test = self._db_value_for_sql("select GUID from PRINCIPAL where GUID = :1", guid)
        return test is not None
    
    def listNames(self):
        """
        List all the names current in the index.
        
        @return: a C{list} of all names.
        """
        
        return self._db_values_for_sql("select NAME from PRINCIPAL")

    def listIndex(self):
        """
        List all the primary index record values. These are name, guid and last-modified.
        
        @return: a C{list} of all C{tuples}.
        """
        
        return self._db_execute("select NAME, GUID, LASTMODIFIED, PRINCIPALURI from PRINCIPAL")

    def _db_version(self):
        """
        @return: the schema version assigned to this index.
        """
        return schema_version
        
    def _db_init_data_tables(self, q):
        """
        Initialise the underlying database tables.
    
        @param q: a database cursor to use.
        """
        q.execute(
            """
            create table PRINCIPAL (
                NAME           text unique,
                GUID           text unique,
                LASTMODIFIED   text,
                PRINCIPALURI   text
            )
            """
        )
        
    def _add_to_db(self, name, guid, lastModified, uri):
        """
        @param name: the name of the principal to add.
        @param guid: the guid of the principal to add.
        @param lastModified: the last-modified value of the directory entry of the principal to add.
        @param uri: the calendar principal uri of the principal to add.
        """
        self._db_execute(
            "insert into PRINCIPAL (NAME, GUID, LASTMODIFIED, PRINCIPALURI) values (:1, :2, :3, :4)", 
            name, guid, lastModified, uri
        )
    
    def _delete_from_db(self, name=None, guid=None):
        """
        Deletes the specified entry from all dbs.
        
        @param name: the name of the resource to delete.
        @param guid: the guid of the resource to delete.
        """
        if name is not None:
            self._db_execute("delete from PRINCIPAL where NAME = :1", name)
        elif guid is not None:
            self._db_execute("delete from PRINCIPAL where GUID = :1", guid)
    
    def _db_recreate(self):
        """
        Populate the DB with data from already existing resources.
        This allows for index recovery if the DB file gets deleted.
        """

        for name in self.resource.listFileChildren():
            if name == db_basename: continue
            principal = self.resource.getChild(name)
            #if not isinstance(principal, DirectoryPrincipalFile): continue
            self.addPrincipal(name, principal, True)
        
        # Do commit outside of the loop for better performance
        self._db_commit()

class UserIndex (PrincipalIndex):
    """
    Index for user principals.
    """
    
    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index. C{resource} must be a calendar collection (ie.
            C{resource.isPseudoCalendarCollection()} returns C{True}.)
        """
        super(UserIndex, self).__init__(resource)

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return collection_types["Users"]
        
class GroupIndex (PrincipalIndex):
    """
    Index for group principals.
    """
    
    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index. C{resource} must be a calendar collection (ie.
            C{resource.isPseudoCalendarCollection()} returns C{True}.)
        """
        super(GroupIndex, self).__init__(resource)

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return collection_types["Groups"]
        
class ResourceIndex (PrincipalIndex):
    """
    Index for resource principals.
    """
    
    def __init__(self, resource):
        """
        @param resource: the L{twistedcaldav.static.CalDAVFile} resource to
            index. C{resource} must be a calendar collection (ie.
            C{resource.isPseudoCalendarCollection()} returns C{True}.)
        """
        super(ResourceIndex, self).__init__(resource)

    def _db_type(self):
        """
        @return: the collection type assigned to this index.
        """
        return collection_types["Resources"]
