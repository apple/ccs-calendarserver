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
#
# DRI: Cyrus Daboo, cdaboo@apple.com
##


from twisted.web2.auth.digest import DigestCredentialFactory

"""
Overrides twisted.web2.auth.digest to allow specifying a qop value as a configuration parameter.

"""

class QopDigestCredentialFactory(DigestCredentialFactory):
    """
    See twisted.web2.auth.digest.DigestCredentialFactory
    """

    def __init__(self, algorithm, qop, realm):
        """
        @type algorithm: C{str}
        @param algorithm: case insensitive string that specifies
            the hash algorithm used, should be either, md5, md5-sess
            or sha

        @type qop: C{str}
        @param qop: case insensitive string that specifies
            the qop to use

        @type realm: C{str}
        @param realm: case sensitive string that specifies the realm
            portion of the challenge
        """
        super(QopDigestCredentialFactory, self).__init__(algorithm, realm)
        self.qop = qop

    def getChallenge(self, peer):
        """
        Do the default behavior but then strip out any 'qop' from the challenge fields
        if no qop was specified.
        """

        challenge = super(QopDigestCredentialFactory, self).getChallenge(peer)
        if self.qop:
            challenge['qop'] = self.qop
        else:
            del challenge['qop']
        return challenge
            

    def decode(self, response, request):
        """
        Do the default behavior but then strip out any 'qop' from the credential fields
        if no qop was specified.
        """

        credentials = super(QopDigestCredentialFactory, self).decode(response, request)
        if not self.qop and credentials.fields.has_key('qop'):
            del credentials.fields['qop']
        return credentials
