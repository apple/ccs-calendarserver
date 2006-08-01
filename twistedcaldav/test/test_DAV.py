##
# Copyright (c) 2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

from twistedcaldav.static import CalDAVFile as MyResource

import twisted.web2.dav.test.test_acl
import twisted.web2.dav.test.test_copy
import twisted.web2.dav.test.test_delete
import twisted.web2.dav.test.test_lock
import twisted.web2.dav.test.test_mkcol
import twisted.web2.dav.test.test_move
import twisted.web2.dav.test.test_options
import twisted.web2.dav.test.test_prop
import twisted.web2.dav.test.test_put
import twisted.web2.dav.test.test_report
import twisted.web2.dav.test.test_report_expand

class ACL           (twisted.web2.dav.test.test_acl.ACL                    ): resource_class = MyResource
class COPY          (twisted.web2.dav.test.test_copy.COPY                  ): resource_class = MyResource
class DELETE        (twisted.web2.dav.test.test_delete.DELETE              ): resource_class = MyResource
class LOCK_UNLOCK   (twisted.web2.dav.test.test_lock.LOCK_UNLOCK           ): resource_class = MyResource
class MKCOL         (twisted.web2.dav.test.test_mkcol.MKCOL                ): resource_class = MyResource
class MOVE          (twisted.web2.dav.test.test_move.MOVE                  ): resource_class = MyResource
class OPTIONS       (twisted.web2.dav.test.test_options.OPTIONS            ): resource_class = MyResource
class PROP          (twisted.web2.dav.test.test_prop.PROP                  ): resource_class = MyResource
class PUT           (twisted.web2.dav.test.test_put.PUT                    ): resource_class = MyResource
class REPORT        (twisted.web2.dav.test.test_report.REPORT              ): resource_class = MyResource
class REPORT_expand (twisted.web2.dav.test.test_report_expand.REPORT_expand): resource_class = MyResource
