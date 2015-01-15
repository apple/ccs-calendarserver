# -*- mode: Makefile; -*-
##
# B&I Makefile for CalendarServer
#
# This is only useful internally at Apple, probably.
##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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
Extra_Environment += PATH="$(SIPP)/usr/bin:$$PATH"
# Extra_Environment += PYTHONPATH="$(CS_PY_LIBS)"

CALDAVDSUBDIR = /caldavd

PYTHON = $(USRBINDIR)/python2.7
CS_VIRTUALENV = $(SIPP)$(NSLOCALDIR)$(NSLIBRARYSUBDIR)/CalendarServer

CS_USER  = _calendar
CS_GROUP = _calendar

#
# Build
#

.SHELLFLAGS = -euc

.phony: build install install_source install-ossfiles cache_deps buildit

build:: $(BuildDirectory)/$(Project)

build-no::
	@echo "Building $(Project)...";
	$(_v) cd $(BuildDirectory)/$(Project) && $(Environment) $(PYTHON) setup.py build

install:: install-python
install-python:: build
	@#
	@# Install virtualenv someplace and put it in PYTHONPATH in case it's not
	@# on the host system.
	@#
	@echo "Installing virtualenv and friends...";
	$(_v) mkdir -p "$(BuildDirectory)/pytools";
	$(_v) mkdir -p "$(BuildDirectory)/pytools/lib";
	$(_v) mkdir -p "$(BuildDirectory)/pytools/junk";
	$(_v) for pkg in $$(find "$(Sources)/.develop/tools" -type f -name "*.tgz"); do \
	          tar -C "$(BuildDirectory)" -xvzf "$${pkg}";                           \
	          cd "$(BuildDirectory)/$$(basename "$${pkg}" .tgz)" &&                 \
	              PYTHONPATH="$(BuildDirectory)/pytools/lib"                        \
	              "$(PYTHON)" setup.py install                                      \
	                  --install-base="$(BuildDirectory)/pytools"                    \
	                  --install-lib="$(BuildDirectory)/pytools/lib"                 \
	                  --install-headers="$(BuildDirectory)/pytools/junk"            \
	                  --install-scripts="$(BuildDirectory)/pytools/junk"            \
	                  --install-data="$(BuildDirectory)/pytools/junk"               \
	                  ;                                                             \
	      done;
	@#
	@# Set up a virtual environment in Server.app; we'll install into that.
	@# Use --system-site-packages so that we use the packages provided by the OS.
	@#
	@echo "Creating virtual environment...";
	$(_v) $(RMDIR) "$(DSTROOT)$(CS_VIRTUALENV)";
	$(_v) PYTHONPATH="$(BuildDirectory)/pytools/lib" \
	          "$(PYTHON)" -m virtualenv              \
		          --system-site-packages             \
		          --always-copy                      \
		          "$(DSTROOT)$(CS_VIRTUALENV)";
	@#
	@# Use the pip in the virtual environment to install.
	@# It knows about where things go in the virtual environment.
	@#
	@echo "Installing Python packages...";
	@# $(_v) for pkg in $$(find "$(Sources)/.develop/pip_downloads" -type f); do \
	@#           $(Environment)                                                  \
	@#               "$(DSTROOT)$(CS_VIRTUALENV)/bin/pip" install                \
	@#                   --pre --allow-all-external --no-index --no-deps         \
	@#                   --log=$(OBJROOT)/pip.log                                \
	@#                   "$${pkg}" || exit 1;                                    \
	@#       done;
	$(_v) for pkg in $$(find "$(Sources)/.develop/pip_downloads" -type f); do \
	          $(Environment)                                                  \
	              "$(DSTROOT)$(CS_VIRTUALENV)/bin/pip" install                \
	                  --pre --allow-all-external --no-index                   \
	                  --find-links="file://$(Sources)/.develop/pip_downloads" \
	                  --log=$(OBJROOT)/pip.log                                \
	                  "$${pkg}" || exit 1;                                    \
	      done;
	@#
	@# Make the virtualenv relocatable
	@#
	@echo "Making virtual environment relocatable...";
	PYTHONPATH="$(BuildDirectory)/pytools/lib" \
	    $(PYTHON) -m virtualenv --relocatable "$(DSTROOT)$(CS_VIRTUALENV)";
	@#
	@# Clean up
	@#
	@echo "Tweaking caldavd to set PYTHON...";
	$(_v) perl -i -pe "s|#PATH|export PYTHON=$(CS_VIRTUALENV)/bin/python;|" "$(DSTROOT)$(CS_VIRTUALENV)/bin/caldavd";
	@echo "Stripping binaries...";
	$(_v) find "$(DSTROOT)$(CS_VIRTUALENV)" -type f -name "*.so" -print0 | xargs -0 $(STRIP) -Sx;
	@echo "Putting comments into empty files...";
	$(_v) find "$(DSTROOT)$(CS_VIRTUALENV)" -type f -size 0 -name "*.py" -exec sh -c 'printf "# empty\n" > {}' ";";
	$(_v) find "$(DSTROOT)$(CS_VIRTUALENV)" -type f -size 0 -name "*.h" -exec sh -c 'printf "/* empty */\n" > {}' ";";
	@# @echo "Replacing symbolic links...";
	@# $(_v) find "$(DSTROOT)$(CS_VIRTUALENV)" -type l |                       \
	@#           while read link; do                                           \
	@#               target="$$(readlink "$${link}")";                         \
	@#               if [ "$$(echo $${target} | cut -f 1 -d /)" == "" ]; then  \
	@#                   rm -fv "$${link}";                                    \
	@#                   cp -aLfv "$${target}" "$${link}" || {                 \
	@#                       rm -rfv "$${link}";                               \
	@#                       ln -sfv "$${target}" "$${link}";                  \
	@#                   }                                                     \
	@#               fi;                                                       \
	@#           done;

install:: install-config
install-config::
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(ETCDIR)$(CALDAVDSUBDIR)";
	$(_v) $(INSTALL_FILE) "$(Sources)/conf/caldavd-apple.plist" "$(DSTROOT)$(SIPP)$(ETCDIR)$(CALDAVDSUBDIR)/caldavd-apple.plist";

# install:: install-logdir-omg-hack-ew
# install-logdir-omg-hack-ew::
# 	$(_v) $(INSTALL_DIRECTORY) -o "$(CS_USER)" -g "$(CS_GROUP)" -m 0755 "$(DSTROOT)$(VARDIR)/log$(CALDAVDSUBDIR)";

install:: install-commands
install-commands::
	@echo "Installing links to executables...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)/usr/sbin";
	$(_v) ln -fs "../..$(NSLOCALDIR)$(NSLIBRARYSUBDIR)/CalendarServer/bin/caldavd" "$(DSTROOT)$(SIPP)/usr/sbin/caldavd";
	$(_v) for cmd in                                                                                                         \
	          caldavd                                                                                                        \
	          calendarserver_config                                                                                          \
	          calendarserver_command_gateway                                                                                 \
	          calendarserver_diagnose                                                                                        \
	          calendarserver_export                                                                                          \
	          calendarserver_import                                                                                          \
	          calendarserver_manage_principals                                                                               \
	          calendarserver_purge_attachments                                                                               \
	          calendarserver_purge_events                                                                                    \
	          calendarserver_purge_principals                                                                                \
	      ; do                                                                                                               \
	          ln -fs "../..$(NSLOCALDIR)$(NSLIBRARYSUBDIR)/CalendarServer/bin/$${cmd}" "$(DSTROOT)$(SIPP)/usr/sbin/$${cmd}"; \
	      done;

install:: install-man
install-man::
	@echo "Installing manual pages...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/caldavd.8"                          "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_command_gateway.8"   "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_export.8"            "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_manage_principals.8" "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_attachments.8" "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_events.8"      "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
	$(_v) $(INSTALL_FILE) "$(Sources)/doc/calendarserver_purge_principals.8"  "$(DSTROOT)$(SIPP)$(MANDIR)/man8";
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

install:: install-caldavtester
install-caldavtester::
	@echo "Installing CalDAVTester package...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)/AppleInternal/ServerTools";
	$(_v) tar -C "$(DSTROOT)/AppleInternal/ServerTools" -xvzf "$(Sources)/CalDAVTester.tgz";

install:: install-caldavsim
install-caldavsim::
	@echo "Installing caldavsim...";
	$(_v) $(INSTALL_DIRECTORY) "$(DSTROOT)/AppleInternal/ServerTools";
	$(_v) cp -a "$(Sources)/contrib/performance/" "$(DSTROOT)/AppleInternal/ServerTools/CalDAVSim/";

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
