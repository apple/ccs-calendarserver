##
# Makefile for CalendarServer
##
# Copyright (c) 2005-2006 Apple Computer, Inc. All rights reserved.
#
# This file contains Original Code and/or Modifications of Original Code
# as defined in and that are subject to the Apple Public Source License
# Version 2.0 (the 'License'). You may not use this file except in
# compliance with the License. Please obtain a copy of the License at
# http://www.opensource.apple.com/apsl/ and read it before using this
# file.
# 
# The Original Code and all software distributed under the License are
# distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
# EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
# INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
# Please see the License for the specific language governing rights and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

# Project info
Project	    = CalendarServer
ProjectName = CalendarServer
UserType    = Server
ToolType    = Applications

# Include common makefile targets for B&I
include $(MAKEFILEPATH)/CoreOS/ReleaseControl/Common.make

PYTHON = /usr/bin/python
PY_INSTALL_FLAGS = --root="$(DSTROOT)" --home="$(SHAREDIR)/caldavd"

USER  = 93 # FIXME: calendar
GROUP = 93 # FIXME: calendar

#
# Build
#

.phony: $(Project) vobject Twisted setup prep

PyKerberos::      $(BuildDirectory)/PyKerberos
PyOpenDirectory:: $(BuildDirectory)/PyOpenDirectory
vobject::         $(BuildDirectory)/vobject
Twisted::         $(BuildDirectory)/Twisted
$(Project)::      $(BuildDirectory)/$(Project)

build:: PyKerberos PyOpenDirectory vobject Twisted $(Project)

setup:
	$(_v) $(Sources)/run -s

prep:: setup PyKerberos.tgz PyOpenDirectory.tgz vobject.tgz Twisted.tgz

PyKerberos PyOpenDirectory vobject $(Project)::
	@echo "Building $@..."
	$(_v) cd $(BuildDirectory)/$@ && $(Environment) $(PYTHON) setup.py build

TwistedSubEnvironment = $(Environment) PYTHONPATH="$(DSTROOT)$(SHAREDIR)/caldavd/lib/python"

Twisted::
	@echo "Building Twisted..."
	$(_v) cd $(BuildDirectory)/Twisted && $(Environment) $(PYTHON) twisted/topfiles/setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/Twisted && $(TwistedSubEnvironment) $(PYTHON) twisted/web/topfiles/setup.py build
	$(_v) cd $(BuildDirectory)/Twisted && $(TwistedSubEnvironment) $(PYTHON) twisted/web2/topfiles/setup.py build

install:: build
	$(_v) cd $(BuildDirectory)/$(Project) && $(Environment) $(PYTHON) setup.py install \
	          $(PY_INSTALL_FLAGS)                                                      \
	          --install-scripts="$(USRSBINDIR)"                                        \
	          --install-data="$(ETCDIR)"
	$(_v) cd $(BuildDirectory)/PyKerberos      && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/PyOpenDirectory && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/vobject         && $(Environment) $(PYTHON) setup.py install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/Twisted && $(TwistedSubEnvironment) $(PYTHON) twisted/web/topfiles/setup.py  install $(PY_INSTALL_FLAGS)
	$(_v) cd $(BuildDirectory)/Twisted && $(TwistedSubEnvironment) $(PYTHON) twisted/web2/topfiles/setup.py install $(PY_INSTALL_FLAGS)
	$(_v) for so in $$(find "$(DSTROOT)$(SHAREDIR)/caldavd/lib" -type f -name '*.so'); do $(STRIP) -Sx "$${so}"; done
	$(_v) for f in $$(find "$(DSTROOT)$(ETCDIR)" -type f ! -name '*.default'); do cp "$${f}" "$${f}.default"; done

install::
	$(_v) $(INSTALL_DIRECTORY) $(DSTROOT)$(MANDIR)/man8
	$(_v) $(INSTALL_FILE) $(Sources)/doc/caldavd.8 $(DSTROOT)$(MANDIR)/man8
	$(_v) gzip -9 -f $(DSTROOT)$(MANDIR)/man8/*.8
	$(_v) $(INSTALL_DIRECTORY) $(DSTROOT)$(NSLIBRARYDIR)/$(Project)
	$(_v) $(INSTALL_DIRECTORY) -o $(USER) -g $(GROUP) $(DSTROOT)$(NSLOCALDIR)/$(NSLIBRARYSUBDIR)/$(Project)/Documents
	$(_v) $(INSTALL_DIRECTORY) -o $(USER) -g $(GROUP) $(DSTROOT)$(VARDIR)/log/caldavd
	$(_v) $(INSTALL_DIRECTORY) $(DSTROOT)$(NSLIBRARYDIR)/LaunchDaemons
	$(_v) $(INSTALL_FILE) $(Sources)/conf/launchd.plist $(DSTROOT)$(NSLIBRARYDIR)/LaunchDaemons/org.darwin.calendarserver.plist

#
# Automatic Extract
#

$(BuildDirectory)/$(Project):
	@echo "Copying source for $(Project)..."
	$(_v) $(MKDIR) -p "$@"
	$(_v) pax -rw bin conf Makefile patches setup.py twistedcaldav "$@/"

$(BuildDirectory)/%: %.tgz
	@echo "Extracting source for $(notdir $<)..."
	$(_v) $(MKDIR) -p "$(BuildDirectory)"
	$(_v) $(RMDIR) "$@"
	$(_v) $(TAR) -C "$(BuildDirectory)" -xzf $<

%.tgz: ../%
	@echo "Archiving sources for $(notdir $<)..."
	$(_v) $(TAR) -C "$(dir $<)"        \
	          --exclude=.svn           \
	          --exclude=build          \
	          --exclude=_trial_temp    \
	          --exclude=dropin.cache   \
	          -czf $@ "$(notdir $<)"

#
# Open Source Hooey
#

OSV = /usr/local/OpenSourceVersions
OSL = /usr/local/OpenSourceLicenses

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
