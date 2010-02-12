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
Extend L{twisted.python.filepath} to provide performance enhancements for
calendar server.
"""

from twisted.python.filepath import FilePath

from stat import S_ISDIR

class CachingFilePath(FilePath, object):
    """
    A descendent of L{twisted.python.filepath.FilePath} which implements a more
    aggressive caching policy.
    """

    def __init__(self, path, alwaysCreate=False):
        super(CachingFilePath, self).__init__(path, alwaysCreate)
        self.existsCached = None
        self.isDirCached = None


    def changed(self):
        """
        This path may have changed in the filesystem, so forget all cached
        information about it.
        """
        self.statinfo = None
        self.existsCached = None
        self.isDirCached = None


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
        Override L{FilePath.moveTo}, updating extended cache information if
        necessary.
        """
        try:
            return super(CachingFilePath, self).moveTo(destination, followLinks)
        except OSError:
            raise
        else:
            self.changed()


    def remove(self):
        """
        Override L{FilePath.remove}, updating extended cache information if
        necessary.
        """
        try:
            return super(CachingFilePath, self).remove()
        finally:
            self.changed()

CachingFilePath.clonePath = CachingFilePath

__all__ = ['CachingFilePath']
