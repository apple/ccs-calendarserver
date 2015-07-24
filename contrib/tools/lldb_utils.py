##
# Copyright (c) 2015 Apple Inc. All rights reserved.
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

"""
Below are a bunch of useful functions that can be used inside of lldb to debug a Python
process (this applies to cPython only).

The steps are as follows:

    > lldb
    (lldb) target symbols add <path to Python.framework.dSYM>
    (lldb) script
    >>> <paste in functions>

pybt - generate a python function call backtrace of the currently selected thread
pybtall - generate a python function call backtrace of all threads
"""

import lldb #@UnresolvedImport

def pybt(thread=None):
    if thread is None:
        thread = lldb.thread
    num_frames = thread.GetNumFrames()
    pystring_t = lldb.target.FindFirstType("PyStringObject").GetPointerType()
    for i in range(num_frames - 1):
        fr = thread.GetFrameAtIndex(i)
        if fr.GetFunctionName() == "PyEval_EvalFrameEx":
            fr_next = thread.GetFrameAtIndex(i + 1)
            if fr_next.GetFunctionName() == "PyEval_EvalCodeEx":
                f = fr.GetValueForVariablePath("f")
                filename = f.GetValueForExpressionPath("->f_code->co_filename").Cast(pystring_t).GetValueForExpressionPath("->ob_sval")
                name = f.GetValueForExpressionPath(".f_code->co_name").Cast(pystring_t).GetValueForExpressionPath("->ob_sval")
                print("{} - {}".format(filename.summary, name.summary))



def pybtall():
    numthreads = lldb.process.GetNumThreads()
    for i in range(numthreads):
        thread = lldb.process.GetThreadAtIndex(i)
        print("----- Thread: {} -----".format(i + 1))
        pybt(thread)
