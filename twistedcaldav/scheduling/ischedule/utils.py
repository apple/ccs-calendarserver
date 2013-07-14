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
##

from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.names import dns
from twisted.names.authority import BindAuthority
from twisted.names.client import getResolver
from twisted.names.error import DomainError, AuthoritativeDomainError

from twistedcaldav.config import config

import socket

log = Logger()

DebugResolver = None


def getIPsFromHost(host):
    """
    Map a hostname to an IPv4 or IPv6 address.

    @param host: the hostname
    @type host: C{str}

    @return: a C{set} of IPs
    """
    ips = set()
    # Use AF_UNSPEC rather than iterating (socket.AF_INET, socket.AF_INET6)
    # because getaddrinfo() will raise an exception if no match is found for
    # the specified family
    # TODO: potentially use twext.internet.gaiendpoint instead
    results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    for _ignore_family, _ignore_socktype, _ignore_proto, _ignore_canonname, sockaddr in results:
        ips.add(sockaddr[0])

    return ips



@inlineCallbacks
def lookupServerViaSRV(domain, service="_ischedules"):

    # Hard-code disable of SRV lookups in this root only until we decide on a better
    # way to disable this for non-POD iSchedule.
    returnValue(None)

    _initResolver()

    lookup = "%s._tcp.%s" % (service, domain,)
    log.debug("DNS SRV: lookup: %s" % (lookup,))
    try:
        answers = (yield DebugResolver.lookupService(lookup))[0]
    except (DomainError, AuthoritativeDomainError), e:
        log.debug("DNS SRV: lookup failed: %s" % (e,))
        returnValue(None)

    if len(answers) == 1 and answers[0].type == dns.SRV \
                         and answers[0].payload \
                         and answers[0].payload.target == dns.Name('.'):
        # decidedly not available
        log.debug("DNS SRV: disabled: %s" % (lookup,))
        returnValue(None)

    servers = []
    for a in answers:

        if a.type != dns.SRV or not a.payload:
            continue

        servers.append((a.payload.priority, a.payload.weight, str(a.payload.target), a.payload.port))

    log.debug("DNS SRV: lookup results: %s\n%s" % (lookup, servers,))
    if len(servers) == 0:
        returnValue(None)


    def _serverCmp(a, b):
        if a[0] != b[0]:
            return cmp(a[0], b[0])
        else:
            return cmp(a[1], b[1])

    servers.sort(_serverCmp)
    minPriority = servers[0][0]

    weightIndex = zip(xrange(len(servers)), [x[1] for x in servers if x[0] == minPriority])
    weightSum = reduce(lambda x, y: (None, x[1] + y[1]), weightIndex, (None, 0))[1]

    for index, weight in weightIndex:
        weightSum -= weight
        if weightSum <= 0:
            chosen = servers[index]
            _ignore_p, _ignore_w, host, port = chosen
            host = host.rstrip(".")
            break
    else:
        log.debug("DNS SRV: unable to determine best record to use: %s" % (lookup,))
        returnValue(None)

    log.debug("DNS SRV: lookup chosen service: %s %s %s" % (lookup, host, port,))
    returnValue((host, port,))



@inlineCallbacks
def lookupDataViaTXT(domain, prefix=""):

    _initResolver()

    lookup = "%s.%s" % (prefix, domain,) if prefix else domain
    log.debug("DNS TXT: lookup: %s" % (lookup,))
    try:
        answers = (yield DebugResolver.lookupText(lookup))[0]
    except (DomainError, AuthoritativeDomainError), e:
        log.debug("DNS TXT: lookup failed: %s" % (e,))
        answers = ()

    results = []
    for a in answers:

        if a.type != dns.TXT or not a.payload:
            continue

        results.append("".join(a.payload.data))

    log.debug("DNS TXT: lookup results: %s\n%s" % (lookup, "\n".join(results),))
    returnValue(results)



class FakeBindAuthority(BindAuthority):

    @inlineCallbacks
    def _lookup(self, name, cls, type, timeout=None):
        log.debug("DNS FakeBindAuthority: lookup: %s %s %s" % (name, cls, type,))
        result = yield BindAuthority._lookup(self, name, cls, type, timeout)
        log.debug("DNS FakeBindAuthority: lookup results: %s %s %s\n%s" % (name, cls, type, result[0]))
        returnValue(result)


    def stripComments(self, lines):
        """
        Work around a bug in the base implementation that causes parsing of TXT RRs with
        a ; in the RDATA to fail because the ; is treated as the start of a comment. Here
        we simply ignore all comments.
        """
        return [
            (a.find(';') == -1 or "TXT" in a) and a or a[:a.find(';')] for a in [
                b.strip() for b in lines
            ]
        ]


    def parseLines(self, lines):
        """
        Work around a bug in the base implementation that causes parsing of TXT RRs with
        spaces in the RDATA to be broken into multiple fragments and for quotes around the
        data to not be removed.
        """
        for line in lines:
            if line[3] == "TXT":
                line[4] = " ".join(line[4:])[1:-1]
                del line[5:]

        BindAuthority.parseLines(self, lines)



def _initResolver():
    global DebugResolver
    if DebugResolver is None:
        if config.Scheduling.iSchedule.DNSDebug:
            DebugResolver = FakeBindAuthority(config.Scheduling.iSchedule.DNSDebug)
        else:
            DebugResolver = getResolver()
