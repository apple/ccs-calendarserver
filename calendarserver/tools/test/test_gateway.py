##
# Copyright (c) 2005-2010 Apple Inc. All rights reserved.
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
##

import os
import plistlib
import xml

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twisted.internet.error import ProcessDone
from twisted.internet.protocol import ProcessProtocol

from twistedcaldav.config import config
from twistedcaldav.test.util import TestCase
from calendarserver.tools.util import getDirectory
from twisted.python.filepath import FilePath
from twistedcaldav.directory.directory import DirectoryError

class ErrorOutput(Exception):
    """
    The process produced some error output and exited with a non-zero exit
    code.
    """


class CapturingProcessProtocol(ProcessProtocol):
    """
    A L{ProcessProtocol} that captures its output and error.

    @ivar output: a C{list} of all C{str}s received to stderr.

    @ivar error: a C{list} of all C{str}s received to stderr.
    """

    def __init__(self, deferred, inputData):
        """
        Initialize a L{CapturingProcessProtocol}.

        @param deferred: the L{Deferred} to fire when the process is complete.

        @param inputData: a C{str} to feed to the subprocess's stdin.
        """
        self.deferred = deferred
        self.input = inputData
        self.output = []
        self.error = []


    def connectionMade(self):
        """
        The process started; feed its input on stdin.
        """
        self.transport.write(self.input)
        self.transport.closeStdin()


    def outReceived(self, data):
        """
        Some output was received on stdout.
        """
        self.output.append(data)


    def errReceived(self, data):
        """
        Some output was received on stderr.
        """
        self.error.append(data)
        # Attempt to exit promptly if a traceback is displayed, so we don't
        # deal with timeouts.
        lines = ''.join(self.error).split("\n")
        if len(lines) > 1:
            errorReportLine = lines[-2].split(": ", 1)
            if len(errorReportLine) == 2 and ' ' not in errorReportLine[0] and '\t' not in errorReportLine[0]:
                self.transport.signalProcess("TERM")


    def processEnded(self, why):
        """
        The process is over, fire the Deferred with the output.
        """
        if why.check(ProcessDone) and not self.error:
            self.deferred.callback(''.join(self.output))
        else:
            self.deferred.errback(ErrorOutput(''.join(self.error)))


class GatewayTestCase(TestCase):

    def setUp(self):
        testRoot = os.path.join(os.path.dirname(__file__), "gateway")
        templateName = os.path.join(testRoot, "caldavd.plist")
        templateFile = open(templateName)
        template = templateFile.read()
        templateFile.close()

        tmpDir = FilePath(self.mktemp())
        tmpDir.makedirs()
        dataRoot = tmpDir.child("data")
        dataRoot.makedirs()
        docRoot = tmpDir.child("documents")
        docRoot.makedirs()

        # Copy xml files to a temp directory because they may get modified

        origUsersFile = FilePath(os.path.join(os.path.dirname(__file__),
            "gateway", "users-groups.xml"))
        copyUsersFile = tmpDir.child("users-groups.xml")
        origUsersFile.copyTo(copyUsersFile)

        origResourcesFile = FilePath(os.path.join(os.path.dirname(__file__),
            "gateway", "resources-locations.xml"))
        copyResourcesFile = tmpDir.child("resources-locations.xml")
        origResourcesFile.copyTo(copyResourcesFile)

        origAugmentFile = FilePath(os.path.join(os.path.dirname(__file__),
            "gateway", "augments.xml"))
        copyAugmentFile = tmpDir.child("augments.xml")
        origAugmentFile.copyTo(copyAugmentFile)

        proxyFile = tmpDir.child("proxies.sqlite")

        newConfig = template % {
            'DataRoot' : dataRoot.path,
            'DocumentRoot' : docRoot.path,
            'DirectoryXMLFile' : copyUsersFile.path,
            'ResourceXMLFile' : copyResourcesFile.path,
            'AugmentXMLFile' : copyAugmentFile.path,
            'ProxyDBFile' : proxyFile.path,
        }
        configFilePath = tmpDir.child("caldavd.plist")
        configFilePath.setContent(newConfig)

        self.configFileName = configFilePath.path
        config.load(self.configFileName)

        super(GatewayTestCase, self).setUp()

        # Make sure trial puts the reactor in the right state, by letting it
        # run one reactor iteration.  (Ignore me, please.)
        d = Deferred()
        reactor.callLater(0, d.callback, True)
        return d

    @inlineCallbacks
    def runCommand(self, command):
        """
        Run the given command by feeding it as standard input to
        calendarserver_command_gateway in a subprocess.
        """
        sourceRoot = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        python = os.path.join(sourceRoot, "python")
        gateway = os.path.join(sourceRoot, "bin", "calendarserver_command_gateway")

        args = [python, gateway, "-f", self.configFileName]
        cwd = sourceRoot

        deferred = Deferred()
        reactor.spawnProcess(CapturingProcessProtocol(deferred, command), python, args, env=os.environ, path=cwd)
        output = yield deferred
        try:
            plist = plistlib.readPlistFromString(output)
        except xml.parsers.expat.ExpatError, e:
            print "Error (%s) parsing (%s)" % (e, output)
            raise

        returnValue(plist)

    @inlineCallbacks
    def test_getLocationList(self):
        results = yield self.runCommand(command_getLocationList)
        self.assertEquals(len(results['result']), 10)

    @inlineCallbacks
    def test_getResourceList(self):
        results = yield self.runCommand(command_getResourceList)
        self.assertEquals(len(results['result']), 10)

    @inlineCallbacks
    def test_createLocation(self):
        directory = getDirectory()

        record = directory.recordWithUID("createdlocation01")
        self.assertEquals(record, None)

        yield self.runCommand(command_createLocation)

        directory.flushCaches()
        record = directory.recordWithUID("createdlocation01")
        self.assertNotEquals(record, None)

    @inlineCallbacks
    def test_destroyRecord(self):
        directory = getDirectory()

        record = directory.recordWithUID("location01")
        self.assertNotEquals(record, None)

        yield self.runCommand(command_deleteLocation)

        directory.flushCaches()
        record = directory.recordWithUID("location01")
        self.assertEquals(record, None)

    @inlineCallbacks
    def test_addWriteProxy(self):
        directory = getDirectory()

        results = yield self.runCommand(command_addWriteProxy)
        self.assertEquals(len(results['result']['Proxies']), 1)

    @inlineCallbacks
    def test_removeWriteProxy(self):
        directory = getDirectory()

        results = yield self.runCommand(command_addWriteProxy)
        results = yield self.runCommand(command_removeWriteProxy)
        self.assertEquals(len(results['result']['Proxies']), 0)



command_deleteLocation = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>deleteLocation</string>
        <key>GeneratedUID</key>
        <string>guidoffice3</string>
</dict>
</plist>
"""

command_addReadProxy = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>addReadProxy</string>
        <key>Principal</key>
        <string>locations:location01</string>
        <key>Proxy</key>
        <string>users:user03</string>
</dict>
</plist>
"""

command_addWriteProxy = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>addWriteProxy</string>
        <key>Principal</key>
        <string>locations:location01</string>
        <key>Proxy</key>
        <string>users:user01</string>
</dict>
</plist>
"""

command_createLocation = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>createLocation</string>
        <key>AutoSchedule</key>
        <true/>
        <key>GeneratedUID</key>
        <string>createdlocation01</string>
        <key>RealName</key>
        <string>Created Location 01</string>
        <key>RecordName</key>
        <array>
                <string>createdlocation01</string>
        </array>
</dict>
</plist>
"""

command_createResource = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>createResource</string>
        <key>AutoSchedule</key>
        <true/>
        <key>GeneratedUID</key>
        <string>guidlaptop1</string>
        <key>RealName</key>
        <string>Laptop 1</string>
        <key>RecordName</key>
        <array>
                <string>laptop1</string>
        </array>
</dict>
</plist>
"""

command_deleteLocation = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>deleteLocation</string>
        <key>GeneratedUID</key>
        <string>location01</string>
</dict>
</plist>
"""

command_deleteResource = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>deleteResource</string>
        <key>GeneratedUID</key>
        <string>guidlaptop1</string>
</dict>
</plist>
"""

command_getLocationList = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>getLocationList</string>
</dict>
</plist>
"""

command_getResourceList = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>getResourceList</string>
</dict>
</plist>
"""

command_listReadProxies = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>listReadProxies</string>
        <key>Principal</key>
        <string>locations:location01</string>
</dict>
</plist>
"""

command_listWriteProxies = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>listWriteProxies</string>
        <key>Principal</key>
        <string>locations:location01</string>
</dict>
</plist>
"""

command_removeReadProxy = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>removeReadProxy</string>
        <key>Principal</key>
        <string>locations:location01</string>
        <key>Proxy</key>
        <string>users:user03</string>
</dict>
</plist>
"""

command_removeWriteProxy = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>command</key>
        <string>removeWriteProxy</string>
        <key>Principal</key>
        <string>locations:location01</string>
        <key>Proxy</key>
        <string>users:user01</string>
</dict>
</plist>
"""
