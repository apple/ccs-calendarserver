##
# Copyright (c) 2006-2007 Apple Inc. All rights reserved.
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
