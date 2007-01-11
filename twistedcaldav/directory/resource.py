##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Implements a directory-backed principal hierarchy.
"""

__all__ = ["AutoProvisioningResourceMixIn"]

from twisted.internet.defer import succeed, maybeDeferred

class AutoProvisioningResourceMixIn (object):
    """
    Adds auto-provisioning to a Resource implementation.
    """
    def provision(self):
        """
        Provision this resource by creating any required backing store, etc. that
        must be set up before the resource can be accessed normally.  Specifically,
        this must have been called before anything that involves I/O happens.
        This method may be called multiple times; provisioning code should ensure that
        it handles this properly, typically by returning immediately if the resource is
        already provisioned (eg. the backing store exists).
        @return: a deferred or None.
        """
        return None

    def provisionChild(self, name):
        """
        Creates the child object with the given name.
        This is basically akin to L{File.createSimilarFile}, but here we know we're
        creating a child of this resource, and take take certain actions to ensure that
        it's prepared appropriately.
        @param name: the name of the child resource.
        @return: the newly created (optionally deferred) child, or None of no resource
            is bound as a child of this resource with the given C{name}.
        """
        return None

    def locateChild(self, request, segments):
        """
        This implementation calls L{provision}, then super's L{locateChild}, thereby
        ensuring that looked-up resources are provisioned.
        """
        name = segments[0]
        if name == "":
            d = succeed(None)
        else:
            d = maybeDeferred(self.provisionChild, name)
        d.addCallback(lambda _: self.provision())
        d.addCallback(lambda _: super(AutoProvisioningResourceMixIn, self).locateChild(request, segments))
        return d
