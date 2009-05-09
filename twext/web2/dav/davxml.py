##
# Copyright (c) 2005-2009 Apple Inc. All rights reserved.
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
Extensions to twisted.web2.dav.davxml
"""

__all__ = [
    "sname2qname",
    "qname2sname",
]

def sname2qname(sname):
    """
    Convert an sname into a qname.

    That is, parse a property name string (eg: C{"{DAV:}displayname"})
    into a tuple (eg: C{("DAV:", "displayname")}).

    @raise ValueError is input is not valid. Note, however, that this
    function does not attempt to fully validate C{sname}.
    """
    def raiseIf(condition):
        if condition:
            raise ValueError("Invalid sname: %s" % (sname,))

    raiseIf(not sname.startswith("{"))

    try:
        i = sname.index("}")
    except ValueError:
        raiseIf(True)

    namespace = sname[1:i]
    name = sname [i+1:]

    raiseIf("{" in namespace or not name)

    return namespace, name

def qname2sname(qname):
    """
    Convert a qname into an sname.
    """
    try:
        return "{%s}%s" % qname
    except TypeError:
        raise ValueError("Invalid qname: %r" % (qname,))
