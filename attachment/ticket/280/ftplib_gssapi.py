##
# Copyright (c) 2008 Jelmer Vernooij <jelmer@samba.org>
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

"""Support for secure authentication using GSSAPI over FTP.

See RFC2228 for details.
"""

from ftplib import *

import base64, ftplib, getpass, kerberos, socket, sys


class SecureFtp(FTP):
    """Extended version of ftplib.FTP that can authenticate using GSSAPI."""
    def mic_putcmd(self, line):
        rc = kerberos.authGSSClientWrap(self.vc, base64.b64encode(line))
        wrapped = kerberos.authGSSClientResponse(self.vc)
        FTP.putcmd(self, "MIC " + wrapped)

    def mic_getline(self):
        resp = FTP.getline(self)
        assert resp[:4] == '631 '
        rc = kerberos.authGSSClientUnwrap(self.vc, resp[4:].strip("\r\n"))
        response = base64.b64decode(kerberos.authGSSClientResponse(self.vc))
        return response

    def gssapi_login(self, user):
        # Try GSSAPI login first
        resp = self.sendcmd('AUTH GSSAPI')
        if resp[:3] == '334':
            rc, self.vc = kerberos.authGSSClientInit("ftp@%s" % self.host)

            if kerberos.authGSSClientStep(self.vc, "") != 1:
                while resp[:3] in ('334', '335'):
                    authdata = kerberos.authGSSClientResponse(self.vc)
                    resp = self.sendcmd('ADAT ' + authdata)
                    if resp[:9] in ('235 ADAT=', '335 ADAT='):
                        rc = kerberos.authGSSClientStep(self.vc, resp[9:])
                        assert ((resp[:3] == '235' and rc == 1) or 
                                (resp[:3] == '335' and rc == 0))
            print "Authenticated as %s" % kerberos.authGSSClientUserName(self.vc)

            # Monkey patch ftplib
            self.putcmd = self.mic_putcmd
            self.getline = self.mic_getline

            self.sendcmd('USER ' + user)
            return resp


def test():
    '''Test program.
    Usage: ftp [-d] [-u[user]] [-r[file]] host [-l[dir]] [-d[dir]] [-p] [file] ...

    -d dir
    -l list
    -u user
    '''
    from getopt import getopt

    if len(sys.argv) < 2:
        print test.__doc__
        sys.exit(0)

    (opts, args) = getopt(sys.argv[1:], "d:u:r:")

    debugging = 0
    rcfile = None
    userid = None

    for (k, v) in opts:
        if k == "-d":
            debugging += 1
        elif k == "-u":
            userid = v
        elif k == "-r":
            rcfile = v

    host = args[0]
    ftp = SecureFtp(host)
    ftp.set_debuglevel(debugging)
    passwd = acct = ''
    try:
        netrc = Netrc(rcfile)
    except IOError:
        if rcfile is not None and userid is None:
            sys.stderr.write("Could not open account file"
                             " -- using anonymous login.")
            userid = ''
    else:
        if userid is None:
            try:
                userid, passwd, acct = netrc.get_account(host)
            except KeyError:
                # no account for host
                sys.stderr.write(
                        "No account -- using anonymous login.")
                userid = ''
    try:
        if userid:
            ftp.gssapi_login(userid)
        else:
            ftp.login(userid, passwd, acct)
    except ftplib.error_perm, e:
        # Fall back to regular authentication
        ftp.login(userid, passwd, acct)
    for file in args[1:]:
        if file[:2] == '-l':
            ftp.dir(file[2:])
        elif file[:2] == '-d':
            cmd = 'CWD'
            if file[2:]: cmd = cmd + ' ' + file[2:]
            resp = ftp.sendcmd(cmd)
        elif file == '-p':
            ftp.set_pasv(not ftp.passiveserver)
        else:
            ftp.retrbinary('RETR ' + file, \
                           sys.stdout.write, 1024)
    ftp.quit()


if __name__ == '__main__':
    test()
