##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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
iSchedule scheduling.
"""

from twext.web2 import http_headers

# These new HTTP headers should appear with case-preserved
hdrs = ("iSchedule-Version", "iSchedule-Message-ID", "DKIM-Signature",)
http_headers.casemappingify(dict([(i, i) for i in hdrs]))
