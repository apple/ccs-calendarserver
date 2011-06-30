# -*- test-case-name: txdav.carddav.datastore.test.test_sql -*-
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

"""
Utility logic common to multiple backend implementations.
"""
from twisted.internet.defer import inlineCallbacks

from twistedcaldav.vcard import Component as VCard
from twistedcaldav.vcard import InvalidVCardDataError

from txdav.common.icommondatastore import InvalidObjectResourceError, \
    NoSuchObjectResourceError, InternalDataStoreError

from twext.python.log import Logger
log = Logger()


def validateAddressBookComponent(addressbookObject, vcard, component, inserting):
    """
    Validate an addressbook component for a particular addressbook.

    @param addressbookObject: The addressbook object whose component will be replaced.
    @type addressbookObject: L{IAddressBookObject}

    @param addressbook: The addressbook which the L{IAddressBookObject} is present in.
    @type addressbook: L{IAddressBook}

    @param component: The VComponent to be validated.
    @type component: L{VComponent}
    """

    if not isinstance(component, VCard):
        raise TypeError(type(component))

    try:
        if not inserting and component.resourceUID() != addressbookObject.uid():
            raise InvalidObjectResourceError(
                "UID may not change (%s != %s)" % (
                    component.resourceUID(), addressbookObject.uid()
                 )
            )
    except NoSuchObjectResourceError:
        pass

    try:
        component.validVCardData()
        component.validForCardDAV()
    except InvalidVCardDataError, e:
        raise InvalidObjectResourceError(e)



@inlineCallbacks
def _migrateAddressbook(inAddressbook, outAddressbook, getComponent):
    """
    Copy all addressbook objects and properties in the given input addressbook
    to the given output addressbook.

    @param inAddressbook: the L{IAddressbook} to retrieve addressbook objects
        from.
    @param outAddressbook: the L{IAddressbook} to store addressbook objects to.
    @param getComponent: a 1-argument callable; see L{migrateHome}.
    """
    outAddressbook.properties().update(inAddressbook.properties())
    inObjects = yield inAddressbook.addressbookObjects()
    for addressbookObject in inObjects:
        
        try:
            component = (yield addressbookObject.component()) # XXX WRONG SHOULD CALL getComponent
            component.md5 = addressbookObject.md5()
            yield outAddressbook.createAddressBookObjectWithName(
                addressbookObject.name(),
                component,
            )
    
            # Only the owner's properties are migrated, since previous releases of
            # addressbook server didn't have per-user properties.
            outObject = yield outAddressbook.addressbookObjectWithName(
                addressbookObject.name())
            if outAddressbook.objectResourcesHaveProperties():
                outObject.properties().update(addressbookObject.properties())


        except InternalDataStoreError:
            log.error("  Failed to migrate adress book object: %s/%s/%s" % (
                inAddressbook.ownerHome().name(),
                inAddressbook.name(),
                addressbookObject.name(),
            ))



@inlineCallbacks
def migrateHome(inHome, outHome, getComponent=lambda x:x.component()):
    yield outHome.removeAddressBookWithName("addressbook")
    outHome.properties().update(inHome.properties())
    inAddressbooks = yield inHome.addressbooks()
    for addressbook in inAddressbooks:
        name = addressbook.name()
        yield outHome.createAddressBookWithName(name)
        outAddressbook = yield outHome.addressbookWithName(name)
        try:
            yield _migrateAddressbook(addressbook, outAddressbook, getComponent)
        except InternalDataStoreError:
            log.error("  Failed to migrate address book: %s/%s" % (inHome.name(), name,))



