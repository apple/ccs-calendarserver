##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

"""
loadsim Web Admin UI.
"""

__all__ = [
    "LoadSimAdminResource",
]

import cStringIO as StringIO
import uuid

from twisted.web import resource


class LoadSimAdminResource (resource.Resource):
    """
    Web administration HTTP resource.
    """
    isLeaf = True

    BODY = """<html>
<body>
    <form method="POST">
        <input name="token" type="hidden" value="%s" />
        <input name="results" type="submit" value="Results" />
        <p />
        <input name="stop" type="submit" value="Stop Sim" />
    </form>
</body>
</html>
"""

    BODY_RESULTS = """<html>
<body>
    <form method="POST">
        <input name="token" type="hidden" value="%s" />
        <input name="results" type="submit" value="Results" />
        <p />
        <input name="stop" type="submit" value="Stop Sim" />
    </form>
    <p />
    <pre>%s</pre>
</body>
</html>
"""

    BODY_RESULTS_STOPPED = """<html>
<body>
    <h3>LoadSim Stopped - Final Results</h3>
    <pre>%s</pre>
</body>
</html>
"""

    def __init__(self, loadsim):
        self.loadsim = loadsim
        self.token = str(uuid.uuid4())

    def render_GET(self, request):
        return self.BODY % (self.token,)

    def render_POST(self, request):
        if 'token' not in request.args or request.args['token'][0] != self.token:
            return self.BODY % (self.token,)

        if 'stop' in request.args:
            self.loadsim.stop()
            return self._renderReport(True)
        elif 'results' in request.args:
            return self._renderReport()
        return self.BODY % (self.token,)

    def _renderReport(self, stopped=False):
        report = StringIO.StringIO()
        self.loadsim.reporter.generateReport(report)
        if stopped:
            return self.BODY_RESULTS_STOPPED % (report.getvalue(),)
        else:
            return self.BODY_RESULTS % (self.token, report.getvalue(),)
