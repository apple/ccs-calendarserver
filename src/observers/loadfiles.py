##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

from src.observers.base import BaseResultsObserver

class Observer(BaseResultsObserver):
    """
    A results observer that prints when a test file is loaded.
    """

    def updateCalls(self):
        super(Observer, self).updateCalls()
        self._calls.update({
            "load": self.load,
        })


    def load(self, name, current, total):
        """
        Message triggered when loading a script file.

        @param name: name of file being loaded, or L{None} for last file
        @type name: L{str}
        @param current: current number of files loaded
        @type current: L{int}
        @param total: total number of files to load
        @type total: L{int}
        """

        if name is not None:
            self.manager.logit("Loading {current} of {total}: {name}".format(current=current, total=total, name=name))
        else:
            self.manager.logit("Loading files complete.\n")
