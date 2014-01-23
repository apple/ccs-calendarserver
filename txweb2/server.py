# -*- test-case-name: txweb2.test.test_server -*-
##
# Copyright (c) 2001-2008 Twisted Matrix Laboratories.
# Copyright (c) 2010-2014 Apple Computer, Inc. All rights reserved.
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
This is a web-server which integrates with the twisted.internet
infrastructure.
"""
from __future__ import print_function

import cgi, time, urlparse
from urllib import quote, unquote
from urlparse import urlsplit
import weakref

from zope.interface import implements

from twisted.internet import defer
from twisted.python import failure

from twext.python.log import Logger
from txweb2 import http, iweb, fileupload, responsecode
from txweb2 import http_headers
from txweb2.filter.range import rangefilter
from txweb2 import error

from txweb2 import __version__ as web2_version
from twisted import __version__ as twisted_version

VERSION = "Twisted/%s TwistedWeb/%s" % (twisted_version, web2_version)
_errorMarker = object()

log = Logger()


def defaultHeadersFilter(request, response):
    if not response.headers.hasHeader('server'):
        response.headers.setHeader('server', VERSION)
    if not response.headers.hasHeader('date'):
        response.headers.setHeader('date', time.time())
    return response
defaultHeadersFilter.handleErrors = True

def preconditionfilter(request, response):
    if request.method in ("GET", "HEAD"):
        http.checkPreconditions(request, response)
    return response

def doTrace(request):
    request = iweb.IRequest(request)
    txt = "%s %s HTTP/%d.%d\r\n" % (request.method, request.uri,
                                    request.clientproto[0], request.clientproto[1])

    l=[]
    for name, valuelist in request.headers.getAllRawHeaders():
        for value in valuelist:
            l.append("%s: %s\r\n" % (name, value))
    txt += ''.join(l)

    return http.Response(
        responsecode.OK,
        {'content-type': http_headers.MimeType('message', 'http')},
        txt)


def parsePOSTData(request, maxMem=100*1024, maxFields=1024,
                  maxSize=10*1024*1024):
    """
    Parse data of a POST request.

    @param request: the request to parse.
    @type request: L{txweb2.http.Request}.
    @param maxMem: maximum memory used during the parsing of the data.
    @type maxMem: C{int}
    @param maxFields: maximum number of form fields allowed.
    @type maxFields: C{int}
    @param maxSize: maximum size of file upload allowed.
    @type maxSize: C{int}

    @return: a deferred that will fire when the parsing is done. The deferred
        itself doesn't hold a return value, the request is modified directly.
    @rtype: C{defer.Deferred}
    """
    if request.stream.length == 0:
        return defer.succeed(None)

    ctype = request.headers.getHeader('content-type')

    if ctype is None:
        return defer.succeed(None)

    def updateArgs(data):
        args = data
        request.args.update(args)

    def updateArgsAndFiles(data):
        args, files = data
        request.args.update(args)
        request.files.update(files)

    def error(f):
        f.trap(fileupload.MimeFormatError)
        raise http.HTTPError(
            http.StatusResponse(responsecode.BAD_REQUEST, str(f.value)))

    if (ctype.mediaType == 'application'
        and ctype.mediaSubtype == 'x-www-form-urlencoded'):
        d = fileupload.parse_urlencoded(request.stream)
        d.addCallbacks(updateArgs, error)
        return d
    elif (ctype.mediaType == 'multipart'
          and ctype.mediaSubtype == 'form-data'):
        boundary = ctype.params.get('boundary')
        if boundary is None:
            return defer.fail(http.HTTPError(
                    http.StatusResponse(
                        responsecode.BAD_REQUEST,
                        "Boundary not specified in Content-Type.")))
        d = fileupload.parseMultipartFormData(request.stream, boundary,
                                              maxMem, maxFields, maxSize)
        d.addCallbacks(updateArgsAndFiles, error)
        return d
    else:
        return defer.fail(http.HTTPError(
            http.StatusResponse(
                responsecode.BAD_REQUEST,
                "Invalid content-type: %s/%s" % (
                    ctype.mediaType, ctype.mediaSubtype))))


class StopTraversal(object):
    """
    Indicates to Request._handleSegment that it should stop handling
    path segments.
    """
    pass


class Request(http.Request):
    """
    vars:
    site

    remoteAddr

    scheme
    host
    port
    path
    params
    querystring

    args
    files

    prepath
    postpath

    @ivar path: The path only (arguments not included).
    @ivar args: All of the arguments, including URL and POST arguments.
    @type args: A mapping of strings (the argument names) to lists of values.
                i.e., ?foo=bar&foo=baz&quux=spam results in
                {'foo': ['bar', 'baz'], 'quux': ['spam']}.

    """
    implements(iweb.IRequest)

    site = None
    _initialprepath = None
    responseFilters = [rangefilter, preconditionfilter,
                       error.defaultErrorHandler, defaultHeadersFilter]

    def __init__(self, *args, **kw):
        
        self.timeStamps = [("t", time.time(),)]

        if kw.has_key('site'):
            self.site = kw['site']
            del kw['site']
        if kw.has_key('prepathuri'):
            self._initialprepath = kw['prepathuri']
            del kw['prepathuri']

        self._resourcesByURL = {}
        self._urlsByResource = {}

        # Copy response filters from the class
        self.responseFilters = self.responseFilters[:]
        self.files = {}
        self.resources = []
        http.Request.__init__(self, *args, **kw)
        try:
            self.serverInstance = self.chanRequest.channel.transport.server.port
        except AttributeError:
            self.serverInstance = "Unknown"

    def timeStamp(self, tag):
        self.timeStamps.append((tag, time.time(),))

    def addResponseFilter(self, filter, atEnd=False, onlyOnce=False):
        """
        Add a response filter to this request.
        Response filters are applied to the response to this request in order.
        @param filter: a callable which takes an response argument and returns
            a response object.
        @param atEnd: if C{True}, C{filter} is added at the end of the list of
            response filters; if C{False}, it is added to the beginning.
        @param onlyOnce: if C{True}, C{filter} is not added to the list of
            response filters if it already in the list.
        """
        if onlyOnce and filter in self.responseFilters:
            return
        if atEnd:
            self.responseFilters.append(filter)
        else:
            self.responseFilters.insert(0, filter)

    def unparseURL(self, scheme=None, host=None, port=None,
                   path=None, params=None, querystring=None, fragment=None):
        """Turn the request path into a url string. For any pieces of
        the url that are not specified, use the value from the
        request. The arguments have the same meaning as the same named
        attributes of Request."""

        if scheme is None: scheme = self.scheme
        if host is None: host = self.host
        if port is None: port = self.port
        if path is None: path = self.path
        if params is None: params = self.params
        if querystring is None: querystring = self.querystring
        if fragment is None: fragment = ''

        if port == http.defaultPortForScheme.get(scheme, 0):
            hostport = host
        else:
            hostport = host + ':' + str(port)

        return urlparse.urlunparse((
            scheme, hostport, path,
            params, querystring, fragment))

    def _parseURL(self):
        if self.uri[0] == '/':
            # Can't use urlparse for request_uri because urlparse
            # wants to be given an absolute or relative URI, not just
            # an abs_path, and thus gets '//foo' wrong.
            self.scheme = self.host = self.path = self.params = self.querystring = ''
            if '?' in self.uri:
                self.path, self.querystring = self.uri.split('?', 1)
            else:
                self.path = self.uri
            if ';' in self.path:
                self.path, self.params = self.path.split(';', 1)
        else:
            # It is an absolute uri, use standard urlparse
            (self.scheme, self.host, self.path,
             self.params, self.querystring, fragment) = urlparse.urlparse(self.uri)

        if self.querystring:
            self.args = cgi.parse_qs(self.querystring, True)
        else:
            self.args = {}

        path = map(unquote, self.path[1:].split('/'))
        if self._initialprepath:
            # We were given an initial prepath -- this is for supporting
            # CGI-ish applications where part of the path has already
            # been processed
            prepath = map(unquote, self._initialprepath[1:].split('/'))

            if path[:len(prepath)] == prepath:
                self.prepath = prepath
                self.postpath = path[len(prepath):]
            else:
                self.prepath = []
                self.postpath = path
        else:
            self.prepath = []
            self.postpath = path
        #print("_parseURL", self.uri, (self.uri, self.scheme, self.host, self.path, self.params, self.querystring))

    def _schemeFromPort(self, port):
        """
        Try to determine the scheme matching the supplied server port. This is needed in case
        where a device in front of the server is changing the scheme (e.g. decoding SSL) but not
        rewriting the scheme in URIs returned in responses (e.g. in Location headers). This could trick
        clients into using an inappropriate scheme for subsequent requests. What we should do is
        take the port number from the Host header or request-URI and map that to the scheme that
        matches the service we configured to listen on that port.
 
        @param port: the port number to test
        @type port: C{int}
        
        @return: C{True} if scheme is https (secure), C{False} otherwise
        @rtype: C{bool}
        """

        #from twistedcaldav.config import config
        if hasattr(self.site, "EnableSSL") and self.site.EnableSSL:
            if port == self.site.SSLPort:
                return True
            elif port in self.site.BindSSLPorts:
                return True
        
        return False

    def _fixupURLParts(self):
        hostaddr, secure = self.chanRequest.getHostInfo()
        if not self.scheme:
            self.scheme = ('http', 'https')[secure]

        if self.host:
            self.host, self.port = http.splitHostPort(self.scheme, self.host)
            self.scheme = ('http', 'https')[self._schemeFromPort(self.port)]
        else:
            # If GET line wasn't an absolute URL
            host = self.headers.getHeader('host')
            if host:
                self.host, self.port = http.splitHostPort(self.scheme, host)
                self.scheme = ('http', 'https')[self._schemeFromPort(self.port)]
            else:
                # When no hostname specified anywhere, either raise an
                # error, or use the interface hostname, depending on
                # protocol version
                if self.clientproto >= (1,1):
                    raise http.HTTPError(responsecode.BAD_REQUEST)
                self.host = hostaddr.host
                self.port = hostaddr.port


    def process(self):
        "Process a request."
        log.info("%s %s %s" % (
            self.method,
            self.uri,
            "HTTP/%s.%s" % self.clientproto
        ))

        try:
            self.checkExpect()
            resp = self.preprocessRequest()
            if resp is not None:
                self._cbFinishRender(resp).addErrback(self._processingFailed)
                return
            self._parseURL()
            self._fixupURLParts()
            self.remoteAddr = self.chanRequest.getRemoteHost()
        except:
            self._processingFailed(failure.Failure())
            return

        d = defer.Deferred()
        d.addCallback(self._getChild, self.site.resource, self.postpath)
        d.addCallback(self._rememberResource, "/" + "/".join(quote(s) for s in self.postpath))
        d.addCallback(self._processTimeStamp)
        d.addCallback(lambda res, req: res.renderHTTP(req), self)
        d.addCallback(self._cbFinishRender)
        d.addErrback(self._processingFailed)
        d.callback(None)
        return d

    def _processTimeStamp(self, res):
        self.timeStamp("t-req-proc")
        return res

    def preprocessRequest(self):
        """Do any request processing that doesn't follow the normal
        resource lookup procedure. "OPTIONS *" is handled here, for
        example. This would also be the place to do any CONNECT
        processing."""

        if self.method == "OPTIONS" and self.uri == "*":
            response = http.Response(responsecode.OK)
            response.headers.setHeader('allow', ('GET', 'HEAD', 'OPTIONS', 'TRACE'))
            return response

        elif self.method == "POST":
            # Allow other methods to tunnel through using POST and a request header.
            # See http://code.google.com/apis/gdata/docs/2.0/basics.html
            if self.headers.hasHeader("X-HTTP-Method-Override"):
                intendedMethod = self.headers.getRawHeaders("X-HTTP-Method-Override")[0];
                if intendedMethod:
                    self.originalMethod = self.method
                    self.method = intendedMethod

        # This is where CONNECT would go if we wanted it
        return None

    def _getChild(self, _, res, path, updatepaths=True):
        """Call res.locateChild, and pass the result on to _handleSegment."""

        self.resources.append(res)

        if not path:
            return res

        result = res.locateChild(self, path)
        if isinstance(result, defer.Deferred):
            return result.addCallback(self._handleSegment, res, path, updatepaths)
        else:
            return self._handleSegment(result, res, path, updatepaths)

    def _handleSegment(self, result, res, path, updatepaths):
        """Handle the result of a locateChild call done in _getChild."""

        newres, newpath = result
        # If the child resource is None then display a error page
        if newres is None:
            raise http.HTTPError(responsecode.NOT_FOUND)

        # If we got a deferred then we need to call back later, once the
        # child is actually available.
        if isinstance(newres, defer.Deferred):
            return newres.addCallback(
                lambda actualRes: self._handleSegment(
                    (actualRes, newpath), res, path, updatepaths)
                )

        if path:
            url = quote("/" + "/".join(path))
        else:
            url = "/"

        if newpath is StopTraversal:
            # We need to rethink how to do this.
            #if newres is res:
                return res
            #else:
            #    raise ValueError("locateChild must not return StopTraversal with a resource other than self.")

        newres = iweb.IResource(newres)
        if newres is res:
            assert not newpath is path, "URL traversal cycle detected when attempting to locateChild %r from resource %r." % (path, res)
            assert len(newpath) < len(path), "Infinite loop impending..."

        if updatepaths:
            # We found a Resource... update the request.prepath and postpath
            for x in xrange(len(path) - len(newpath)):
                self.prepath.append(self.postpath.pop(0))
            url = quote("/" + "/".join(self.prepath) + ("/" if self.prepath and self.prepath[-1] else ""))
            self._rememberResource(newres, url)
        else:
            try:
                previousURL = self.urlForResource(res)
                url = quote(previousURL + path[0] + ("/" if path[0] and len(path) > 1 else ""))
                self._rememberResource(newres, url)
            except NoURLForResourceError:
                pass

        child = self._getChild(None, newres, newpath, updatepaths=updatepaths)

        return child

    _urlsByResource = weakref.WeakKeyDictionary()

    def _rememberResource(self, resource, url):
        """
        Remember the URL of a visited resource.
        """
        self._resourcesByURL[url] = resource
        self._urlsByResource[resource] = url
        return resource

    def _forgetResource(self, resource, url):
        """
        Remember the URL of a visited resource.
        """
        del self._resourcesByURL[url]
        del self._urlsByResource[resource]

    def urlForResource(self, resource):
        """
        Looks up the URL of the given resource if this resource was found while
        processing this request.  Specifically, this includes the requested
        resource, and resources looked up via L{locateResource}.

        Note that a resource may be found at multiple URIs; if the same resource
        is visited at more than one location while processing this request,
        this method will return one of those URLs, but which one is not defined,
        nor whether the same URL is returned in subsequent calls.

        @param resource: the resource to find a URI for.  This resource must
            have been obtained from the request (i.e. via its C{uri} attribute, or
            through its C{locateResource} or C{locateChildResource} methods).
        @return: a valid URL for C{resource} in this request.
        @raise NoURLForResourceError: if C{resource} has no URL in this request
            (because it was not obtained from the request).
        """
        url = self._urlsByResource.get(resource, None)
        if url is None:
            raise NoURLForResourceError(resource)
        return url

    def locateResource(self, url):
        """
        Looks up the resource with the given URL.
        @param uri: The URL of the desired resource.
        @return: a L{Deferred} resulting in the L{IResource} at the
            given URL or C{None} if no such resource can be located.
        @raise HTTPError: If C{url} is not a URL on the site that this
            request is being applied to.  The contained response will
            have a status code of L{responsecode.BAD_GATEWAY}.
        @raise HTTPError: If C{url} contains a query or fragment.
            The contained response will have a status code of
            L{responsecode.BAD_REQUEST}.
        """
        if url is None:
            return defer.succeed(None)

        #
        # Parse the URL
        #
        (scheme, host, path, query, fragment) = urlsplit(url)

        if query or fragment:
            raise http.HTTPError(http.StatusResponse(
                responsecode.BAD_REQUEST,
                "URL may not contain a query or fragment: %s" % (url,)
            ))

        # Look for cached value
        cached = self._resourcesByURL.get(path, None)
        if cached is not None:
            return defer.succeed(cached)

        segments = unquote(path).split("/")
        assert segments[0] == "", "URL path didn't begin with '/': %s" % (path,)

        # Walk the segments up to see if we can find a cached resource to start from
        preSegments = segments[:-1]
        postSegments = segments[-1:]
        cachedParent = None
        while(len(preSegments)):
            parentPath = "/".join(preSegments) + "/"
            cachedParent = self._resourcesByURL.get(parentPath, None)
            if cachedParent is not None:
                break
            else:
                postSegments.insert(0, preSegments.pop())
        
        if cachedParent is None:
            cachedParent = self.site.resource
            postSegments = segments[1:]

        def notFound(f):
            f.trap(http.HTTPError)
            if f.value.response.code != responsecode.NOT_FOUND:
                return f
            return None

        d = defer.maybeDeferred(self._getChild, None, cachedParent, postSegments, updatepaths=False)
        d.addCallback(self._rememberResource, path)
        d.addErrback(notFound)
        return d

    def locateChildResource(self, parent, childName):
        """
        Looks up the child resource with the given name given the parent
        resource.  This is similar to locateResource(), but doesn't have to
        start the lookup from the root resource, so it is potentially faster.
        @param parent: the parent of the resource being looked up.  This resource
            must have been obtained from the request (i.e. via its C{uri} attribute,
            or through its C{locateResource} or C{locateChildResource} methods).
        @param childName: the name of the child of C{parent} to looked up.
            to C{parent}.
        @return: a L{Deferred} resulting in the L{IResource} at the
            given URL or C{None} if no such resource can be located.
        @raise NoURLForResourceError: if C{resource} was not obtained from the
            request.
        """
        if parent is None or childName is None:
            return None

        assert "/" not in childName, "Child name may not contain '/': %s" % (childName,)

        parentURL = self.urlForResource(parent)
        if not parentURL.endswith("/"):
            parentURL += "/"
        url = parentURL + quote(childName)

        segment = childName

        def notFound(f):
            f.trap(http.HTTPError)
            if f.value.response.code != responsecode.NOT_FOUND:
                return f
            return None

        d = defer.maybeDeferred(self._getChild, None, parent, [segment], updatepaths=False)
        d.addCallback(self._rememberResource, url)
        d.addErrback(notFound)
        return d

    def _processingFailed(self, reason):
        if reason.check(http.HTTPError) is not None:
            # If the exception was an HTTPError, leave it alone
            d = defer.succeed(reason.value.response)
        else:
            # Otherwise, it was a random exception, so give a
            # ICanHandleException implementer a chance to render the page.
            def _processingFailed_inner(reason):
                handler = iweb.ICanHandleException(self, self)
                return handler.renderHTTP_exception(self, reason)
            d = defer.maybeDeferred(_processingFailed_inner, reason)

        d.addCallback(self._cbFinishRender)
        d.addErrback(self._processingReallyFailed, reason)
        return d


    def _processingReallyFailed(self, reason, origReason):
        """
        An error occurred when attempting to report an error to the HTTP
        client.
        """
        log.failure("Exception rendering error page", reason)
        log.failure("Original exception", origReason)

        try:
            body = (
                "<html><head><title>Internal Server Error</title></head>"
                "<body><h1>Internal Server Error</h1>"
                "An error occurred rendering the requested page. "
                "Additionally, an error occurred rendering the error page."
                "</body></html>"
            )
            response = http.Response(
                responsecode.INTERNAL_SERVER_ERROR,
                {'content-type': http_headers.MimeType('text','html')},
                body
            )
            self.writeResponse(response)
        except:
            log.failure(
                "An error occurred.  We tried to report that error.  "
                "Reporting that error caused an error.  "
                "In the process of reporting the error-reporting error to "
                "the client, there was *yet another* error.  Here it is.  "
                "I give up."
            )
            self.chanRequest.abortConnection()


    def _cbFinishRender(self, result):
        def filterit(response, f):
            if (hasattr(f, 'handleErrors') or
                (response.code >= 200 and response.code < 300)):
                return f(self, response)
            else:
                return response

        response = iweb.IResponse(result, None)
        if response:
            d = defer.Deferred()
            for f in self.responseFilters:
                d.addCallback(filterit, f)
            d.addCallback(self.writeResponse)
            d.callback(response)
            return d

        resource = iweb.IResource(result, None)
        if resource:
            self.resources.append(resource)
            d = defer.maybeDeferred(resource.renderHTTP, self)
            d.addCallback(self._cbFinishRender)
            return d

        raise TypeError("html is not a resource or a response")

    def renderHTTP_exception(self, req, reason):
        log.failure("Exception rendering request: {request}", reason, request=req)

        body = ("<html><head><title>Internal Server Error</title></head>"
                "<body><h1>Internal Server Error</h1>An error occurred rendering the requested page. More information is available in the server log.</body></html>")

        return http.Response(
            responsecode.INTERNAL_SERVER_ERROR,
            {'content-type': http_headers.MimeType('text','html')},
            body)

class Site(object):
    def __init__(self, resource):
        """Initialize.
        """
        self.resource = iweb.IResource(resource)

    def __call__(self, *args, **kwargs):
        return Request(site=self, *args, **kwargs)


class NoURLForResourceError(RuntimeError):
    def __init__(self, resource):
        RuntimeError.__init__(self, "Resource %r has no URL in this request." % (resource,))
        self.resource = resource


__all__ = ['Request', 'Site', 'StopTraversal', 'VERSION', 'defaultHeadersFilter', 'doTrace', 'parsePOSTData', 'preconditionfilter', 'NoURLForResourceError']
