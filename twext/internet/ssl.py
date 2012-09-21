##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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
Extentions to twisted.internet.ssl.
"""

__all__ = [
    "ChainingOpenSSLContextFactory",
]

from OpenSSL.SSL import Context as SSLContext, SSLv3_METHOD

from twisted.internet.ssl import DefaultOpenSSLContextFactory


class ChainingOpenSSLContextFactory (DefaultOpenSSLContextFactory):
    def __init__(
        self, privateKeyFileName, certificateFileName,
        sslmethod=SSLv3_METHOD, certificateChainFile=None,
        passwdCallback=None, ciphers=None
    ):
        self.certificateChainFile = certificateChainFile
        self.passwdCallback = passwdCallback
        self.ciphers = ciphers

        DefaultOpenSSLContextFactory.__init__(
            self,
            privateKeyFileName,
            certificateFileName,
            sslmethod=sslmethod
        )

    def cacheContext(self):
        # Unfortunate code duplication.
        ctx = SSLContext(self.sslmethod)

        if self.ciphers is not None:
            ctx.set_cipher_list(self.ciphers)

        if self.passwdCallback is not None:
            ctx.set_passwd_cb(self.passwdCallback)

        ctx.use_certificate_file(self.certificateFileName)
        ctx.use_privatekey_file(self.privateKeyFileName)

        if self.certificateChainFile != "":
            ctx.use_certificate_chain_file(self.certificateChainFile)

        self._context = ctx
