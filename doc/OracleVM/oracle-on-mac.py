
import webbrowser

from pipes import quote as shellquote
from textwrap import wrap, dedent
from os.path import exists, expanduser, join as j
from os import mkdir, symlink
from errno import EEXIST, EISDIR
from zipfile import ZipFile

dlpage = "http://www.oracle.com/technetwork/topics/intel-macsoft-096467.html"

downloads = [
    "instantclient-basic-macos.x64-11.2.0.4.0.zip",
    "instantclient-sdk-macos.x64-11.2.0.4.0.zip",
    "instantclient-sqlplus-macos.x64-11.2.0.4.0.zip",
]

ordir = expanduser("~/.oracle")



def mkdirp(d):
    try:
        mkdir(d)
    except OSError, ose:
        if ose.errno not in (EEXIST, EISDIR):
            pass
mkdirp(ordir)



def downloaded():
    for download in downloads:
        dl = j(expanduser("~/Downloads/OracleDB"), download)
        if exists(dl):
            ZipFile(dl).extractall(ordir)
            continue
        break
    else:
        return True
    return False

import fcntl
import tty
import struct
th, tw, ign, ign = struct.unpack("4H", fcntl.ioctl(0, tty.TIOCGWINSZ, 'x' * 8))

while not downloaded():
    txt = "\n".join(wrap(" ".join("""
 Please sanctify the files, which I cannot automatically download, with your
 consent to abide by their respective license agreements via your web browser,
 then hit 'enter' to continue.  You need:
        """.split()), tw)) + "\n\n" + "\n".join(downloads)
    webbrowser.open(dlpage)
    raw_input(txt)

instantclient = j(ordir, "instantclient_11_2")

# # Oracle is for Professional Software Engineers only.  Don't look for any namby-
# # pamby "user interface" or "working installation process" here!
for pdest in ["libclntsh.dylib.11.2", "libclntsh.dylib.11.1"]:
    pdestfull = j(instantclient, pdest)
    psrcfull = j(instantclient, "libclntsh.dylib")
    if exists(pdestfull) and not exists(psrcfull):
        symlink(pdestfull, psrcfull)
        break

ldestfull = j(instantclient, "lib")
if not exists(ldestfull):
    symlink(".", ldestfull)

with open(expanduser("~/.bash_profile"), "a") as f:
    f.write(dedent(
        """
        function oracle_11 () {
            export ORACLE_HOME="$HOME/.oracle/instantclient_11_2";

            # make sure we can find the client libraries
            export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$ORACLE_HOME";
            export DYLD_LIBRARY_PATH="$DYLD_LIBRARY_PATH:$ORACLE_HOME";
        }
        """))

