##
# Copyright (c) 2012 Apple Inc. All rights reserved.
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

# Adjust method names

# PROPFINDs
METHOD_PROPFIND_CALENDAR_HOME = "PROPFIND Calendar Home"
METHOD_PROPFIND_CACHED_CALENDAR_HOME = "PROPFIND cached Calendar Home"
METHOD_PROPFIND_CALENDAR = "PROPFIND Calendar"
METHOD_PROPFIND_INBOX = "PROPFIND Inbox"
METHOD_PROPFIND_ADDRESSBOOK_HOME = "PROPFIND Adbk Home"
METHOD_PROPFIND_CACHED_ADDRESSBOOK_HOME = "PROPFIND cached Adbk Home"
METHOD_PROPFIND_ADDRESSBOOK = "PROPFIND Adbk"
METHOD_PROPFIND_DIRECTORY = "PROPFIND Directory"
METHOD_PROPFIND_PRINCIPALS = "PROPFIND Principals"
METHOD_PROPFIND_CACHED_PRINCIPALS = "PROPFIND cached Principals"

# PROPPATCHs
METHOD_PROPPATCH_CALENDAR = "PROPPATCH Calendar"
METHOD_PROPPATCH_ADDRESSBOOK = "PROPPATCH Adbk Home"

# REPORTs
METHOD_REPORT_CALENDAR_MULTIGET = "REPORT cal-multi"
METHOD_REPORT_CALENDAR_QUERY = "REPORT cal-query"
METHOD_REPORT_CALENDAR_FREEBUSY = "REPORT freebusy"
METHOD_REPORT_CALENDAR_SYNC = "REPORT cal-sync"
METHOD_REPORT_ADDRESSBOOK_MULTIGET = "REPORT adbk-multi"
METHOD_REPORT_ADDRESSBOOK_QUERY = "REPORT adbk-query"
METHOD_REPORT_DIRECTORY_QUERY = "REPORT dir-query"
METHOD_REPORT_ADDRESSBOOK_SYNC = "REPORT adbk-sync"
METHOD_REPORT_P_SEARCH_P_SET = "REPORT p-set"
METHOD_REPORT_P_P_SEARCH = "REPORT p-search"
METHOD_REPORT_EXPAND_P = "REPORT expand"

# POSTs
METHOD_POST_CALENDAR_HOME = "POST Calendar Home"
METHOD_POST_CALENDAR = "POST Calendar"
METHOD_POST_CALENDAR_OBJECT = "POST Calendar Object"
METHOD_POST_ADDRESSBOOK_HOME = "POST Adbk Home"
METHOD_POST_ADDRESSBOOK = "POST Adbk"
METHOD_POST_ISCHEDULE_FREEBUSY = "POST Freebusy iSchedule"
METHOD_POST_ISCHEDULE = "POST iSchedule"
METHOD_POST_TIMEZONES = "POST Timezones"
METHOD_POST_FREEBUSY = "POST Freebusy"
METHOD_POST_ORGANIZER = "POST Organizer"
METHOD_POST_ATTENDEE = "POST Attendee"
METHOD_POST_OUTBOX = "POST Outbox"
METHOD_POST_APNS = "POST apns"

# PUTs
METHOD_PUT_ICS = "PUT ics"
METHOD_PUT_ORGANIZER = "PUT Organizer"
METHOD_PUT_ATTENDEE = "PUT Attendee"
METHOD_PUT_DROPBOX = "PUT dropbox"
METHOD_PUT_VCF = "PUT VCF"

# GETs
METHOD_GET_CALENDAR_HOME = "GET Calendar Home"
METHOD_GET_CALENDAR = "GET Calendar"
METHOD_GET_ICS = "GET ics"
METHOD_GET_INBOX_ICS = "GET inbox ics"
METHOD_GET_DROPBOX = "GET dropbox"
METHOD_GET_ADDRESSBOOK_HOME = "GET Adbk Home"
METHOD_GET_ADDRESSBOOK = "GET Adbk"
METHOD_GET_VCF = "GET VCF"
METHOD_GET_TIMEZONES = "GET Timezones"

# DELETEs
METHOD_DELETE_CALENDAR_HOME = "DELETE Calendar Home"
METHOD_DELETE_CALENDAR = "DELETE Calendar"
METHOD_DELETE_ICS = "DELETE ics"
METHOD_DELETE_INBOX_ICS = "DELETE inbox ics"
METHOD_DELETE_DROPBOX = "DELETE dropbox"
METHOD_DELETE_ADDRESSBOOK_HOME = "DELETE Adbk Home"
METHOD_DELETE_ADDRESSBOOK = "DELETE Adbk"
METHOD_DELETE_VCF = "DELETE vcf"


def getAdjustedMethodName(method, uri, extended):

    uribits = uri.rstrip("/").split('/')[1:]
    if len(uribits) == 0:
        uribits = [uri]

    calendar_specials = ("attachments", "dropbox", "notification", "freebusy", "outbox",)
    adbk_specials = ("notification",)

    def _PROPFIND():
        cached = "cached" in extended

        if uribits[0] == "calendars":

            if len(uribits) == 3:
                return METHOD_PROPFIND_CACHED_CALENDAR_HOME if cached else METHOD_PROPFIND_CALENDAR_HOME
            elif len(uribits) > 3:
                if uribits[3] in calendar_specials:
                    return "PROPFIND %s" % (uribits[3],)
                elif len(uribits) == 4:
                    if uribits[3] == "inbox":
                        return METHOD_PROPFIND_INBOX
                    else:
                        return METHOD_PROPFIND_CALENDAR

        elif uribits[0] == "addressbooks":

            if len(uribits) == 3:
                return METHOD_PROPFIND_CACHED_ADDRESSBOOK_HOME if cached else METHOD_PROPFIND_ADDRESSBOOK_HOME
            elif len(uribits) > 3:
                if uribits[3] in adbk_specials:
                    return "PROPFIND %s" % (uribits[3],)
                elif len(uribits) == 4:
                    return METHOD_PROPFIND_ADDRESSBOOK

        elif uribits[0] == "directory":
            return METHOD_PROPFIND_DIRECTORY

        elif uribits[0] == "principals":
            return METHOD_PROPFIND_CACHED_PRINCIPALS if cached else METHOD_PROPFIND_PRINCIPALS

        return method


    def _REPORT():

        if "(" in method:
            report_type = method.split("}" if "}" in method else ":")[1][:-1]
            if report_type == "addressbook-query":
                if uribits[0] == "directory":
                    report_type = "directory-query"
            if report_type == "sync-collection":
                if uribits[0] == "calendars":
                    report_type = "cal-sync"
                elif uribits[0] == "addressbooks":
                    report_type = "adbk-sync"
            mappedNames = {
                "calendar-multiget"             : METHOD_REPORT_CALENDAR_MULTIGET,
                "calendar-query"                : METHOD_REPORT_CALENDAR_QUERY,
                "free-busy-query"               : METHOD_REPORT_CALENDAR_FREEBUSY,
                "cal-sync"                      : METHOD_REPORT_CALENDAR_SYNC,
                "addressbook-multiget"          : METHOD_REPORT_ADDRESSBOOK_MULTIGET,
                "addressbook-query"             : METHOD_REPORT_ADDRESSBOOK_QUERY,
                "directory-query"               : METHOD_REPORT_DIRECTORY_QUERY,
                "adbk-sync"                     : METHOD_REPORT_ADDRESSBOOK_SYNC,
                "principal-search-property-set" : METHOD_REPORT_P_SEARCH_P_SET,
                "principal-property-search"     : METHOD_REPORT_P_P_SEARCH,
                "expand-property"               : METHOD_REPORT_EXPAND_P,
            }
            return mappedNames.get(report_type, "REPORT %s" % (report_type,))

        return method


    def _PROPPATCH():

        if uribits[0] == "calendars":
            return METHOD_PROPPATCH_CALENDAR
        elif uribits[0] == "addressbooks":
            return METHOD_PROPPATCH_ADDRESSBOOK

        return method


    def _POST():

        if uribits[0] == "calendars":

            if len(uribits) == 3:
                return METHOD_POST_CALENDAR_HOME
            elif len(uribits) == 4:
                if uribits[3] == "outbox":
                    if "recipients" in extended:
                        return METHOD_POST_FREEBUSY
                    elif "freebusy" in extended:
                        return METHOD_POST_FREEBUSY
                    elif "itip.request" in extended or "itip.cancel" in extended:
                        return METHOD_POST_ORGANIZER
                    elif "itip.reply" in extended:
                        return METHOD_POST_ATTENDEE
                    else:
                        return METHOD_POST_OUTBOX
                elif uribits[3] in calendar_specials:
                    pass
                else:
                    return METHOD_POST_CALENDAR
            elif len(uribits) == 5:
                return METHOD_POST_CALENDAR_OBJECT

        elif uribits[0] == "addressbooks":

            if len(uribits) == 3:
                return METHOD_POST_ADDRESSBOOK_HOME
            elif len(uribits) == 4:
                if uribits[3] in adbk_specials:
                    pass
                else:
                    return METHOD_POST_ADDRESSBOOK

        elif uribits[0] == "ischedule":
            if "fb-cached" in extended or "fb-uncached" in extended or "freebusy" in extended:
                return METHOD_POST_ISCHEDULE_FREEBUSY
            else:
                return METHOD_POST_ISCHEDULE

        elif uribits[0].startswith("timezones"):
            return METHOD_POST_TIMEZONES

        elif uribits[0].startswith("apns"):
            return METHOD_POST_APNS

        return method


    def _PUT():

        if uribits[0] == "calendars":
            if len(uribits) > 3:
                if uribits[3] in calendar_specials:
                    return "PUT %s" % (uribits[3],)
                elif len(uribits) == 4:
                    pass
                else:
                    if "itip.requests" in extended:
                        return METHOD_PUT_ORGANIZER
                    elif "itip.reply" in extended:
                        return METHOD_PUT_ATTENDEE
                    else:
                        return METHOD_PUT_ICS

        elif uribits[0] == "addressbooks":
            if len(uribits) > 3:
                if uribits[3] in adbk_specials:
                    return "PUT %s" % (uribits[3],)
                elif len(uribits) == 4:
                    pass
                else:
                    return METHOD_PUT_VCF

        return method


    def _GET():

        if uribits[0] == "calendars":

            if len(uribits) == 3:
                return METHOD_GET_CALENDAR_HOME
            elif len(uribits) > 3:
                if uribits[3] in calendar_specials:
                    return "GET %s" % (uribits[3],)
                elif len(uribits) == 4:
                    return METHOD_GET_CALENDAR
                elif uribits[3] == "inbox":
                    return METHOD_GET_INBOX_ICS
                else:
                    return METHOD_GET_ICS

        elif uribits[0] == "addressbooks":

            if len(uribits) == 3:
                return METHOD_GET_ADDRESSBOOK_HOME
            elif len(uribits) > 3:
                if uribits[3] in adbk_specials:
                    return "GET %s" % (uribits[3],)
                elif len(uribits) == 4:
                    return METHOD_GET_ADDRESSBOOK
                else:
                    return METHOD_GET_VCF

        elif uribits[0].startswith("timezones"):
            return METHOD_GET_TIMEZONES

        return method


    def _DELETE():

        if uribits[0] == "calendars":

            if len(uribits) == 3:
                return METHOD_DELETE_CALENDAR_HOME
            elif len(uribits) > 3:
                if uribits[3] in calendar_specials:
                    return "DELETE %s" % (uribits[3],)
                elif len(uribits) == 4:
                    return METHOD_DELETE_CALENDAR
                elif uribits[3] == "inbox":
                    return METHOD_DELETE_INBOX_ICS
                else:
                    return METHOD_DELETE_ICS

        elif uribits[0] == "addressbooks":

            if len(uribits) == 3:
                return METHOD_DELETE_ADDRESSBOOK_HOME
            elif len(uribits) > 3:
                if uribits[3] in adbk_specials:
                    return "DELETE %s" % (uribits[3],)
                elif len(uribits) == 4:
                    return METHOD_DELETE_ADDRESSBOOK
                else:
                    return METHOD_DELETE_VCF

        return method


    def _ANY():
        return method

    return {
        "DELETE" : _DELETE,
        "GET" : _GET,
        "POST" : _POST,
        "PROPFIND" : _PROPFIND,
        "PROPPATCH" : _PROPPATCH,
        "PUT" : _PUT,
        "REPORT" : _REPORT,
    }.get(method.split("(")[0], _ANY)()
