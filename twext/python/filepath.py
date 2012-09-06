# -*- test-case-name: twext.python.test.test_filepath -*-
##
# Copyright (c) 2010-2012 Apple Inc. All rights reserved.
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
Extend L{twisted.python.filepath} to provide performance enhancements for
calendar server.
"""

from os import listdir as _listdir

from os.path import (join as _joinpath,
                     basename as _basename,
                     exists as _exists,
                     dirname as _dirname)

from time import sleep as _sleep
from types import FunctionType, MethodType
from errno import EINVAL

from twisted.python.filepath import FilePath as _FilePath

from stat import S_ISDIR

class CachingFilePath(_FilePath, object):
    """
    A descendent of L{_FilePath} which implements a more aggressive caching
    policy.
    """

    _listdir = _listdir         # integration points for tests
    _sleep = _sleep

    BACKOFF_MAX = 5.0           # Maximum time to wait between calls to
                                # listdir()

    def __init__(self, path, alwaysCreate=False):
        super(CachingFilePath, self).__init__(path, alwaysCreate)
        self.existsCached = None
        self.isDirCached = None


    @property
    def siblingExtensionSearch(self):
        """
        Dynamically create a version of L{_FilePath.siblingExtensionSearch} that
        uses a pluggable 'listdir' implementation.
        """
        return MethodType(FunctionType(
                _FilePath.siblingExtensionSearch.im_func.func_code,
                {'listdir': self._retryListdir,
                 'basename': _basename,
                 'dirname': _dirname,
                 'joinpath': _joinpath,
                 'exists': _exists}), self, self.__class__)


    def changed(self):
        """
        This path may have changed in the filesystem, so forget all cached
        information about it.
        """
        self.statinfo = None
        self.existsCached = None
        self.isDirCached = None


    def _retryListdir(self, pathname):
        """
        Implementation of retry logic for C{listdir} and
        C{siblingExtensionSearch}.
        """
        delay = 0.1
        while True:
            try:
                return self._listdir(pathname)
            except OSError, e:
                if e.errno == EINVAL:
                    self._sleep(delay)
                    delay = min(self.BACKOFF_MAX, delay * 2.0)
                else:
                    raise
        raise RuntimeError("unreachable code.")


    def listdir(self):
        """
        List the directory which C{self.path} points to, compensating for
        EINVAL from C{os.listdir}.
        """
        return self._retryListdir(self.path)


    def restat(self, reraise=True):
        """
        Re-cache stat information.
        """
        try:
            return super(CachingFilePath, self).restat(reraise)
        finally:
            if self.statinfo:
                self.existsCached = True
                self.isDirCached = S_ISDIR(self.statinfo.st_mode)
            else:
                self.existsCached = False
                self.isDirCached = None


    def moveTo(self, destination, followLinks=True):
        """
        Override L{_FilePath.moveTo}, updating extended cache information if
        necessary.
        """
        result = super(CachingFilePath, self).moveTo(destination, followLinks)
        self.changed()
        # Work with vanilla FilePath destinations to pacify the tests. 
        if hasattr(destination, "changed"):
            destination.changed()
        return result


    def remove(self):
        """
        Override L{_FilePath.remove}, updating extended cache information if
        necessary.
        """
        try:
            return super(CachingFilePath, self).remove()
        finally:
            self.changed()

CachingFilePath.clonePath = CachingFilePath

__all__ = ["CachingFilePath"]
