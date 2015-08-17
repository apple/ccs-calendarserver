from caldavclientlibrary.protocol.webdav.propfindparser import PropFindParser

from contrib.performance.httpauth import AuthHandlerAgent
from contrib.performance.httpclient import StringProducer, readBody

from twisted.web.http import OK, MULTI_STATUS, CREATED, NO_CONTENT
from twisted.web.http_headers import Headers
from twisted.web.client import Agent, ContentDecoderAgent, GzipDecoder, \
    _DeprecatedToCurrentPolicyForHTTPS

from twisted.python.log import msg

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.ssl import ClientContextFactory

"""
TODO
Finish the comment table
THink about better ways to do default headers
Try to log messages in a more intelligent way

"""

class Requester(object):
    """
    Utility to create requests on behalf of a client. Public methods are:
    method     url     body     headers     status     method_label
    ------------------------------------------------------------------------
    GET        req     ---
    POST       req     req
    PUT        req     req*
    DELETE     req     ---
    PROPFIND   req
    PROPPATCH  req
    REPORT     req
    MKCALENDAR req

    req: required
    opt: optional
    ---: disallowed
    All of these rely on a private method _request

    """

    def __init__(
        self,
        root,
        headers,
        title,
        uid,
        client_id,
        auth,
        reactor
    ):
        self._root = root
        self._headers = headers
        self._title = title
        self._uid = uid
        self._client_id = client_id

        self._reactor = reactor

        # The server might use gzip encoding
        agent = Agent(
            self._reactor,
            contextFactory=_DeprecatedToCurrentPolicyForHTTPS(WebClientContextFactory()),
        )
        agent = ContentDecoderAgent(agent, [("gzip", GzipDecoder)])
        self._agent = AuthHandlerAgent(agent, auth)

    def _addDefaultHeaders(self, headers):
        """
        Add the clients default set of headers to ones being used in a request.
        Default is to add User-Agent, sub-classes should override to add other
        client specific things, Accept etc.
        """
        for k, v in self._headers.iteritems():
            headers.setRawHeaders(k, v)

    @inlineCallbacks
    def _request(self, method, url, expectedResponseCodes, headers=None, body=None, method_label=None):
        """
        Execute a request and check against the expected response codes.
        """
        if type(expectedResponseCodes) is int:
            expectedResponseCodes = (expectedResponseCodes,)
        if not method_label:
            method_label = method
        if headers is None:
            headers = Headers({})
        self._addDefaultHeaders(headers)
        url = self._root + url.encode('utf-8')

        msg(
            type="request",
            method=method_label,
            url=url,
            user=self._uid,
            client_type=self._title,
            client_id=self._client_id,
        )

        before = self._reactor.seconds()
        response = yield self._agent.request(method, url, headers, StringProducer(body) if body else None)

        # XXX This is time to receive response headers, not time
        # to receive full response.  Should measure the latter, if
        # not both.
        after = self._reactor.seconds()

        success = response.code in expectedResponseCodes

        msg(
            type="response",
            success=success,
            method=method_label,
            headers=headers,
            body=body,
            code=response.code,
            user=self._uid,
            client_type=self._title,
            client_id=self._client_id,
            duration=(after - before),
            url=url,
        )

        if success:
            returnValue(response)

        raise IncorrectResponseCode(expectedResponseCodes, response)


    @inlineCallbacks
    def get(self, url, method_label=None):
        response = yield self._request(
            'GET',
            url,
            (OK,),
            method_label=method_label
        )
        returnValue(response)


    @inlineCallbacks
    def post(self, url, body, headers=None, method_label=None):
        response = yield self._request(
            'POST',
            url,
            (OK, CREATED, MULTI_STATUS),
            headers=headers,
            body=body,
            method_label=method_label
        )
        returnValue(response)


    @inlineCallbacks
    def put(self, expectedResponseCodes, url, component, headers=None, method_label=None):
        response = yield self._request(
            'PUT',
            url,
            expectedResponseCodes,
            headers=headers,
            body=component.getTextWithTimezones(includeTimezones=True),
            method_label=method_label
        )
        returnValue(response)


    @inlineCallbacks
    def delete(self, url, method_label=None):
        response = yield self._request(
            'DELETE',
            url,
            (NO_CONTENT,),
            method_label=method_label
        )
        returnValue(response)


    def _parseMultiStatus(self, response, otherTokens=False):
        """
        Parse a <multistatus> - might need to return other top-level elements
        in the response - e.g. DAV:sync-token
        I{PROPFIND} request for the principal URL.

        @type response: C{str}
        @rtype: C{cls}
        """
        parser = PropFindParser()
        parser.parseData(response)
        if otherTokens:
            return (parser.getResults(), parser.getOthers(),)
        else:
            return parser.getResults()

    @inlineCallbacks
    def propfind(self, url, body, depth='0', allowedStatus=(MULTI_STATUS,), method_label=None):
        """
        Issue a PROPFIND on the chosen URL
        """
        hdrs = Headers({'content-type': ['text/xml']})
        if depth is not None:
            hdrs.addRawHeader('depth', depth)
        response = yield self._request(
            'PROPFIND',
            url,
            allowedStatus,
            headers=hdrs,
            body=body,
            method_label=method_label,
        )

        body = yield readBody(response)
        result = self._parseMultiStatus(body) if response.code == MULTI_STATUS else None

        returnValue((response, result,))

    @inlineCallbacks
    def proppatch(self, url, body, method_label=None):
        """
        Issue a PROPPATCH on the chosen URL
        """
        hdrs = Headers({'content-type': ['text/xml']})
        response = yield self._request(
            'PROPPATCH',
            url,
            (OK, MULTI_STATUS,),
            headers=hdrs,
            body=body,
            method_label=method_label,
        )
        if response.code == MULTI_STATUS:
            body = yield readBody(response)
            result = self._parseMultiStatus(body)
            returnValue(result)
        else:
            returnValue(None)

    @inlineCallbacks
    def report(self, url, body, depth='0', allowedStatus=(MULTI_STATUS,), otherTokens=False, method_label=None):
        """
        Issue a REPORT on the chosen URL
        """
        hdrs = Headers({'content-type': ['text/xml']})
        if depth is not None:
            hdrs.addRawHeader('depth', depth)
        response = yield self._request(
            'REPORT',
            url,
            allowedStatus,
            headers=hdrs,
            body=body,
            method_label=method_label,
        )

        body = yield readBody(response)
        result = self._parseMultiStatus(body, otherTokens) if response.code == MULTI_STATUS else None

        returnValue(result)

    @inlineCallbacks
    def mkcalendar(self, url, body, method_label=None):
        """
        Issue a MKCALENDAR on the chosen URL with the given body
        url: an href like /calendars/__uids__/<user-uid>/<calendar-uid>/
        body: the XML body of the request
        """
        headers = Headers({'content-type': ['text/xml']})
        response = yield self._request(
            'MKCALENDAR',
            url,
            (CREATED,),
            headers=headers,
            body=body,
            method_label=method_label
        )
        body = yield readBody(response)
        returnValue(body)


class IncorrectResponseCode(Exception):
    """
    Raised when a response has a code other than the one expected.

    @ivar expected: The response codes which was expected.
    @type expected: C{tuple} of C{int}

    @ivar response: The response which was received
    @type response: L{twisted.web.client.Response}
    """
    def __init__(self, expected, response):
        self.expected = expected
        self.response = response


class WebClientContextFactory(ClientContextFactory):
    """
    A web context factory which ignores the hostname and port and does no
    certificate verification.
    """
    def getContext(self, hostname, port):
        return ClientContextFactory.getContext(self)
