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

import twext.web2.dav.test.test_acl
import twext.web2.dav.test.test_copy
import twext.web2.dav.test.test_delete
import twext.web2.dav.test.test_lock
import twext.web2.dav.test.test_mkcol
import twext.web2.dav.test.test_move
import twext.web2.dav.test.test_options
import twext.web2.dav.test.test_prop
import twext.web2.dav.test.test_put
import twext.web2.dav.test.test_report
import twext.web2.dav.test.test_report_expand

class ACL           (twext.web2.dav.test.test_acl.ACL                    ): resource_class = MyResource
class COPY          (twext.web2.dav.test.test_copy.COPY                  ): resource_class = MyResource
class DELETE        (twext.web2.dav.test.test_delete.DELETE              ): resource_class = MyResource
class LOCK_UNLOCK   (twext.web2.dav.test.test_lock.LOCK_UNLOCK           ): resource_class = MyResource
class MKCOL         (twext.web2.dav.test.test_mkcol.MKCOL                ): resource_class = MyResource
class MOVE          (twext.web2.dav.test.test_move.MOVE                  ): resource_class = MyResource
class OPTIONS       (twext.web2.dav.test.test_options.OPTIONS            ): resource_class = MyResource
class PROP          (twext.web2.dav.test.test_prop.PROP                  ): resource_class = MyResource
class PUT           (twext.web2.dav.test.test_put.PUT                    ): resource_class = MyResource
class REPORT        (twext.web2.dav.test.test_report.REPORT              ): resource_class = MyResource
class REPORT_expand (twext.web2.dav.test.test_report_expand.REPORT_expand): resource_class = MyResource
