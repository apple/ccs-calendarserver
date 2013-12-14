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
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
web2.dav interfaces.
"""

__all__ = [ "IDAVResource", "IDAVPrincipalResource", "IDAVPrincipalCollectionResource", ]

from txweb2.iweb import IResource

class IDAVResource(IResource):
    """
    WebDAV resource.
    """
    def isCollection():
        """
        Checks whether this resource is a collection resource.
        @return: C{True} if this resource is a collection resource, C{False}
            otherwise.
        """

    def findChildren(depth, request, callback, privileges, inherited_aces):
        """
        Returns an iterable of child resources for the given depth.
        Because resources do not know their request URIs, chidren are returned
        as tuples C{(resource, uri)}, where C{resource} is the child resource
        and C{uri} is a URL path relative to this resource.
        @param depth: the search depth (one of C{"0"}, C{"1"}, or C{"infinity"})
        @param request: The current L{IRequest} responsible for this call.
        @param callback: C{callable} that will be called for each child found
        @param privileges: the list of L{Privilege}s to test for.  This should 
            default to None.
        @param inherited_aces: a list of L{Privilege}s for aces being inherited from
            the parent collection used to bypass inheritance lookup.
        @return: An L{Deferred} that fires when all the children have been found
        """

    def hasProperty(property, request):
        """
        Checks whether the given property is defined on this resource.
        @param property: an empty L{davxml.WebDAVElement} instance or a qname
            tuple.
        @param request: the request being processed.
        @return: a deferred value of C{True} if the given property is set on
            this resource, or C{False} otherwise.
        """

    def readProperty(property, request):
        """
        Reads the given property on this resource.
        @param property: an empty L{davxml.WebDAVElement} class or instance, or
            a qname tuple.
        @param request: the request being processed.
        @return: a deferred L{davxml.WebDAVElement} instance
            containing the value of the given property.
        @raise HTTPError: (containing a response with a status code of
            L{responsecode.CONFLICT}) if C{property} is not set on this
            resource.
        """

    def writeProperty(property, request):
        """
        Writes the given property on this resource.
        @param property: a L{davxml.WebDAVElement} instance.
        @param request: the request being processed.
        @return: an empty deferred which fires when the operation is completed.
        @raise HTTPError: (containing a response with a status code of
            L{responsecode.CONFLICT}) if C{property} is a read-only property.
        """

    def removeProperty(property, request):
        """
        Removes the given property from this resource.
        @param property: a L{davxml.WebDAVElement} instance or a qname tuple.
        @param request: the request being processed.
        @return: an empty deferred which fires when the operation is completed.
        @raise HTTPError: (containing a response with a status code of
            L{responsecode.CONFLICT}) if C{property} is a read-only property or
            if the property does not exist.
        """

    def listProperties(request):
        """
        @param request: the request being processed.
        @return: a deferred iterable of qnames for all properties
            defined for this resource.
        """

    def supportedReports():
        """
        @return: an iterable of L{davxml.Report} elements for each report
            supported by this resource.
        """

    def authorize(request, privileges, recurse=False):
        """
        Verify that the given request is authorized to perform actions that
        require the given privileges.

        @param request: the request being processed.

        @param privileges: an iterable of L{davxml.WebDAVElement} elements
            denoting access control privileges.

        @param recurse: C{True} if a recursive check on all child
            resources of this resource should be performed as well,
            C{False} otherwise.

        @return: a Deferred which fires with C{None} when authorization is
            complete, or errbacks with L{HTTPError} (containing a response with
            a status code of L{responsecode.UNAUTHORIZED}) if not authorized.
        """

    def principalCollections():
        """
        @return: an interable of L{IDAVPrincipalCollectionResource}s which
            contain principals used in ACLs for this resource.
        """

    def setAccessControlList(acl):
        """
        Sets the access control list containing the access control list for
        this resource.
        @param acl: an L{davxml.ACL} element.
        """

    def supportedPrivileges(request):
        """
        @param request: the request being processed.
        @return: a L{Deferred} with an L{davxml.SupportedPrivilegeSet} result describing
            the access control privileges which are supported by this resource.
        """

    def currentPrivileges(request):
        """
        @param request: the request being processed.
        @return: a sequence of the access control privileges which are
            set for the currently authenticated user.
        """

    def accessControlList(request, inheritance=True, expanding=False):
        """
        Obtains the access control list for this resource.
        @param request: the request being processed.
        @param inheritance: if True, replace inherited privileges with those
            from the import resource being inherited from, if False just return
            whatever is set in this ACL.
        @param expanding: if C{True}, method is called during parent inheritance
            expansion, if C{False} then not doing parent expansion.
        @return: a deferred L{davxml.ACL} element containing the
            access control list for this resource.
        """

    def privilegesForPrincipal(principal, request):
        """
        Evaluate the set of privileges that apply to the specified principal.
        This involves examing all ace's and granting/denying as appropriate for
        the specified principal's membership of the ace's prinicpal.
        @param request: the request being processed.
        @return: a list of L{Privilege}s that are allowed on this resource for
            the specified principal.
        """

    ##
    # Quota
    ##
    
    def quota(request):
        """
        Get current available & used quota values for this resource's quota root
        collection.

        @return: a C{tuple} containing two C{int}'s the first is 
            quota-available-bytes, the second is quota-used-bytes, or
            C{None} if quota is not defined on the resource.
        """
    
    def hasQuota(request):
        """
        Check whether this resource is undre quota control by checking each parent to see if
        it has a quota root.
        
        @return: C{True} if under quota control, C{False} if not.
        """
        
    def hasQuotaRoot(request):
        """
        Determine whether the resource has a quota root.

        @return: a C{True} if this resource has quota root, C{False} otherwise.
        """
    

    def quotaRoot(request):
        """
        Get the quota root (max. allowed bytes) value for this collection.

        @return: a C{int} containing the maximum allowed bytes if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """
    
    def setQuotaRoot(request, maxsize):
        """
        Set the quota root (max. allowed bytes) value for this collection.

        @param maxsize: a C{int} containing the maximum allowed bytes for the contents
            of this collection.
        """
    
    def quotaSize(request):
        """
        Get the size of this resource (if its a collection get total for all children as well).
        TODO: Take into account size of dead-properties.

        @return: a L{Deferred} with a C{int} result containing the size of the resource.
        """
        
    def currentQuotaUse(request):
        """
        Get the cached quota use value, or if not present (or invalid) determine
        quota use by brute force.

        @return: an L{Deferred} with a C{int} result containing the current used byte count if
            this collection is quota-controlled, or C{None} if not quota controlled.
        """
        
    def updateQuotaUse(request, adjust):
        """
        Adjust current quota use on this all all parent collections that also
        have quota roots.

        @param adjust: a C{int} containing the number of bytes added (positive) or
        removed (negative) that should be used to adjust the cached total.
        @return: an L{Deferred} with a C{int} result containing the current used byte if this collection
            is quota-controlled, or C{None} if not quota controlled.
        """

class IDAVPrincipalResource (IDAVResource):
    """
    WebDAV principal resource.  (RFC 3744, section 2)
    """

    def alternateURIs():
        """
        Provides the URIs of network resources with additional descriptive
        information about the principal, for example, a URI to an LDAP record.
        (RFC 3744, section 4.1)
        @return: a iterable of URIs.
        """


    def principalURL():
        """
        Provides the URL which must be used to identify this principal in ACL
        requests.  (RFC 3744, section 4.2)
        @return: a URL.
        """


    def groupMembers():
        """
        Provides the principal URLs of principals that are direct members of
        this (group) principal.  (RFC 3744, section 4.3)
        @return: a deferred returning an iterable of principal URLs.
        """


    def expandedGroupMembers():
        """
        Provides the principal URLs of principals that are members of this
        (group) principal, as well as members of any group principal which are
        members of this one.

        @return: a L{Deferred} that fires with an iterable of principal URLs.
        """


    def groupMemberships():
        """
        Provides the URLs of the group principals in which the principal is
        directly a member.  (RFC 3744, section 4.4)
        @return: a deferred containing an iterable of group principal URLs.
        """



class IDAVPrincipalCollectionResource(IDAVResource):
    """
    WebDAV principal collection resource.  (RFC 3744, section 5.8)
    """

    def principalCollectionURL():
        """
        Provides a URL for this resource which may be used to identify this
        resource in ACL requests.  (RFC 3744, section 5.8)
        @return: a URL.
        """


    def principalForUser(user):
        """
        Retrieve the principal for a given username.

        @param user: the (short) name of a user.
        @type user: C{str}

        @return: the resource representing the DAV principal resource for the
            given username.

        @rtype: L{IDAVPrincipalResource}
        """

