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

import httplib
import socket
_haveSSL = False
try:
    import ssl as sslmodule
    _haveSSL = True
except ImportError:
    pass

if _haveSSL:
    class HTTPSConnection_SSLv3(httplib.HTTPSConnection):
        "This class allows communication via SSL."

        def connect(self):
            "Connect to a host on a given (SSL) port."

            sock = socket.create_connection((self.host, self.port), self.timeout)
            self.sock = sslmodule.wrap_socket(sock, self.key_file, self.cert_file, ssl_version=sslmodule.PROTOCOL_SSLv3)
else:
    HTTPSConnection_SSLv3 = httplib.HTTPSConnection

https_v23_connects = set()
https_v3_connects = set()

def SmartHTTPConnection(host, port, ssl):

    def trySSL(cls,):
        connect = cls(host, port)
        connect.connect()
        return connect

    if ssl:
        if (host, port) in https_v3_connects:
            try:
                return trySSL(HTTPSConnection_SSLv3)
            except:
                https_v3_connects.remove((host, port))
        elif (host, port) in https_v23_connects:
            try:
                return trySSL(httplib.HTTPSConnection)
            except:
                https_v23_connects.remove((host, port))

        try:
            https_v3_connects.add((host, port))
            return trySSL(HTTPSConnection_SSLv3)
        except:
            https_v3_connects.remove((host, port))

        try:
            https_v23_connects.add((host, port))
            return trySSL(httplib.HTTPSConnection)
        except:
            https_v23_connects.remove((host, port))

        raise RuntimeError("Cannot connect via with SSLv23 or SSLv3")
    else:
        connect = httplib.HTTPConnection(host, port)
        connect.connect()
        return connect
