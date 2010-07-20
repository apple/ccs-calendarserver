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
Storage interfaces that are not implied by DAV, but are shared between the
requirements for both CalDAV and CardDAV extensions.
"""

from txdav.idav import ITransaction

__all__ = [
    # Exceptions
    "CommonStoreError",
    "NameNotAllowedError",
    "HomeChildNameNotAllowedError",
    "ObjectResourceNameNotAllowedError",
    "AlreadyExistsError",
    "HomeChildNameAlreadyExistsError",
    "ObjectResourceNameAlreadyExistsError",
    "ObjectResourceUIDAlreadyExistsError",
    "NotFoundError",
    "NoSuchHomeChildError",
    "NoSuchObjectResourceError",
    "InvalidObjectResourceError",
    "InternalDataStoreError",
]

#
# Exceptions
#

class CommonStoreError(RuntimeError):
    """
    Store generic error.
    """

class NameNotAllowedError(CommonStoreError):
    """
    Attempt to create an object with a name that is not allowed.
    """

class HomeChildNameNotAllowedError(NameNotAllowedError):
    """
    Home child name not allowed.
    """

class ObjectResourceNameNotAllowedError(NameNotAllowedError):
    """
    Object resource name not allowed.
    """

class AlreadyExistsError(CommonStoreError):
    """
    Attempt to create an object that already exists.
    """

class HomeChildNameAlreadyExistsError(AlreadyExistsError):
    """
    Home child already exists.
    """

class ObjectResourceNameAlreadyExistsError(AlreadyExistsError):
    """
    An object resource with the requested name already exists.
    """

class ObjectResourceUIDAlreadyExistsError(AlreadyExistsError):
    """
    An object resource with the requested UID already exists.
    """

class NotFoundError(CommonStoreError):
    """
    Requested data not found.
    """

class NoSuchHomeChildError(NotFoundError):
    """
    The requested home child does not exist.
    """

class NoSuchObjectResourceError(NotFoundError):
    """
    The requested object resource does not exist.
    """

class InvalidObjectResourceError(CommonStoreError):
    """
    Invalid object resource data.
    """

class InternalDataStoreError(CommonStoreError):
    """
    Uh, oh.
    """

#
# Interfaces
#

class ICommonTransaction(ITransaction):
    """
    Transaction functionality shared in common by calendar and addressbook
    stores.
    """

    def notificationsWithUID(uid):
        """
        Retrieve the notification collection for the principal with the given
        C{uid}.

        @return: an L{INotificationCollection} or C{None} if no such
            notification collection exists.
        """



