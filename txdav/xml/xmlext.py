########################################################################
#
# File Name:            __init__.py
#
#
from types import UnicodeType
"""
WWW: http://4suite.com/4DOM         e-mail: support@4suite.com

Copyright (c) 2000 Fourthought Inc, USA.   All Rights Reserved.
See  http://4suite.com/COPYRIGHT  for license and copyright information
"""

"""Some Helper functions: 4DOM/PyXML-specific Extensions to the DOM,
and DOM-related utilities."""

__all__ = ["Print", "PrettyPrint"]

import string
import sys
import re

from xml.dom import Node
from xml.dom import XML_NAMESPACE, XMLNS_NAMESPACE

HTML_4_TRANSITIONAL_INLINE = ['TT', 'I', 'B', 'U', 'S', 'STRIKE', 'BIG', 'SMALL', 'EM', 'STRONG', 'DFN', 'CODE', 'SAMP', 'KBD', 'VAR', 'CITE', 'ABBR', 'ACRONYM', 'A', 'IMG', 'APPLET', 'OBJECT', 'FONT', 'BASEFONT', 'SCRIPT', 'MAP', 'Q', 'SUB', 'SUP', 'SPAN', 'BDO', 'IFRAME', 'INPUT', 'SELECT', 'TEXTAREA', 'LABEL', 'BUTTON']
HTML_FORBIDDEN_END = ['AREA', 'BASE', 'BASEFONT', 'BR', 'COL', 'FRAME', 'HR', 'IMG', 'INPUT', 'ISINDEX', 'LINK', 'META', 'PARAM']
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"


def Print(root, stream=sys.stdout, encoding='UTF-8'):
    if not hasattr(root, "nodeType"):
        return
    nss = SeekNss(root)
    visitor = PrintVisitor(stream, encoding, nsHints=nss)
    PrintWalker(visitor, root).run()
    return



def PrettyPrint(root, stream=sys.stdout, encoding='UTF-8', indent='  ',
                preserveElements=None):
    if not hasattr(root, "nodeType"):
        return
    nss_hints = SeekNss(root)
    preserveElements = preserveElements or []
    owner_doc = root.ownerDocument or root
    if hasattr(owner_doc, 'getElementsByName'):
        #We don't want to insert any whitespace into HTML inline elements
        preserveElements = preserveElements + HTML_4_TRANSITIONAL_INLINE
    visitor = PrintVisitor(stream, encoding, indent,
                                   preserveElements, nss_hints)
    PrintWalker(visitor, root).run()
    stream.write('\n')
    return



def GetAllNs(node):
    #The xml namespace is implicit
    nss = {'xml': XML_NAMESPACE}
    if node.nodeType == Node.ATTRIBUTE_NODE and node.ownerElement:
        return GetAllNs(node.ownerElement)
    if node.nodeType == Node.ELEMENT_NODE:
        if node.namespaceURI:
            nss[node.prefix] = node.namespaceURI
        for attr in node.attributes.values():
            if attr.namespaceURI == XMLNS_NAMESPACE:
                if attr.localName == 'xmlns':
                    nss[None] = attr.value
                else:
                    nss[attr.localName] = attr.value
            elif attr.namespaceURI:
                nss[attr.prefix] = attr.namespaceURI
    if node.parentNode:
        #Inner NS/Prefix mappings take precedence over outer ones
        parent_nss = GetAllNs(node.parentNode)
        parent_nss.update(nss)
        nss = parent_nss
    return nss



def SeekNss(node, nss=None):
    '''traverses the tree to seek an approximate set of defined namespaces'''
    nss = nss or {}
    for child in node.childNodes:
        if child.nodeType == Node.ELEMENT_NODE:
            if child.namespaceURI:
                nss[child.prefix] = child.namespaceURI
            for attr in child.attributes.values():
                if attr.namespaceURI == XMLNS_NAMESPACE:
                    if attr.localName == 'xmlns':
                        nss[None] = attr.value
                    else:
                        nss[attr.localName] = attr.value
                elif attr.namespaceURI:
                    nss[attr.prefix] = attr.namespaceURI
            SeekNss(child, nss)
    return nss



class PrintVisitor:
    def __init__(self, stream, encoding, indent='', plainElements=None,
                 nsHints=None, isXhtml=0, force8bit=0):
        self.stream = stream
        self.encoding = encoding
        # Namespaces
        self._namespaces = [{}]
        self._nsHints = nsHints or {}
        # PrettyPrint
        self._indent = indent
        self._depth = 0
        self._inText = 0
        self._plainElements = plainElements or []
        # HTML support
        self._html = None
        self._isXhtml = isXhtml
        self.force8bit = force8bit
        return


    def _write(self, text):
        if self.force8bit:
            obj = strobj_to_utf8str(text, self.encoding)
        else:
            obj = utf8_to_code(text, self.encoding)
        self.stream.write(obj)
        return


    def _tryIndent(self):
        if not self._inText and self._indent:
            self._write('\n' + self._indent * self._depth)
        return


    def visit(self, node):
        if self._html is None:
            # Set HTMLDocument flag here for speed
            self._html = hasattr(node.ownerDocument, 'getElementsByName')

        if node.nodeType == Node.ELEMENT_NODE:
            return self.visitElement(node)

        elif node.nodeType == Node.ATTRIBUTE_NODE:
            return self.visitAttr(node)

        elif node.nodeType == Node.TEXT_NODE:
            return self.visitText(node)

        elif node.nodeType == Node.CDATA_SECTION_NODE:
            return self.visitCDATASection(node)

        elif node.nodeType == Node.ENTITY_REFERENCE_NODE:
            return self.visitEntityReference(node)

        elif node.nodeType == Node.ENTITY_NODE:
            return self.visitEntity(node)

        elif node.nodeType == Node.PROCESSING_INSTRUCTION_NODE:
            return self.visitProcessingInstruction(node)

        elif node.nodeType == Node.COMMENT_NODE:
            return self.visitComment(node)

        elif node.nodeType == Node.DOCUMENT_NODE:
            return self.visitDocument(node)

        elif node.nodeType == Node.DOCUMENT_TYPE_NODE:
            return self.visitDocumentType(node)

        elif node.nodeType == Node.DOCUMENT_FRAGMENT_NODE:
            return self.visitDocumentFragment(node)

        elif node.nodeType == Node.NOTATION_NODE:
            return self.visitNotation(node)

        # It has a node type, but we don't know how to handle it
        raise Exception("Unknown node type: %s" % repr(node))


    def visitNodeList(self, node, exclude=None):
        for curr in node:
            if curr is not exclude:
                self.visit(curr)
        return


    def visitNamedNodeMap(self, node):
        for item in node.values():
            self.visit(item)
        return


    def visitAttr(self, node):
        if node.namespaceURI == XMLNS_NAMESPACE:
            # Skip namespace declarations
            return
        self._write(' ' + node.name)
        value = node.value
        if value or not self._html:
            text = TranslateCdata(value, self.encoding)
            text, delimiter = TranslateCdataAttr(text)
            self.stream.write("=%s%s%s" % (delimiter, text, delimiter))
        return


    def visitProlog(self):
        self._write("<?xml version='1.0' encoding='%s'?>" % (
            self.encoding or 'utf-8'
            ))
        self._inText = 0
        return


    def visitDocument(self, node):
        not self._html and self.visitProlog()
        node.doctype and self.visitDocumentType(node.doctype)
        self.visitNodeList(node.childNodes, exclude=node.doctype)
        return


    def visitDocumentFragment(self, node):
        self.visitNodeList(node.childNodes)
        return


    def visitElement(self, node):
        self._namespaces.append(self._namespaces[-1].copy())
        inline = node.tagName in self._plainElements
        not inline and self._tryIndent()
        self._write('<%s' % node.tagName)
        if self._isXhtml or not self._html:
            namespaces = ''
            if self._isXhtml:
                nss = {'xml': XML_NAMESPACE, None: XHTML_NAMESPACE}
            else:
                nss = GetAllNs(node)
            if self._nsHints:
                self._nsHints.update(nss)
                nss = self._nsHints
                self._nsHints = {}
            del nss['xml']
            for prefix in nss.keys():
                if prefix not in self._namespaces[-1] or self._namespaces[-1][prefix] != nss[prefix]:
                    nsuri, delimiter = TranslateCdataAttr(nss[prefix])
                    if prefix:
                        xmlns = " xmlns:%s=%s%s%s" % (prefix, delimiter, nsuri, delimiter)
                    else:
                        xmlns = " xmlns=%s%s%s" % (delimiter, nsuri, delimiter)
                    namespaces = namespaces + xmlns

                self._namespaces[-1][prefix] = nss[prefix]
            self._write(namespaces)
        for attr in node.attributes.values():
            self.visitAttr(attr)
        if len(node.childNodes):
            self._write('>')
            self._depth = self._depth + 1
            self.visitNodeList(node.childNodes)
            self._depth = self._depth - 1
            if not self._html or (node.tagName not in HTML_FORBIDDEN_END):
                not (self._inText and inline) and self._tryIndent()
                self._write('</%s>' % node.tagName)
        elif not self._html:
            self._write('/>')
        elif node.tagName not in HTML_FORBIDDEN_END:
            self._write('></%s>' % node.tagName)
        else:
            self._write('>')
        del self._namespaces[-1]
        self._inText = 0
        return


    def visitText(self, node):
        text = node.data
        if self._indent:
            text = string.strip(text) and text
        if text:
            if self._html:
                text = TranslateHtmlCdata(text, self.encoding)
            else:
                text = TranslateCdata(text, self.encoding)
            self.stream.write(text)
            self._inText = 1
        return


    def visitDocumentType(self, doctype):
        if not doctype.systemId and not doctype.publicId:
            return
        self._tryIndent()
        self._write('<!DOCTYPE %s' % doctype.name)
        if doctype.systemId and '"' in doctype.systemId:
            system = "'%s'" % doctype.systemId
        else:
            system = '"%s"' % doctype.systemId
        if doctype.publicId and '"' in doctype.publicId:
            # We should probably throw an error
            # Valid characters:  <space> | <newline> | <linefeed> |
            #                    [a-zA-Z0-9] | [-'()+,./:=?;!*#@$_%]
            public = "'%s'" % doctype.publicId
        else:
            public = '"%s"' % doctype.publicId
        if doctype.publicId and doctype.systemId:
            self._write(' PUBLIC %s %s' % (public, system))
        elif doctype.systemId:
            self._write(' SYSTEM %s' % system)
        if doctype.entities or doctype.notations:
            self._write(' [')
            self._depth = self._depth + 1
            self.visitNamedNodeMap(doctype.entities)
            self.visitNamedNodeMap(doctype.notations)
            self._depth = self._depth - 1
            self._tryIndent()
            self._write(']>')
        else:
            self._write('>')
        self._inText = 0
        return


    def visitEntity(self, node):
        """Visited from a NamedNodeMap in DocumentType"""
        self._tryIndent()
        self._write('<!ENTITY %s' % (node.nodeName))
        node.publicId and self._write(' PUBLIC %s' % node.publicId)
        node.systemId and self._write(' SYSTEM %s' % node.systemId)
        node.notationName and self._write(' NDATA %s' % node.notationName)
        self._write('>')
        return


    def visitNotation(self, node):
        """Visited from a NamedNodeMap in DocumentType"""
        self._tryIndent()
        self._write('<!NOTATION %s' % node.nodeName)
        node.publicId and self._write(' PUBLIC %s' % node.publicId)
        node.systemId and self._write(' SYSTEM %s' % node.systemId)
        self._write('>')
        return


    def visitCDATASection(self, node):
        self._tryIndent()
        self._write('<![CDATA[%s]]>' % (node.data))
        self._inText = 0
        return


    def visitComment(self, node):
        self._tryIndent()
        self._write('<!--%s-->' % (node.data))
        self._inText = 0
        return


    def visitEntityReference(self, node):
        self._write('&%s;' % node.nodeName)
        self._inText = 1
        return


    def visitProcessingInstruction(self, node):
        self._tryIndent()
        self._write('<?%s %s?>' % (node.target, node.data))
        self._inText = 0
        return



class PrintWalker:
    def __init__(self, visitor, startNode):
        self.visitor = visitor
        self.start_node = startNode
        return


    def step(self):
        """There is really no step to printing.  It prints the whole thing"""
        self.visitor.visit(self.start_node)
        return


    def run(self):
        return self.step()

ILLEGAL_LOW_CHARS = '[\x01-\x08\x0B-\x0C\x0E-\x1F]'
SURROGATE_BLOCK = '[\xF0-\xF7][\x80-\xBF][\x80-\xBF][\x80-\xBF]'
ILLEGAL_HIGH_CHARS = '\xEF\xBF[\xBE\xBF]'
#Note: Prolly fuzzy on this, but it looks as if characters from the surrogate block are allowed if in scalar form, which is encoded in UTF8 the same was as in surrogate block form
XML_ILLEGAL_CHAR_PATTERN = re.compile('%s|%s' % (ILLEGAL_LOW_CHARS, ILLEGAL_HIGH_CHARS))

g_utf8TwoBytePattern = re.compile('([\xC0-\xC3])([\x80-\xBF])')
g_cdataCharPattern = re.compile('[&<]|]]>')
g_charToEntity = {
        '&': '&amp;',
        '<': '&lt;',
        ']]>': ']]&gt;',
        }

# Slightly modified to not use types.Unicode
import codecs
def utf8_to_code(text, encoding):
    encoder = codecs.lookup(encoding)[0] # encode,decode,reader,writer
    if type(text) is not unicode:
        text = unicode(text, "utf-8")
    return encoder(text)[0] # result,size



def strobj_to_utf8str(text, encoding):
    if string.upper(encoding) not in ["UTF-8", "ISO-8859-1", "LATIN-1"]:
        raise ValueError("Invalid encoding: %s" % encoding)
    encoder = codecs.lookup(encoding)[0] # encode,decode,reader,writer
    if type(text) is not unicode:
        text = unicode(text, "utf-8")
    #FIXME
    return str(encoder(text)[0])



def TranslateCdataAttr(characters):
    '''Handles normalization and some intelligence about quoting'''
    if not characters:
        return '', "'"
    if "'" in characters:
        delimiter = '"'
        new_chars = re.sub('"', '&quot;', characters)
    else:
        delimiter = "'"
        new_chars = re.sub("'", '&apos;', characters)
    #FIXME: There's more to normalization
    #Convert attribute new-lines to character entity
    # characters is possibly shorter than new_chars (no entities)
    if "\n" in characters:
        new_chars = re.sub('\n', '&#10;', new_chars)
    return new_chars, delimiter



#Note: Unicode object only for now
def TranslateCdata(characters, encoding='UTF-8', prev_chars='', markupSafe=0,
                   charsetHandler=utf8_to_code):
    """
    charsetHandler is a function that takes a string or unicode object as the
    first argument, representing the string to be processed, and an encoding
    specifier as the second argument.  It must return a string or unicode
    object
    """
    if not characters:
        return ''
    if not markupSafe:
        if g_cdataCharPattern.search(characters):
            new_string = g_cdataCharPattern.subn(
                lambda m, d=g_charToEntity: d[m.group()],
                characters)[0]
        else:
            new_string = characters
        if prev_chars[-2:] == ']]' and characters[0] == '>':
            new_string = '&gt;' + new_string[1:]
    else:
        new_string = characters
    #Note: use decimal char entity rep because some browsers are broken
    #FIXME: This will bomb for high characters.  Should, for instance, detect
    #The UTF-8 for 0xFFFE and put out &#xFFFE;
    if XML_ILLEGAL_CHAR_PATTERN.search(new_string):
        new_string = XML_ILLEGAL_CHAR_PATTERN.subn(
            lambda m: '&#%i;' % ord(m.group()),
            new_string)[0]
    new_string = charsetHandler(new_string, encoding)
    return new_string



def TranslateHtmlCdata(characters, encoding='UTF-8', prev_chars=''):
    #Translate numerical char entity references with HTML entity equivalents
    new_string, _ignore_num_subst = re.subn(
        g_cdataCharPattern,
        lambda m, d=g_charToEntity: d[m.group()],
        characters
        )
    if prev_chars[-2:] == ']]' and new_string[0] == '>':
        new_string = '&gt;' + new_string[1:]
    new_string = UseHtmlCharEntities(new_string)
    try:
        new_string = utf8_to_code(new_string, encoding)
    except:
        #FIXME: This is a work-around, contributed by Mike Brown, that
        #Deals with escaping output, until we have XML/HTML aware codecs
        tmp_new_string = ""
        for c in new_string:
            try:
                new_c = utf8_to_code(c, encoding)
            except:
                new_c = '&#%i;' % ord(c)
            tmp_new_string = tmp_new_string + new_c
        new_string = tmp_new_string
    #new_string, num_subst = re.subn(g_xmlIllegalCharPattern, lambda m: '&#%i;'%ord(m.group()), new_string)
    #Note: use decimal char entity rep because some browsers are broken
    return new_string


HTML_CHARACTER_ENTITIES = {
    # Sect 24.2 -- ISO 8859-1
    160: 'nbsp',
    161: 'iexcl',
    162: 'cent',
    163: 'pound',
    164: 'curren',
    165: 'yen',
    166: 'brvbar',
    167: 'sect',
    168: 'uml',
    169: 'copy',
    170: 'ordf',
    171: 'laquo',
    172: 'not',
    173: 'shy',
    174: 'reg',
    175: 'macr',
    176: 'deg',
    177: 'plusmn',
    178: 'sup2',
    179: 'sup3',
    180: 'acute',
    181: 'micro',
    182: 'para',
    183: 'middot',
    184: 'cedil',
    185: 'sup1',
    186: 'ordm',
    187: 'raquo',
    188: 'frac14',
    189: 'frac12',
    190: 'frac34',
    191: 'iquest',
    192: 'Agrave',
    193: 'Aacute',
    194: 'Acirc',
    195: 'Atilde',
    196: 'Auml',
    197: 'Aring',
    198: 'AElig',
    199: 'Ccedil',
    200: 'Egrave',
    201: 'Eacute',
    202: 'Ecirc',
    203: 'Euml',
    204: 'Igrave',
    205: 'Iacute',
    206: 'Icirc',
    207: 'Iuml',
    208: 'ETH',
    209: 'Ntilde',
    210: 'Ograve',
    211: 'Oacute',
    212: 'Ocirc',
    213: 'Otilde',
    214: 'Ouml',
    215: 'times',
    216: 'Oslash',
    217: 'Ugrave',
    218: 'Uacute',
    219: 'Ucirc',
    220: 'Uuml',
    221: 'Yacute',
    222: 'THORN',
    223: 'szlig',
    224: 'agrave',
    225: 'aacute',
    226: 'acirc',
    227: 'atilde',
    228: 'auml',
    229: 'aring',
    230: 'aelig',
    231: 'ccedil',
    232: 'egrave',
    233: 'eacute',
    234: 'ecirc',
    235: 'euml',
    236: 'igrave',
    237: 'iacute',
    238: 'icirc',
    239: 'iuml',
    240: 'eth',
    241: 'ntilde',
    242: 'ograve',
    243: 'oacute',
    244: 'ocirc',
    245: 'otilde',
    246: 'ouml',
    247: 'divide',
    248: 'oslash',
    249: 'ugrave',
    250: 'uacute',
    251: 'ucirc',
    252: 'uuml',
    253: 'yacute',
    254: 'thorn',
    255: 'yuml',

    # Sect 24.3 -- Symbols, Mathematical Symbols, and Greek Letters
    # Latin Extended-B
    402: 'fnof',
    # Greek
    913: 'Alpha',
    914: 'Beta',
    915: 'Gamma',
    916: 'Delta',
    917: 'Epsilon',
    918: 'Zeta',
    919: 'Eta',
    920: 'Theta',
    921: 'Iota',
    922: 'Kappa',
    923: 'Lambda',
    924: 'Mu',
    925: 'Nu',
    926: 'Xi',
    927: 'Omicron',
    928: 'Pi',
    929: 'Rho',
    931: 'Sigma',
    932: 'Tau',
    933: 'Upsilon',
    934: 'Phi',
    935: 'Chi',
    936: 'Psi',
    937: 'Omega',
    945: 'alpha',
    946: 'beta',
    947: 'gamma',
    948: 'delta',
    949: 'epsilon',
    950: 'zeta',
    951: 'eta',
    952: 'theta',
    953: 'iota',
    954: 'kappa',
    955: 'lambda',
    956: 'mu',
    957: 'nu',
    958: 'xi',
    959: 'omicron',
    960: 'pi',
    961: 'rho',
    962: 'sigmaf',
    963: 'sigma',
    964: 'tau',
    965: 'upsilon',
    966: 'phi',
    967: 'chi',
    968: 'psi',
    969: 'omega',
    977: 'thetasym',
    978: 'upsih',
    982: 'piv',
    # General Punctuation
    8226: 'bull',      # bullet
    8230: 'hellip',    # horizontal ellipsis
    8242: 'prime',     # prime (minutes/feet)
    8243: 'Prime',     # double prime (seconds/inches)
    8254: 'oline',     # overline (spacing overscore)
    8250: 'frasl',     # fractional slash
    # Letterlike Symbols
    8472: 'weierp',    # script capital P (power set/Weierstrass p)
    8465: 'image',     # blackletter capital I (imaginary part)
    8476: 'real',      # blackletter capital R (real part)
    8482: 'trade',     # trademark
    8501: 'alefsym',   # alef symbol (first transfinite cardinal)
    # Arrows
    8592: 'larr',      # leftwards arrow
    8593: 'uarr',      # upwards arrow
    8594: 'rarr',      # rightwards arrow
    8595: 'darr',      # downwards arrow
    8596: 'harr',      # left right arrow
    8629: 'crarr',     # downwards arrow with corner leftwards (carriage return)
    8656: 'lArr',      # leftwards double arrow
    8657: 'uArr',      # upwards double arrow
    8658: 'rArr',      # rightwards double arrow
    8659: 'dArr',      # downwards double arrow
    8660: 'hArr',      # left right double arrow
    # Mathematical Operators
    8704: 'forall',    # for all
    8706: 'part',      # partial differential
    8707: 'exist',     # there exists
    8709: 'empty',     # empty set, null set, diameter
    8711: 'nabla',     # nabla, backward difference
    8712: 'isin',      # element of
    8713: 'notin',     # not an element of
    8715: 'ni',        # contains as member
    8719: 'prod',      # n-ary product, product sign
    8721: 'sum',       # n-ary sumation
    8722: 'minus',     # minus sign
    8727: 'lowast',    # asterisk operator
    8730: 'radic',     # square root, radical sign
    8733: 'prop',      # proportional to
    8734: 'infin',     # infinity
    8736: 'ang',       # angle
    8743: 'and',       # logical and, wedge
    8744: 'or',        # logical or, vee
    8745: 'cap',       # intersection, cap
    8746: 'cup',       # union, cup
    8747: 'int',       # integral
    8756: 'there4',    # therefore
    8764: 'sim',       # tilde operator, varies with, similar to
    8773: 'cong',      # approximately equal to
    8776: 'asymp',     # almost equal to, asymptotic to
    8800: 'ne',        # not equal to
    8801: 'equiv',     # identical to
    8804: 'le',        # less-than or equal to
    8805: 'ge',        # greater-than or equal to
    8834: 'sub',       # subset of
    8835: 'sup',       # superset of
    8836: 'nsub',      # not subset of
    8838: 'sube',      # subset of or equal to
    8839: 'supe',      # superset of or equal to
    8853: 'oplus',     # circled plus, direct sum
    8855: 'otimes',    # circled times, vector product
    8869: 'perp',      # up tack, orthogonal to, perpendicular
    8901: 'sdot',      # dot operator
    8968: 'lceil',     # left ceiling, apl upstile
    8969: 'rceil',     # right ceiling
    8970: 'lfloor',    # left floor, apl downstile
    8971: 'rfloor',    # right floor
    9001: 'lang',      # left-pointing angle bracket, bra
    9002: 'rang',      # right-pointing angle bracket, ket
    9674: 'loz',       # lozenge
    # Miscellaneous Symbols
    9824: 'spades',
    9827: 'clubs',
    9829: 'hearts',
    9830: 'diams',

    # Sect 24.4 -- Markup Significant and Internationalization
    # Latin Extended-A
    338: 'OElig',      # capital ligature OE
    339: 'oelig',      # small ligature oe
    352: 'Scaron',     # capital S with caron
    353: 'scaron',     # small s with caron
    376: 'Yuml',       # capital Y with diaeresis
    # Spacing Modifier Letters
    710: 'circ',       # circumflexx accent
    732: 'tidle',      # small tilde
    # General Punctuation
    8194: 'ensp',      # en space
    8195: 'emsp',      # em space
    8201: 'thinsp',    # thin space
    8204: 'zwnj',      # zero-width non-joiner
    8205: 'zwj',       # zero-width joiner
    8206: 'lrm',       # left-to-right mark
    8207: 'rlm',       # right-to-left mark
    8211: 'ndash',     # en dash
    8212: 'mdash',     # em dash
    8216: 'lsquo',     # left single quotation mark
    8217: 'rsquo',     # right single quotation mark
    8218: 'sbquo',     # single low-9 quotation mark
    8220: 'ldquo',     # left double quotation mark
    8221: 'rdquo',     # right double quotation mark
    8222: 'bdquo',     # double low-9 quotation mark
    8224: 'dagger',    # dagger
    8225: 'Dagger',    # double dagger
    8240: 'permil',    # per mille sign
    8249: 'lsaquo',    # single left-pointing angle quotation mark
    8250: 'rsaquo',    # single right-pointing angle quotation mark
    8364: 'euro',      # euro sign
}

g_htmlUniCharEntityPattern = re.compile('[\xa0-\xff]')

def ConvertChar(m):
    return '&' + HTML_CHARACTER_ENTITIES[ord(m.group())] + ';'



def UseHtmlCharEntities(text):
    if type(text) is not UnicodeType:
        text = unicode(text, "utf-8")
    new_text, _ignore_num_subst = re.subn(g_htmlUniCharEntityPattern, ConvertChar, text)
    return new_text
