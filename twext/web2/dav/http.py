##
# Copyright (c) 2005 Apple Computer, Inc. All rights reserved.
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
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

"""
HTTP Utilities
"""

__all__ = [
    "ErrorResponse",
    "NeedPrivilegesResponse",
    "MultiStatusResponse",
    "ResponseQueue",
    "PropertyStatusResponseQueue",
    "statusForFailure",
    "errorForFailure",
    "messageForFailure",
]

import errno

from twisted.python.failure import Failure
from twisted.python.filepath import InsecurePath

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.iweb import IResponse
from twext.web2.http import Response, HTTPError, StatusResponse
from twext.web2.http_headers import MimeType
from twext.web2.dav.util import joinURL
from txdav.xml import element

log = Logger()


class ErrorResponse(Response):
    """
    A L{Response} object which contains a status code and a L{element.Error}
    element.
    Renders itself as a DAV:error XML document.
    """
    error = None
    unregistered = True     # base class is already registered

    def __init__(self, code, error, description=None):
        """
        @param code: a response code.
        @param error: an L{WebDAVElement} identifying the error, or a
            tuple C{(namespace, name)} with which to create an empty element
            denoting the error.  (The latter is useful in the case of
            preconditions ans postconditions, not all of which have defined
            XML element classes.)
        @param description: an optional string that, if present, will get
            wrapped in a (twisted_dav_namespace, error-description) element.
        """
        if type(error) is tuple:
            xml_namespace, xml_name = error
            error = element.WebDAVUnknownElement()
            error.namespace = xml_namespace
            error.name = xml_name

        self.description = description
        if self.description:
            output = element.Error(error, element.ErrorDescription(self.description)).toxml()
        else:
            output = element.Error(error).toxml()

        Response.__init__(self, code=code, stream=output)

        self.headers.setHeader("content-type", MimeType("text", "xml"))

        self.error = error


    def __repr__(self):
        return "<%s %s %s>" % (self.__class__.__name__, self.code, self.error.sname())

class NeedPrivilegesResponse (ErrorResponse):
    def __init__(self, base_uri, errors):
        """
        An error response which is due to unsufficient privileges, as
        determined by L{DAVResource.checkPrivileges}.
        @param base_uri: the base URI for the resources with errors (the URI of
            the resource on which C{checkPrivileges} was called).
        @param errors: a sequence of tuples, as returned by
            C{checkPrivileges}.
        """
        denials = []

        for subpath, privileges in errors:
            if subpath is None:
                uri = base_uri
            else:
                uri = joinURL(base_uri, subpath)

            for p in privileges:
                denials.append(element.Resource(element.HRef(uri), 
                                               element.Privilege(p)))

        super(NeedPrivilegesResponse, self).__init__(responsecode.FORBIDDEN, element.NeedPrivileges(*denials))

class MultiStatusResponse (Response):
    """
    Multi-status L{Response} object.
    Renders itself as a DAV:multi-status XML document.
    """
    def __init__(self, xml_responses):
        """
        @param xml_responses: an interable of element.Response objects.
        """
        Response.__init__(self, code=responsecode.MULTI_STATUS,
                          stream=element.MultiStatus(*xml_responses).toxml())

        self.headers.setHeader("content-type", MimeType("text", "xml"))

class ResponseQueue (object):
    """
    Stores a list of (typically error) responses for use in a
    L{MultiStatusResponse}.
    """
    def __init__(self, path_basename, method, success_response):
        """
        @param path_basename: the base path for all responses to be added to the 
            queue.
            All paths for responses added to the queue must start with
            C{path_basename}, which will be stripped from the beginning of each
            path to determine the response's URI.
        @param method: the name of the method generating the queue.
        @param success_response: the response to return in lieu of a
            L{MultiStatusResponse} if no responses are added to this queue.
        """
        self.responses         = []
        self.path_basename     = path_basename
        self.path_basename_len = len(path_basename)
        self.method            = method
        self.success_response  = success_response

    def add(self, path, what):
        """
        Add a response.
        @param path: a path, which must be a subpath of C{path_basename} as
            provided to L{__init__}.
        @param what: a status code or a L{Failure} for the given path.
        """
        assert path.startswith(self.path_basename), "%s does not start with %s" % (path, self.path_basename)

        if type(what) is int:
            code    = what
            error   = None
            message = responsecode.RESPONSES[code]
        elif isinstance(what, Failure):
            code    = statusForFailure(what)
            error   = errorForFailure(what)
            message = messageForFailure(what)
        else:
            raise AssertionError("Unknown data type: %r" % (what,))

        if code > 400: # Error codes only
            log.err("Error during %s for %s: %s" % (self.method, path, message))

        uri = path[self.path_basename_len:]

        children = []
        children.append(element.HRef(uri))
        children.append(element.Status.fromResponseCode(code))
        if error is not None:
            children.append(error)
        if message is not None:
            children.append(element.ResponseDescription(message))
        self.responses.append(element.StatusResponse(*children))

    def response(self):
        """
        Generate a L{MultiStatusResponse} with the responses contained in the
        queue or, if no such responses, return the C{success_response} provided
        to L{__init__}.
        @return: the response.
        """
        if self.responses:
            return MultiStatusResponse(self.responses)
        else:
            return self.success_response

class PropertyStatusResponseQueue (object):
    """
    Stores a list of propstat elements for use in a L{Response}
    in a L{MultiStatusResponse}.
    """
    def __init__(self, method, uri, success_response):
        """
        @param method: the name of the method generating the queue.
        @param uri: the URI for the response.
        @param success_response: the status to return if no
            L{PropertyStatus} are added to this queue.
        """
        self.method            = method
        self.uri               = uri
        self.propstats         = []
        self.success_response  = success_response

    def add(self, what, property):
        """
        Add a response.
        @param what: a status code or a L{Failure} for the given path.
        @param property: the property whose status is being reported.
        """
        if type(what) is int:
            code    = what
            error   = None
            message = responsecode.RESPONSES[code]
        elif isinstance(what, Failure):
            code    = statusForFailure(what)
            error   = errorForFailure(what)
            message = messageForFailure(what)
        else:
            raise AssertionError("Unknown data type: %r" % (what,))

        if len(property.children) > 0:
            # Re-instantiate as empty element.
            property = element.WebDAVUnknownElement.withName(property.namespace, property.name)

        if code > 400: # Error codes only
            log.err("Error during %s for %s: %s" % (self.method, property, message))

        children = []
        children.append(element.PropertyContainer(property))
        children.append(element.Status.fromResponseCode(code))
        if error is not None:
            children.append(error)
        if message is not None:
            children.append(element.ResponseDescription(message))
        self.propstats.append(element.PropertyStatus(*children))

    def error(self):
        """
        Convert any 2xx codes in the propstat responses to 424 Failed Dependency.
        """
        for index, propstat in enumerate(self.propstats):
            # Check the status
            changed_status = False
            newchildren = []
            for child in propstat.children:
                if isinstance(child, element.Status) and (child.code / 100 == 2):
                    # Change the code
                    newchildren.append(element.Status.fromResponseCode(responsecode.FAILED_DEPENDENCY))
                    changed_status = True
                elif changed_status and isinstance(child, element.ResponseDescription):
                    newchildren.append(element.ResponseDescription(responsecode.RESPONSES[responsecode.FAILED_DEPENDENCY]))
                else:
                    newchildren.append(child)
            self.propstats[index] = element.PropertyStatus(*newchildren)

    def response(self):
        """
        Generate a response from the responses contained in the queue or, if
        there are no such responses, return the C{success_response} provided to
        L{__init__}.
        @return: a L{element.PropertyStatusResponse}.
        """
        if self.propstats:
            return element.PropertyStatusResponse(
                element.HRef(self.uri),
                *self.propstats
            )
        else:
            return element.StatusResponse(
                element.HRef(self.uri),
                element.Status.fromResponseCode(self.success_response)
            )

##
# Exceptions and response codes
##

def statusForFailure(failure, what=None):
    """
    @param failure: a L{Failure}.
    @param what: a decription of what was going on when the failure occurred.
        If what is not C{None}, emit a cooresponding message via L{log.err}.
    @return: a response code cooresponding to the given C{failure}.
    """
    def msg(err):
        if what is not None:
            log.msg("%s while %s" % (err, what))

    if failure.check(IOError, OSError):
        e = failure.value[0]
        if e == errno.EACCES or e == errno.EPERM:
            msg("Permission denied")
            return responsecode.FORBIDDEN
        elif e == errno.ENOSPC:
            msg("Out of storage space")
            return responsecode.INSUFFICIENT_STORAGE_SPACE
        elif e == errno.ENOENT:
            msg("Not found")
            return responsecode.NOT_FOUND
        else:
            failure.raiseException()
    elif failure.check(NotImplementedError):
        msg("Unimplemented error")
        return responsecode.NOT_IMPLEMENTED
    elif failure.check(InsecurePath):
        msg("Insecure path")
        return responsecode.FORBIDDEN
    elif failure.check(HTTPError):
        code = IResponse(failure.value.response).code
        msg("%d response" % (code,))
        return code
    else:
        failure.raiseException()

def errorForFailure(failure):
    if failure.check(HTTPError) and isinstance(failure.value.response, ErrorResponse):
        return element.Error(failure.value.response.error)
    else:
        return None

def messageForFailure(failure):
    if failure.check(HTTPError):
        if isinstance(failure.value.response, ErrorResponse):
            return failure.value.response.description
        elif isinstance(failure.value.response, StatusResponse):
            return failure.value.response.description
    return str(failure)
