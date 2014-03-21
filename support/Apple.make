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

Cruft += .develop
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

.phony: $(Project) prep build install install-ossfiles buildit

$(Project):: $(BuildDirectory)/$(Project)
	@echo "Building $@..."
	$(_v) cd $(BuildDirectory)/$@ && $(Environment) $(PYTHON) setup.py build

build:: $(Project)

install:: build
	$(_v) cd $(BuildDirectory)/$(Project) && \
		$(Environment) $(PYTHON) setup.py \
		build_ext $(CS_BUILD_EXT_FLAGS) \
		install $(PY_INSTALL_FLAGS) $(CS_INSTALL_FLAGS) \
		;
	$(_v) for so in $$(find "$(DSTROOT)$(PY_HOME)/lib" -type f -name '*.so'); do $(STRIP) -Sx "$${so}"; done;
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(ETCDIR)$(CALDAVDSUBDIR)";
	$(_v) $(INSTALL_FILE) "$(Sources)/conf/caldavd-apple.plist" "$(DSTROOT)$(SIPP)$(ETCDIR)$(CALDAVDSUBDIR)/caldavd-apple.plist";
	$(_v) chmod -R ugo+r "$(DSTROOT)$(PY_HOME)";
	$(_v) for f in $$(find "$(DSTROOT)$(SIPP)$(ETCDIR)" -type f ! -name '*.default'); do cp "$${f}" "$${f}.default"; done;

install::
	@echo "Installing manual pages..."
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/caldavd.8"                              "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_command_gateway.8"       "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_export.8"                "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_principals.8"     "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_attachments.8"     "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_events.8"          "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_principals.8"      "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_shell.8"                 "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_timezones.8"      "$(DSTROOT)$(SIPP)$(MANDIR)/man8"
	$(_v) gzip -9 -f "$(DSTROOT)$(SIPP)$(MANDIR)/man8/"*.[0-9]

install::
	@echo "Installing launchd config...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(NSLOCALDIR)/$(NSLIBRARYSUBDIR)/Server/Calendar and Contacts";
	$(_v) $(INSTALL_DIRECTORY) -o "$(CS_USER)" -g "$(CS_GROUP)" -m 0755 "$(DSTROOT)$(VARDIR)/log$(CALDAVDSUBDIR)";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(NSLIBRARYDIR)/LaunchDaemons";
	$(_v) $(INSTALL_FILE) "$(Sources)/contrib/launchd/calendarserver.plist" "$(DSTROOT)$(SIPP)$(NSLIBRARYDIR)/LaunchDaemons/org.calendarserver.calendarserver.plist";

install::
	@echo "Installing changeip script...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip";
	$(_v) $(INSTALL_FILE) "$(Sources)/calendarserver/tools/changeip_calendar.py" "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip/changeip_calendar.py";
	$(_v) chmod ugo+x "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip/changeip_calendar.py";

install::
	@echo "Installing CalDAVTester package...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)/AppleInternal/ServerTools";
	$(_v) cd "$(DSTROOT)/AppleInternal/ServerTools" && unzip "$(BuildDirectory)/$(Project)/requirements/cache/CalDAVTester-*.zip";

#
# Automatic Extract
#

$(BuildDirectory)/$(Project):
	@echo "Copying source for $(Project) to build directory...";
	$(_v) $(MKDIR) -p "$@";
	$(_v) cp -a "$(Sources)/" "$@/";

#
# Open Source Hooey
#

OSV = $(USRDIR)/local/OpenSourceVersions
OSL = $(USRDIR)/local/OpenSourceLicenses

#install:: install-ossfiles

install-ossfiles::
	$(_v) $(INSTALL_DIRECTORY) $(DSTROOT)/$(OSV);
	$(_v) $(INSTALL_FILE) $(Sources)/$(ProjectName).plist $(DSTROOT)/$(OSV)/$(ProjectName).plist;
	$(_v) $(INSTALL_DIRECTORY) $(DSTROOT)/$(OSL);
	$(_v) $(INSTALL_FILE) $(BuildDirectory)/$(Project)/LICENSE $(DSTROOT)/$(OSL)/$(ProjectName).txt;

#
# B&I Hooey
#

buildit:
	@echo "Downloading dependencies...";
	$(_v) ./support/_cache_deps
	@echo "Running buildit...";
	$(_v) sudo ~rc/bin/buildit $(CC_Archs) $(Sources);
