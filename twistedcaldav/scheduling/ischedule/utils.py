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

import socket


def getIPsFromHost(host):
    """
    Map a hostname to an IPv4 or IPv6 address.

    @param host: the hostname
    @type host: C{str}

    @return: a C{set} of IPs
    """
    ips = set()
    for family in (socket.AF_INET, socket.AF_INET6):
        results = socket.getaddrinfo(host, None, family, socket.SOCK_STREAM)
        for _ignore_family, _ignore_socktype, _ignore_proto, _ignore_canonname, sockaddr in results:
            ips.add(sockaddr[0])

    return ips
