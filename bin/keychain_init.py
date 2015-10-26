#!/usr/bin/env python
##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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

from subprocess import Popen, PIPE, STDOUT
import os
import re
import sys

identity_preference = "org.calendarserver.test"
certname_regex = re.compile(r'"alis"<blob>="(.*)"')

certificate_name = "localhost"
certificate_file = "./twistedcaldav/test/data/server.pem"

def identityExists():
    child = Popen(
        args=[
            "/usr/bin/security", "get-identity-preference",
            "-s", identity_preference,
            "login.keychain",
        ],
        stdout=PIPE, stderr=STDOUT,
    )
    output, _ignore_error = child.communicate()

    if child.returncode:
        print("Could not find identity '{}'".format(identity_preference))
        return False
    else:
        match = certname_regex.search(output)
        if not match:
            raise RuntimeError("No certificate found for identity '{}'".format(identity_preference))
        else:
            print("Found certificate '{}' for identity '{}'".format(match.group(1), identity_preference))
            return True



def identityCreate():
    child = Popen(
        args=[
            "/usr/bin/security", "set-identity-preference",
            "-s", identity_preference,
            "-c", certificate_name,
        ],
        stdout=PIPE, stderr=STDOUT,
    )
    output, error = child.communicate()

    if child.returncode:
        raise RuntimeError(error if error else output)
    else:
        print("Created identity '{}' for certificate '{}'".format(identity_preference, certificate_name))
        return True



def certificateExists():
    child = Popen(
        args=[
            "/usr/bin/security", "find-certificate",
            "-c", certificate_name,
            "login.keychain",
        ],
        stdout=PIPE, stderr=STDOUT,
    )
    _ignore_output, _ignore_error = child.communicate()

    if child.returncode:
        print("No certificate '{}' found for identity '{}'".format(certificate_name, identity_preference))
        return False
    else:
        print("Found certificate '{}'".format(certificate_name))
        return True



def certificateImport():
    child = Popen(
        args=[
            "/usr/bin/security", "import",
            certificate_file,
            "-k", "login.keychain",
            "-A",
        ],
        stdout=PIPE, stderr=STDOUT,
    )
    output, error = child.communicate()

    if child.returncode:
        raise RuntimeError(error if error else output)
    else:
        print("Imported certificate '{}'".format(certificate_name))
        return True

if __name__ == '__main__':

    if os.path.isfile("/usr/bin/security"):
        # If the identity exists we are done
        if identityExists():
            sys.exit(0)

        # Check for certificate and import if not present
        if not certificateExists():
            certificateImport()

        # Create the identity
        identityCreate()

    else:
        raise RuntimeError("Keychain access utility ('security') not found")
