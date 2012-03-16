##
# Cyrus Daboo, cdaboo@apple.com
# Copyright 2006 Apple Computer, Inc.  All Rights Reserved.
##

__all__ = [
    "responseForHref",
    "propertyListForResource",
]

from twisted.internet.defer import deferredGenerator, waitForDeferred
from twisted.python.failure import Failure

from twext.python.log import Logger
from twext.web2 import responsecode
from twext.web2.dav import davxml
from txdav.xml.base import WebDAVElement
from twext.web2.dav.http import statusForFailure
from twext.web2.dav.method.propfind import propertyName

log = Logger()


def responseForHref(request, responses, href, resource, propertiesForResource, propertyreq):

    if propertiesForResource is not None:
        properties_by_status = waitForDeferred(propertiesForResource(request, propertyreq, resource))
        yield properties_by_status
        properties_by_status = properties_by_status.getResult()

        propstats = []

        for status in properties_by_status:
            properties = properties_by_status[status]
            if properties:
                xml_status = davxml.Status.fromResponseCode(status)
                xml_container = davxml.PropertyContainer(*properties)
                xml_propstat = davxml.PropertyStatus(xml_container, xml_status)

                propstats.append(xml_propstat)

        if propstats:
            responses.append(davxml.PropertyStatusResponse(href, *propstats))

    else:
        responses.append(
            davxml.StatusResponse(
                href,
                davxml.Status.fromResponseCode(responsecode.OK),
            )
        )

responseForHref = deferredGenerator(responseForHref)

def propertyListForResource(request, prop, resource):
    """
    Return the specified properties on the specified resource.
    @param request: the L{IRequest} for the current request.
    @param prop: the L{PropertyContainer} element for the properties of interest.
    @param resource: the L{DAVFile} for the targetted resource.
    @return: a map of OK and NOT FOUND property values.
    """
    
    return _namedPropertiesForResource(request, prop.children, resource)

def _namedPropertiesForResource(request, props, resource):
    """
    Return the specified properties on the specified resource.
    @param request: the L{IRequest} for the current request.
    @param props: a list of property elements or qname tuples for the properties of interest.
    @param resource: the L{DAVFile} for the targetted resource.
    @return: a map of OK and NOT FOUND property values.
    """
    properties_by_status = {
        responsecode.OK        : [],
        responsecode.NOT_FOUND : [],
    }
    
    for property in props:
        if isinstance(property, WebDAVElement):
            qname = property.qname()
        else:
            qname = property
    
        props = waitForDeferred(resource.listProperties(request))
        yield props
        props = props.getResult()
        if qname in props:
            try:
                prop = waitForDeferred(resource.readProperty(qname, request))
                yield prop
                prop = prop.getResult()
                properties_by_status[responsecode.OK].append(prop)
            except:
                f = Failure()
                status = statusForFailure(f, "getting property: %s" % (qname,))
                if status != responsecode.NOT_FOUND:
                    log.err("Error reading property %r for resource %s: %s" %
                            (qname, request.uri, f.value))
                if status not in properties_by_status: properties_by_status[status] = []
                properties_by_status[status].append(propertyName(qname))
        else:
            properties_by_status[responsecode.NOT_FOUND].append(propertyName(qname))
    
    yield properties_by_status

_namedPropertiesForResource = deferredGenerator(_namedPropertiesForResource)
