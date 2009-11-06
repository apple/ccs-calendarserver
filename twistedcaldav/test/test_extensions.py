
from xml.etree.cElementTree import XML# , tostring

from twisted.trial.unittest import TestCase

from twisted.internet.defer import inlineCallbacks
from twisted.python.filepath import FilePath

from twisted.web.microdom import parseString

from twistedcaldav.extensions import DAVFile

class SimpleFakeRequest(object):
    """
    Emulate a very small portion of the web2 'Request' API, just enough to
    render a L{DAVFile}.

    @ivar path: the path portion of the URL being rendered.
    """

    def __init__(self, path):
        self.path = path


    def urlForResource(self, resource):
        """
        @return: this L{SimpleFakeRequest}'s 'path' attribute, since this
            request can render only one thing.
        """
        return self.path



def browserHTML2ETree(htmlString):
    """
    Loosely interpret an HTML string as XML and return an ElementTree object for it.
    
    We're not promising strict XML (in fact, we're specifically saying HTML) in
    the content-type of certain responses, but it's much easier to work with
    the ElementTree data structures present in Python 2.5+ for testing; so
    we'll use Twisted's built-in facilities to sanitize the inputs before
    making any structured assertions about them.

    A more precise implementation would use
    U{HTML5Lib<http://code.google.com/p/html5lib/wiki/UserDocumentation>}'s
    etree bindings to do the parsing, as that is more directly 'what a browser
    would do', but Twisted's built-in stuff is a good approximation and doesn't
    drag in another dependency.

    @param htmlString: a L{str}, encoded in UTF-8, representing a pile of
        browser-friendly HTML tag soup.

    @return: an object implementing the standard library ElementTree interface.
    """
    return XML(parseString(htmlString, beExtremelyLenient=True).toxml().decode("utf-8"))



class DirectoryListingTest(TestCase):
    """
    Test cases for HTML directory listing.
    """

    @inlineCallbacks
    def doDirectoryTest(self, expectedNames):
        """
        Do a test of a L{DAVFile} pointed at a directory, verifying that files
        existing with the given names will be faithfully 'played back' via HTML
        rendering.
        """
        fp = FilePath(self.mktemp())
        fp.createDirectory()
        for sampleName in expectedNames:
            fp.child(sampleName).touch()
        df = DAVFile(fp)
        responseXML = browserHTML2ETree(
            (yield df.render(SimpleFakeRequest('/'))).stream.read()
        )
        names = set([element.text for element in responseXML.findall(".//a")])
        self.assertEquals(set(expectedNames), names)


    def test_simpleList(self):
        """
        Rendering a L{DAVFile} that is backed by a directory will produce an
        HTML document including links to its contents.
        """
        return self.doDirectoryTest(['gamma.txt', 'beta.html', 'alpha.xml'])


    def test_emptyList(self):
        """
        Listing a directory with no files in it will produce an index with no
        links.
        """
        return self.doDirectoryTest([])
        
