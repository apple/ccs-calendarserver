##
# Copyright (c) 2009-2015 Apple Inc. All rights reserved.
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

from twistedcaldav.ical import Component as iComponent
from twistedcaldav.vcard import Component as vComponent

__all__ = [
    "CalendarFilter",
    "AddressFilter",
]

class CalendarFilter(object):
    """
    Abstract class that defines an iCalendar filter/merge object
    """

    def __init__(self):
        pass


    def filter(self, ical):
        """
        Filter the supplied iCalendar object using the request information.

        @param ical: iCalendar object
        @type ical: L{Component}

        @return: L{Component} for the filtered calendar data
        """
        raise NotImplementedError


    def merge(self, icalnew, icalold):
        """
        Merge the old iCalendar object into the new iCalendar data using the request information.

        @param icalnew: new iCalendar object to merge data into
        @type icalnew: L{Component}
        @param icalold: old iCalendar data to merge data from
        @type icalold: L{Component}
        """
        raise NotImplementedError


    def validCalendar(self, ical):

        # If we were passed a string, parse it out as a Component
        if isinstance(ical, str):
            try:
                ical = iComponent.fromString(ical)
            except ValueError:
                raise ValueError("Not a calendar: %r" % (ical,))

        if ical is None or ical.name() != "VCALENDAR":
            raise ValueError("Not a calendar: %r" % (ical,))

        return ical



class AddressFilter(object):
    """
    Abstract class that defines a vCard filter/merge object
    """

    def __init__(self):
        pass


    def filter(self, vcard):
        """
        Filter the supplied vCard object using the request information.

        @param vcard: iCalendar object
        @type vcard: L{Component}

        @return: L{Component} for the filtered vcard data
        """
        raise NotImplementedError


    def merge(self, vcardnew, vcardold):
        """
        Merge the old vcard object into the new vcard data using the request information.

        @param vcardnew: new vcard object to merge data into
        @type vcardnew: L{Component}
        @param vcardold: old vcard data to merge data from
        @type vcardold: L{Component}
        """
        raise NotImplementedError


    def validAddress(self, vcard):

        # If we were passed a string, parse it out as a Component
        if isinstance(vcard, str):
            try:
                vcard = vComponent.fromString(vcard)
            except ValueError:
                raise ValueError("Not a vcard: %r" % (vcard,))

        if vcard is None or vcard.name() != "VCARD":
            raise ValueError("Not a vcard: %r" % (vcard,))

        return vcard
