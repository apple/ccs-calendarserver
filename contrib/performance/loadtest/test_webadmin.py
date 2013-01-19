##
# Copyright (c) 2012-2013 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
##

from twisted.trial.unittest import TestCase
from contrib.performance.loadtest.webadmin import LoadSimAdminResource

class WebAdminTests(TestCase):
    """
    Tests for L{LoadSimAdminResource}.
    """

    class FakeReporter(object):
        
        def generateReport(self, output):
            output.write("FakeReporter")


    class FakeReactor(object):
        
        def __init__(self):
            self.running = True
        
        def stop(self):
            self.running = False


    class FakeLoadSim(object):
        
        def __init__(self):
            self.reactor = WebAdminTests.FakeReactor()
            self.reporter = WebAdminTests.FakeReporter()
            self.running = True
        
        def stop(self):
            self.running = False

    
    class FakeRequest(object):
        
        def __init__(self, **kwargs):
            self.args = kwargs


    def test_resourceGET(self):
        """
        Test render_GET
        """
        
        loadsim = WebAdminTests.FakeLoadSim()
        resource = LoadSimAdminResource(loadsim)
        
        response = resource.render_GET(WebAdminTests.FakeRequest())
        self.assertTrue(response.startswith("<html>"))
        self.assertTrue(response.find(resource.token) != -1)
        
    def test_resourcePOST_Stop(self):
        """
        Test render_POST when Stop button is clicked
        """
        
        loadsim = WebAdminTests.FakeLoadSim()
        resource = LoadSimAdminResource(loadsim)
        self.assertTrue(loadsim.reactor.running)
       
        response = resource.render_POST(WebAdminTests.FakeRequest(
            token=(resource.token,),
            stop=None,
        ))
        self.assertTrue(response.startswith("<html>"))
        self.assertTrue(response.find(resource.token) == -1)
        self.assertTrue(response.find("FakeReporter") != -1)
        self.assertFalse(loadsim.running)
        
    def test_resourcePOST_Stop_BadToken(self):
        """
        Test render_POST when Stop button is clicked but token is wrong
        """
        
        loadsim = WebAdminTests.FakeLoadSim()
        resource = LoadSimAdminResource(loadsim)
        self.assertTrue(loadsim.reactor.running)
       
        response = resource.render_POST(WebAdminTests.FakeRequest(
            token=("xyz",),
            stop=None,
        ))
        self.assertTrue(response.startswith("<html>"))
        self.assertTrue(response.find(resource.token) != -1)
        self.assertTrue(response.find("FakeReporter") == -1)
        self.assertTrue(loadsim.running)
        
    def test_resourcePOST_Results(self):
        """
        Test render_POST when Results button is clicked
        """
        
        loadsim = WebAdminTests.FakeLoadSim()
        resource = LoadSimAdminResource(loadsim)
        self.assertTrue(loadsim.reactor.running)
       
        response = resource.render_POST(WebAdminTests.FakeRequest(
            token=(resource.token,),
            results=None,
        ))
        self.assertTrue(response.startswith("<html>"))
        self.assertTrue(response.find(resource.token) != -1)
        self.assertTrue(response.find("FakeReporter") != -1)
        self.assertTrue(loadsim.running)
        
    def test_resourcePOST_Results_BadToken(self):
        """
        Test render_POST when Results button is clicked and token is wrong
        """
        
        loadsim = WebAdminTests.FakeLoadSim()
        resource = LoadSimAdminResource(loadsim)
        self.assertTrue(loadsim.reactor.running)
       
        response = resource.render_POST(WebAdminTests.FakeRequest(
            token=("xyz",),
            results=None,
        ))
        self.assertTrue(response.startswith("<html>"))
        self.assertTrue(response.find(resource.token) != -1)
        self.assertTrue(response.find("FakeReporter") == -1)
        self.assertTrue(loadsim.running)
