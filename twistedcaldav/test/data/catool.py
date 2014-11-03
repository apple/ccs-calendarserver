#!/usr/bin/env python
##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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

from __future__ import print_function
from getopt import getopt
import sys
import shutil
import os
import subprocess


def newCA(caPath):
    """
    Create a new certificate authority with supporting files at the specified path.

    @param caPath: path to store CA files
    @type caPath: L{str}
    """

    print("Creating new Certificate Authority")

    # Delete anything that exists first
    if os.path.exists(caPath):
        shutil.rmtree(caPath)

    # Create directories
    os.mkdir(caPath)
    os.mkdir(os.path.join(caPath, "certs"))
    os.mkdir(os.path.join(caPath, "crl"))
    os.mkdir(os.path.join(caPath, "newcerts"))
    os.mkdir(os.path.join(caPath, "private"))
    with open(os.path.join(caPath, "index.txt"), "w"):
        pass

    keyfile = os.path.join(caPath, "private", "cakey.pem")
    reqfile = os.path.join(caPath, "careq.pem")
    certfile = os.path.join(caPath, "cacert.pem")

    # Create a certificate request
    subprocess.call("openssl req -batch -new -keyout {keyout} -out {reqout} -passout pass:{passwd} -subj {subject}".format(
        keyout=keyfile,
        reqout=reqfile,
        passwd="secret",
        subject="/C=US/ST=CA/O=Example.com/CN=admin/emailAddress=admin@example.com"
    ).split())

    # Create a CA certificate
    subprocess.call("openssl ca -batch -create_serial -out {certout} -days {days} -batch -keyfile {keyfile} -passin pass:{passwd} -notext -selfsign -extensions v3_ca -infiles {reqin}".format(
        keyfile=keyfile,
        reqin=reqfile,
        certout=certfile,
        days=365 * 3,
        passwd="secret",
    ).split())

    os.remove(reqfile)



def makeUserCertificate(caPath, user):
    """
    Create a new certificate for the specified user and sign using the CA cert.

    @param caPath: path of CA files
    @type caPath: L{str}
    @param user: user id
    @type user: L{str}
    """
    print("Creating new Certificate for {}".format(user))

    keyfile = os.path.join(caPath, "certs", "{}-key.pem".format(user))
    reqfile = os.path.join(caPath, "certs", "{}-req.pem".format(user))
    certfile = os.path.join(caPath, "certs", "{}-cert.pem".format(user))
    pemfile = os.path.join(caPath, "certs", "{}.pem".format(user))
    pkcs12file = os.path.join(caPath, "certs", "{}.p12".format(user))

    # Create a certificate request
    subprocess.call("openssl req -batch -new -keyout {keyout} -out {reqout} -passout pass:{passwd} -days {days} -subj {subject}".format(
        keyout=keyfile,
        reqout=reqfile,
        passwd="secret",
        days=365 * 3,
        subject="/C=US/ST=CA/O=Example.com/CN={user}/emailAddress={user}@example.com".format(user=user)
    ).split())

    # Sign certificate
    subprocess.call("openssl ca -batch -policy policy_anything -out {certout} -passin pass:{passwd} -notext -infiles {reqin}".format(
        certout=certfile,
        reqin=reqfile,
        passwd="secret",
    ).split())

    os.remove(reqfile)

    with open(keyfile) as f:
        privkey = f.read()
    with open(certfile) as f:
        pubkey = f.read()

    with open(pemfile, "w") as f:
        f.write(privkey)
        f.write(pubkey)

    os.remove(keyfile)
    os.remove(certfile)

    # PKCS12 certificate
    subprocess.call("openssl pkcs12 -export -in {pemin} -out {p12out} -passin pass:{passwd} -passout pass:{passwd}".format(
        pemin=pemfile,
        p12out=pkcs12file,
        passwd="secret",
    ).split())



def usage():
    print("catool [OPTIONS]")
    print("")
    print("OPTIONS")
    print("-h         print help and exit")
    print("--newca   create a new CA - delete any existing demoCA directory")
    print("--newuser USER  create a new user certificate with user id \"USER\" signed by the CA")
    print("--users N  generate a set of user certificates for \"user01\", \"user02\", etc. up to \"userN\"")
    print("")
    print("Version: 1")


if __name__ == '__main__':

    caPath = "demoCA"
    newca = False
    newuser = None
    users = None

    options, args = getopt(sys.argv[1:], "h", ["newca", "newuser=", "users="])

    for option, value in options:
        if option == "-h":
            usage()
            sys.exit(0)
        elif option == "--newca":
            newca = True
        elif option == "--newuser":
            newuser = value
        elif option == "--users":
            users = int(value)

    if newca:
        newCA(caPath)

    if newuser:
        makeUserCertificate(caPath, newuser)

    if users:
        for user in range(1, users + 1):
            makeUserCertificate(caPath, "user{:02d}".format(user))

    print("Certificate Authority operations complete.")
