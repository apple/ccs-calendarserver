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

from __future__ import print_function, with_statement
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



def updateCRL(caPath):
    """
    Create a new certificate authority with supporting files at the specified path.

    @param caPath: path to store CA files
    @type caPath: L{str}
    """

    print("Updating CRLs for Certificate Authority")

    crlfile = os.path.join(caPath, "crl.pem".format(user))
    certfile = os.path.join(caPath, "cacert.pem")
    certcrlfile = os.path.join(caPath, "cacertcrl.pem")

    # Generate CRL
    subprocess.call("openssl ca -batch -gencrl -out {certout} -passin pass:{passwd} -notext -config openssl.cnf".format(
        certout=crlfile,
        passwd="secret",
    ).split())

    with open(certfile) as f:
        with open(crlfile) as g:
            with open(certcrlfile, "w") as h:
                h.write(f.read())
                h.write(g.read())



def makeUserCertificate(caPath, user, self_signed=False):
    """
    Create a new certificate for the specified user and sign using the CA cert.

    @param caPath: path of CA files
    @type caPath: L{str}
    @param user: user id
    @type user: L{str}
    @param self_signed: L{True} to generate a self-signed cert, L{False} to generate a CA signed cert
    @type self_signed: L{bool}
    """
    print("Creating new Certificate for {}".format(user))

    keyfile = os.path.join(caPath, "certs", "{}-key.pem".format(user))
    reqfile = os.path.join(caPath, "certs", "{}-req.pem".format(user))
    certfile = os.path.join(caPath, "certs", "{}-cert.pem".format(user))
    pemfile = os.path.join(caPath, "certs", "{}.pem".format(user))
    pkcs12file = os.path.join(caPath, "certs", "{}.p12".format(user))

    if not self_signed:
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
    else:
        # Create a self-signed certificate
        subprocess.call("openssl req -batch -new -x509 -keyout {keyout} -out {certout} -passout pass:{passwd} -days {days} -subj {subject}".format(
            keyout=keyfile,
            certout=certfile,
            passwd="secret",
            days=365 * 3,
            subject="/C=US/ST=CA/O=Example.com/CN={user}/emailAddress={user}@example.com".format(user=user)
        ).split())


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
    print("--bogus N  generate a set of self-signed user certificates for \"bogus01\", \"bogus02\", etc. up to \"bogusN\"")
    print("")
    print("Version: 1")


if __name__ == '__main__':

    caPath = "demoCA"
    newca = False
    newuser = None
    users = None
    bogus = None
    usersCreated = False

    options, args = getopt(sys.argv[1:], "h", ["newca", "newuser=", "users=", "bogus="])

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
        elif option == "--bogus":
            bogus = int(value)

    if newca:
        newCA(caPath)

    if newuser:
        makeUserCertificate(caPath, newuser)
        usersCreated = True

    if users:
        for user in range(1, users + 1):
            makeUserCertificate(caPath, "user{:02d}".format(user))
        usersCreated = True

    if bogus:
        for user in range(1, bogus + 1):
            makeUserCertificate(caPath, "bogus{:02d}".format(user), self_signed=True)
        usersCreated = True

    if usersCreated:
        updateCRL(caPath)

    print("Certificate Authority operations complete.")
