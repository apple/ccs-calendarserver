##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
CardDAV multiget report
"""

__all__ = ["report_urn_ietf_params_xml_ns_carddav_addressbook_multiget"]

from twext.python.log import Logger

from twistedcaldav.carddavxml import carddav_namespace
from twistedcaldav.method.report_common import COLLECTION_TYPE_ADDRESSBOOK
from twistedcaldav.method.report_multiget_common import multiget_common

log = Logger()

def report_urn_ietf_params_xml_ns_carddav_addressbook_multiget(self, request, multiget):
    """
    Generate a multiget REPORT.
    (CardDAV, section 8.7)
    """

    # Verify root element
    if multiget.qname() != (carddav_namespace, "addressbook-multiget"):
        raise ValueError("{CardDAV:}addressbook-multiget expected as root element, not %s." % (multiget.sname(),))

    return multiget_common(self, request, multiget, COLLECTION_TYPE_ADDRESSBOOK)
