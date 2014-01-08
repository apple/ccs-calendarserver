##
# Copyright (c) 2011-2014 Apple Inc. All rights reserved.
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
A small utility for defining static class properties.
"""

class classproperty(object):
    """
    Decorator for a method that wants to return a static class property.  The
    decorated method will only be invoked once, for each class, and that value
    will be returned for that class.
    """

    def __init__(self, thunk=None, cache=True):
        self.cache = cache
        self.thunk = thunk
        self._classcache = {}


    def __call__(self, thunk):
        return self.__class__(thunk, self.cache)


    def __get__(self, instance, owner):
        if not self.cache:
            return self.thunk(owner)
        cc = self._classcache
        if owner in cc:
            cached = cc[owner]
        else:
            cached = self.thunk(owner)
            cc[owner] = cached
        return cached

