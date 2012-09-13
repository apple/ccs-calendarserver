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

from twext.web2.http_headers import Headers, MimeType
from twext.web2.stream import MemoryStream
from twisted.internet.defer import inlineCallbacks, succeed
from twistedcaldav.scheduling.ischedule.dkim import DKIMRequest, DKIMVerifier, \
    DKIMVerificationError, DKIMUtils, PublicKeyLookup_DNSTXT, \
    PublicKeyLookup_HTTP_WellKnown, PublicKeyLookup_PrivateExchange
import base64
import hashlib
import rsa
import time
import twistedcaldav.test.util
import os

class TestDKIMBase (twistedcaldav.test.util.TestCase):
    """
    DKIM support tests
    """

    class PublicKeyLookup_Testing(PublicKeyLookup_HTTP_WellKnown):

        keys = []

        def _lookupKeys(self):
            """
            Do the key lookup using the actual lookup method.
            """
            return succeed(self.keys)


    def setUp(self):
        super(TestDKIMBase, self).setUp()

        self.private_keyfile = self.mktemp()
        f = open(self.private_keyfile, "w")
        f.write("""-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEAw7bJxD1k5VSA5AqdfmJ7vj99oKQ4qYtSeJ5HiK6W40dzC++k
LweUWLzeUErgXwcJlyOC6rqVVPBfSJq4l7yPdVqpWUo6s2jnUsSWOfhpre22yc4B
K0QY2Euc3R+gT59eM0mtJPtWaQw5BmQ2GrV6f0OUiKi17jEPasKcxf1qZrWU0+Ik
D2DhUCuRrNb/baUkuIkxoit6M7k7s5X9swT1hE/Eso0gS79FSti1fkDeoPZ296Gu
5uYWdpaLl03Nr0w65Gbw+2v79AcwOyvbZD6y9xYGLWubic0dUeWuhUipZdmQf8Bd
t7cZVgjQX/giQQqqLDFhfNFwapUZDhS7TCtujQIDAQABAoIBADfFuzHFHR+NOT3D
GKaPghvxE+fXZJ5MKbBdypzUxAL4tXxNSkhsrIWtLN1MuSvbYYxEfmZNzYhrB3w1
Oy1ieq9CqsfbM2c1GdaoVvcmJ1d9Sn2vyv19ZmcdBRKulIycKcgL0t+bEEDXTtjX
beOmm8XwiD95dH7wVChkVTDGyq+BxtSY6wav9y15zWnBH7+BAeq3OnKaNIQB0iTI
UA41jWocKYI18/6D5gQTDSoYvKB7saFVGw9IgmmHA/3rYztcHCxUoE15x7wWuwtF
vzQanEt/QwEEFMibNTjvfIUPoeIeQH7MzcD56AL9u/cs8LNeSbappWE7BneQ0ll3
CfTsAQECgYEA/eoDkpPMWxuoSrZ1oXLxeImEAB2EHNs4UV9dmcUkhNeYZP0rv7pL
4jpkNHTRvFeeovy5khXhykb9BUYDuZy6rcELlFxpCKYRw3d+PPWM+wfqmJp+fIN7
Z4F1Kpznt0F2e+9LXF1Qi5bM2dHy1maxEjaBUIOIoczbjJJDmNN8zR0CgYEAxVJg
2VCpjaRoJtaZYeserkVgB8SFffBnm/8XQv8uTbKrz104t9nFyezbINmKrQs3cxT3
1+PiVbLJpPRcik129x4xIlz3zapsMqwXL97Lz92vXm/nELRnV8d+F9SxVzlijRDL
rvl3X3Vayq2zKb6euBOwOu8UnQO3xJkTtLPtHDECgYAptxuVJkEJqtaQR7+1oZu4
UOdl2XOOBhoPjFplW/Uu+fiohst8OVAkP7GcyKB4j/CZGGoobP3mbJk/F4yfHvew
eim72x7Kc/YxJd2QiEr8JwXMwn0LWdKZY7RrJtIO0mtz2xGHgDEubb0EADEkNkTb
GCdQoft9kZl0U8dVQVGcpQKBgHsvjIre0ps8slDc1HDO6h597Q+sXnJbLTO0Mv9+
c5fKHXydhBUy/UmsdrixVuPlBr7vrjK3b8t0jHJQo50r80MfNClxxLo+1MFlsiwO
eUrR6POaBLTnC0U/o7aY8AW2K5JJk/8uepm7l+zEN/+to0Tj9bc1HrdPZOB1eFnt
oe9hAoGAEwwDhNrmSlZjmZMT8WehCdyS7zQgI8OCLAlu9KTiwFzoSDcnhVbS4nd4
iblllHCLZ2Q/rHSH3cQor94kxePm+b3KH9ZwAgInMModuSPcScrR5/vsORZCtJEO
CAXnxZHhrExMGIIa7KV33W5v7Hstl7SnPWKFgCvlBH2QoMTjoUE=
-----END RSA PRIVATE KEY-----
""")
        f.close()

        pkey_data = """MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAw7bJxD1k5VSA5AqdfmJ7
vj99oKQ4qYtSeJ5HiK6W40dzC++kLweUWLzeUErgXwcJlyOC6rqVVPBfSJq4l7yP
dVqpWUo6s2jnUsSWOfhpre22yc4BK0QY2Euc3R+gT59eM0mtJPtWaQw5BmQ2GrV6
f0OUiKi17jEPasKcxf1qZrWU0+IkD2DhUCuRrNb/baUkuIkxoit6M7k7s5X9swT1
hE/Eso0gS79FSti1fkDeoPZ296Gu5uYWdpaLl03Nr0w65Gbw+2v79AcwOyvbZD6y
9xYGLWubic0dUeWuhUipZdmQf8Bdt7cZVgjQX/giQQqqLDFhfNFwapUZDhS7TCtu
jQIDAQAB
"""
        self.public_keyfile = self.mktemp()
        f = open(self.public_keyfile, "w")
        f.write("""-----BEGIN PUBLIC KEY-----
%s-----END PUBLIC KEY-----
""" % (pkey_data,))
        f.close()
        self.public_key_data = pkey_data.replace("\n", "")



class TestDKIMRequest (TestDKIMBase):
    """
    L{DKIMRequest} support tests.
    """

    @inlineCallbacks
    def test_body_hash(self):

        data = "Hello World!"
        for algorithm, hash_method in (
            ("rsa-sha1", hashlib.sha1,),
            ("rsa-sha256", hashlib.sha256,),
        ):
            stream = str(data)
            headers = Headers()
            headers.addRawHeader("Originator", "mailto:user01@example.com")
            headers.addRawHeader("Recipient", "mailto:user02@example.com")
            headers.setHeader("Content-Type", MimeType("text", "calendar", **{"component": "VEVENT", "charset": "utf-8"}))
            request = DKIMRequest("POST", "/", headers, stream, "example.com", "dkim", "/tmp/key", algorithm, ("Originator", "Recipient", "Content-Type",), True, True, True, 3600)
            hash = base64.b64encode(hash_method(DKIMUtils.canonicalizeBody(data)).digest())
            result = (yield request.bodyHash())
            self.assertEqual(result, hash)


    def test_generateSignature(self):

        data = "Hello World!"

        for algorithm, hash_method, hash_name in (
            ("rsa-sha1", hashlib.sha1, "SHA-1",),
            ("rsa-sha256", hashlib.sha256, "SHA-256"),
        ):
            stream = MemoryStream(data)
            headers = Headers()
            headers.addRawHeader("Originator", "mailto:user01@example.com")
            headers.addRawHeader("Recipient", "mailto:user02@example.com")
            headers.setHeader("Content-Type", MimeType("text", "calendar", **{"component": "VEVENT", "charset": "utf-8"}))
            request = DKIMRequest("POST", "/", headers, stream, "example.com", "dkim", self.private_keyfile, algorithm, ("Originator", "Recipient", "Content-Type",), True, True, True, 3600)

            # Manually create what should be the correct thing to sign
            bodyhash = base64.b64encode(hash_method(data).digest())
            sign_this = """originator:mailto:user01@example.com
recipient:mailto:user02@example.com
content-type:%s
ischedule-version:1.0
dkim-signature:v=1; d=example.com; s=dkim; t=%s; x=%s; a=%s; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient; bh=%s; b=
""".replace("\n", "\r\n") % (headers.getRawHeaders("Content-Type")[0], str(int(time.time())), str(int(time.time() + 3600)), algorithm, bodyhash)

            result = request.generateSignature(sign_this)

            key = rsa.PrivateKey.load_pkcs1(open(self.private_keyfile).read())
            signature = base64.b64encode(rsa.sign(sign_this, key, hash_name))

            self.assertEqual(result, signature)


    @inlineCallbacks
    def test_signatureHeaders(self):

        data = "Hello World!"

        for algorithm, hash_method in (
            ("rsa-sha1", hashlib.sha1,),
            ("rsa-sha256", hashlib.sha256,),
        ):
            stream = MemoryStream(data)
            headers = Headers()
            headers.addRawHeader("Originator", "mailto:user01@example.com")
            headers.addRawHeader("Recipient", "mailto:user02@example.com")
            headers.setHeader("Content-Type", MimeType("text", "calendar", **{"component": "VEVENT", "charset": "utf-8"}))
            request = DKIMRequest("POST", "/", headers, stream, "example.com", "dkim", self.private_keyfile, algorithm, ("Originator", "Recipient", "Content-Type",), True, True, True, 3600)
            result, _ignore_tags = (yield request.signatureHeaders())

            # Manually create what should be the correct thing to sign
            bodyhash = base64.b64encode(hash_method(DKIMUtils.canonicalizeBody(data)).digest())
            sign_this = """originator:mailto:user01@example.com
recipient:mailto:user02@example.com
content-type:%s
ischedule-version:1.0
ischedule-message-id:%s
cache-control:no-cache
cache-control:no-transform
dkim-signature:v=1; d=example.com; s=dkim; t=%s; x=%s; a=%s; q=dns/txt:http/well-known:private-exchange; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient:Content-Type:iSchedule-Version:iSchedule-Message-ID:Cache-Control:Cache-Control; bh=%s; b=
""".replace("\n", "\r\n") % (headers.getRawHeaders("Content-Type")[0], request.message_id, request.time, request.expire, algorithm, bodyhash)

            self.assertEqual(result, sign_this)


    @inlineCallbacks
    def test_sign(self):

        data = "Hello World!"
        for algorithm, hash_method, hash_name in (
            ("rsa-sha1", hashlib.sha1, "SHA-1",),
            ("rsa-sha256", hashlib.sha256, "SHA-256"),
        ):
            stream = MemoryStream(data)
            headers = Headers()
            headers.addRawHeader("Originator", "mailto:user01@example.com")
            headers.addRawHeader("Recipient", "mailto:user02@example.com")
            headers.setHeader("Content-Type", MimeType("text", "calendar", **{"component": "VEVENT", "charset": "utf-8"}))
            request = DKIMRequest("POST", "/", headers, stream, "example.com", "dkim", self.private_keyfile, algorithm, ("Originator", "Recipient", "Content-Type",), True, True, True, 3600)
            result = (yield request.sign())

            # Manually create what should be the correct thing to sign and make sure signatures match
            bodyhash = base64.b64encode(hash_method(DKIMUtils.canonicalizeBody(data)).digest())
            sign_this = """originator:mailto:user01@example.com
recipient:mailto:user02@example.com
content-type:%s
ischedule-version:1.0
ischedule-message-id:%s
cache-control:no-cache
cache-control:no-transform
dkim-signature:v=1; d=example.com; s=dkim; t=%s; x=%s; a=%s; q=dns/txt:http/well-known:private-exchange; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient:Content-Type:iSchedule-Version:iSchedule-Message-ID:Cache-Control:Cache-Control; bh=%s; b=
""".replace("\n", "\r\n") % (headers.getRawHeaders("Content-Type")[0], request.message_id, request.time, request.expire, algorithm, bodyhash)
            key = rsa.PrivateKey.load_pkcs1(open(self.private_keyfile).read())
            signature = base64.b64encode(rsa.sign(sign_this, key, hash_name))

            self.assertEqual(result, signature)

            # Make sure header is updated in the request
            updated_header = "v=1; d=example.com; s=dkim; t=%s; x=%s; a=%s; q=dns/txt:http/well-known:private-exchange; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient:Content-Type:iSchedule-Version:iSchedule-Message-ID:Cache-Control:Cache-Control; bh=%s; b=%s" % (request.time, request.expire, algorithm, bodyhash, signature,)
            self.assertEqual(request.headers.getRawHeaders("DKIM-Signature")[0], updated_header)

            # Try to verify result using public key
            pubkey = rsa.PublicKey.load_pkcs1(open(self.public_keyfile).read())
            self.assertEqual(rsa.verify(sign_this, base64.b64decode(result), pubkey), None)



class TestDKIMVerifier (TestDKIMBase):
    """
    L{DKIMVerifier} support tests.
    """

    class StubRequest(object):

        def __init__(self, method, uri, headers, body):
            self.method = method
            self.uri = uri
            self.headers = Headers()
            for name, value in headers:
                self.headers.addRawHeader(name, value)
            self.stream = MemoryStream(body)


    def test_valid_dkim_headers(self):
        """
        L{DKIMVerifier.processDKIMHeader} correctly validates DKIM-Signature headers.
        """

        data = (
            # Bogus
            ((("DKIM-Signature", "v=1"),), False,),

            # More than one
            ((
                ("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; a=rsa-sha1; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient; bh=abc; b=def"),
                ("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; a=rsa-sha256; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient; bh=abc; b=def"),
            ), False,),

            # Valid
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; a=rsa-sha1; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient; bh=abc; b=def"),), True,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; a=rsa-sha256; q=dns/txt; http=UE9TVDov; c=relaxed; h=Originator:Recipient; bh=abc; b=def"),), True,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; x=%d; a=rsa-sha256; q=dns/txt; http=UE9TVDov; c=relaxed; h=Originator:Recipient; bh=abc; b=def" % (int(time.time() + 30),)),), True,),

            # Invalid
            ((("DKIM-Signature", "v=2; d=example.com; s=dkim; t=1234; a=rsa-sha1; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient; bh=abc; b=def"),), False,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; a=rsa-sha512; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient; bh=abc; b=def"),), False,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; a=rsa-sha1; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/relaxed; h=Originator:Recipient; bh=abc; b=def"),), False,),
            ((("DKIM-Signature", "v=1; d=example.com; t=1234; a=rsa-sha1; q=dns/txt:http/well-known; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient; bh=abc; b=def"),), False,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; x=%d; a=rsa-sha256; q=dns/txt; http=UE9TVDov; c=relaxed; h=Originator:Recipient; bh=abc; b=def" % (int(time.time() - 30),)),), False,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; x=%d; a=rsa-sha256; q=dns/txt; c=relaxed; h=Originator:Recipient; bh=abc; b=def" % (int(time.time() - 30),)),), False,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; x=%d; a=rsa-sha256; q=dns/txt; http=UE9TVDovaXNjaGVkdWxl; c=relaxed; h=Originator:Recipient; bh=abc; b=def" % (int(time.time() - 30),)),), False,),
            ((("DKIM-Signature", "v=1; d=example.com; s=dkim; t=1234; x=%d; a=rsa-sha256; q=dns/txt; http=POST:/; c=relaxed; h=Originator:Recipient; bh=abc; b=def" % (int(time.time() - 30),)),), False,),
        )

        for headers, result in data:
            request = self.StubRequest("POST", "/", headers, "")
            verifier = DKIMVerifier(request)
            if result:
                verifier.processDKIMHeader()
            else:
                self.assertRaises(DKIMVerificationError, verifier.processDKIMHeader)


    def test_canonicalize_header(self):
        """
        L{DKIMVerifier.canonicalizeHeader} correctly canonicalizes headers.
        """

        data = (
            ("Content-Type", " text/calendar  ; charset =  \"utf-8\"  ", "content-type:text/calendar ; charset = \"utf-8\"\r\n"),
            ("Originator", "  mailto:user01@example.com  ", "originator:mailto:user01@example.com\r\n"),
            ("Recipient", "  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t  ", "recipient:mailto:user02@example.com , mailto:user03@example.com\r\n"),
            ("iSchedule-Version", " 1.0 ", "ischedule-version:1.0\r\n"),
            (
                "DKIM-Signature",
                "  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def",
                "dkim-signature:v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known ; http=UE9TVDov; c=relaxed/simple; h=Originator:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=\r\n",
            ),
            (
                "DKIM-Signature",
                "  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; b= def ; http=\tUE9TVDov   ; c=relaxed/simple; h=Originator:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc",
                "dkim-signature:v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known ; b= ; http= UE9TVDov ; c=relaxed/simple; h=Originator:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc\r\n",
            ),
        )

        for name, value, result in data:
            request = self.StubRequest("POST", "/", ((name, value,),), "")
            verifier = DKIMVerifier(request)
            if name == "DKIM-Signature":
                verifier.processDKIMHeader()
            canonicalized = DKIMUtils.canonicalizeHeader(name, value, remove_b=verifier.dkim_tags["b"] if name == "DKIM-Signature" else None)
            self.assertEqual(canonicalized, result)


    def test_extract_headers(self):
        """
        L{DKIMVerifier.extractSignedHeaders} correctly extracts canonicalizes headers.
        """

        data = (
            # Over count on Recipient
            ("""Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
iSchedule-Version: 1.0
DKIM-Signature:  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def
Cache-Control:no-cache
Connection:close
""",
            """content-type:text/calendar ; charset = "utf-8"
originator:mailto:user01@example.com
recipient:mailto:user02@example.com , mailto:user03@example.com
ischedule-version:1.0
dkim-signature:v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=
"""
            ),
            # Exact count on Recipient
            ("""Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Recipient:\t\t  mailto:user04@example.com
iSchedule-Version: 1.0
DKIM-Signature:  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def
Cache-Control:no-cache
Connection:close
""",
            """content-type:text/calendar ; charset = "utf-8"
originator:mailto:user01@example.com
recipient:mailto:user02@example.com , mailto:user03@example.com
recipient:mailto:user04@example.com
ischedule-version:1.0
dkim-signature:v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=
"""
            ),
            # Under count on Recipient
            ("""Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
iSchedule-Version: 1.0
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Recipient:\t\t  mailto:user04@example.com
Recipient:\t\t  mailto:user05@example.com
DKIM-Signature:  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def
Cache-Control:no-cache
Connection:close
""",
            """content-type:text/calendar ; charset = "utf-8"
originator:mailto:user01@example.com
recipient:mailto:user02@example.com , mailto:user03@example.com
recipient:mailto:user04@example.com
ischedule-version:1.0
dkim-signature:v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=
"""
            ),
            # Re-ordered Content-Type
            ("""Host:example.com
iSchedule-Version: 1.0
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
DKIM-Signature:  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def
Content-Type: text/calendar  ; charset =  "utf-8"
Cache-Control:no-cache
Connection:close
""",
            """content-type:text/calendar ; charset = "utf-8"
originator:mailto:user01@example.com
recipient:mailto:user02@example.com , mailto:user03@example.com
ischedule-version:1.0
dkim-signature:v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=
"""
            ),
        )

        for hdrs, result in data:
            headers = [hdr.split(":", 1) for hdr in hdrs.splitlines()]
            request = self.StubRequest("POST", "/", headers, "")
            verifier = DKIMVerifier(request)
            verifier.processDKIMHeader()
            extracted = verifier.extractSignedHeaders()
            self.assertEqual(extracted, result.replace("\n", "\r\n"))


    def test_locate_public_key(self):
        """
        L{DKIMVerifier.locatePublicKey} correctly finds key matching headers.
        """

        data = (
            # Valid
            ("""Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
DKIM-Signature:  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def
Cache-Control:no-cache
Connection:close
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            True,
            ),
            # Invalid - no method
            ("""Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
DKIM-Signature:  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt\t\t; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def
Cache-Control:no-cache
Connection:close
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            False,
            ),
            # Invalid - wrong algorithm
            ("""Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
DKIM-Signature:  v=1;\t\t d=example.com; s = dkim; t\t=\t1234; a=rsa-sha1; \t\tq=dns/txt:http/well-known\t\t; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=def
Cache-Control:no-cache
Connection:close
""",
            [DKIMUtils.extractTags("v=DKIM1; h=sha-1; p=%s" % (self.public_key_data,))],
            False,
            ),
        )

        for hdrs, keys, result in data:
            headers = [hdr.split(":", 1) for hdr in hdrs.splitlines()]
            request = self.StubRequest("POST", "/", headers, "")
            TestPublicKeyLookup.PublicKeyLookup_Testing.keys = keys
            verifier = DKIMVerifier(request, key_lookup=(TestPublicKeyLookup.PublicKeyLookup_Testing,))
            verifier.processDKIMHeader()
            pkey = (yield verifier.locatePublicKey())
            if result:
                self.assertNotEqual(pkey, None)
            else:
                self.assertEqual(pkey, None)


    @inlineCallbacks
    def test_verify(self):
        """
        L{DKIMVerifier.verify} correctly finds key matching headers.
        """

        @inlineCallbacks
        def _verify(hdrs, body, keys, result, sign_headers=("Originator", "Recipient", "Content-Type",), manipulate_request=None):
            for algorithm in ("rsa-sha1", "rsa-sha256",):
                # Create signature
                stream = MemoryStream(body)
                headers = Headers()
                for name, value in [hdr.split(":", 1) for hdr in hdrs.splitlines()]:
                    headers.addRawHeader(name, value)
                request = DKIMRequest("POST", "/", headers, stream, "example.com", "dkim", self.private_keyfile, algorithm, sign_headers, True, True, True, 3600)
                yield request.sign()

                # Possibly munge the request after the signature is done
                if manipulate_request is not None:
                    manipulate_request(request)

                # Verify signature
                TestPublicKeyLookup.PublicKeyLookup_Testing.keys = keys
                verifier = DKIMVerifier(request, key_lookup=(TestPublicKeyLookup.PublicKeyLookup_Testing,))
                TestPublicKeyLookup.PublicKeyLookup_Testing({}).flushCache()
                try:
                    yield verifier.verify()
                except Exception, e:
                    if result:
                        self.fail("DKIMVerifier:verify failed: %s" % (e,))
                else:
                    if not result:
                        self.fail("DKIMVerifier:verify did not fail")

        # Valid
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            True,
        )

        # Invalid - key revoked
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=")],
            False,
        )

        # Invalid - missing header
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            False,
            manipulate_request=lambda request: request.headers.removeHeader("Originator")
        )

        # Invalid - changed header
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            False,
            manipulate_request=lambda request: request.headers.setRawHeaders("Originator", ("mailto:user04@example.com",))
        )

        # Invalid - changed body
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            False,
            manipulate_request=lambda request: setattr(request, "stream", MemoryStream("BEGIN:DATA\n")),
        )

        # Valid - extra header no over sign
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            True,
            manipulate_request=lambda request: request.headers.addRawHeader("Recipient", ("mailto:user04@example.com",))
        )

        # Valid - over sign header
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            False,
            sign_headers=("Originator", "Recipient", "Recipient", "Content-Type",),
        )

        # Invalid - over sign header extra header
        yield _verify(
            """Host:example.com
Content-Type: text/calendar  ; charset =  "utf-8"
Originator:  mailto:user01@example.com
Recipient:  mailto:user02@example.com  ,\t mailto:user03@example.com\t\t
Cache-Control:no-cache
Connection:close
""",
            """BEGIN:DATA
END:DATA
""",
            [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))],
            False,
            sign_headers=("Originator", "Recipient", "Recipient", "Content-Type",),
            manipulate_request=lambda request: request.headers.addRawHeader("Recipient", ("mailto:user04@example.com",))
        )



class TestPublicKeyLookup (TestDKIMBase):
    """
    L{PublicKeyLookup} support tests.
    """

    def test_selector_key(self):

        for lookup, d, result in (
            (PublicKeyLookup_DNSTXT, "example.com", "dkim._domainkey.example.com"),
            (PublicKeyLookup_DNSTXT, "calendar.example.com", "dkim._domainkey.calendar.example.com"),
            (PublicKeyLookup_HTTP_WellKnown, "example.com", "https://example.com/.well-known/domainkey/example.com/dkim"),
            (PublicKeyLookup_HTTP_WellKnown, "calendar.example.com", "https://example.com/.well-known/domainkey/calendar.example.com/dkim"),
            (PublicKeyLookup_PrivateExchange, "example.com", "example.com#dkim"),
            (PublicKeyLookup_PrivateExchange, "calendar.example.com", "calendar.example.com#dkim"),
        ):
            dkim = "v=1; d=%s; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b=" % (d,)
            tester = lookup(DKIMUtils.extractTags(dkim))
            self.assertEqual(tester._getSelectorKey(), result)


    @inlineCallbacks
    def test_get_key(self):

        # Valid
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))]
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)

        # Valid with more tags
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [DKIMUtils.extractTags("v=DKIM1; k = rsa ; h=  sha1 : sha256  ; s=ischedule ; p=%s" % (self.public_key_data,))]
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)

        # Invalid - key type
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [DKIMUtils.extractTags("v=DKIM1; k=dsa ; p=%s" % (self.public_key_data,))]
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)

        # Invalid - hash
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [DKIMUtils.extractTags("v=DKIM1; k=rsa ; h=sha512 ; p=%s" % (self.public_key_data,))]
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)

        # Invalid - service
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [DKIMUtils.extractTags("v=DKIM1; k=rsa ; s=email ; p=%s" % (self.public_key_data,))]
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)

        # Invalid - revoked
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [DKIMUtils.extractTags("v=DKIM1; k=rsa ; s=email ; p=")]
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)

        # Multiple valid
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [
            DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,)),
            DKIMUtils.extractTags("v=DKIM1; k = rsa ; h=  sha1 : sha256  ; s=ischedule ; p=%s" % (self.public_key_data,)),
            DKIMUtils.extractTags("v=DKIM1; k = rsa ; h=  sha1 : sha256  ; s=* ; p=%s" % (self.public_key_data,)),
        ]
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)

        # Multiple - some valid, some invalid
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [
            DKIMUtils.extractTags("v=DKIM1; k=rsa ; s=email ; p="),
            DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,)),
            DKIMUtils.extractTags("v=DKIM1; k = rsa ; h=  sha1 : sha256  ; s=ischedule ; p=%s" % (self.public_key_data,)),
            DKIMUtils.extractTags("v=DKIM1; k = rsa ; h=  sha1 : sha256  ; s=* ; p=%s" % (self.public_key_data,)),
        ]
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)

        # Multiple - invalid
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [
            DKIMUtils.extractTags("v=DKIM1; k=rsa ; s=email ; p="),
            DKIMUtils.extractTags("v=DKIM1; k=rsa ; s=email ; p="),
        ]
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)


    @inlineCallbacks
    def test_cached_key(self):

        # Create cache entry
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = [DKIMUtils.extractTags("v=DKIM1; p=%s" % (self.public_key_data,))]
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)

        # Cache valid
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.keys = []
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)

        # Cache invalid
        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = TestPublicKeyLookup.PublicKeyLookup_Testing(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        lookup.keys = []
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)


    @inlineCallbacks
    def test_private_exchange(self):

        keydir = self.mktemp()
        PublicKeyLookup_PrivateExchange.directory = keydir
        os.mkdir(keydir)
        keyfile = os.path.join(keydir, "example.com#dkim")
        with open(keyfile, "w") as f:
            f.write("""v=DKIM1; p=%s
""" % (self.public_key_data,))

        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = PublicKeyLookup_PrivateExchange(DKIMUtils.extractTags(dkim))
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)

        dkim = "v=1; d=example.com; s = dkim2; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = PublicKeyLookup_PrivateExchange(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)

        with open(keyfile, "w") as f:
            f.write("""v=DKIM1; s=email; p=%s
""" % (self.public_key_data,))

        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = PublicKeyLookup_PrivateExchange(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        pubkey = (yield lookup.getPublicKey())
        self.assertEqual(pubkey, None)

        with open(keyfile, "w") as f:
            f.write("""v=DKIM1; s=email; p=%s
v=DKIM1; s=ischedule; p=%s
""" % (self.public_key_data, self.public_key_data,))

        dkim = "v=1; d=example.com; s = dkim; t = 1234; a=rsa-sha1; q=dns/txt:http/well-known:private-exchange ; http=UE9TVDov; c=relaxed/simple; h=Content-Type:Originator:Recipient:Recipient:iSchedule-Version:iSchedule-Message-ID; bh=abc; b="
        lookup = PublicKeyLookup_PrivateExchange(DKIMUtils.extractTags(dkim))
        lookup.flushCache()
        pubkey = (yield lookup.getPublicKey())
        self.assertNotEqual(pubkey, None)
