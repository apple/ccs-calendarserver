# -*- test-case-name: twext.who.test.test_util -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Directory service module utilities.
"""

__all__ = [
    "ConstantsContainer",
    "uniqueResult",
    "describe",
    "iterFlags",
]

from twisted.python.constants import FlagConstant

from twext.who.idirectory import DirectoryServiceError



class ConstantsContainer(object):
    """
    A container for constants.
    """
    def __init__(self, constants):
        myConstants = {}
        for constant in constants:
            if constant.name in myConstants:
                raise ValueError("Name conflict: %r" % (constant.name,))
            myConstants[constant.name] = constant

        self._constants = myConstants

    def __getattr__(self, name):
        try:
            return self._constants[name]
        except KeyError:
            raise AttributeError(name)

    def iterconstants(self):
        return self._constants.itervalues()

    def lookupByName(self, name):
        try:
            return self._constants[name]
        except KeyError:
            raise ValueError(name)


def uniqueResult(values):
    result = None
    for value in values:
        if result is None:
            result = value
        else:
            raise DirectoryServiceError(
                "Multiple values found where one expected."
            )
    return result


def describe(constant):
    if isinstance(constant, FlagConstant):
        parts = []
        for flag in iterFlags(constant):
            parts.append(getattr(flag, "description", flag.name))
        return "|".join(parts)
    else:
        return getattr(constant, "description", constant.name)


def iterFlags(flags):
    if hasattr(flags, "__iter__"):
        return flags
    else:
        # Work around http://twistedmatrix.com/trac/ticket/6302
        # FIXME: This depends on a private attribute (flags._container)
        return (flags._container.lookupByName(name) for name in flags.names)
