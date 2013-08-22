##
# Copyright (c) 2013 Apple Inc. All rights reserved.
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
Watch the availablity of a file system directory
"""

import os
from zope.interface import Interface
from twisted.internet import reactor
from twisted.python.log import Logger

try:
    from select import (kevent, KQ_FILTER_VNODE, KQ_EV_ADD, KQ_EV_ENABLE,
                        KQ_EV_CLEAR, KQ_NOTE_DELETE, KQ_NOTE_RENAME, KQ_EV_EOF)
    kqueueSupported = True
except ImportError:
    # kqueue not supported on this platform
    kqueueSupported = False


class IDirectoryChangeListenee(Interface):
    """
    A delegate of DirectoryChangeListener
    """

    def disconnected(): #@NoSelf
        """
        The directory has been unmounted
        """

    def deleted(): #@NoSelf
        """
        The directory has been deleted
        """

    def renamed(): #@NoSelf
        """
        The directory has been renamed
        """

    def connectionLost(reason): #@NoSelf
        """
        The file descriptor has been closed
        """


#TODO: better way to tell if reactor is kqueue or not
if kqueueSupported and hasattr(reactor, "_doWriteOrRead"):


    def patchReactor(reactor):
        # Wrap _doWriteOrRead to support KQ_FILTER_VNODE
        origDoWriteOrRead = reactor._doWriteOrRead
        def _doWriteOrReadOrVNodeEvent(selectable, fd, event):
            origDoWriteOrRead(selectable, fd, event)
            if event.filter == KQ_FILTER_VNODE:
                selectable.vnodeEventHappened(event)
        reactor._doWriteOrRead = _doWriteOrReadOrVNodeEvent

    patchReactor(reactor)



    class DirectoryChangeListener(Logger, object):
        """
        Listens for the removal, renaming, or general unavailability of a
        given directory, and lets a delegate listenee know about them.
        """

        def __init__(self, reactor, dirname, listenee):
            """
            @param reactor: the reactor
            @param dirname: the full path to the directory to watch; it must
                already exist
            @param listenee: the delegate to call
            @type listenee: IDirectoryChangeListenee
            """
            self._reactor = reactor
            self._fd = os.open(dirname, os.O_RDONLY)
            self._dirname = dirname
            self._listenee = listenee


        def logPrefix(self):
            return repr(self._dirname)


        def fileno(self):
            return self._fd


        def vnodeEventHappened(self, evt):
            if evt.flags & KQ_EV_EOF:
                self._listenee.disconnected()
            if evt.fflags & KQ_NOTE_DELETE:
                self._listenee.deleted()
            if evt.fflags & KQ_NOTE_RENAME:
                self._listenee.renamed()


        def startListening(self):
            ke = kevent(self._fd, filter=KQ_FILTER_VNODE,
                        flags=(KQ_EV_ADD | KQ_EV_ENABLE | KQ_EV_CLEAR),
                        fflags=KQ_NOTE_DELETE | KQ_NOTE_RENAME)
            self._reactor._kq.control([ke], 0, None)
            self._reactor._selectables[self._fd] = self


        def connectionLost(self, reason):
            os.close(self._fd)
            self._listenee.connectionLost(reason)


else:

    # TODO: implement this for systems without kqueue support:

    class DirectoryChangeListener(Logger, object):
        """
        Listens for the removal, renaming, or general unavailability of a
        given directory, and lets a delegate listenee know about them.
        """

        def __init__(self, reactor, dirname, listenee):
            """
            @param reactor: the reactor
            @param dirname: the full path to the directory to watch
            @param listenee: 
            """
            self._reactor = reactor
            self._fd = os.open(dirname, os.O_RDONLY)
            self._dirname = dirname
            self._listenee = listenee


        def logPrefix(self):
            return repr(self._dirname)


        def fileno(self):
            return self._fd


        def vnodeEventHappened(self, evt):
            pass


        def startListening(self):
            pass


        def connectionLost(self, reason):
            os.close(self._fd)
            self._listenee.connectionLost(reason)

