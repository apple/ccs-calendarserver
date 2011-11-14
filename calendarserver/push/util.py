##
# Copyright (c) 2011 Apple Inc. All rights reserved.
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

from OpenSSL import crypto

def getAPNTopicFromCertificate(certPath):
    """
    Given the path to a certificate, extract the UID value portion of the
    subject, which in this context is used for the associated APN topic.

    @param certPath: file path of the certificate
    @type certPath: C{str}

    @return: C{str} topic, or empty string if value is not found
    """
    certData = open(certPath).read()
    x509 = crypto.load_certificate(crypto.FILETYPE_PEM, certData)
    subject = x509.get_subject()
    components = subject.get_components()
    for name, value in components:
        if name == "UID":
            return value
    return ""
