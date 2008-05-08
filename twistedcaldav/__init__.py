##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
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
WebDAV support for Twisted Web2.

See draft spec: http://ietf.webdav.org/caldav/draft-dusseault-caldav.txt
"""

from twisted.web2.static import File, loadMimeTypes

__all__ = [
    "accesslog",
    "accounting",
    "authkerb",
    "caldavxml",
    "customxml",
    "dateops",
    "db",
    "directory",
    "dropbox",
    "extensions",
    "fileops",
    "ical",
    "icaldav",
    "index",
    "instance",
    "itip",
    "log",
    "principalindex",
    "resource",
    "root",
    "schedule",
    "sql",
    "static",
]

try:
    from twistedcaldav.version import version as __version__
except ImportError:
    __version__ = None

# Load in suitable file extension/content-type map from OS X
File.contentTypes = loadMimeTypes(("/etc/apache2/mime.types", "/etc/httpd/mime.types",))

import twisted.web2.dav.davxml
import twistedcaldav.caldavxml
import twistedcaldav.customxml

twisted.web2.dav.davxml.registerElements(twistedcaldav.caldavxml)
twisted.web2.dav.davxml.registerElements(twistedcaldav.customxml)
