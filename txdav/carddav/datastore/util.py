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

from twistedcaldav.vcard import Component as VCard
from twistedcaldav.vcard import InvalidVCardDataError

from txdav.common.icommondatastore import InvalidObjectResourceError,\
    NoSuchObjectResourceError

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
        component.validForCardDAV()
    except InvalidVCardDataError, e:
        raise InvalidObjectResourceError(e)
        