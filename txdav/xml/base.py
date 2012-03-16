##
# Copyright (c) 2005-2012 Apple Computer, Inc. All rights reserved.
# Copyright (c) 2007 Twisted Matrix Laboratories.
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
##

"""
WebDAV XML base classes.

This module provides XML utilities for use with WebDAV.

See RFC 2518: http://www.ietf.org/rfc/rfc2518.txt (WebDAV)
"""

__all__ = [
    "dav_namespace",
    "twisted_dav_namespace",
    "twisted_private_namespace",
    "encodeXMLName",
    "decodeXMLName",
    "WebDAVElement",
    "PCDATAElement",
    "WebDAVOneShotElement",
    "WebDAVUnknownElement",
    "WebDAVEmptyElement",
    "WebDAVTextElement",
    "WebDAVDateTimeElement",
    "DateTimeHeaderElement",
]

import datetime
import string
import cStringIO as StringIO
import re

from twext.python.log import Logger
from twext.web2.http_headers import parseDateTime

log = Logger()

##
# Base XML elements
##

dav_namespace = "DAV:"
twisted_dav_namespace = "http://twistedmatrix.com/xml_namespace/dav/"
twisted_private_namespace = twisted_dav_namespace + "private/"


def encodeXMLName(namespace, name):
    """
    Encodes an XML namespace and name into a UTF-8 string.
    If namespace is None, returns "name", otherwise, returns
    "{namespace}name".
    """
    if not namespace:
        sname = name
    else:
        sname = u"{%s}%s" % (namespace, name)

    return sname.encode("utf-8")


def decodeXMLName(name):
    """
    Decodes an XML (namespace, name) pair from an ASCII string as
    encoded by encodeXMLName().
    """
    def invalid():
        raise ValueError("Invalid encoded name: %r" % (name,))

    if not name:
        invalid()

    if name[0] is "{":
        index = name.find("}")
        if (index is -1 or not len(name) > index):
            invalid()

        namespace = name[1:index].decode("utf-8")
        localname = name[index+1:].decode("utf-8")

        if not namespace:
            namespace = None

        if not localname:
            invalid()

    else:
        namespace = None
        localname = name.decode("utf-8")
    
    if "{" in localname or "}" in localname:
        invalid()

    return (namespace, localname)


class WebDAVElement (object):
    """
    WebDAV XML element. (RFC 2518, section 12)
    """
    namespace          = dav_namespace # Element namespace (class variable)
    name               = None          # Element name (class variable)
    allowed_children   = None          # Types & count limits on child elements
    allowed_attributes = None          # Allowed attribute names
    hidden             = False         # Don't list in PROPFIND with <allprop>
    protected          = False         # See RFC 3253 section 1.4.1
    unregistered       = False         # Subclass of factory; doesn't register

    def __init__(self, *children, **attributes):
        super(WebDAVElement, self).__init__()

        if self.allowed_children is None:
            raise NotImplementedError(
                "WebDAVElement subclass %s is not implemented."
                % (self.__class__.__name__,)
            )

        my_children = []

        allowPCDATA = self.allowed_children.has_key(PCDATAElement)

        for child in children:
            if child is None:
                continue

            if isinstance(child, (str, unicode)):
                child = PCDATAElement(child)

            if isinstance(child, PCDATAElement) and not allowPCDATA:
                continue

            my_children.append(child)

        self.children = tuple(my_children)
        self.attributes = attributes

    @classmethod
    def qname(cls):
        return (cls.namespace, cls.name)

    @classmethod
    def sname(cls):
        return encodeXMLName(cls.namespace, cls.name)

    def validate(self):
        children = self.children
        attributes = self.attributes

        if self.allowed_children is None:
            raise NotImplementedError(
                "WebDAVElement subclass %s is not implemented."
                % (self.__class__.__name__,)
            )

        #
        # Validate that children are of acceptable types
        #
        allowed_children = dict([
            (child_type, list(limits))
            for child_type, limits
            in self.allowed_children.items()
        ])

        my_children = []

        for child in children:

            assert isinstance(child, (WebDAVElement, PCDATAElement)), "Not an element: %r" % (child,)
            
            child.validate()

            for allowed, (min, max) in allowed_children.items():
                if type(allowed) == type and isinstance(child, allowed):
                    qname = allowed
                elif child.qname() == allowed:
                    qname = allowed
                else:
                    continue

                if min is not None and min > 0:
                    min -= 1
                if max is not None:
                    assert max > 0, "Too many children of type %s for %s" % (child.sname(), self.sname())
                    max -= 1
                allowed_children[qname] = (min, max)
                my_children.append(child)
                break
            else:
                if not (isinstance(child, PCDATAElement) and child.isWhitespace()):
                    log.debug(
                        "Child of type %s is unexpected and therefore ignored in %s element"
                        % (child.sname(), self.sname())
                    )

        for qname, (min, max) in allowed_children.items():
            if min != 0:
                raise ValueError("Not enough children of type %s for %s"
                                 % (encodeXMLName(*qname), self.sname()))

        self.children = tuple(my_children)

        #
        # Validate that attributes have known names
        #
        my_attributes = {}

        if self.allowed_attributes:
            for name in attributes:
                if name not in self.allowed_attributes:
                    log.debug("Attribute %s is unexpected in %s element" % (name, self.sname()))
                my_attributes[name] = attributes[name]

            for name, required in self.allowed_attributes.items():
                if required and name not in my_attributes:
                    raise ValueError("Attribute %s is required in %s element"
                                     % (name, self.sname()))

        else:
            if not isinstance(self, WebDAVUnknownElement) and attributes:
                log.debug("Attributes %s are unexpected in %s element"
                          % (attributes.keys(), self.sname()))
            my_attributes.update(attributes)

        self.attributes = my_attributes

    def __str__(self):
        return self.sname()

    def __repr__(self):
        if hasattr(self, "attributes") and hasattr(self, "children"):
            return "<%s %r: %r>" % (self.sname(), self.attributes, self.children)
        else:
            return "<%s>" % (self.sname())

    def __eq__(self, other):
        if isinstance(other, WebDAVElement):
            return (
                self.name       == other.name       and
                self.namespace  == other.namespace  and
                self.attributes == other.attributes and
                self.children   == other.children
            )
        else:
            return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def __contains__(self, child):
        return child in self.children

    def writeXML(self, output, pretty=True):
        output.write("<?xml version='1.0' encoding='UTF-8'?>" + ("\n" if pretty else ""))
        self._writeToStream(output, "", 0, pretty)

    def _writeToStream(self, output, ns, level, pretty):
        """
        Fast XML output.

        @param output: C{stream} to write to.
        @param ns: C{str} containing the namespace of the enclosing element.
        @param level: C{int} containing the element nesting level (starts at 0).
        @param pretty: C{bool} whether to use 'pretty' formatted output or not.
        """
        
        # Do pretty indent
        if pretty and level:
            output.write("  " * level)
        
        # Check for empty element (one with either no children or a single PCDATA that is itself empty)
        if (len(self.children) == 0 or
            (len(self.children) == 1 and isinstance(self.children[0], PCDATAElement) and len(str(self.children[0])) == 0)):

            # Write out any attributes or the namespace if difference from enclosing element.
            if self.attributes or (ns != self.namespace):
                output.write("<%s" % (self.name,))
                for name, value in self.attributes.iteritems():
                    self._writeAttributeToStream(output, name, value)
                if ns != self.namespace:
                    output.write(" xmlns='%s'" % (self.namespace,))
                output.write("/>")
            else:
                output.write("<%s/>" % (self.name,))
        else:
            # Write out any attributes or the namespace if difference from enclosing element.
            if self.attributes or (ns != self.namespace):
                output.write("<%s" % (self.name,))
                for name, value in self.attributes.iteritems():
                    self._writeAttributeToStream(output, name, value)
                if ns != self.namespace:
                    output.write(" xmlns='%s'" % (self.namespace,))
                    ns = self.namespace
                output.write(">")
            else:
                output.write("<%s>" % (self.name,))
                
            # Determine nature of children when doing pretty print: we do
            # not want to insert CRLFs or any other whitespace in PCDATA.
            hasPCDATA = False
            for child in self.children:
                if isinstance(child, PCDATAElement):
                    hasPCDATA = True
                    break
            
            # Write out the children.
            if pretty and not hasPCDATA:
                output.write("\r\n")
            for child in self.children:
                child._writeToStream(output, ns, level+1, pretty)
                
            # Close the element.
            if pretty and not hasPCDATA and level:
                output.write("  " * level)
            output.write("</%s>" % (self.name,))

        if pretty and level:
            output.write("\r\n")

    def _writeAttributeToStream(self, output, name, value):
        
        # Quote any single quotes. We do not need to be any smarter than this.
        value = value.replace("'", "&apos;")

        output.write(" %s='%s'" % (name, value,))  
      
    def toxml(self, pretty=True):
        output = StringIO.StringIO()
        self.writeXML(output, pretty)
        return str(output.getvalue())

    def element(self, document):
        element = document.createElementNS(self.namespace, self.name)
        if hasattr(self, "attributes"):
            for name, value in self.attributes.items():
                namespace, name = decodeXMLName(name)
                attribute = document.createAttributeNS(namespace, name)
                attribute.nodeValue = value
                element.setAttributeNodeNS(attribute)
        return element

    def addToDOM(self, document, parent):
        element = self.element(document)

        if parent is None:
            document.appendChild(element)
        else:
            parent.appendChild(element)

        for child in self.children:
            if child:
                try:
                    child.addToDOM(document, element)
                except:
                    log.err("Unable to add child %r of element %s to DOM" % (child, self))
                    raise

    def childrenOfType(self, child_type):
        """
        Returns a list of children with the same qname as the given type.
        """
        if type(child_type) is tuple:
            qname = child_type
        else:
            qname = child_type.qname()

        return [ c for c in self.children if c.qname() == qname ]

    def childOfType(self, child_type):
        """
        Returns a child of the given type, if any, or None.
        Raises ValueError if more than one is found.
        """
        found = None
        for child in self.childrenOfType(child_type):
            if found:
                raise ValueError("Multiple %s elements found in %s" % (child_type.sname(), self.toxml()))
            found = child
        return found

    def removeWhitespaceNodes(self):
        """ Removes all of the whitespace-only text decendants of a DOM node. """
        # prepare the list of text nodes to remove (and recurse when needed)
        remove_list = []
        for child in self.children:
            if isinstance(child, PCDATAElement) and not child.data.strip():
                # add this text node to the to-be-removed list
                remove_list.append(child)
            elif isinstance(child, WebDAVElement):
                # recurse, it's the simplest way to deal with the subtree
                child.removeWhitespaceNodes()

        # perform the removals
        newchildren = []
        for child in self.children:
            if child not in remove_list:
                newchildren.append(child)
        self.children = tuple(newchildren)


class PCDATAElement (object):
    def __init__(self, data):
        super(PCDATAElement, self).__init__()

        if data is None:
            data = ""
        elif type(data) is unicode:
            data = data.encode("utf-8")
        else:
            assert type(data) is str, ("PCDATA must be a string: %r" % (data,))

        self.data = data

    @classmethod
    def qname(cls):
        return (None, "#PCDATA")

    @classmethod
    def sname(cls):
        return "#PCDATA"

    def validate(self):
        pass

    def __str__(self):
        return str(self.data)

    def __repr__(self):
        return "<%s: %r>" % (self.__class__.__name__, self.data)

    def __add__(self, other):
        if isinstance(other, PCDATAElement):
            return self.__class__(self.data + other.data)
        else:
            return self.__class__(self.data + other)

    def __eq__(self, other):
        if isinstance(other, PCDATAElement):
            return self.data == other.data
        elif type(other) in (str, unicode):
            return self.data == other
        else:
            return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def isWhitespace(self):
        for char in str(self):
            if char not in string.whitespace:
                return False
        return True

    def element(self, document):
        return document.createTextNode(self.data)

    def addToDOM(self, document, parent):
        try:
            parent.appendChild(self.element(document))
        except TypeError:
            log.err("Invalid PCDATA: %r" % (self.data,))
            raise

    def _writeToStream(self, output, ns, level, pretty):
        # Do escaping/CDATA behavior
        if "\r" in self.data or "\n" in self.data:
            # Do CDATA
            cdata = "<![CDATA[%s]]>" % (self.data.replace("]]>", "]]&gt;"),)
        else:
            cdata = self.data
            if "&" in cdata:
                cdata = cdata.replace("&", "&amp;")
            if "<" in cdata:
                cdata = cdata.replace("<", "&lt;")
            if ">" in cdata:
                cdata = cdata.replace(">", "&gt;")

        output.write(cdata)


class WebDAVOneShotElement (WebDAVElement):
    """
    Element with exactly one WebDAVEmptyElement child and no attributes.
    """
    __singletons = {}

    def __new__(clazz, *children):
        child = None
        for next in children:
            if isinstance(next, WebDAVEmptyElement):
                if child is not None:
                    raise ValueError("%s must have exactly one child, not %r"
                                     % (clazz.__name__, children))
                child = next
            elif isinstance(next, PCDATAElement):
                pass
            else:
                raise ValueError("%s child is not a WebDAVEmptyElement instance: %s"
                                 % (clazz.__name__, next))

        if clazz not in WebDAVOneShotElement.__singletons:
            WebDAVOneShotElement.__singletons[clazz] = {
                child: WebDAVElement.__new__(clazz)
            }
        elif child not in WebDAVOneShotElement.__singletons[clazz]:
            WebDAVOneShotElement.__singletons[clazz][child] = (
                WebDAVElement.__new__(clazz)
            )

        return WebDAVOneShotElement.__singletons[clazz][child]


class WebDAVUnknownElement (WebDAVElement):
    """
    Placeholder for unknown element tag names.
    """
    allowed_children = {
        WebDAVElement: (0, None),
        PCDATAElement: (0, None),
    }

    @classmethod
    def withName(cls, namespace, name):
        child = cls()
        child.namespace = namespace
        child.name = name
        return child

    def qname(self):
        return (self.namespace, self.name)

    def sname(self):
        return encodeXMLName(self.namespace, self.name)


class WebDAVEmptyElement (WebDAVElement):
    """
    WebDAV element with no contents.
    """
    __singletons = {}

    def __new__(clazz, *args, **kwargs):
        assert not args

        if kwargs:
            return WebDAVElement.__new__(clazz)
        else:
            if clazz not in WebDAVEmptyElement.__singletons:
                WebDAVEmptyElement.__singletons[clazz] = (WebDAVElement.__new__(clazz))
            return WebDAVEmptyElement.__singletons[clazz]

    allowed_children = {}
    children = ()

    def __hash__(self):
        """
        Define a hash method, so that an empty element can serve as dictionary
        keys. It's mainly useful to define singletons with
        L{WebDAVOneShotElement}.
        """
        return hash((self.name, self.namespace))


class WebDAVTextElement (WebDAVElement):
    """
    WebDAV element containing PCDATA.
    """
    @classmethod
    def fromString(clazz, string):
        if string is None:
            return clazz()
        elif isinstance(string, (str, unicode)):
            return clazz(PCDATAElement(string))
        else:
            return clazz(PCDATAElement(str(string)))

    allowed_children = { PCDATAElement: (0, None) }

    def __str__(self):
        return "".join([c.data for c in self.children])

    def __repr__(self):
        content = str(self)
        if content:
            return "<%s: %r>" % (self.sname(), content)
        else:
            return "<%s>" % (self.sname(),)

    def __eq__(self, other):
        if isinstance(other, WebDAVTextElement):
            return str(self) == str(other)
        elif type(other) in (str, unicode):
            return str(self) == other
        else:
            return NotImplemented


class WebDAVDateTimeElement (WebDAVTextElement):
    """
    WebDAV date-time element. (RFC 2518, section 23.2)
    """
    @classmethod
    def fromDate(clazz, date):
        """
        date may be a datetime.datetime instance, a POSIX timestamp
        (integer value, such as returned by time.time()), or an ISO
        8601-formatted (eg. "2005-06-13T16:14:11Z") date/time string.
        """
        def isoformat(date):
            if date.utcoffset() is None:
                return date.isoformat() + "Z"
            else:
                return date.isoformat()

        if type(date) is int:
            date = isoformat(datetime.datetime.fromtimestamp(date))
        elif type(date) is str:
            pass
        elif type(date) is unicode:
            date = date.encode("utf-8")
        elif isinstance(date, datetime.datetime):
            date = isoformat(date)
        else:
            raise ValueError("Unknown date type: %r" % (date,))

        return clazz(PCDATAElement(date))

    def __init__(self, *children, **attributes):
        super(WebDAVDateTimeElement, self).__init__(*children, **attributes)
        self.datetime() # Raise ValueError if the format is wrong

    def __eq__(self, other):
        if isinstance(other, WebDAVDateTimeElement):
            return self.datetime() == other.datetime()
        else:
            return NotImplemented

    def datetime(self):
        s = str(self)
        if not s:
            return None
        else:
            return parse_date(s)


class DateTimeHeaderElement (WebDAVTextElement):
    """
    WebDAV date-time element for elements that substitute for HTTP
    headers. (RFC 2068, section 3.3.1)
    """
    @classmethod
    def fromDate(clazz, date):
        """
        date may be a datetime.datetime instance, a POSIX timestamp
        (integer value, such as returned by time.time()), or an RFC
        2068 Full Date (eg. "Mon, 23 May 2005 04:52:22 GMT") string.
        """
        def format(date):
            #
            # FIXME: strftime() is subject to localization nonsense; we need to
            # ensure that we're using the correct localization, or don't use
            # strftime().
            #
            return date.strftime("%a, %d %b %Y %H:%M:%S GMT")

        if type(date) is int:
            date = format(datetime.datetime.fromtimestamp(date))
        elif type(date) is str:
            pass
        elif type(date) is unicode:
            date = date.encode("utf-8")
        elif isinstance(date, datetime.datetime):
            if date.tzinfo:
                raise NotImplementedError("I need to normalize to UTC")
            date = format(date)
        else:
            raise ValueError("Unknown date type: %r" % (date,))

        return clazz(PCDATAElement(date))

    def __init__(self, *children, **attributes):
        super(DateTimeHeaderElement, self).__init__(*children, **attributes)
        self.datetime() # Raise ValueError if the format is wrong

    def __eq__(self, other):
        if isinstance(other, WebDAVDateTimeElement):
            return self.datetime() == other.datetime()
        else:
            return NotImplemented

    def datetime(self):
        s = str(self)
        if not s:
            return None
        else:
            return parseDateTime(s)


##
# Utilities
##

class FixedOffset (datetime.tzinfo):
    """
    Fixed offset in minutes east from UTC.
    """
    def __init__(self, offset, name=None):
        super(FixedOffset, self).__init__()

        self._offset = datetime.timedelta(minutes=offset)
        self._name   = name

    def utcoffset(self, dt): return self._offset
    def tzname   (self, dt): return self._name
    def dst      (self, dt): return datetime.timedelta(0)


_regex_ISO8601Date = re.compile(
    "^" +
    "(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})T" +
    "(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})(?:.(?P<subsecond>\d+))*" +
    "(?:Z|(?P<offset_sign>\+|-)(?P<offset_hour>\d{2}):(?P<offset_minute>\d{2}))" +
    "$"
)

def parse_date(date):
    """
    Parse an ISO 8601 date and return a corresponding datetime.datetime object.
    """
    # See http://www.iso.org/iso/en/prods-services/popstds/datesandtime.html

    match = _regex_ISO8601Date.match(date)
    if match is not None:
        subsecond = match.group("subsecond")
        if subsecond is None:
            subsecond = 0
        else:
            subsecond = int(subsecond)

        offset_sign = match.group("offset_sign")
        if offset_sign is None:
            offset = FixedOffset(0)
        else:
            offset_hour   = int(match.group("offset_hour"  ))
            offset_minute = int(match.group("offset_minute"))

            delta = (offset_hour * 60) + offset_minute

            if   offset_sign == "+": offset = FixedOffset(0 - delta)
            elif offset_sign == "-": offset = FixedOffset(0 + delta)

        return datetime.datetime(
            int(match.group("year"  )),
            int(match.group("month" )),
            int(match.group("day"   )),
            int(match.group("hour"  )),
            int(match.group("minute")),
            int(match.group("second")),
            subsecond,
            offset
        )
    else:
        raise ValueError("Invalid ISO 8601 date format: %r" % (date,))
