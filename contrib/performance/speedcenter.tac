
from twisted.python.modules import getModule
from twisted.application.service import Application
from twisted.application.internet import TCPServer
from twisted.web.server import Site
from twisted.web.wsgi import WSGIResource
from twisted.internet import reactor

speedcenter = getModule("speedcenter").filePath
django = speedcenter.sibling("wsgi").child("django.wsgi")
namespace = {"__file__": django.path}
execfile(django.path, namespace, namespace)

application = Application("SpeedCenter")
resource = WSGIResource(reactor, reactor.getThreadPool(), namespace["application"])
site = Site(resource, 'httpd.log')
TCPServer(8000, site).setServiceParent(application)
