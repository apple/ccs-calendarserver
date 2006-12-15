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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
Implements a directory-backed principal hierarchy.
"""

__all__ = ["AutoProvisioningResourceMixIn"]

class AutoProvisioningResourceMixIn (object):
    """
    Adds auto-provisioning to a Resource implementation.
    """
    def provision(self):
        """
        Provision this resource by creating any required backing store, etc. that
        must be set up before the resource can be accessed normally.
        FIXME: More description of what that means would be helpful here.  Basically,
        RenderMixIn methods should work (perhaps returning None) without having to
        call this first, so that dirlist can happen, but it is expected that this will
        have been called before anything that involves I/O happens.
        This method may be called multiple times; provisioning code should ensure that
        it handles this properly, typically by returning immediately if the resource is
        already provisioned (eg. the backing store exists).
        @return: a deferred or None.
        """
        return None

    def locateChild(self, *args):
        """
        This implementation calls L{provision}, then super's L{locateChild}, thereby
        ensuring that looked-up resources are provisioned.
        """
        super_method = super(AutoProvisioningResourceMixIn, self).locateChild
        d = self.provision()
        if d is None:
            return super_method(*args)
        else:
            d.addCallback(lambda _: super_method(*args))
            return d
