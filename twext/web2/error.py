# -*- test-case-name: twext.web2.test.test_log -*-
##
# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# Copyright (c) 2010 Apple Computer, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
##

"""
Default error output filter for twext.web2.
"""

from twext.web2 import stream, http_headers
from twext.web2.responsecode import (
    MOVED_PERMANENTLY, FOUND, SEE_OTHER, USE_PROXY, TEMPORARY_REDIRECT,
    BAD_REQUEST, UNAUTHORIZED, PAYMENT_REQUIRED, FORBIDDEN, NOT_FOUND,
    NOT_ALLOWED, NOT_ACCEPTABLE, PROXY_AUTH_REQUIRED, REQUEST_TIMEOUT, CONFLICT,
    GONE, LENGTH_REQUIRED, PRECONDITION_FAILED, REQUEST_ENTITY_TOO_LARGE,
    REQUEST_URI_TOO_LONG, UNSUPPORTED_MEDIA_TYPE,
    REQUESTED_RANGE_NOT_SATISFIABLE, EXPECTATION_FAILED, INTERNAL_SERVER_ERROR,
    NOT_IMPLEMENTED, BAD_GATEWAY, SERVICE_UNAVAILABLE, GATEWAY_TIMEOUT,
    HTTP_VERSION_NOT_SUPPORTED, INSUFFICIENT_STORAGE_SPACE, NOT_EXTENDED,
    RESPONSES,
)

from twisted.web.template import Element, flattenString, XMLString, renderer

# 300 - Should include entity with choices
# 301 -
# 304 - Must include Date, ETag, Content-Location, Expires, Cache-Control, Vary.
# 
# 401 - Must include WWW-Authenticate.
# 405 - Must include Allow.
# 406 - Should include entity describing allowable characteristics
# 407 - Must include Proxy-Authenticate
# 413 - May  include Retry-After
# 416 - Should include Content-Range
# 503 - Should include Retry-After
ERROR_MESSAGES = {
    # 300
    # no MULTIPLE_CHOICES
    MOVED_PERMANENTLY: 'The document has permanently moved <a>here<t:attr name="href"><t:slot name="location" /></t:attr></a>.',
    FOUND: 'The document has temporarily moved <a>here<t:attr name="href"><t:slot name="location" /></t:attr></a>.',
    SEE_OTHER: 'The results are available <a>here<t:attr name="href"><t:slot name="location" /></t:attr></a>.',
    # no NOT_MODIFIED
    USE_PROXY: 'Access to this resource must be through the proxy <t:slot name="location" />.',
    # 306 unused
    TEMPORARY_REDIRECT: 'The document has temporarily moved <a>here<t:attr name="href"><t:slot name="location" /></t:attr></a>.',

    # 400
    BAD_REQUEST: 'Your browser sent an invalid request.',
    UNAUTHORIZED: 'You are not authorized to view the resource at <t:slot name="uri" />. Perhaps you entered a wrong password, or perhaps your browser doesn\'t support authentication.',
    PAYMENT_REQUIRED: 'Payment Required (useful result code, this...).',
    FORBIDDEN: 'You don\'t have permission to access <t:slot name="uri" />.',
    NOT_FOUND: 'The resource <t:slot name="uri" /> cannot be found.',
    NOT_ALLOWED: 'The requested method <t:slot name="method" /> is not supported by <t:slot name="uri" />.',
    NOT_ACCEPTABLE: 'No representation of <t:slot name="uri" /> that is acceptable to your client could be found.',
    PROXY_AUTH_REQUIRED: 'You are not authorized to view the resource at <t:slot name="uri" />. Perhaps you entered a wrong password, or perhaps your browser doesn\'t support authentication.',
    REQUEST_TIMEOUT: 'Server timed out waiting for your client to finish sending the HTTP request.',
    CONFLICT: 'Conflict (?)',
    GONE: 'The resource <t:slot name="uri" /> has been permanently removed.',
    LENGTH_REQUIRED: 'The resource <t:slot name="uri" /> requires a Content-Length header.',
    PRECONDITION_FAILED: 'A precondition evaluated to false.',
    REQUEST_ENTITY_TOO_LARGE: 'The provided request entity data is too longer than the maximum for the method <t:slot name="method" /> at <t:slot name="uri" />.',
    REQUEST_URI_TOO_LONG: 'The request URL is longer than the maximum on this server.',
    UNSUPPORTED_MEDIA_TYPE: 'The provided request data has a format not understood by the resource at <t:slot name="uri" />.',
    REQUESTED_RANGE_NOT_SATISFIABLE: 'None of the ranges given in the Range request header are satisfiable by the resource <t:slot name="uri" />.',
    EXPECTATION_FAILED: 'The server does support one of the expectations given in the Expect header.',

    # 500
    INTERNAL_SERVER_ERROR: 'An internal error occurred trying to process your request. Sorry.',
    NOT_IMPLEMENTED: 'Some functionality requested is not implemented on this server.',
    BAD_GATEWAY: 'An upstream server returned an invalid response.',
    SERVICE_UNAVAILABLE: 'This server cannot service your request becaues it is overloaded.',
    GATEWAY_TIMEOUT: 'An upstream server is not responding.',
    HTTP_VERSION_NOT_SUPPORTED: 'HTTP Version not supported.',
    INSUFFICIENT_STORAGE_SPACE: 'There is insufficient storage space available to perform that request.',
    NOT_EXTENDED: 'This server does not support the a mandatory extension requested.'
}



class DefaultErrorElement(Element):
    """
    An L{ErrorElement} is an L{Element} that renders some HTML for the default
    rendering of an error page.
    """

    loader = XMLString("""
    <html xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1"
          t:render="error">
          <head>
              <title><t:slot name="code"/> <t:slot name="title"/></title>
          </head>
        <body>
            <h1><t:slot name="title" /></h1>
            <t:slot name="message" />
        </body>
    </html>
    """)

    def __init__(self, request, response):
        super(DefaultErrorElement, self).__init__()
        self.request = request
        self.response = response


    @renderer
    def error(self, request, tag):
        """
        Top-level renderer for page.
        """
        return tag.fillSlots(
            code=str(self.response.code),
            title=RESPONSES.get(self.response.code),
            message=self.loadMessage(self.response.code).fillSlots(
                uri=self.request.uri,
                location=self.response.headers.getHeader('location'),
                method=self.request.method,
            )
        )


    def loadMessage(self, code):
        tag = XMLString(('<t:transparent xmlns:t="http://twistedmatrix.com/'
                   'ns/twisted.web.template/0.1">') +
                  ERROR_MESSAGES.get(code, "") +
                    '</t:transparent>').load()[0]
        return tag




def defaultErrorHandler(request, response):
    if response.stream is not None:
        # Already got an error message
        return response
    if response.code < 300:
        # We only do error messages
        return response

    message = ERROR_MESSAGES.get(response.code, None)
    if message is None:
        # No message specified for that code
        return response

    message = message % {
        'uri': request.uri,
        'location': response.headers.getHeader('location'),
        'method': request.method,
    }
    data = []
    error = []
    (flattenString(request, DefaultErrorElement(request, response))
     .addCallbacks(data.append, error.append))
    # No deferreds from our renderers above, so this has always already fired.
    if data:
        subtype = 'html'
        body = data[0]
    else:
        subtype = 'error'
        data = 'Error in default error handler:\n' + error[0].getTraceback()
    ctype = http_headers.MimeType('text', subtype,
                                  {'charset':'utf-8'})
    response.headers.setHeader("content-type", ctype)
    response.stream = stream.MemoryStream(body)
    return response
defaultErrorHandler.handleErrors = True


__all__ = ['defaultErrorHandler',]

