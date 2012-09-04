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

from twext.python.log import Logger
from twext.web2.client.http import ClientRequest
from twext.web2.dav.util import allDataFromStream
from twext.web2.stream import MemoryStream
from twisted.internet.defer import inlineCallbacks, returnValue
import base64
import binascii
import collections
import hashlib
import rsa
import textwrap
import time
import uuid

"""
DKIM HTTP message generation and validation,
"""

log = Logger()

# DKIM/iSchedule Constants
RSA1   = "rsa-sha1"
RSA256 = "rsa-sha256"
Q_DNS  = "dns/txt"
Q_HTTP = "http/well-known"

KEY_SERVICE_TYPE = "ischedule"

# Headers
DKIM_SIGNATURE = "DKIM-Signature"
ISCHEDULE_VERSION = "iSchedule-Version"
ISCHEDULE_VERSION_VALUE = "1.0"
ISCHEDULE_MESSAGE_ID = "iSchedule-Message-ID"

class DKIMUtils(object):
    """
    Some useful functions.
    """
    
    @staticmethod
    def hashlib_method(algorithm):
        """
        Return hashlib function for DKIM algorithm.
        """
        return {
            RSA1  : hashlib.sha1,
            RSA256: hashlib.sha256,
        }[algorithm]
    
    @staticmethod
    def hash_name(algorithm):
        """
        Return RSA hash name for DKIM algorithm.
        """
        return {
            RSA1  : "SHA-1",
            RSA256: "SHA-256"
        }[algorithm]


    @staticmethod
    def extractTags(data):
        """
        Split a DKIM tag list into a dict, removing unneeded whitespace.
        """
        # Extract tags from the data
        splits = [item.strip() for item in data.split(";")]
        dkim_tags = {}
        for item in splits:
            name, value = item.split("=", 1)
            dkim_tags[name.strip()] = value.strip()
        return dkim_tags

    @staticmethod
    def canonicalizeHeader(name, value, remove_b=None):
        """
        Canonicalize the header using "relaxed" method. Optionally remove the b= value from
        any DKIM-Signature present.
        
        FIXME: this needs to be smarter about where valid WSP can occur in a header. Right now it will
        blindly collapse all runs of SP/HTAB into a single SP. That could be wrong if a legitimate sequence of
        SP/HTAB occurs in a header value.
        
        @param name: header name
        @type name: C{str}
        @param value: header value
        @type value: C{str}
        @param remove_b: the b= value to remove, or C{None} if no removal needed
        @type remove_b: C{str} or C{None}
        """
        
        # Basic relaxed behavior
        name = name.lower()
        value = " ".join(value.split())

        # Special case DKIM-Signature: remove the b= value for signature
        if remove_b is not None and name == DKIM_SIGNATURE.lower():
            pos = value.find(remove_b)
            value = value[:pos] + value[pos + len(remove_b):]
            value = " ".join(value.split())

        return "%s:%s\r\n" % (name, value,)

    

class DKIMRequest(ClientRequest):
    """
    A ClientRequest that optionally creates a DKIM signature.
    """
    
    keys = {}

    def __init__(
        self,
        method,
        uri,
        headers,
        stream,
        domain,
        selector,
        key_file,
        algorithm,
        sign_headers,
        useDNSKey,
        useHTTPKey,
        expire,
    ):
        """
        Create a DKIM request, which is a regular client request with the additional information needed to sign the message.
        
        @param method: HTTP method to use
        @type method: C{str}
        @param uri: request-URI
        @type uri: C{str}
        @param headers: request headers 
        @type headers: L{http_headers}
        @param stream: body data
        @type stream: L{Stream}
        @param domain: the signing domain
        @type domain: C{str}
        @param selector: the signing key selector
        @type selector: C{str}
        @param key_file: path to a private key file
        @type key_file: C{str}
        @param algorithm: the signing algorithm to use
        @type algorithm: C{str}
        @param sign_headers: list of header names to sign - to "over sign" a header append a "+" to the name
        @type sign_headers: C{tuple}
        @param useDNSKey: whether or not to add DNS TXT lookup as a key lookup option
        @type useDNSKey: C{bool}
        @param useHTTPKey: whether or not to add HTTP .well-known as a key lookup option
        @type useHTTPKey: C{bool}
        @param expire: number of seconds to expiration of signature 
        @type expire: C{int}
        """
        super(DKIMRequest, self).__init__(method, uri, headers, stream)
        self.domain = domain
        self.selector = selector
        self.algorithm = algorithm
        self.key_file = key_file
        self.sign_headers = sign_headers
        self.time = str(int(time.time()))
        self.expire = str(int(time.time() + expire))
        
        assert self.domain
        assert self.selector
        assert self.algorithm in (RSA1, RSA256,)
        assert useDNSKey or useHTTPKey

        self.hash_method = DKIMUtils.hashlib_method(self.algorithm)
        self.hash_name = DKIMUtils.hash_name(self.algorithm)
        
        self.keyMethods = []
        if useDNSKey: self.keyMethods.append(Q_DNS)
        if useHTTPKey: self.keyMethods.append(Q_HTTP)
        
        self.message_id = str(uuid.uuid4())


    @inlineCallbacks
    def sign(self):
        """
        Generate the DKIM headers by signing the request. This should only be called once on the request and there must
        be no changes to the request (no headers, no body change) after it is called.
        """

        # Get the headers and the DKIM-Signature tags        
        headers, dkim_tags = (yield self.signatureHeaders())

        # Sign the hash
        signature = self.generateSignature(headers)
    
        # Complete the header
        dkim_tags[-1] = ("b", signature,)
        dkim_header = "; ".join(["%s=%s" % item for item in dkim_tags])
        self.headers.addRawHeader(DKIM_SIGNATURE, dkim_header)
        
        log.debug("DKIM: Generated header: DKIM-Signature:%s" % (dkim_header,))
        log.debug("DKIM: Signed headers:\n%s" % (headers,))

        returnValue(signature)

        
    @inlineCallbacks
    def bodyHash(self):
        """
        Generate the hash of the request body data.
        """

        # We need to play a trick with the request stream as we can only read it once. So we
        # read it, store the value in a MemoryStream, and replace the request's stream with that,
        # so the data can be read again.
        data = (yield allDataFromStream(self.stream))
        self.stream = MemoryStream(data if data is not None else "")
        self.stream.doStartReading = None

        returnValue(base64.b64encode(self.hash_method(data).digest()))


    @inlineCallbacks
    def signatureHeaders(self):
        """
        Generate the headers that are going to be signed as well as the DKIM-Signature tags.
        """
        
        # Make sure we have the required iSchedule headers
        self.headers.addRawHeader(ISCHEDULE_VERSION, ISCHEDULE_VERSION_VALUE)
        self.headers.addRawHeader(ISCHEDULE_MESSAGE_ID, self.message_id)
        self.sign_headers += (ISCHEDULE_VERSION, ISCHEDULE_MESSAGE_ID,)

        # Figure out all the existing headers to sign
        headers = []
        sign_headers = []
        raw = dict([(name.lower(), values) for name, values in self.headers.getAllRawHeaders()])
        for name in self.sign_headers:
            oversign = name[-1] == "+"
            name = name.rstrip("+")
            for value in raw.get(name.lower(), ()):
                headers.append(DKIMUtils.canonicalizeHeader(name, value))
                sign_headers.append(name)
            if oversign:
                sign_headers.append(name)

        # Generate the DKIM header tags we care about
        dkim_tags = []
        dkim_tags.append(("v", "1",))
        dkim_tags.append(("d", self.domain,))
        dkim_tags.append(("s", self.selector,))
        dkim_tags.append(("t", self.time,))
        dkim_tags.append(("x", self.expire,))
        dkim_tags.append(("a", self.algorithm,))
        dkim_tags.append(("q", ":".join(self.keyMethods),))
        dkim_tags.append(("http", base64.encodestring("%s:%s" % (self.method, self.uri,)).strip()))
        dkim_tags.append(("c", "relaxed/simple",))
        dkim_tags.append(("h", ":".join(sign_headers),))
        dkim_tags.append(("bh", (yield self.bodyHash()),))
        dkim_tags.append(("b", "",))
        dkim_header = "; ".join(["%s=%s" % item for item in dkim_tags])

        headers.append(DKIMUtils.canonicalizeHeader(DKIM_SIGNATURE, dkim_header))
        headers = "".join(headers)

        returnValue((headers, dkim_tags,))


    def generateSignature(self, headers):
        # Sign the hash
        if self.key_file not in self.keys:
            self.keys[self.key_file] = rsa.PrivateKey.load_pkcs1(open(self.key_file).read())
        return base64.b64encode(rsa.sign(headers, self.keys[self.key_file], self.hash_name))



class DKIMVerificationError(Exception):
    """
    Used to indicate a DKIM verification error.
    """
    pass


class DKIMVerifier(object):
    """
    Class used to verify an DKIM-signed HTTP request.
    """
    
    def __init__(self, request, key_lookup=None):
        """
        @param request: The HTTP request to process
        @type request: L{twext.server.Request}
        """
        self.request = request
        self.dkim_tags = {}

        # Prefer HTTP over DNS when both are present
        self.key_lookup_methods = (
            PublicKeyLookup_HTTP_WellKnown,
            PublicKeyLookup_DNSTXT,
        ) if key_lookup is None else key_lookup
            
            

    @inlineCallbacks
    def verify(self):
        """
        @raise: DKIMVerificationError
        """
        
        # Check presence of DKIM header
        self.processDKIMHeader()
        
        # Extract the set of canonicalized headers being signed
        headers = self.extractSignedHeaders()
        log.debug("DKIM: Signed headers:\n%s" % (headers,))
        
        # Locate the public key
        pubkey = (yield self.locatePublicKey())
        if pubkey is None:
            raise DKIMVerificationError("No public key to verify the DKIM signature")            
        
        # Do header verification
        try:
            rsa.verify(headers, base64.b64decode(self.dkim_tags["b"]), pubkey)
        except rsa.VerificationError:
            msg = "Could not verify signature"
            log.debug("DKIM: %s: DKIM-Signature:%s" % (msg, self.request.headers.getRawHeaders(DKIM_SIGNATURE),))
            raise DKIMVerificationError(msg)

        # Do body validation
        data = (yield allDataFromStream(self.request.stream))
        self.request.stream = MemoryStream(data if data is not None else "")
        self.request.stream.doStartReading = None
        bh = base64.b64encode(self.hash_method(data).digest())
        if bh != self.dkim_tags["bh"]:
            msg = "Could not verify the DKIM body hash"
            log.debug("DKIM: %s: DKIM-Signature:%s" % (msg, self.request.headers.getRawHeaders(DKIM_SIGNATURE),))
            raise DKIMVerificationError(msg)

        
    def processDKIMHeader(self):
        """
        Extract the DKIM-Signature header and process the tags.
        
        @raise: DKIMVerificationError
        """
        
        # Check presence of header
        dkim = self.request.headers.getRawHeaders(DKIM_SIGNATURE)
        if dkim is None:
            msg = "No DKIM-Signature header present in the request"
            log.debug("DKIM: " + msg)
            raise DKIMVerificationError(msg)
        if len(dkim) != 1:
            # TODO: This might need to be changed if we ever support forwarding of iSchedule messages - the forwarder
            # might also sign the message and add its own header
            msg = "Only one DKIM-Signature allowed in the request"
            log.debug("DKIM: " + msg)
            raise DKIMVerificationError(msg)
        dkim = dkim[0]
        log.debug("DKIM: Found header: DKIM-Signature:%s" % (dkim,))

        # Extract tags from the header
        self.dkim_tags = DKIMUtils.extractTags(dkim)
        
        # Verify validity of tags
        required_tags = ("v", "a", "b", "bh", "c", "d", "h", "s", "http",)
        for tag in required_tags:
            if tag not in self.dkim_tags:
                msg = "Missing DKIM-Signature tag: %s" % (tag,)
                log.debug("DKIM: " + msg)
                raise DKIMVerificationError(msg)

        check_values = {
            "v": ("1",),
            "a": (RSA1, RSA256,),
            "c": ("relaxed", "relaxed/simple",),
            "q": (Q_DNS, Q_HTTP,),
        }
        for tag, values in check_values.items():
            if tag not in required_tags and tag not in self.dkim_tags:
                pass
            
            # Handle some structured values
            if tag == "q":
                test = self.dkim_tags[tag].split(":")
            else:
                test = (self.dkim_tags[tag],)
            for item in test:
                if item not in values:
                    msg = "Tag: %s has incorrect value: %s" % (tag, self.dkim_tags[tag],)
                    log.debug("DKIM: " + msg)
                    raise DKIMVerificationError(msg)

        # Check expiration
        if "x" in self.dkim_tags:
            diff_time = int(time.time()) - int(self.dkim_tags["x"])
            if diff_time > 0:
                msg = "Signature expired: %d seconds" % (diff_time,)
                log.debug("DKIM: " + msg)
                raise DKIMVerificationError(msg)

        # Check HTTP method/request-uri
        try:
            http_tag = base64.decodestring(self.dkim_tags["http"])
        except binascii.Error:
            msg = "Tag: http is not valid base64"
            log.debug("DKIM: " + msg)
            raise DKIMVerificationError(msg)
        try:
            method, uri = http_tag.split(":", 1)
        except ValueError:
            msg = "Tag: base64-decoded http is not valid: %s" % (http_tag,)
            log.debug("DKIM: " + msg)
            raise DKIMVerificationError(msg)
        if method != self.request.method:
            msg = "Tag: http method does not match: %s" % (method,)
            log.debug("DKIM: " + msg)
            raise DKIMVerificationError(msg)
        if uri != self.request.uri:
            msg = "Tag: http request-URI does not match: %s" % (uri,)
            log.debug("DKIM: " + msg)
            raise DKIMVerificationError(msg)
            

        # Some useful bits
        self.hash_method = DKIMUtils.hashlib_method(self.dkim_tags["a"])
        self.key_methods = self.dkim_tags["q"].split(":")


    def extractSignedHeaders(self):
        """
        Extract the set of headers from the request that are supposed to be signed. Canonicalize them
        and return the expected signed data.
        """

        # Extract all the expected signed headers taking into account the possibility of "over_counting"
        # headers - a technique used to ensure headers cannot be added in transit
        header_list = [hdr.strip() for hdr in self.dkim_tags["h"].split(":")]
        header_counter = collections.defaultdict(int)
        
        headers = []
        for header in header_list:
            actual_headers = self.request.headers.getRawHeaders(header)
            if actual_headers:
                try:
                    headers.append((header, actual_headers[header_counter[header]],))
                except IndexError:
                    pass
            header_counter[header] += 1

        # DKIM-Signature is always included at the end
        headers.append((DKIM_SIGNATURE, self.request.headers.getRawHeaders(DKIM_SIGNATURE)[0],))

        # Now canonicalize the values
        return "".join([DKIMUtils.canonicalizeHeader(name, value, remove_b=self.dkim_tags["b"]) for name, value in headers])


    @inlineCallbacks
    def locatePublicKey(self):
        """
        Try to lookup the public key matching the signature.
        """
        
        for lookup in self.key_lookup_methods:
            if lookup.method in self.key_methods or lookup.method == "*":
                pubkey = (yield lookup(self.dkim_tags).getPublicKey())
                if pubkey is not None:
                    returnValue(pubkey)
        else:
            returnValue(None)
    

class PublicKeyLookup(object):
    """
    Abstract base class for public key lookup methods.
    
    The L{method} attribute indicated the DKIM q= lookup method that the class will support, or if set to "*",
    the class will handle any q= value.
    """
    
    keyCache = {}
    method = None

    def __init__(self, dkim_tags):
        self.dkim_tags = dkim_tags
    
        
    @inlineCallbacks
    def getPublicKey(self, useCache=True):
        """
        Get key from cache or directly do query.

        @param useCache: whether or not to use the cache
        @type useCache: C{bool}
        """
        key = self._getSelectorKey()
        if key not in PublicKeyLookup.keyCache or not useCache:
            pubkeys = (yield self._lookupKeys())
            PublicKeyLookup.keyCache[key] = pubkeys
        
        returnValue(self._selectKey())
    
    
    def _getSelectorKey(self):
        """
        Get a token used to uniquely identify the key being looked up. Token format will
        depend on the lookup method.
        """
        raise NotImplementedError
        
    
    def _lookupKeys(self):
        """
        Do the key lookup using the actual lookup method. Return a C{list} of C{dict}
        that contains the key tag-list. Return a L{Deferred}.
        """
        raise NotImplementedError
    
    
    def _selectKey(self):
        """
        Select a specific key from the list that best matches the DKIM-Signature tags
        """
        
        pubkeys = PublicKeyLookup.keyCache.get(self._getSelectorKey(), [])
        for pkey in pubkeys:
            # Check validity
            if pkey.get("v", "DKIM1") != "DKIM1":
                continue
            
            # Check key type
            if pkey.get("k", "rsa") != "rsa":
                continue

            # Check valid hash algorithms
            hashes = set([hash.strip() for hash in pkey.get("h", "sha1:sha256").split(":")])
            if self.dkim_tags["a"][4:] not in hashes:
                continue
            
            # Service type
            if pkey.get("s", KEY_SERVICE_TYPE) not in ("*", KEY_SERVICE_TYPE,):
                continue
    
            # Non-revoked key
            if len(pkey.get("p", "")) == 0:
                continue
            
            return self._makeKey(pkey)
        
        log.debug("DKIM: No valid public key: %s %s" % (self._getSelectorKey(), pubkeys,))
        return None
    
    
    def _makeKey(self, pkey):
        """
        Turn the key tag list into an actual RSA public key object

        @param pkey: key tag list
        @type pkey: C{list}
        """
        key_data = """-----BEGIN PUBLIC KEY-----
%s
-----END PUBLIC KEY-----
""" % (textwrap.wrap(pkey["p"], 64),)

        try:
            return rsa.PublicKey.load_pkcs1(key_data)
        except:
            log.debug("DKIM: Unable to make public key:\n%s" % (key_data,))
            return None
        
    
    def flushCache(self):
        PublicKeyLookup.keyCache = {}



class PublicKeyLookup_DNSTXT(PublicKeyLookup):
    
    
    method = Q_DNS


    def _getSelectorKey(self):
        """
        Get a token used to uniquely identify the key being looked up. Token format will
        depend on the lookup method.
        """
        return "%s._domainkey.%s" % (self.dkim_tags["s"], self.dkim_tags["d"],)
        
    
    def _lookupKeys(self):
        """
        Do the key lookup using the actual lookup method.
        """
        raise NotImplementedError
        


class PublicKeyLookup_HTTP_WellKnown(PublicKeyLookup):
    
    
    method = Q_HTTP


    def _getSelectorKey(self):
        """
        Get a token used to uniquely identify the key being looked up. Token format will
        depend on the lookup method.
        """
        return "https://%s/.well-known/domainkey/%s" % (self.dkim_tags["d"], self.dkim_tags["s"],)
        
    
    def _lookupKeys(self):
        """
        Do the key lookup using the actual lookup method.
        """
        raise NotImplementedError

