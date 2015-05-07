# -*- test-case-name: txdav.caldav.datastore.scheduling.test.test_imip -*-
##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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

from twext.enterprise.dal.record import fromTable, SerializableRecord
from txdav.common.datastore.sql_tables import schema

"""
Database L{Record} for iMIP tokens.
"""

class iMIPTokenRecord(SerializableRecord, fromTable(schema.IMIP_TOKENS)):
    """
    @DynamicAttrs
    L{Record} for L{schema.NOTIFICATION}.
    """
    pass
