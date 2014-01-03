##
# Copyright (c) 2012-2014 Apple Inc. All rights reserved.
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

from time import clock
from twisted.web import resource


class LoadSimAdminResource (resource.Resource):
    """
    Web administration HTTP resource.
    """
    isLeaf = True

    HEAD = """\
<html>
<head>
<style type="text/css">
body {color:#000000;}
h1 h2 h3 {color:#333333;}
td {text-align: center; padding: 5px;}
pre.light {color:#CCCCCC; font-size:12px;}
table.rounded-corners {
    border: 1px solid #000000; background-color:#cccccc;
    -moz-border-radius: 5px;
    -webkit-border-radius: 5px;
    -khtml-border-radius: 5px;
    border-radius: 5px;
}
</style>
</head>
<body>
    <h1>Load Simulator Web Admin</h1>
    <form method="POST">
        <input name="token" type="hidden" value="%s" />
        <table class="rounded-corners">
        <tr><td><input name="results" type="submit" value="Refresh" /></td></tr>
        <tr><td><input name="stop" type="submit" value="Stop Sim" /></td></tr>
        </table>
    </form>
"""

    BODY = """\
</body>
</html>
"""

    BODY_RESULTS = """\
<pre>%s</pre><pre class="light">Generated in %.1f milliseconds</pre>
</body>
</html>
"""

    BODY_RESULTS_STOPPED = "<h3>LoadSim Stopped - Final Results</h3>" + BODY_RESULTS

    def __init__(self, loadsim):
        self.loadsim = loadsim
        self.token = str(uuid.uuid4())


    def render_GET(self, request):
        return self._renderReport()


    def render_POST(self, request):
        html = self.HEAD + self.BODY
        if 'token' not in request.args or request.args['token'][0] != self.token:
            return html % (self.token,)

        if 'stop' in request.args:
            self.loadsim.stop()
            return self._renderReport(True)
        elif 'results' in request.args:
            return self._renderReport()
        return html % (self.token,)


    def _renderReport(self, stopped=False):
        report = StringIO.StringIO()
        before = clock()
        self.loadsim.reporter.generateReport(report)
        after = clock()
        ms = (after - before) * 1000
        if stopped:
            html = self.HEAD + self.BODY_RESULTS_STOPPED
            return html % (None, report.getvalue(), ms)
        else:
            html = self.HEAD + self.BODY_RESULTS
            return html % (self.token, report.getvalue(), ms)
