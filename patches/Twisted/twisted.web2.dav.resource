Index: twisted/web2/dav/resource.py
===================================================================
--- twisted/web2/dav/resource.py	(revision 17940)
+++ twisted/web2/dav/resource.py	(working copy)
@@ -262,7 +262,8 @@
                 if name == "acl":
                     return ifAllowed(
                         (davxml.ReadACL(),),
-                        lambda: self.accessControlList(request)
+                        # TODO: Merge change from original patch
+                        lambda: self.safeAccessControlList(request)
                     )
 
             if namespace == twisted_dav_namespace:
@@ -582,17 +583,28 @@
 
         authHeader = request.headers.getHeader('authorization')
         if authHeader is not None:
-            if authHeader[0] in request.credentialFactories:
+            if authHeader[0] not in request.credentialFactories:
                 log.err("Client authentication scheme %s is not provided by server %s"
                         % (authHeader[0], request.credentialFactories.keys()))
-                return succeed((True, False))
+                raise HTTPError(responsecode.FORBIDDEN)
             else:
                 factory = request.credentialFactories[authHeader[0]]
 
-                # FIXME: response, req are not defined
-                creds = factory.decode(response, req.method)
+                creds = factory.decode(authHeader[1], request.method)
+
+                # Try to match principals in each principal collection on the resource
+                pdetails = self.findPrincipalForAuthID(request, creds.username)
+                assert pdetails.called
+                pdetails = pdetails.result
+                if pdetails:
+                    principal = IDAVPrincipalResource(pdetails[0])
+                    principalURI = pdetails[1]
+                else:
+                   raise HTTPError(responsecode.FORBIDDEN) 
+                from twisted.web2.dav.auth import PrincipalCredentials
+                pcreds = PrincipalCredentials(principal, principalURI, creds)
 
-                d = request.portal.login(creds, None, *request.loginInterfaces)
+                d = request.portal.login(pcreds, None, *request.loginInterfaces)
                 d.addCallback(loginSuccess)
                 return d
         else:
@@ -609,7 +621,7 @@
         @return: the current principal, as derived from the given request.
         """
         if hasattr(request, "user"):
-            return request.user
+            return request.user.element
         else:
             return unauthenticatedPrincipal
 
@@ -716,6 +728,10 @@
         yield oldacl
         oldacl = oldacl.getResult()
 
+        # Check disabled
+        if oldacl is None:
+            yield None
+
         # Need to get list of supported privileges
         supported = []
         def addSupportedPrivilege(sp):
@@ -747,10 +763,18 @@
                         yield (davxml.dav_namespace, "no-protected-ace-conflict")
                         return
                     # Step 2
-                    elif oldace.inherited:
-                        log.err("Attempt to overwrite inherited ace %r on resource %r" % (oldace, self))
-                        yield (davxml.dav_namespace, "no-inherited-ace-conflict")
-                        return
+                    """
+                    RFC3744 says that we either enforce the inherited ace conflict or we ignore it
+                    # but use access control evaluation to determine whether there us any impact. Given that we
+                    # have the 'inheritable' behavior it does not make sense to disallow overrides of inherited ACEs
+                    # since 'inheritable' cannot itself be controlled via protocol.
+                    
+                    So the following lines have been commented out for now.
+                    """
+                    #elif oldace.inherited:
+                    #    log.err("Attempt to overwrite inherited ace %r on resource %r" % (oldace, self))
+                    #    yield (davxml.dav_namespace, "no-inherited-ace-conflict")
+                    #    return
 
             # Step 3
             if ace.allow and got_deny:
@@ -806,7 +830,7 @@
         # FIXME: verify acl is self-consistent
 
         # Step 11
-        self.writeDeadProperty(TwistedACLProperty(davxml.ACL(*newset)))
+        self.writeNewACEs(newset)
         yield None
 
     mergeAccessControlList = deferredGenerator(mergeAccessControlList)
@@ -811,7 +835,24 @@
 
     mergeAccessControlList = deferredGenerator(mergeAccessControlList)
         
-    def checkAccess(self, request, privileges, recurse=False, principal=None):
+    def writeNewACEs(self, newaces):
+        """
+        Write a new ACL to the resource's property store.
+        NB We have this as a separate method so that it can be overridden by resources that need to do extra
+        processing of ACLs being set via the ACL command.
+        
+        @param newaces: C{list} of L{ACE} for ACL being set.
+        """
+        self.writeDeadProperty(TwistedACLProperty(davxml.ACL(*newaces)))
+
+    def matchPrivilege(self, privilege, ace_privileges, supportedPrivileges):
+        for ace_privilege in ace_privileges:
+            if privilege == ace_privilege or ace_privilege.isAggregateOf(privilege, supportedPrivileges):
+                return True
+
+        return False
+
+    def checkAccess(self, request, privileges, recurse=False, principal=None, inheritedaces=None):
         """
         Check whether the given principal has the given privileges.
         (RFC 3744, section 5.5)
@@ -821,6 +862,8 @@
         @param recurse: a boolean.  C{True} if a recursive check on all child
             resources should be performed as well, C{False} otherwise.  (Has
             no effect if this resource is not a collection resource.)
+        @param inheritedaces: a list of L{Aces} corresponding to the precomputed
+            inheritable aces from the parent resource hierarchy.
         @return: A L{Deferred} that callbacks with C{None} or errbacks with an
             L{twisted.web2.dav.acl.AccessDeniedError}
         """
@@ -918,7 +961,13 @@
         current = self.currentPrincipal(request)
         return self.privilegesForPrincipal(current, request)
 
-    def accessControlList(self, request, inheritance=True, expanding=False):
+    def safeAccessControlList(self, request):
+        acl = self.accessControlList(request)
+        if acl is None:
+            acl = davxml.ACL()
+        return acl
+
+    def accessControlList(self, request, inheritance=True, expanding=False, inheritedaces=None):
         """
         See L{IDAVResource.accessControlList}.
 
@@ -926,6 +975,7 @@
         C{(L{twisted_private_namespace}, "acl")}.
         If no ACL has been stored for this resource, it returns the value
         returned by C{defaultAccessControlList}.
+        If access is disabled it will return C{None}.
         """
         #
         # Inheritance is problematic. Here is what we do:
@@ -941,6 +991,12 @@
         # If those are defined, the relevant ace is applied to the ACL on the
         # current resource.
         #
+
+        # Check disabled
+        disabled = self.hasDeadProperty(TwistedAccessDisabledProperty)
+        if disabled:
+            yield None
+
         myURL = None
 
         def getMyURL():
@@ -976,29 +1032,36 @@
             if myURL is None:
                 myURL = getMyURL()
 
-            if myURL != "/":
-                parentURL = parentForURL(myURL)
-
-                parent = waitForDeferred(request.locateResource(parentURL))
-                yield parent
-                parent = parent.getResult()
-
-                if parent:
-                    parent_acl = waitForDeferred(
-                        parent.accessControlList(request, inheritance=True, expanding=True)
-                    )
-                    yield parent_acl
-                    parent_acl = parent_acl.getResult()
-
-                    for ace in parent_acl.children:
-                        if ace.inherited:
-                            aces.append(ace)
-                        elif TwistedACLInheritable() in ace.children:
-                            # Adjust ACE for inherit on this resource
-                            children = list(ace.children)
-                            children.remove(TwistedACLInheritable())
-                            children.append(davxml.Inherited(davxml.HRef.fromString(parentURL)))
-                            aces.append(davxml.ACE(*children))
+            if inheritedaces is None:
+                if myURL != "/":
+                    parentURL = parentForURL(myURL)
+    
+                    parent = waitForDeferred(request.locateResource(parentURL))
+                    yield parent
+                    parent = parent.getResult()
+    
+                    if parent:
+                        parent_acl = waitForDeferred(
+                            parent.accessControlList(request, inheritance=True, expanding=True)
+                        )
+                        yield parent_acl
+                        parent_acl = parent_acl.getResult()
+    
+                        # Check disabled
+                        if parent_acl is None:
+                            yield None
+    
+                        for ace in parent_acl.children:
+                            if ace.inherited:
+                                aces.append(ace)
+                            elif TwistedACLInheritable() in ace.children:
+                                # Adjust ACE for inherit on this resource
+                                children = list(ace.children)
+                                children.remove(TwistedACLInheritable())
+                                children.append(davxml.Inherited(davxml.HRef.fromString(parentURL)))
+                                aces.append(davxml.ACE(*children))
+            else:
+                aces.extend(inheritedaces)
 
             # Always filter out any remaining private properties when we are
             # returning the ACL for the final resource after doing parent
@@ -1018,6 +1081,49 @@
 
     accessControlList = deferredGenerator(accessControlList)
 
+    # TODO: Convert to deferredGenerator
+    def inheritedACEsforChildren(self, request):
+        """
+        Do some optimisation of access control calculation by determining any inherited ACLs outside of
+        the child resource loop and supply those to the checkAccess on each child.
+
+        @param request: the L{IRequest} for the request in progress.
+        @return:        a C{list} of L{Ace}s that child resources of this one will
+            inherit and which will match the currently authenticated principal.
+        """
+        
+        # Get the parent ACLs with inheritance and preserve the <inheritable> element.
+        parent_acl = self.accessControlList(request, inheritance=True, expanding=True)
+        
+        # Check disabled
+        if parent_acl is None:
+            return None
+
+        # Filter out those that are not inheritable (and remove the inheritable element from those that are)
+        aces = []
+        for ace in parent_acl.children:
+            if ace.inherited:
+                aces.append(ace)
+            elif TwistedACLInheritable() in ace.children:
+                # Adjust ACE for inherit on this resource
+                children = list(ace.children)
+                children.remove(TwistedACLInheritable())
+                children.append(davxml.Inherited(davxml.HRef.fromString(self.getURI(request))))
+                aces.append(davxml.ACE(*children))
+                
+        # Filter out those that do not have a principal match with the current principal
+        principal = self.currentPrincipal(request)
+        filteredaces = []
+        for ace in aces:
+            if self.matchPrincipal(principal, ace.principal, request):
+                if ace.invert:
+                    continue
+            else:
+                if not ace.invert:
+                    continue
+            filteredaces.append(ace)
+        return filteredaces
+
     def inheritedACLSet(self):
         """
         @return: a sequence of L{davxml.HRef}s from which ACLs are inherited.
@@ -1054,6 +1160,10 @@
                 yield (principal, principalURI)
                 return
         else:
+            if len(self.principalCollections(request)) == 0:
+                log.msg("<DAV:principal-collection-set> property cannot be found on the resource being authorized: %s" % self)
+            else:
+                log.msg("Could not find principal matching user id: %s" % authid)
             yield None
 
     findPrincipalForAuthID = deferredGenerator(findPrincipalForAuthID)
@@ -1135,13 +1245,12 @@
 
         # Now principal2 is an HRef
 
-        if principal1 == principal2:
+        # Compare two HRefs and do group membership test as well
+        if ((principal1 == principal2) or
+            self.principalIsGroupMember(str(principal1), str(principal2), request)):
             yield True
             return
 
-        # FIXME: We still need to handle the case where principal2 is a group
-        # containing principal1.
-
         yield False
 
     matchPrincipal = deferredGenerator(matchPrincipal)
@@ -1146,6 +1255,29 @@
 
     matchPrincipal = deferredGenerator(matchPrincipal)
 
+    def principalIsGroupMember(self, principal1, principal2, request):
+        """
+        Check whether one principal is a group member of another.
+        
+        @param principal1: C{str} principalURL for principal to test.
+        @param principal2: C{str} principalURL for possible group principal to test against.
+        @param request: the request being processed.
+        @return: C{True} if principal1 is a member of principal2, C{False} otherwise
+        """
+        
+        def defer():
+            # Get principal resource for principal2
+            group = self.locateSiblingResource(request, principal2)
+            from twisted.web2.dav.acl import DAVPrincipalResource
+            if group and isinstance(group, DAVPrincipalResource):
+                members = group.groupMembers()
+                if principal1 in members:
+                    return True
+                
+            return False
+
+        return maybeDeferred(defer)
+        
     def validPrincipal(self, ace_principal, request):
         """
         Check whether the supplied principal is valid for this resource.
@@ -1207,11 +1339,10 @@
         All other principals, including meta-principals (eg. L{davxml.All}),
         resolve to C{None}.
 
-        @param principal: the L{davxml.Principal} element to resolve.
+        @param principal: the L{davxml.Principal} child element to resolve.
         @param request: the request being processed.
         @return: a deferred L{davxml.HRef} element or C{None}.
         """
-        principal = principal.children[0]
 
         if isinstance(principal, davxml.Property):
             # raise NotImplementedError("Property principals are not implemented.")
@@ -1291,6 +1422,10 @@
         yield acl
         acl = acl.getResult()
 
+        # Check disabled
+        if acl is None:
+            yield []
+
         granted = []
         denied = []
         for ace in acl.children:
@@ -1430,6 +1565,10 @@
 davxml.registerElement(TwistedPrincipalCollectionSetProperty)
 
 class TwistedACLInheritable (davxml.WebDAVEmptyElement):
+    """
+    When set on an ACE, this indicates that the ACE privileges should be inherited by
+    all child resources within the resource with this ACE.
+    """
     namespace = twisted_dav_namespace
     name = "inheritable"
 
@@ -1436,6 +1575,16 @@
 davxml.registerElement(TwistedACLInheritable)
 davxml.ACE.allowed_children[(twisted_dav_namespace, "inheritable")] = (0, 1)
 
+"""
+When set on a resource, this property indicates that all access to the resource and any of its children
+is completely disabled - irrespective of any other privileges directly set or inherited.
+"""
+class TwistedAccessDisabledProperty (davxml.WebDAVEmptyElement):
+    namespace = twisted_private_namespace
+    name = "access-disabled"
+
+davxml.registerElement(TwistedAccessDisabledProperty)
+
 allACL = davxml.ACL(
     davxml.ACE(
         davxml.Principal(davxml.All()),
