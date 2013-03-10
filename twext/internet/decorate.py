##
# Copyright (c) 2010-2013 Apple Inc. All rights reserved.
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
Decorators.
"""

__all__ = [
    "memoizedKey",
]


from inspect import getargspec

from twisted.internet.defer import Deferred, succeed

class Memoizable(object):
    """
    A class that stores itself in the memo dictionary.
    """

    def memoMe(self, key, memo):
        """
        Add this object to the memo dictionary in whatever fashion is appropriate.

        @param key: key used for lookup
        @type key: C{object} (typically C{str} or C{int})
        @param memo: the dict to store to
        @type memo: C{dict}
        """
        raise NotImplementedError



def memoizedKey(keyArgument, memoAttribute, deferredResult=True):
    """
    Decorator which memoizes the result of a method on that method's instance. If the instance is derived from
    class Memoizable, then the memoMe method is used to store the result, otherwise it is stored directly in
    the dict.

    @param keyArgument: The name of the "key" argument.
    @type keyArgument: C{str}

    @param memoAttribute: The name of the attribute on the instance which
        should be used for memoizing the result of this method; the attribute
        itself must be a dictionary.  Alternately, if the specified argument is
        callable, it is a callable that takes the arguments passed to the
        decorated method and returns the memo dictionaries.
    @type memoAttribute: C{str} or C{callable}

    @param deferredResult: Whether the result must be a deferred.
    """
    def getarg(argname, argspec, args, kw):
        """
        Get an argument from some arguments.

        @param argname: The name of the argument to retrieve.

        @param argspec: The result of L{inspect.getargspec}.

        @param args: positional arguments passed to the function specified by
            argspec.

        @param kw: keyword arguments passed to the function specified by
            argspec.

        @return: The value of the argument named by 'argname'.
        """
        argnames = argspec[0]
        try:
            argpos = argnames.index(argname)
        except ValueError:
            argpos = None
        if argpos is not None:
            if len(args) > argpos:
                return args[argpos]
        if argname in kw:
            return kw[argname]
        else:
            raise TypeError("could not find key argument %r in %r/%r (%r)" %
                (argname, args, kw, argpos)
            )


    def decorate(thunk):
        # cheater move to try to get the right argspec from inlineCallbacks.
        # This could probably be more robust, but the 'cell_contents' thing
        # probably can't (that's the only real reference to the underlying
        # function).
        if thunk.func_code.co_name == "unwindGenerator":
            specTarget = thunk.func_closure[0].cell_contents
        else:
            specTarget = thunk
        spec = getargspec(specTarget)

        def outer(*a, **kw):
            self = a[0]
            if callable(memoAttribute):
                memo = memoAttribute(*a, **kw)
            else:
                memo = getattr(self, memoAttribute)
            key = getarg(keyArgument, spec, a, kw)
            if key in memo:
                memoed = memo[key]
                if deferredResult:
                    return succeed(memoed)
                else:
                    return memoed
            result = thunk(*a, **kw)

            if isinstance(result, Deferred):
                def memoResult(finalResult):
                    if isinstance(finalResult, Memoizable):
                        finalResult.memoMe(key, memo)
                    elif finalResult is not None:
                        memo[key] = finalResult
                    return finalResult
                result.addCallback(memoResult)
            elif result is not None:
                memo[key] = result
            return result

        return outer

    return decorate
