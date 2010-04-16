##
# Copyright (c) 2006-2010 Apple Inc. All rights reserved.
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
Convert a addressbook-query into an expression tree.
Convert a addressbook-query into a partial SQL statement.
"""

__version__ = "0.0"

__all__ = [
    "addressbookquery",
    "sqladdressbookquery",
]

from twistedcaldav.query import expression, sqlgenerator
from twistedcaldav import carddavxml

# SQL Index column (field) names

FIELD_TYPE      = "RESOURCE.TYPE"
FIELD_UID       = "RESOURCE.UID"

def addressbookquery(filter):
    """
    Convert the supplied addressbook-query into an expression tree.

    @param filter: the L{Filter} for the addressbook-query to convert.
    @return: a L{baseExpression} for the expression tree.
    """
    # Lets assume we have a valid filter from the outset.
    
    # Top-level filter contains zero or more prop-filter element
    if len(filter.children) > 0:
        return propfilterListExpression(filter.children)
    else:
        return expression.allExpression()

def propfilterListExpression(propfilters):
    """
    Create an expression for a list of prop-filter elements.
    
    @param propfilters: the C{list} of L{ComponentFilter} elements.
    @return: a L{baseExpression} for the expression tree.
    """
    
    if len(propfilters) == 1:
        return propfilterExpression(propfilters[0])
    else:
        return expression.orExpression([propfilterExpression(c) for c in propfilters])

def propfilterExpression(propfilter):
    """
    Create an expression for a single prop-filter element.
    
    @param propfilter: the L{PropertyFilter} element.
    @return: a L{baseExpression} for the expression tree.
    """
    
    # Only handle UID right now
    if propfilter.filter_name != "UID":
        raise ValueError

    # Handle is-not-defined case
    if not propfilter.defined:
        # Test for <<field>> != "*"
        return expression.isExpression(FIELD_UID, "", True)
    
    # Handle text-match
    tm = None
    if propfilter.qualifier and isinstance(propfilter.qualifier, carddavxml.TextMatch):
        if propfilter.qualifier.negate:
            tm = expression.notcontainsExpression(propfilter.filter_name, str(propfilter.qualifier), propfilter.qualifier)
        else:
            tm = expression.containsExpression(propfilter.filter_name, str(propfilter.qualifier), propfilter.qualifier)
    
    # Handle embedded parameters - we do not right now as our Index does not handle them
    params = []
    if len(propfilter.filters) > 0:
        raise ValueError
    if len(params) > 1:
        paramsExpression = expression.orExpression[params]
    elif len(params) == 1:
        paramsExpression = params[0]
    else:
        paramsExpression = None

    # Now build return expression
    if (tm is not None) and (paramsExpression is not None):
        return expression.andExpression([tm, paramsExpression])
    elif tm is not None:
        return tm
    elif paramsExpression is not None:
        return paramsExpression
    else:
        return None

def sqladdressbookquery(filter):
    """
    Convert the supplied addressbook-query into a partial SQL statement.

    @param filter: the L{Filter} for the addressbook-query to convert.
    @return: a C{tuple} of (C{str}, C{list}), where the C{str} is the partial SQL statement,
            and the C{list} is the list of argument substitutions to use with the SQL API execute method.
            Or return C{None} if it is not possible to create an SQL query to fully match the addressbook-query.
    """
    try:
        expression = addressbookquery(filter)
        sql = sqlgenerator.sqlgenerator(expression)
        return sql.generate()
    except ValueError:
        return None
