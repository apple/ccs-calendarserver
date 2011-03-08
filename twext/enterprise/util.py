
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
Utilities for dealing with different databases.
"""

from datetime import datetime
from twistedcaldav.dateops import SQL_TIMESTAMP_FORMAT

def mapOracleOutputType(column):
    """
    Map a single output value from cx_Oracle based on some rules and
    expectations that we have based on the pgdb bindings.

    @param column: a single value from a column.

    @return: a converted value based on the type of the input; oracle CLOBs and
        datetime timestamps will be converted to strings, all other types will
        be left alone.
    """
    if hasattr(column, 'read'):
        # Try to detect large objects and format convert them to
        # strings on the fly.  We need to do this as we read each
        # row, due to the issue described here -
        # http://cx-oracle.sourceforge.net/html/lob.html - in
        # particular, the part where it says "In particular, do not
        # use the fetchall() method".
        return column.read()
    elif isinstance(column, datetime):
        # cx_Oracle properly maps the type of timestamps to datetime
        # objects.  However, our code is mostly written against
        # PyGreSQL, which just emits strings as results and expects
        # to have to convert them itself..  Since it's easier to
        # just detect the datetimes and stringify them, for now
        # we'll do that.
        return column.strftime(SQL_TIMESTAMP_FORMAT)
    elif isinstance(column, float):
        if int(column) == column:
            return int(column)
        else:
            return column
    else:
        return column



