# -*- mode: Makefile; -*-
##
# B&I Makefile for CalendarServer
#
# This is only useful internally at Apple, probably.
##
# Copyright (c) 2005-2014 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

# Project info
Project	    = CalendarServer
ProjectName = CalendarServer
UserType    = Server
ToolType    = Applications

# Include common makefile targets for B&I
include $(MAKEFILEPATH)/CoreOS/ReleaseControl/Common.make
include /AppleInternal/ServerTools/ServerBuildVariables.xcconfig

SIPP = $(SERVER_INSTALL_PATH_PREFIX)
SERVERSETUP = $(SIPP)$(NSSYSTEMDIR)$(NSLIBRARYSUBDIR)/ServerSetup

Cruft += .dependencies
Extra_Environment += PATH="$(SIPP)/usr/bin:$$PATH"
Extra_Environment += PYTHONPATH="$(PY_TMP_LIB)"

CALDAVDSUBDIR = /caldavd

PYTHON = $(USRBINDIR)/python
PY_HOME = $(SIPP)$(SHAREDIR)$(CALDAVDSUBDIR)
PY_TMP_LIB = $(DSTROOT)$(SIPP)/usr/share/caldavd/lib/python/
PY_INSTALL_FLAGS = --root="$(DSTROOT)" --prefix="$(SIPP)" --install-lib="$(PY_HOME)/lib/python" --install-scripts="$(SIPP)$(LIBEXECDIR)$(CALDAVDSUBDIR)"
CS_INSTALL_FLAGS = --install-scripts="$(SIPP)$(USRSBINDIR)" --install-data="$(SIPP)$(ETCDIR)"
CS_BUILD_EXT_FLAGS = --include-dirs="$(SIPP)/usr/include" --library-dirs="$(SIPP)/usr/lib"

CS_USER  = _calendar
CS_GROUP = _calendar

#
# Build
#

.phony: $(Project) pycalendar twext build setup prep install install-ossfiles buildit

CALDAVTESTER = CalDAVTester
PYKERBEROS   = PyKerberos-9409
PYCALENDAR   = PyCalendar-11947
TWEXT        = twext-12213
PYGRESQL     = PyGreSQL-4.1.1
SQLPARSE     = sqlparse-0.1.2
SETPROCTITLE = setproctitle-1.1.8
PSUTIL       = psutil-1.2.0
PYCRYPTO     = pycrypto-2.6.1
CFFI         = cffi-0.6
PYCPARSER    = pycparser-2.10

$(CALDAVTESTER):: $(BuildDirectory)/$(CALDAVTESTER)
$(PYKERBEROS)::   $(BuildDirectory)/$(PYKERBEROS)
$(PYCALENDAR)::   $(BuildDirectory)/$(PYCALENDAR)
$(TWEXT)::        $(BuildDirectory)/$(TWEXT)
$(PYGRESQL)::     $(BuildDirectory)/$(PYGRESQL)
$(SQLPARSE)::     $(BuildDirectory)/$(SQLPARSE)
$(SETPROCTITLE):: $(BuildDirectory)/$(SETPROCTITLE)
$(PSUTIL)::       $(BuildDirectory)/$(PSUTIL)
$(PYCRYPTO)::	  $(BuildDirectory)/$(PYCRYPTO)
$(CFFI)::	  $(BuildDirectory)/$(CFFI)
$(PYCPARSER)::	  $(BuildDirectory)/$(PYCPARSER)
$(Project)::      $(BuildDirectory)/$(Project)

build:: $(PYKERBEROS) $(PYCALENDAR) $(TWEXT) $(PYGRESQL) $(SQLPARSE) $(SETPROCTITLE) $(PSUTIL) $(PYCRYPTO) $(CFFI) $(PYCPARSER) $(Project)

setup:
	$(_v) ./run -g

prep:: setup $(CALDAVTESTER).tgz $(PYKERBEROS).tgz $(PYCALENDAR).tgz $(TWEXT).tgz $(PYGRESQL).tgz $(SQLPARSE).tgz $(SETPROCTITLE).tgz $(PSUTIL).tgz $(PYCRYPTO).tgz $(CFFI).tgz $(PYCPARSER).tgz

# $(PYKERBEROS) $(PYCALENDAR) $(PYGRESQL) $(SQLPARSE) $(SETPROCTITLE) $(PSUTIL) $(PYCRYPTO) $(CFFI) $(PYCPARSER) $(Project)::
# 	@echo "Building $@..."
# 	$(_v) cd $(BuildDirectory)/$@ && $(Environment) $(PYTHON) setup.py build

install:: build
	$(_v) cd $(BuildDirectory)/$(PYKERBEROS)   && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(PYCALENDAR)   && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(TWEXT)        && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(PYGRESQL)     && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(SQLPARSE)     && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(SETPROCTITLE) && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(PSUTIL)       && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(PYCRYPTO)     && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(PYCPARSER)    && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(CFFI)         && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/$(Project)      && $(Environment) $(PYTHON) setup.py build_ext $(CS_BUILD_EXT_FLAGS) install $(PY_INSTALL_FLAGS) $(CS_INSTALL_FLAGS)
	$(_v) for so in $$(find "$(DSTROOT)$(PY_HOME)/lib" -type f -name '*.so'); do $(STRIP) -Sx "$${so}"; done 
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(ETCDIR)$(CALDAVDSUBDIR)"
	$(_v) $(INSTALL_FILE) "$(Sources)/conf/caldavd-apple.plist" "$(DSTROOT)$(SIPP)$(ETCDIR)$(CALDAVDSUBDIR)/caldavd-apple.plist"
	$(_v) chmod -R ugo+r "$(DSTROOT)$(PY_HOME)"
	$(_v) for f in $$(find "$(DSTROOT)$(SIPP)$(ETCDIR)" -type f ! -name '*.default'); do cp "$${f}" "$${f}.default"; done

install::
	@echo "Installing manual pages..."
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/caldavd.8"                              "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_bootstrap_database.8"    "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_command_gateway.8"       "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_export.8"                "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_principals.8"     "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_migrate_resources.8"     "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_attachments.8"     "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_events.8"          "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_principals.8"      "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_push.8"           "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_shell.8"                 "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_timezones.8"      "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) gzip -9 -f "$(DSTROOT)$(SIPP)$(MANDIR)/man8/"*.[0-9]
	@echo "Installing launchd config..."
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(NSLOCALDIR)/$(NSLIBRARYSUBDIR)/Server/Calendar and Contacts"
	$(_v) $(INSTALL_DIRECTORY) -o "$(CS_USER)" -g "$(CS_GROUP)" -m 0755 "$(DSTROOT)$(VARDIR)/log$(CALDAVDSUBDIR)"
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(NSLIBRARYDIR)/LaunchDaemons"
	$(_v) $(INSTALL_FILE) "$(Sources)/contrib/launchd/calendarserver.plist" "$(DSTROOT)$(SIPP)$(NSLIBRARYDIR)/LaunchDaemons/org.calendarserver.calendarserver.plist"
	@echo "Installing changeip script..."
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip"
	$(_v) $(INSTALL_FILE) "$(Sources)/calendarserver/tools/changeip_calendar.py" "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip/changeip_calendar.py"
	$(_v) chmod ugo+x "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip/changeip_calendar.py"

install::
	@echo "Installing CalDAVTester package..."
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)/AppleInternal/ServerTools"
	$(_v) $(INSTALL_FILE) "$(Sources)/CalDAVTester.tgz" "$(DSTROOT)/AppleInternal/ServerTools/CalDAVTester.tgz"

#
# Automatic Extract
#

$(BuildDirectory)/$(Project):
	@echo "Copying source for $(Project)..."
	$(_v) $(MKDIR) -p "$@"
	$(_v) pax -rw bin conf Makefile lib-patches setup.py calendarserver twistedcaldav txdav txweb2 twisted support "$@/"

$(BuildDirectory)/%: %.tgz
	@echo "Extracting source for $(notdir $<)..."
	$(_v) $(MKDIR) -p "$(BuildDirectory)"
	$(_v) $(RMDIR) "$@"
	$(_v) $(TAR) -C "$(BuildDirectory)" -xzf "$<"

%.tgz: ../%
	@echo "Archiving sources for $(notdir $<)..."
	$(_v) if [ -f "$</setup.py" ] && grep setuptools "$</setup.py" > /dev/null; then \
	        echo "Working around setuptools' stupid need to download a new version."; \
	        cd "$<" && $(Environment) $(PYTHON) "setup.py" --help >/dev/null; \
	      fi
	$(_v) $(TAR) -C "$(dir $<)"        \
	          --exclude=.svn           \
	          --exclude=build          \
	          --exclude=_trial_temp    \
	          --exclude=dropin.cache   \
	          --exclude='*.exe'        \
	          -czf "$@" "$(notdir $<)"

#
# Open Source Hooey
#

OSV = $(USRDIR)/local/OpenSourceVersions
OSL = $(USRDIR)/local/OpenSourceLicenses

#install:: install-ossfiles

install-ossfiles::
	$(_v) $(INSTALL_DIRECTORY) $(DSTROOT)/$(OSV)
	$(_v) $(INSTALL_FILE) $(Sources)/$(ProjectName).plist $(DSTROOT)/$(OSV)/$(ProjectName).plist
	$(_v) $(INSTALL_DIRECTORY) $(DSTROOT)/$(OSL)
	$(_v) $(INSTALL_FILE) $(BuildDirectory)/$(Project)/LICENSE $(DSTROOT)/$(OSL)/$(ProjectName).txt

#
# B&I Hooey
#

buildit: prep
	@echo "Running buildit..."
	$(_v) sudo ~rc/bin/buildit $(CC_Archs) $(Sources)
