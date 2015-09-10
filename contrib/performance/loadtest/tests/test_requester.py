from twisted.trial.unittest import TestCase

from contrib.performance.loadtest.requester import (
    Requester, IncorrectResponseCode, WebClientContextFactory
)

class _FakeAgent(object):
    def __init__(self):
        self.requests = []
        self.next = None

    def request(self, method, uri, headers=None, bodyProducer=None):
        self.requests.append((method, uri, headers, bodyProducer))

    def setNextResponse(response):


    # {'reactor': <contrib.performance.loadtest.trafficlogger.(Logged Reactor) object at 0x10d1860d0>, 'title': '10.11 Intern', 'self': <contrib.performance.loadtest.requester.Requester object at 0x10d184a10>, 'auth': {'digest': <urllib2.HTTPDigestAuthHandler instance at 0x10d192128>, 'basic': <urllib2.HTTPBasicAuthHandler instance at 0x10d180fc8>}, 'headers': {'Connection': ['keep-alive'], 'Accept-Language': ['en-us'], 'Accept-Encoding': ['gzip,deflate'], 'Accept': ['*/*'], 'User-Agent': ['Mac+OS+X/10.11 (15A216g) CalendarAgent/353']}, 'client_id': 'a11bce96-f787-4096-91a3-44f7dbf38a06', 'root': 'https://127.0.0.1:8443', 'uid': u'user01'}
    

class RequesterTests(TestCase):
    def setUp(self):
        self.root = '/foo/bar/'
        self.headers = Headers({
            'Connection': ['keep-alive'],
            'Accept-Language': ['en-us'],
            'Accept-Encoding': ['gzip,deflate'],
            'Accept': ['*/*'],
            'User-Agent': ['Mac+OS+X/10.11 (15A216g) CalendarAgent/353'
        }
        self.title = 'Requester '

    self,
        root,
        headers,
        title,
        uid,
        client_id,
        auth,
        reactor

    

class IncorrectResponseCodeTests(TestCase):
    pass

class WebClientContextFactoryTests(TestCase):
    pass