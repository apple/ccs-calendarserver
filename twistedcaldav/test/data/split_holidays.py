#!/usr/bin/env python2.4

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

#
# Splits up the monolithic .Mac holidays calendar into a separate calendar
# for each subcomponent therein.
# These split-up calendars are useable as CalDAV resources.
#

import os

from twistedcaldav.ical import Component

monolithic_filename = os.path.join(os.path.dirname(__file__), "Holidays.ics")

calendar = Component.fromStream(file(monolithic_filename))

assert calendar.name() == "VCALENDAR"

for subcomponent in calendar.subcomponents():
    subcalendar = Component("VCALENDAR")

    #
    # Add top-level properties from monolithic calendar to top-level properties
    # of subcomponent calendar.
    #
    for property in calendar.properties():
        subcalendar.addProperty(property)

    subcalendar.addComponent(subcomponent)

    uid = subcalendar.resourceUID()
    subcalendar_filename = os.path.join(os.path.dirname(__file__), "Holidays", uid + ".ics")

    print "Writing %s" % (subcalendar_filename,)

    subcalendar_file = file(subcalendar_filename, "w")
    try:
        subcalendar_file.write(str(subcalendar))
    finally:
        subcalendar_file.close()
