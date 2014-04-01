##
# Copyright (c) 2014 Apple Inc. All rights reserved.
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
from src.manager import manager
from src.observers.base import BaseResultsObserver


class Observer(BaseResultsObserver):
    """
    A results observer that prints results to standard output.
    """

    RESULT_STRINGS = {
        manager.RESULT_OK: "[OK]",
        manager.RESULT_FAILED: "[FAILED]",
        manager.RESULT_ERROR: "[ERROR]",
        manager.RESULT_IGNORED: "[IGNORED]",
    }

    _print_details = False

    def __init__(self, manager):
        super(Observer, self).__init__(manager)
        self.loggedFailures = []
        self.currentFile = None
        self.currentSuite = None


    def updateCalls(self):
        super(Observer, self).updateCalls()
        self._calls.update({
            "start": self.start,
            "testFile": self.testFile,
            "testSuite": self.testSuite,
            "testResult": self.testResult,
            "finish": self.finish,
        })


    def start(self):
        self.manager.logit("Starting tests")
        if self.manager.randomSeed is not None:
            self.manager.logit("Randomizing order using seed '{}'".format(self.manager.randomSeed))


    def testFile(self, result):
        self.currentFile = result["name"].replace("/", ".")[:-4]
        self.manager.logit("")
        self._logResult(self.currentFile, result)
        if result["result"] in (manager.RESULT_FAILED, manager.RESULT_ERROR):
            failtxt = "{result}\n{details}\n\n{file}".format(
                result=self.RESULT_STRINGS[result["result"]],
                details=result["details"],
                file=self.currentFile,
            )
            self.loggedFailures.append(failtxt)


    def testSuite(self, result):
        self.currentSuite = result["name"]
        result_name = "  Suite: " + result["name"]
        self._logResult(result_name, result)
        if result["result"] in (manager.RESULT_FAILED, manager.RESULT_ERROR):
            failtxt = "{result}\n{details}\n\n{file}/{suite}".format(
                result=self.RESULT_STRINGS[result["result"]],
                details=result["details"],
                file=self.currentFile,
                suite=self.currentSuite,
            )
            self.loggedFailures.append(failtxt)


    def testResult(self, result):
        result_name = "    Test: " + result["name"]
        self._logResult(result_name, result)
        if result["result"] in (manager.RESULT_FAILED, manager.RESULT_ERROR):
            failtxt = "{result}\n{details}\n\n{file}/{suite}/{test}".format(
                result=self.RESULT_STRINGS[result["result"]],
                details=result["details"],
                file=self.currentFile,
                suite=self.currentSuite,
                test=result["name"],
            )
            self.loggedFailures.append(failtxt)


    def _logResult(self, name, result):
        if result["result"] is not None:
            result_value = self.RESULT_STRINGS[result["result"]]
            self.manager.logit("{name:<60}{value:>10}".format(name=name, value=result_value))
        else:
            self.manager.logit("{name:<60}".format(name=name))
        if self._print_details and result["details"]:
            self.manager.logit(result["details"])


    def finish(self):
        self.manager.logit("")
        if self.manager.totals[manager.RESULT_FAILED] + self.manager.totals[manager.RESULT_ERROR] != 0:
            for failed in self.loggedFailures:
                self.manager.logit("=" * 70)
                self.manager.logit(failed)
            overall = "FAILED (ok={}, ignored={}, failed={}, errors={})".format(
                self.manager.totals[manager.RESULT_OK],
                self.manager.totals[manager.RESULT_IGNORED],
                self.manager.totals[manager.RESULT_FAILED],
                self.manager.totals[manager.RESULT_ERROR],
            )
        else:
            overall = "PASSED (ok={}, ignored={})".format(
                self.manager.totals[manager.RESULT_OK],
                self.manager.totals[manager.RESULT_IGNORED],
            )
        self.manager.logit("-" * 70)
        self.manager.logit("Ran {total} tests in {time:.3f}s\n".format(
            total=sum(self.manager.totals.values()),
            time=self.manager.timeDiff,
        ))

        self.manager.logit(overall)
