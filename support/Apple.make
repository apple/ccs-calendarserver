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
-include /AppleInternal/ServerTools/ServerBuildVariables.xcconfig

ifeq ($(RPCFILES),)
SIPP = /Applications/Server.app/Contents/ServerRoot
else
SIPP = $(SERVER_INSTALL_PATH_PREFIX)
endif
SERVERSETUP = $(SIPP)$(NSSYSTEMDIR)$(NSLIBRARYSUBDIR)/ServerSetup

# Cruft += .develop
# Extra_Environment += PATH="$(SIPP)/usr/bin:$$PATH"
# Extra_Environment += PYTHONPATH="$(CS_PY_LIBS)"

CALDAVDSUBDIR = /caldavd

PYTHON = $(USRBINDIR)/python2.7
CS_VIRTUALENV = $(SIPP)$(NSLOCALDIR)$(NSLIBRARYSUBDIR)/CalendarServer

# CS_SHAREDIR = $(SHAREDIR)$(CALDAVDSUBDIR)
# CS_PY_LIBS = $(CS_SHAREDIR)/lib/python
# CS_LIBEXEC = $(SIPP)$(LIBEXECDIR)$(CALDAVDSUBDIR)
# PY_INSTALL_FLAGS = --root="$(DSTROOT)" --prefix="$(SIPP)" --install-lib="$(CS_PY_LIBS)" --install-scripts="$(CS_LIBEXEC)"
# CS_INSTALL_FLAGS = --install-scripts="$(SIPP)$(USRSBINDIR)" --install-data="$(SIPP)$(ETCDIR)"
# CS_BUILD_EXT_FLAGS = --include-dirs="$(SIPP)/usr/include" --library-dirs="$(SIPP)/usr/lib"

CS_USER  = _calendar
CS_GROUP = _calendar

#
# Build
#

.phony: build install install_source install-ossfiles cache_deps buildit

build:: $(BuildDirectory)/$(Project)

build-no::
	@echo "Building $(Project)...";
	$(_v) cd $(BuildDirectory)/$(Project) && $(Environment) $(PYTHON) setup.py build

install:: install-python
install-python:: build
	@#
	@# Set up a virtual environment in Server.app; we'll install into that.
	@# Use --system-site-packages so that we use the packages provided by the OS.
	@#
	@echo "Creating virtual environment...";
	$(_v) $(RMDIR) "$(DSTROOT)$(CS_VIRTUALENV)";
	$(_v) $(PYTHON) -m virtualenv --system-site-packages "$(DSTROOT)$(CS_VIRTUALENV)";
	@#
	@# Use the pip in the virtual environment to install.
	@# It knows about where things go in the virtual environment.
	@#
	@echo "Installing Python packages...";
	$(_v) "$(DSTROOT)$(CS_VIRTUALENV)/bin/pip" install                       \
        --pre --allow-all-external --no-index                                \
        --find-links="$(Sources)/.develop/pip_downloads"                     \
	    --requirement="$(BuildDirectory)/$(Project)/requirements-apple.txt"  \
	    ;
	@#
	@# Make the virtualenv relocatable
	@#
	@echo "Making virtual environment relocatable...";
	$(PYTHON) -m virtualenv --relocatable "$(DSTROOT)$(CS_VIRTUALENV)";
	@#
	@# Clean up
	@#
	@echo "Cleaning up virtual environment...";
	$(_v) $(FIND) "$(DSTROOT)$(CS_VIRTUALENV)" -type d -name .svn -print0 | xargs -0 rm -rf;
	$(_v) $(FIND) "$(DSTROOT)$(CS_VIRTUALENV)" -type f -name '*.so' -print0 | xargs -0 $(STRIP) -Sx;
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(CS_VIRTUALENV)/etc";
	$(_v) $(INSTALL_FILE) "$(Sources)/conf/caldavd-apple.plist" "$(DSTROOT)$(CS_VIRTUALENV)/etc/caldavd.plist";

install:: install-commands
install-commands::
	@echo "Installing links to executables...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)/usr/bin";
	$(_v) ln -fs "../..$(NSLOCALDIR)$(NSLIBRARYSUBDIR)/CalendarServer/bin/caldavd" "$(DSTROOT)$(SIPP)/usr/sbin";
	$(_v) cd "$(DSTROOT)$(SIPP)/usr/bin/" &&                                                         \
	      for cmd in "../..$(NSLOCALDIR)$(NSLIBRARYSUBDIR)/CalendarServer/bin/calendarserver_"*; do  \
	          ln -fs "$${cmd}" .;                                                                    \
	      done;

install:: install-man
install-man::
	@echo "Installing manual pages...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/caldavd.8"                           "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_command_gateway.8"    "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_export.8"             "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_principals.8"  "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_attachments.8"  "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_events.8"       "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_principals.8"   "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_shell.8"              "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_timezones.8"   "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) gzip -9 -f "$(DSTROOT)$(SIPP)$(MANDIR)/man8/"*.[0-9];

install:: install-launchd
install-launchd::
	@echo "Installing launchd config...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(NSLIBRARYDIR)/LaunchDaemons";
	$(_v) $(INSTALL_FILE) "$(Sources)/contrib/launchd/calendarserver.plist" "$(DSTROOT)$(SIPP)$(NSLIBRARYDIR)/LaunchDaemons/org.calendarserver.calendarserver.plist";

install:: install-changeip
install-changeip::
	@echo "Installing changeip script...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip";
	$(_v) $(INSTALL_SCRIPT) "$(Sources)/calendarserver/tools/changeip_calendar.py" "$(DSTROOT)$(SIPP)$(LIBEXECDIR)/changeip/changeip_calendar";

# install:: install-caldavtester
# install-caldavtester::
# 	@echo "Installing CalDAVTester package...";
# 	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)/AppleInternal/ServerTools";
# 	$(_v) cd "$(DSTROOT)/AppleInternal/ServerTools" && unzip "$(BuildDirectory)/$(Project)/requirements/cache/CalDAVTester-*.zip";

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
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)/$(OSV)";
	$(_v) $(INSTALL_FILE) "$(Sources)/$(ProjectName).plist" "$(DSTROOT)/$(OSV)/$(ProjectName).plist";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)/$(OSL)";
	$(_v) $(INSTALL_FILE) "$(BuildDirectory)/$(Project)/LICENSE" "$(DSTROOT)/$(OSL)/$(ProjectName).txt";

#
# B&I Hooey
#

buildit: cache_deps
	@echo "Running buildit...";
	$(_v) sudo ~rc/bin/buildit $(CC_Archs) "$(Sources)";
