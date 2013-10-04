##
# Copyright (c) 2005-2013 Apple Computer, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
##

"""
RFC 3744 (WebDAV Access Control Protocol) XML Elements

This module provides XML element definitions for use with WebDAV.

See RFC 3744: http://www.ietf.org/rfc/rfc3744.txt
"""

__all__ = []


from txdav.xml.base import WebDAVElement, PCDATAElement
from txdav.xml.base import WebDAVEmptyElement, WebDAVTextElement
from txdav.xml.element import dav_namespace, registerElement, registerElementClass


##
# Section 3 (Privileges)
##

@registerElement
@registerElementClass
class Read (WebDAVEmptyElement):
    """
    Privilege which controls methods that return information about the state
    of a resource, including the resource's properties. (RFC 3744, section
    3.1)
    """
    name = "read"


# For DAV:write element (RFC 3744, section 3.2) see Write class in
# rfc2518.py.



@registerElement
@registerElementClass
class WriteProperties (WebDAVEmptyElement):
    """
    Privilege which controls methods that modify the dead properties of a
    resource. (RFC 3744, section 3.3)
    """
    name = "write-properties"



@registerElement
@registerElementClass
class WriteContent (WebDAVEmptyElement):
    """
    Privilege which controls methods that modify the content of an existing
    resource. (RFC 3744, section 3.4)
    """
    name = "write-content"



@registerElement
@registerElementClass
class Unlock (WebDAVEmptyElement):
    """
    Privilege which controls the use of the UNLOCK method by a principal other
    than the lock owner. (RFC 3744, section 3.5)
    """
    name = "unlock"



@registerElement
@registerElementClass
class ReadACL (WebDAVEmptyElement):
    """
    Privilege which controls the use of the PROPFIND method to retrieve the
    DAV:acl property of a resource. (RFC 3744, section 3.6)
    """
    name = "read-acl"



@registerElement
@registerElementClass
class ReadCurrentUserPrivilegeSet (WebDAVEmptyElement):
    """
    Privilege which controls the use of the PROPFIND method to retrieve the
    DAV:current-user-privilege-set property of a resource. (RFC 3744, section
    3.7)
    """
    name = "read-current-user-privilege-set"



@registerElement
@registerElementClass
class WriteACL (WebDAVEmptyElement):
    """
    Privilege which controls the use of the ACL method to modify the DAV:acl
    property of a resource. (RFC 3744, section 3.8)
    """
    name = "write-acl"



@registerElement
@registerElementClass
class Bind (WebDAVEmptyElement):
    """
    Privilege which allows a method to add a new member URL from the a
    collection resource. (RFC 3744, section 3.9)
    """
    name = "bind"



@registerElement
@registerElementClass
class Unbind (WebDAVEmptyElement):
    """
    Privilege which allows a method to remove a member URL from the a collection
    resource. (RFC 3744, section 3.10)
    """
    name = "unbind"



@registerElement
@registerElementClass
class All (WebDAVEmptyElement):
    """
    Aggregate privilege that contains the entire set of privileges that can be
    applied to a resource. (RFC 3744, section 3.11)
    Principal which matches all users. (RFC 3744, section 5.5.1)
    """
    name = "all"



##
# Section 4 (Principal Properties)
##

@registerElement
@registerElementClass
class Principal (WebDAVElement):
    """
    Indicates a principal resource type. (RFC 3744, section 4)
    Identifies the principal to which an ACE applies. (RFC 3744, section 5.5.1)
    """
    name = "principal"

    allowed_children = {
        (dav_namespace, "href"): (0, 1),
        (dav_namespace, "all"): (0, 1),
        (dav_namespace, "authenticated"): (0, 1),
        (dav_namespace, "unauthenticated"): (0, 1),
        (dav_namespace, "property"): (0, 1),
        (dav_namespace, "self"): (0, 1),
    }

    def validate(self):
        super(Principal, self).validate()

        if len(self.children) > 1:
            raise ValueError(
                "Exactly one of DAV:href, DAV:all, DAV:authenticated, "
                "DAV:unauthenticated, DAV:property or DAV:self is required for "
                "%s, got: %r"
                % (self.sname(), self.children)
            )



@registerElement
@registerElementClass
class AlternateURISet (WebDAVElement):
    """
    Property which contains the URIs of network resources with additional
    descriptive information about the principal. (RFC 3744, section 4.1)
    """
    name = "alternate-URI-set"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



@registerElement
@registerElementClass
class PrincipalURL (WebDAVElement):
    """
    Property which contains the URL that must be used to identify this principal
    in an ACL request. (RFC 3744, section 4.2)
    """
    name = "principal-URL"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, 1)}



@registerElement
@registerElementClass
class GroupMemberSet (WebDAVElement):
    """
    Property which identifies the principals that are direct members of a group
    principal.
    (RFC 3744, section 4.3)
    """
    name = "group-member-set"
    hidden = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



@registerElement
@registerElementClass
class GroupMembership (WebDAVElement):
    """
    Property which identifies the group principals in which a principal is
    directly a member. (RFC 3744, section 4.4)
    """
    name = "group-membership"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, None)}


##
# Section 5 (Access Control Properties)
##

# For DAV:owner element (RFC 3744, section 5.1) see Owner class in
# rfc2518.py.



@registerElement
@registerElementClass
class Group (WebDAVElement):
    """
    Property which identifies a particular principal as being the group
    principal of a resource. (RFC 3744, section 5.2)
    """
    name = "group"
    hidden = True
    protected = True # may be protected, per RFC 3744, section 5.2

    allowed_children = {(dav_namespace, "href"): (0, 1)}



@registerElement
@registerElementClass
class SupportedPrivilegeSet (WebDAVElement):
    """
    Property which identifies the privileges defined for a resource. (RFC 3744,
    section 5.3)
    """
    name = "supported-privilege-set"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "supported-privilege"): (0, None)}



@registerElement
@registerElementClass
class SupportedPrivilege (WebDAVElement):
    """
    Identifies a privilege defined for a resource. (RFC 3744, section 5.3)
    """
    name = "supported-privilege"

    allowed_children = {
        (dav_namespace, "privilege"): (1, 1),
        (dav_namespace, "abstract"): (0, 1),
        (dav_namespace, "description"): (1, 1),
        (dav_namespace, "supported-privilege"): (0, None),
    }



@registerElement
@registerElementClass
class Privilege (WebDAVElement):
    """
    Identifies a privilege. (RFC 3744, sections 5.3 and 5.5.1)
    """
    name = "privilege"

    allowed_children = {WebDAVElement: (0, None)}

    def isAggregateOf(self, subprivilege, supportedPrivileges):
        """
        Check whether this privilege is an aggregate of another.
        @param subprivilege: a L{Privilege}
        @param supportedPrivileges: a L{SupportedPrivilegeSet}
        @return: C{True} is this privilege is an aggregate of C{subprivilege}
            according to C{supportedPrivileges}.
        """
        # DAV: all is an aggregate of all privileges
        if len(self.children) == 1 and self.children[0].qname() == (dav_namespace, "all"):
            return True

        def isAggregate(supportedPrivilege):
            sp = supportedPrivilege.childOfType(Privilege)

            if sp == self:
                def find(supportedPrivilege):
                    if supportedPrivilege.childOfType(Privilege) == subprivilege:
                        return True

                    for child in supportedPrivilege.childrenOfType(SupportedPrivilege):
                        if find(child):
                            return True
                    else:
                        return False

                return find(supportedPrivilege)
            else:
                for child in supportedPrivilege.childrenOfType(SupportedPrivilege):
                    if isAggregate(child):
                        return True
                else:
                    return False

        for supportedPrivilege in supportedPrivileges.children:
            if isAggregate(supportedPrivilege):
                return True
        else:
            return False


    def expandAggregate(self, supportedPrivileges):
        """
        Expand this privilege into the set of privileges aggregated under it
        based on the structure of the given supported privileges. If this
        privilege is not an aggregate, just return it as-is.
        @param supportedPrivileges: a L{SupportedPrivilegeSet}
        @return: the list of expanded L{Privileges}
        """

        # Find ourselves in supported privileges
        def find(supportedPrivilege):
            """
            Find the supportPrivilege which matches this privilege.
            """
            if supportedPrivilege.childOfType(Privilege) == self:
                return supportedPrivilege

            for child in supportedPrivilege.childrenOfType(SupportedPrivilege):
                result = find(child)
                if result is not None:
                    return result
            else:
                return None

        for supportedPrivilege in supportedPrivileges.children:
            result = find(supportedPrivilege)
            if result is not None:
                break
        else:
            return [self]

        # Now add sub-privileges recursively
        aggregates = []
        def add(supportedPrivilege):
            """
            Add all sub-privileges to the list.
            """
            aggregates.append(supportedPrivilege.childOfType(Privilege))
            for child in supportedPrivilege.childrenOfType(SupportedPrivilege):
                add(child)
        add(result)

        return aggregates



@registerElement
@registerElementClass
class Abstract (WebDAVElement):
    """
    Identifies a privilege as abstract. (RFC 3744, section 5.3)
    """
    name = "abstract"



@registerElement
@registerElementClass
class Description (WebDAVTextElement):
    """
    A human-readable description of what privilege controls access to. (RFC
    3744, sections 5.3 and 9.5)
    """
    name = "description"
    allowed_attributes = {"xml:lang": True}



@registerElement
@registerElementClass
class CurrentUserPrivilegeSet (WebDAVElement):
    """
    Property which contains the exact set of privileges (as computer by the
    server) granted to the currently authenticated HTTP user. (RFC 3744, section
    5.4)
    """
    name = "current-user-privilege-set"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "privilege"): (0, None)}


# For DAV:privilege element (RFC 3744, section 5.4) see Privilege class above.



@registerElement
@registerElementClass
class ACL (WebDAVElement):
    """
    Property which specifies the list of access control entries which define
    what privileges are granted to which users for a resource. (RFC 3744,
    section 5.5)
    """
    name = "acl"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "ace"): (0, None)}



@registerElement
@registerElementClass
class ACE (WebDAVElement):
    """
    Specifies the list of access control entries which define what privileges
    are granted to which users for a resource. (RFC 3744, section 5.5)
    """
    name = "ace"

    allowed_children = {
        (dav_namespace, "principal"): (0, 1),
        (dav_namespace, "invert"): (0, 1),
        (dav_namespace, "grant"): (0, 1),
        (dav_namespace, "deny"): (0, 1),
        (dav_namespace, "protected"): (0, 1),
        (dav_namespace, "inherited"): (0, 1),
    }

    def __init__(self, *children, **attributes):
        super(ACE, self).__init__(*children, **attributes)

        self.principal = None
        self.invert = None
        self.allow = None
        self.privileges = None
        self.inherited = None
        self.protected = False

        my_children = []

        for child in self.children:
            namespace, name = child.qname()

            if isinstance(child, PCDATAElement):
                continue

            if (namespace == dav_namespace):
                if name in ("principal", "invert"):
                    if self.principal is not None:
                        raise ValueError(
                            "Only one of DAV:principal or DAV:invert allowed in %s, got: %s"
                            % (self.sname(), self.children)
                        )
                    if name == "invert":
                        self.invert = True
                        self.principal = child.children[0]
                    else:
                        self.invert = False
                        self.principal = child

                elif name in ("grant", "deny"):
                    if self.allow is not None:
                        raise ValueError(
                            "Only one of DAV:grant or DAV:deny allowed in %s, got: %s"
                            % (self.sname(), self.children)
                        )
                    self.allow = (name == "grant")
                    self.privileges = child.children

                elif name == "inherited":
                    self.inherited = str(child.children[0])

                elif name == "protected":
                    self.protected = True

            my_children.append(child)

        self.children = tuple(my_children)

        if self.principal is None:
            raise ValueError(
                "One of DAV:principal or DAV:invert is required in %s, got: %s"
                % (self.sname(), self.children)
            )
        assert self.invert is not None

        if self.allow is None:
            raise ValueError(
                "One of DAV:grant or DAV:deny is required in %s, got: %s"
                % (self.sname(), self.children)
            )
        assert self.privileges is not None


# For DAV:principal element (RFC 3744, section 5.5.1) see Principal
# class above.


# For DAV:all element (RFC 3744, section 5.5.1) see All class above.



@registerElement
@registerElementClass
class Authenticated (WebDAVEmptyElement):
    """
    Principal which matches authenticated users. (RFC 3744, section 5.5.1)
    """
    name = "authenticated"



@registerElement
@registerElementClass
class Unauthenticated (WebDAVEmptyElement):
    """
    Principal which matches unauthenticated users. (RFC 3744, section 5.5.1)
    """
    name = "unauthenticated"


# For DAV:property element (RFC 3744, section 5.5.1) see Property
# class above.



@registerElement
@registerElementClass
class Self (WebDAVEmptyElement):
    """
    Principal which matches a user if a resource is a principal and the user
    matches the resource. (RFC 3744, sections 5.5.1 and 9.3)
    """
    name = "self"



@registerElement
@registerElementClass
class Invert (WebDAVElement):
    """
    Principal which matches a user if the user does not match the principal
    contained by this principal. (RFC 3744, section 5.5.1)
    """
    name = "invert"

    allowed_children = {(dav_namespace, "principal"): (1, 1)}



@registerElement
@registerElementClass
class Grant (WebDAVElement):
    """
    Grants the contained privileges to a principal. (RFC 3744, section 5.5.2)
    """
    name = "grant"

    allowed_children = {(dav_namespace, "privilege"): (1, None)}



@registerElement
@registerElementClass
class Deny (WebDAVElement):
    """
    Denies the contained privileges to a principal. (RFC 3744, section 5.5.2)
    """
    name = "deny"

    allowed_children = {(dav_namespace, "privilege"): (1, None)}


# For DAV:privilege element (RFC 3744, section 5.5.2) see Privilege
# class above.



@registerElement
@registerElementClass
class Protected (WebDAVEmptyElement):
    """
    Identifies an ACE as protected. (RFC 3744, section 5.5.3)
    """
    name = "protected"



@registerElement
@registerElementClass
class Inherited (WebDAVElement):
    """
    Indicates that an ACE is inherited from the resource indentified by the
    contained DAV:href element. (RFC 3744, section 5.5.4)
    """
    name = "inherited"

    allowed_children = {(dav_namespace, "href"): (1, 1)}



@registerElement
@registerElementClass
class ACLRestrictions (WebDAVElement):
    """
    Property which defines the types of ACLs supported by this server, to avoid
    clients needlessly getting errors. (RFC 3744, section 5.6)
    """
    name = "acl-restrictions"
    hidden = True
    protected = True

    allowed_children = {
        (dav_namespace, "grant-only"): (0, 1),
        (dav_namespace, "no-invert"): (0, 1),
        (dav_namespace, "deny-before-grant"): (0, 1),
        (dav_namespace, "required-principal"): (0, 1),
    }



@registerElement
@registerElementClass
class GrantOnly (WebDAVEmptyElement):
    """
    Indicates that ACEs with deny clauses are not allowed. (RFC 3744, section
    5.6.1)
    """
    name = "grant-only"



@registerElement
@registerElementClass
class NoInvert (WebDAVEmptyElement):
    """
    Indicates that ACEs with the DAV:invert element are not allowed. (RFC 3744,
    section 5.6.2)
    """
    name = "no-invert"



@registerElement
@registerElementClass
class DenyBeforeGrant (WebDAVEmptyElement):
    """
    Indicates that all deny ACEs must precede all grant ACEs. (RFC 3744, section
    5.6.3)
    """
    name = "deny-before-grant"



@registerElement
@registerElementClass
class RequiredPrincipal (WebDAVElement):
    """
    Indicates which principals must have an ACE defined in an ACL. (RFC 3744,
    section 5.6.4)
    """
    name = "required-principal"

    allowed_children = {
        (dav_namespace, "all"): (0, 1),
        (dav_namespace, "authenticated"): (0, 1),
        (dav_namespace, "unauthenticated"): (0, 1),
        (dav_namespace, "self"): (0, 1),
        (dav_namespace, "href"): (0, None),
        (dav_namespace, "property"): (0, None),
    }

    def validate(self):
        super(RequiredPrincipal, self).validate()

        type = None

        for child in self.children:
            if type is None:
                type = child.qname()
            elif child.qname() != type:
                raise ValueError(
                    "Only one of DAV:all, DAV:authenticated, DAV:unauthenticated, "
                    "DAV:self, DAV:href or DAV:property allowed for %s, got: %s"
                    % (self.sname(), self.children)
                )



@registerElement
@registerElementClass
class InheritedACLSet (WebDAVElement):
    """
    Property which contains a set of URLs that identify other resources that
    also control the access to this resource. (RFC 3744, section 5.7)
    """
    name = "inherited-acl-set"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



@registerElement
@registerElementClass
class PrincipalCollectionSet (WebDAVElement):
    """
    Property which contains a set of URLs that identify the root collections
    that contain the principals that are available on the server that implements
    a resource. (RFC 3744, section 5.8)
    """
    name = "principal-collection-set"
    hidden = True
    protected = True

    allowed_children = {(dav_namespace, "href"): (0, None)}



##
# Section 7 (Access Control and existing methods)
##

@registerElement
@registerElementClass
class NeedPrivileges (WebDAVElement):
    """
    Error which indicates insufficient privileges. (RFC 3744, section 7.1.1)
    """
    name = "need-privileges"

    allowed_children = {(dav_namespace, "resource"): (0, None)}



@registerElement
@registerElementClass
class Resource (WebDAVElement):
    """
    Identifies which resource had insufficient privileges. (RFC 3744, section
    7.1.1)
    """
    name = "resource"

    allowed_children = {
        (dav_namespace, "href"): (1, 1),
        (dav_namespace, "privilege"): (1, 1),
    }



##
# Section 9 (Access Control Reports)
##

@registerElement
@registerElementClass
class ACLPrincipalPropSet (WebDAVElement):
    """
    Report which returns, for all principals in the DAV:acl property (of the
    resource identified by the Request-URI) that are identified by http(s) URLs
    or by a DAV:property principal, the value of the properties specified in the
    REPORT request body. (RFC 3744, section 9.2)
    """
    name = "acl-principal-prop-set"

    allowed_children = {WebDAVElement: (0, None)}

    def validate(self):
        super(ACLPrincipalPropSet, self).validate()

        prop = False

        for child in self.children:
            if child.qname() == (dav_namespace, "prop"):
                if prop:
                    raise ValueError(
                        "Only one DAV:prop allowed for %s, got: %s"
                        % (self.sname(), self.children)
                    )
                prop = True



@registerElement
@registerElementClass
class PrincipalMatch (WebDAVElement):
    """
    Report used to identify all members (at any depth) of the collection
    identified by the Request-URI that are principals and that match the current
    user. (RFC 3744, section 9.3)
    """
    name = "principal-match"

    allowed_children = {
        (dav_namespace, "principal-property"): (0, 1),
        (dav_namespace, "self"): (0, 1),
        (dav_namespace, "prop"): (0, 1),
    }

    def validate(self):
        super(PrincipalMatch, self).validate()

        # This element can be empty when uses in supported-report-set
        if not len(self.children):
            return

        principalPropertyOrSelf = False

        for child in self.children:
            namespace, name = child.qname()

            if (namespace == dav_namespace) and name in ("principal-property", "self"):
                if principalPropertyOrSelf:
                    raise ValueError(
                        "Only one of DAV:principal-property or DAV:self allowed in %s, got: %s"
                        % (self.sname(), self.children)
                    )
                principalPropertyOrSelf = True

        if not principalPropertyOrSelf:
            raise ValueError(
                "One of DAV:principal-property or DAV:self is required in %s, got: %s"
                % (self.sname(), self.children)
            )



@registerElement
@registerElementClass
class PrincipalProperty (WebDAVElement):
    """
    Identifies a property. (RFC 3744, section 9.3)
    """
    name = "principal-property"

    allowed_children = {WebDAVElement: (0, None)}


# For DAV:self element (RFC 3744, section 9.3) see Self class above.



@registerElement
@registerElementClass
class PrincipalPropertySearch (WebDAVElement):
    """
    Report which performs a search for all principals whose properties contain
    character data that matches the search criteria specified in the request.
    (RFC 3744, section 9.4)
    """
    name = "principal-property-search"

    allowed_children = {
        (dav_namespace, "property-search"): (0, None),    # This is required but this element must be empty in supported-report-set
        (dav_namespace, "prop"): (0, 1),
        (dav_namespace, "apply-to-principal-collection-set"): (0, 1),
    }
    allowed_attributes = {"test": False}



@registerElement
@registerElementClass
class PropertySearch (WebDAVElement):
    """
    Contains a DAV:prop element enumerating the properties to be searched and a
    DAV:match element, containing the search string. (RFC 3744, section 9.4)
    """
    name = "property-search"

    allowed_children = {
        (dav_namespace, "prop"): (1, 1),
        (dav_namespace, "match"): (1, 1),
    }



@registerElement
@registerElementClass
class Match (WebDAVTextElement):
    """
    Contains a search string. (RFC 3744, section 9.4)
    """
    name = "match"



@registerElement
@registerElementClass
class PrincipalSearchPropertySet (WebDAVElement):
    """
    Report which identifies those properties that may be searched using the
    DAV:principal-property-search report. (RFC 3744, section 9.5)
    """
    name = "principal-search-property-set"

    allowed_children = {(dav_namespace, "principal-search-property"): (0, None)}



@registerElement
@registerElementClass
class PrincipalSearchProperty (WebDAVElement):
    """
    Contains exactly one searchable property, and a description of the property.
    (RFC 3744, section 9.5)
    """
    name = "principal-search-property"

    allowed_children = {
        (dav_namespace, "prop"): (1, 1),
        (dav_namespace, "description"): (1, 1),
    }



@registerElement
@registerElementClass
class NumberOfMatchesWithinLimits (WebDAVEmptyElement):
    """
    Error which indicates too many results
    """
    name = "number-of-matches-within-limits"


# For DAV:description element (RFC 3744, section 9.5) see Description
# class above.
