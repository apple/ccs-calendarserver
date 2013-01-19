#!/usr/bin/python
# -*- test-case-name: twext.python.test.test_sendmsg -*-
##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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

if __name__ == '__main__':
    from twext.python.sendfd import recvfd
    import sys, os
    fd, description = recvfd(int(sys.argv[1]))
    os.write(fd, "Test fixture data: %s.\n" % (description,))
    os.close(fd)

    
