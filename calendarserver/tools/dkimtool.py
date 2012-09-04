#!/usr/bin/env python
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

from StringIO import StringIO
from subprocess import PIPE
from twext.web2.http_headers import Headers
from twext.web2.stream import MemoryStream
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.python.usage import Options
from twistedcaldav.scheduling.ischedule.dkim import RSA256, DKIMRequest,\
    PublicKeyLookup, DKIMVerifier, DKIMVerificationError
import subprocess
import sys
from twext.web2.client.http import ClientRequest
import rsa


def _doKeyGeneration(options):
    child = subprocess.Popen(
        args=["openssl", "genrsa", str(options["key-size"]),],
        stdout=PIPE,
    )
    output, status = child.communicate()
    if status:
        print "Failed to generate private key"
        sys.exit(1)
    output = output.strip()
    if options["key"]:
        open(options["key"], "w").write(output)
    else:
        print output
    
    child = subprocess.Popen(
        args=["openssl", "rsa", "-pubout",],
        stdout=PIPE,
        stdin=PIPE,
    )
    output, status = child.communicate(output)
    if status:
        print "Failed to generate public key"
        sys.exit(1)
    output = output.strip()
    if options["pub-key"]:
        open(options["pub-key"], "w").write(output)
    else:
        print output
    
    if options["txt"]:
        output = "".join(output.splitlines()[1:-1])
        txt = "v=DKIM1; p=%s" % (output,)
        print txt

@inlineCallbacks
def _doRequest(options):
    
    # Parse the HTTP file
    request = open(options["request"]).read()
    method, uri, headers, stream = _parseRequest(request)

    # Setup signing headers
    sign_headers = options["signing"]
    if sign_headers is None:
        sign_headers = []
        for hdr in ("Host", "Content-Type", "Originator", "Recipient+"):
            if headers.hasHeader(hdr.rstrip("+")):
                sign_headers.append(hdr)
    else:
        sign_headers = sign_headers.split(":")
    
    dkim = DKIMRequest(
        method,
        uri,
        headers,
        stream,
        options["domain"],
        options["selector"],
        options["key"],
        options["algorithm"],
        sign_headers,
        True,
        True,
        int(options["expire"]),
    )
    yield dkim.sign()

    s = StringIO()
    _writeRequest(dkim, s)
    print s.getvalue()


@inlineCallbacks
def _doVerify(options):
    # Parse the HTTP file
    verify = open(options["verify"]).read()
    method, uri, headers, stream = _parseRequest(verify)
    
    request = ClientRequest(method, uri, headers, stream)
    
    # Check for local public key
    if options["pub-key"]:
        PublicKeyLookup_File.pubkeyfile = options["pub-key"]
        lookup = (PublicKeyLookup_File,)
    else:
        lookup = None
    
    dkim = DKIMVerifier(request, lookup)
    
    try:
        yield dkim.verify()
    except DKIMVerificationError, e:
        print "Verification Failed: %s" % (e,)
    else:
        print "Verification Succeeded"


def _parseRequest(request):
    
    lines = request.replace("\r\n", "\n").splitlines()
    
    method, uri, _ignore_version = lines.pop(0).split()
    
    hdrs = []
    body = None
    for line in lines:
        if body is not None:
            body.append(line)
        elif line == "":
            body = []
        elif line[0] in (" ", "\t"):
            hdrs[-1] += line
        else:
            hdrs.append(line)
    
    headers = Headers()
    for hdr in hdrs:
        name, value = hdr.split(':', 1)
        headers.addRawHeader(name, value.lstrip())
    
    stream = MemoryStream("\r\n".join(body))

    return method, uri, headers, stream 
        

def _writeRequest(request, f):
    
    f.write("%s %s HTTP/1.1\r\n" % (request.method, request.uri,))
    for name, valuelist in request.headers.getAllRawHeaders():
        for value in valuelist:
            f.write("%s: %s\r\n" % (name, value))
    f.write("\r\n")
    f.write(request.stream.read())


class PublicKeyLookup_File(PublicKeyLookup):
    
    method = "*"
    pubkeyfile = None    
        
    def getPublicKey(self):
        """
        Do the key lookup using the actual lookup method.
        """
        return rsa.PublicKey.load_pkcs1(open(self.pubkeyfile).read())


def usage(e=None):
    if e:
        print e
        print ""
    try:
        DKIMToolOptions().opt_help()
    except SystemExit:
        pass
    if e:
        sys.exit(64)
    else:
        sys.exit(0)


description = """Usage: dkimtool [options]
Options:
    -h            Print this help and exit

    # Key Generation
    --key-gen          Generate private/public key files
    --key FILE         Private key file to create [stdout]
    --pub-key FILE     Public key file to create [stdout]
    --key-size SIZE    Key size [1024]
    --txt              Also generate the public key TXT record
    
    # Request
    --request FILE      An HTTP request to sign
    --algorithm ALGO    Signature algorithm [rsa-sha256]
    --domain DOMAIN     Signature domain [example.com]
    --selector SELECTOR Signature selector [dkim]
    --key FILE          Private key to use
    --signing HEADERS   List of headers to sign [automatic]
    --expire SECONDS    When to expire signature [no expiry]

    # Verify
    --verify FILE       An HTTP request to verify
    --pkey   FILE       Public key to use in place of
                        q= lookup

Description:
    This utility is for testing DKIM signed HTTP request.

"""


class DKIMToolOptions(Options):
    """
    Command-line options for 'calendarserver_dkimtool'
    """

    synopsis = description

    optFlags = [
        ['verbose', 'v', "Verbose logging."],
        ['key-gen', 'g', "Generate private/public key files"],
        ['txt',     't', "Also generate the public key TXT record"],
    ]

    optParameters = [
        ['key',       'k', None, "Private key file to create [default: stdout]"],
        ['pub-key',   'p', None, 'Public key file to create [default: stdout]'],
        ['key-size',  'x', 1024, 'Key size'],
        ['request',   'r', None, 'An HTTP request to sign'],
        ['algorithm', 'a', RSA256, 'Signature algorithm'],
        ['domain',    'd', 'example.com', 'Signature domain'],
        ['selector',  's', 'dkim', 'Signature selector'],
        ['signing',   'h', None, 'List of headers to sign [automatic]'],
        ['expire',    'e', 3600, 'When to expire signature'],
        ['verify',    'w', None, 'An HTTP request to verify'],
    ]

    def __init__(self):
        super(DKIMToolOptions, self).__init__()
        self.outputName = '-'


@inlineCallbacks
def _runInReactor(fn, options):
    
    try:
        yield fn(options)
    except Exception, e:
        print e
    finally:
        reactor.stop()


def main(argv=sys.argv, stderr=sys.stderr):
    options = DKIMToolOptions()
    options.parseOptions(argv[1:])

    if options["key-gen"]:
        _doKeyGeneration(options)
    elif options["request"]:
        reactor.callLater(0, _runInReactor, _doRequest, options)
        reactor.run()
    elif options["verify"]:
        reactor.callLater(0, _runInReactor, _doVerify, options)
        reactor.run()
    else:
        usage("Invalid options")

if __name__ == '__main__':
    main()
