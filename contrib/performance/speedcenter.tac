##
# Copyright (c) 2010 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

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
