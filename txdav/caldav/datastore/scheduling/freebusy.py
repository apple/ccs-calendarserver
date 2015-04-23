##
# Copyright (c) 2005-2015 Apple Inc. All rights reserved.
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

from pycalendar.datetime import DateTime
from pycalendar.duration import Duration
from pycalendar.period import Period
from pycalendar.timezone import Timezone

from twext.python.log import Logger

from twisted.internet.defer import inlineCallbacks, returnValue

from twistedcaldav import caldavxml
from twistedcaldav.caldavxml import TimeRange
from twistedcaldav.config import config
from twistedcaldav.dateops import compareDateTime, normalizeToUTC, \
    parseSQLTimestampToPyCalendar, tupleToDateTime, clipPeriod, \
    timeRangesOverlap, normalizePeriodList, tupleFromDateTime
from twistedcaldav.ical import Component, Property, iCalendarProductID
from twistedcaldav.instance import InstanceList
from twistedcaldav.memcacher import Memcacher

from txdav.caldav.datastore.query.filter import Filter
from txdav.caldav.icalendarstore import QueryMaxResources
from txdav.caldav.datastore.scheduling.cuaddress import LocalCalendarUser
from txdav.common.icommondatastore import IndexedSearchException, \
    InternalDataStoreError

import uuid
from collections import namedtuple

log = Logger()


class FBCacheEntry(object):

    CACHE_DAYS_FLOATING_ADJUST = 1

    fbcacher = Memcacher("FBCache", pickle=True)

    def __init__(self, key, token, timerange, fbresults):
        self.key = key
        self.token = token
        self.timerange = timerange.getText()
        self.fbresults = fbresults


    @classmethod
    @inlineCallbacks
    def getCacheEntry(cls, calresource, useruid, timerange):

        key = str(calresource.id()) + "/" + useruid
        token = (yield calresource.syncToken())
        entry = (yield cls.fbcacher.get(key))

        if entry:

            # Offset one day at either end to account for floating
            entry_timerange = Period.parseText(entry.timerange)
            cached_start = entry_timerange.getStart() + Duration(days=cls.CACHE_DAYS_FLOATING_ADJUST)
            cached_end = entry_timerange.getEnd() - Duration(days=cls.CACHE_DAYS_FLOATING_ADJUST)

            # Verify that the requested time range lies within the cache time range
            if compareDateTime(timerange.getEnd(), cached_end) <= 0 and compareDateTime(timerange.getStart(), cached_start) >= 0:

                # Verify that cached entry is still valid
                if token == entry.token:
                    returnValue(entry.fbresults)

        returnValue(None)


    @classmethod
    @inlineCallbacks
    def makeCacheEntry(cls, calresource, useruid, timerange, fbresults):

        key = str(calresource.id()) + "/" + useruid
        token = (yield calresource.syncToken())
        entry = cls(key, token, timerange, fbresults)
        yield cls.fbcacher.set(key, entry)



class FreebusyQuery(object):
    """
    Class that manages the process of getting free busy information of a particular attendee.
    """

    FBInfo = namedtuple("FBInfo", ("busy", "tentative", "unavailable",))
    FBInfo_mapper = {"BUSY": "busy", "BUSY-TENTATIVE": "tentative", "BUSY-UNAVAILABLE": "unavailable"}
    FBInfo_index_mapper = {'B': "busy", 'T': "tentative", 'U': "unavailable"}

    def __init__(
        self,
        organizer=None, organizerProp=None, recipient=None, attendeeProp=None,
        uid=None, timerange=None, excludeUID=None, logItems=None, accountingItems=None, event_details=None
    ):
        """

        @param organizer: the organizer making the freebusy request
        @type organizer: L{CalendarUser}
        @param organizerProp: iCalendar ORGANIZER property from the request
        @type organizerProp: L{Property}
        @param recipient: the attendee whose freebusy is being requested
        @type recipient: L{CalendarUser}
        @param attendeeProp: iCalendar ATTENDEE property from the request
        @type attendeeProp: L{Property}
        @param authzuid: directory UID of the currently authenticated user (i.e., the one making
            the actual free busy request - might be different from the organizer)
        @type authzuid: L{str}
        @param uid: iCalendar UID in the request
        @type uid: L{str}
        @param timerange: time range for freebusy request
        @type timerange: L{Period}
        @param excludeUID: an iCalendar UID to exclude from busy results
        @type excludeUID: L{str}
        @param logItems: items to add to logging
        @type logItems: L{dict}
        @param accountingItems: items to add to accounting logging
        @type accountingItems: L{dict}
        @param event_details: if not L{None}, a list in which busy event details are stored
        @type event_details: L{list} or L{None}
        """
        self.organizer = organizer
        self.organizerProp = organizerProp
        self.recipient = recipient
        self.attendeeProp = attendeeProp
        self.uid = uid
        self.timerange = timerange
        self.excludeuid = excludeUID
        self.logItems = logItems
        self.accountingItems = accountingItems
        self.event_details = event_details

        # Check to see if the recipient is the same calendar user as the organizer.
        # Needed for masked UID stuff.
        if isinstance(self.organizer, LocalCalendarUser):
            self.same_calendar_user = self.organizer.record.uid == self.recipient.record.uid
        else:
            self.same_calendar_user = False

        # May need organizer principal
        self.organizer_record = self.organizer.record if self.organizer and self.organizer.hosted() else None
        self.organizer_uid = self.organizer_record.uid if self.organizer_record else None

        # Free busy is per-user
        self.attendee_record = self.recipient.record if self.recipient and self.recipient.hosted() else None
        self.attendee_uid = self.attendee_record.uid if self.attendee_record else None


    @inlineCallbacks
    def checkRichOptions(self, txn):
        if not hasattr(self, "rich_options"):
            # Look for possible extended free busy information
            self.rich_options = {
                "organizer": False,
                "delegate": False,
                "resource": False,
            }
            if self.event_details is not None and self.organizer_record is not None and self.attendee_record is not None:

                # Get the principal of the authorized user which may be different from the organizer if a delegate of
                # the organizer is making the request
                authzuid = txn._authz_uid if txn is not None else None
                if authzuid is not None and authzuid != self.organizer_uid:
                    authz_record = yield txn.directoryService().recordWithUID(authzuid.decode("utf-8"))
                else:
                    self.authzuid = self.organizer_uid
                    authz_record = self.organizer_record

                # Check if attendee is also the organizer or the delegate doing the request
                if self.attendee_uid in (self.organizer_uid, authzuid):
                    self.rich_options["organizer"] = True

                # Check if authorized user is a delegate of attendee
                proxy = (yield authz_record.isProxyFor(self.attendee_record))
                if config.Scheduling.Options.DelegeteRichFreeBusy and proxy:
                    self.rich_options["delegate"] = True

                # Check if attendee is room or resource
                if config.Scheduling.Options.RoomResourceRichFreeBusy and self.attendee_record.getCUType() in ("RESOURCE", "ROOM",):
                    self.rich_options["resource"] = True


    @inlineCallbacks
    def generateAttendeeFreeBusyResponse(self, fbset=None, method="REPLY"):

        # First list is BUSY, second BUSY-TENTATIVE, third BUSY-UNAVAILABLE
        fbinfo = self.FBInfo([], [], [])

        if self.recipient is not None:
            # Find the current recipients calendars that are not transparent
            if fbset is None:
                fbset = (yield self.recipient.inbox.ownerHome().loadCalendars())
                fbset = [calendar for calendar in fbset if calendar.isUsedForFreeBusy()]

            # Process the availability property from the Inbox.
            if hasattr(self.recipient, "inbox"):
                availability = self.recipient.inbox.ownerHome().getAvailability()
                if availability is not None:
                    self.processAvailabilityFreeBusy(availability, fbinfo)

        # Now process free-busy set calendars
        yield self.generateFreeBusyInfo(fbset, fbinfo)

        # Build VFREEBUSY iTIP reply for this recipient
        fbresult = self.buildFreeBusyResult(fbinfo, method=method)

        returnValue(fbresult)


    def processAvailabilityFreeBusy(self, calendar, fbinfo):
        """
        Extract free-busy data from a VAVAILABILITY component.

        @param calendar: the L{Component} that is the VCALENDAR containing the VAVAILABILITY's.
        @param fbinfo: the tuple used to store the three types of fb data.
        """

        for vav in [x for x in calendar.subcomponents() if x.name() == "VAVAILABILITY"]:

            # Get overall start/end
            start = vav.getStartDateUTC()
            if start is None:
                start = DateTime(1900, 1, 1, 0, 0, 0, tzid=Timezone.UTCTimezone)
            end = vav.getEndDateUTC()
            if end is None:
                end = DateTime(2100, 1, 1, 0, 0, 0, tzid=Timezone.UTCTimezone)
            period = Period(start, end)
            overall = clipPeriod(period, self.timerange)
            if overall is None:
                continue

            # Now get periods for each instance of AVAILABLE sub-components
            periods = self.processAvailablePeriods(vav)

            # Now invert the periods and store in accumulator
            busyperiods = []
            last_end = self.timerange.getStart()
            for period in periods:
                if last_end < period.getStart():
                    busyperiods.append(Period(last_end, period.getStart()))
                last_end = period.getEnd()
            if last_end < self.timerange.getEnd():
                busyperiods.append(Period(last_end, self.timerange.getEnd()))

            # Add to actual results mapped by busy type
            fbtype = vav.propertyValue("BUSYTYPE")
            if fbtype is None:
                fbtype = "BUSY-UNAVAILABLE"

            getattr(fbinfo, self.FBInfo_mapper.get(fbtype, "unavailable")).extend(busyperiods)


    def processAvailablePeriods(self, calendar):
        """
        Extract instance period data from an AVAILABLE component.
        @param calendar: the L{Component} that is the VAVAILABILITY containing the AVAILABLE's.
        @param timerange: the time range to restrict free busy data to.
        """

        periods = []

        # First we need to group all AVAILABLE sub-components by UID
        uidmap = {}
        for component in calendar.subcomponents():
            if component.name() == "AVAILABLE":
                uid = component.propertyValue("UID")
                uidmap.setdefault(uid, []).append(component)

        # Then we expand each uid set separately
        for componentSet in uidmap.itervalues():
            instances = InstanceList(ignoreInvalidInstances=True)
            instances.expandTimeRanges(componentSet, self.timerange.getEnd())

            # Now convert instances into period list
            for key in instances:
                instance = instances[key]
                # Ignore any with floating times (which should not happen as the spec requires UTC or local
                # but we will try and be safe here).
                start = instance.start
                if start.floating():
                    continue
                end = instance.end
                if end.floating():
                    continue

                # Clip period for this instance - use duration for period end if that
                # is what original component used
                if instance.component.hasProperty("DURATION"):
                    period = Period(start, duration=end - start)
                else:
                    period = Period(start, end)
                clipped = clipPeriod(period, self.timerange)
                if clipped:
                    periods.append(clipped)

        normalizePeriodList(periods)
        return periods


    @inlineCallbacks
    def generateFreeBusyInfo(self, fbset, fbinfo, matchtotal=0):
        """
        Get freebusy information for a calendar. Different behavior for internal vs external calendars.

        See L{_internalGenerateFreeBusyInfo} for argument description.
        """

        # Split calendar set into internal/external items
        fbset_internal = [calendar for calendar in fbset if not calendar.external()]
        fbset_external = [calendar for calendar in fbset if calendar.external()]

        # TODO: we should probably figure out how to run the internal and external ones in parallel
        if fbset_external:
            matchtotal += (yield self._externalGenerateFreeBusyInfo(
                fbset_external,
                fbinfo,
                matchtotal,
            ))

        if fbset_internal:
            matchtotal += (yield self._internalGenerateFreeBusyInfo(
                fbset_internal,
                fbinfo,
                matchtotal,
            ))

        returnValue(matchtotal)


    @inlineCallbacks
    def _externalGenerateFreeBusyInfo(self, fbset, fbinfo, matchtotal):
        """
        Generate a freebusy response for an external (cross-pod) calendar by making a cross-pod call. This will bypass
        any type of smart caching on this pod in favor of using caching on the pod hosting the actual calendar data.

        See L{_internalGenerateFreeBusyInfo} for argument description.
        """
        for calresource in fbset:
            fbresults, matchtotal = yield calresource._txn.store().conduit.send_freebusy(
                calresource,
                self.organizer.cuaddr if self.organizer else None,
                self.recipient.cuaddr if self.recipient else None,
                self.timerange,
                matchtotal,
                self.excludeuid,
                self.event_details,
            )
            for i in range(3):
                fbinfo[i].extend([Period.parseText(p) for p in fbresults[i]])
        returnValue(matchtotal)


    @inlineCallbacks
    def _internalGenerateFreeBusyInfo(
        self,
        fbset,
        fbinfo,
        matchtotal,
    ):
        """
        Run a free busy report on the specified calendar collection
        accumulating the free busy info for later processing.
        @param calresource: the L{Calendar} for a calendar collection.
        @param fbinfo:      the array of busy periods to update.
        @param matchtotal:  the running total for the number of matches.
        """

        yield self.checkRichOptions(fbset[0]._txn)

        calidmap = dict([(fbcalendar.id(), fbcalendar,) for fbcalendar in fbset])
        directoryService = fbset[0].directoryService()

        results = yield self._matchResources(fbset)

        if self.accountingItems is not None:
            self.accountingItems["fb-resources"] = {}
            for calid, result in results.items():
                aggregated_resources, tzinfo, filter = result
                for k, v in aggregated_resources.items():
                    name, uid, comptype, test_organizer = k
                    self.accountingItems["fb-resources"][uid] = []
                    for float, start, end, fbtype in v:
                        fbstart = tupleToDateTime(start, withTimezone=tzinfo if float == 'Y' else Timezone.UTCTimezone)
                        fbend = tupleToDateTime(end, withTimezone=tzinfo if float == 'Y' else Timezone.UTCTimezone)
                        self.accountingItems["fb-resources"][uid].append((
                            float,
                            str(fbstart),
                            str(fbend),
                            fbtype,
                        ))

        # Cache directory record lookup outside this loop as it is expensive and will likely
        # always end up being called with the same organizer address.
        recordUIDCache = {}
        for calid, result in results.items():
            calresource = calidmap[calid]
            aggregated_resources, tzinfo, filter = result
            for key in aggregated_resources.iterkeys():

                name, uid, comptype, test_organizer = key

                # Short-cut - if an fbtype exists we can use that
                if comptype == "VEVENT" and aggregated_resources[key][0][3] != '?':

                    matchedResource = False

                    # Look at each instance
                    for float, start, end, fbtype in aggregated_resources[key]:
                        # Ignore free time or unknown
                        if fbtype in ('F', '?'):
                            continue

                        # Apply a timezone to any floating times
                        fbstart = tupleToDateTime(start, withTimezone=tzinfo if float == 'Y' else Timezone.UTCTimezone)
                        fbend = tupleToDateTime(end, withTimezone=tzinfo if float == 'Y' else Timezone.UTCTimezone)

                        # Clip instance to time range
                        clipped = clipPeriod(Period(fbstart, end=fbend), self.timerange)

                        # Double check for overlap
                        if clipped:
                            # Ignore ones of this UID
                            if not (yield self._testIgnoreExcludeUID(uid, test_organizer, recordUIDCache, directoryService)):
                                clipped.setUseDuration(True)
                                matchedResource = True
                                getattr(fbinfo, self.FBInfo_index_mapper.get(fbtype, "busy")).append(clipped)

                    if matchedResource:
                        # Check size of results is within limit
                        matchtotal += 1
                        if matchtotal > config.MaxQueryWithDataResults:
                            raise QueryMaxResources(config.MaxQueryWithDataResults, matchtotal)

                        # Add extended details
                        if any(self.rich_options.values()):
                            child = (yield calresource.calendarObjectWithName(name))
                            # Only add fully public events
                            if not child.accessMode or child.accessMode == Component.ACCESS_PUBLIC:
                                calendar = (yield child.componentForUser())
                                self._addEventDetails(calendar, self.rich_options, tzinfo)

                else:
                    child = (yield calresource.calendarObjectWithName(name))
                    calendar = (yield child.componentForUser())

                    # The calendar may come back as None if the resource is being changed, or was deleted
                    # between our initial index query and getting here. For now we will ignore this error, but in
                    # the longer term we need to implement some form of locking, perhaps.
                    if calendar is None:
                        log.error("Calendar %s is missing from calendar collection %r" % (name, calresource))
                        continue

                    if self.accountingItems is not None:
                        self.accountingItems.setdefault("fb-filter-match", []).append(uid)

                    if filter.match(calendar, None):

                        # Ignore ones of this UID
                        if (yield self._testIgnoreExcludeUID(uid, calendar.getOrganizer(), recordUIDCache, calresource.directoryService())):
                            continue

                        if self.accountingItems is not None:
                            self.accountingItems.setdefault("fb-filter-matched", []).append(uid)

                        # Check size of results is within limit
                        matchtotal += 1
                        if matchtotal > config.MaxQueryWithDataResults:
                            raise QueryMaxResources(config.MaxQueryWithDataResults, matchtotal)

                        if calendar.mainType() == "VEVENT":
                            self.processEventFreeBusy(calendar, fbinfo, tzinfo)
                        elif calendar.mainType() == "VFREEBUSY":
                            self.processFreeBusyFreeBusy(calendar, fbinfo)
                        elif calendar.mainType() == "VAVAILABILITY":
                            self.processAvailabilityFreeBusy(calendar, fbinfo)
                        else:
                            assert "Free-busy query returned unwanted component: %s in %r", (name, calresource,)

                        # Add extended details
                        if calendar.mainType() == "VEVENT" and any(self.rich_options.values()):
                            # Only add fully public events
                            if not child.accessMode or child.accessMode == Component.ACCESS_PUBLIC:
                                self._addEventDetails(calendar, self.rich_options, tzinfo)

        returnValue(matchtotal)


    @inlineCallbacks
    def _matchResources(self, fbset):
        """
        For now iterate over each calendar and collect the results. In the longer term we might want to consider
        doing a single DB query in the case where multiple calendars need to be searched.

        @param fbset: list of calendars to process
        @type fbset: L{list} of L{Calendar}
        """

        results = {}
        for calresource in fbset:
            aggregated_resources, tzinfo, filter = yield self._matchCalendarResources(calresource)
            results[calresource.id()] = (aggregated_resources, tzinfo, filter,)

        returnValue(results)


    @inlineCallbacks
    def _matchCalendarResources(self, calresource):

        # Get the timezone property from the collection.
        tz = calresource.getTimezone()

        # Try cache
        aggregated_resources = (yield FBCacheEntry.getCacheEntry(calresource, self.attendee_uid, self.timerange)) if config.EnableFreeBusyCache else None

        if aggregated_resources is None:

            if self.accountingItems is not None:
                self.accountingItems["fb-uncached"] = self.accountingItems.get("fb-uncached", 0) + 1

            caching = False
            if config.EnableFreeBusyCache:
                # Log extended item
                if self.logItems is not None:
                    self.logItems["fb-uncached"] = self.logItems.get("fb-uncached", 0) + 1

                # We want to cache a large range of time based on the current date
                cache_start = normalizeToUTC(DateTime.getToday() + Duration(days=0 - config.FreeBusyCacheDaysBack))
                cache_end = normalizeToUTC(DateTime.getToday() + Duration(days=config.FreeBusyCacheDaysForward))

                # If the requested time range would fit in our allowed cache range, trigger the cache creation
                if compareDateTime(self.timerange.getStart(), cache_start) >= 0 and compareDateTime(self.timerange.getEnd(), cache_end) <= 0:
                    cache_timerange = Period(cache_start, cache_end)
                    caching = True

            #
            # What we do is a fake calendar-query for VEVENT/VFREEBUSYs in the specified time-range.
            # We then take those results and merge them into one VFREEBUSY component
            # with appropriate FREEBUSY properties, and return that single item as iCal data.
            #

            # Create fake filter element to match time-range
            tr = TimeRange(
                start=(cache_timerange if caching else self.timerange).getStart().getText(),
                end=(cache_timerange if caching else self.timerange).getEnd().getText(),
            )
            filter = caldavxml.Filter(
                caldavxml.ComponentFilter(
                    caldavxml.ComponentFilter(
                        tr,
                        name=("VEVENT", "VFREEBUSY", "VAVAILABILITY"),
                    ),
                    name="VCALENDAR",
                )
            )
            filter = Filter(filter)
            tzinfo = filter.settimezone(tz)
            if self.accountingItems is not None:
                self.accountingItems["fb-query-timerange"] = (str(tr.start), str(tr.end),)

            try:
                resources = yield calresource.search(filter, useruid=self.attendee_uid, fbtype=True)

                aggregated_resources = {}
                for name, uid, comptype, test_organizer, float, start, end, fbtype, transp in resources:
                    if transp == 'T' and fbtype != '?':
                        fbtype = 'F'
                    aggregated_resources.setdefault((name, uid, comptype, test_organizer,), []).append((
                        float,
                        tupleFromDateTime(parseSQLTimestampToPyCalendar(start)),
                        tupleFromDateTime(parseSQLTimestampToPyCalendar(end)),
                        fbtype,
                    ))

                if caching:
                    yield FBCacheEntry.makeCacheEntry(calresource, self.attendee_uid, cache_timerange, aggregated_resources)
            except IndexedSearchException:
                raise InternalDataStoreError("Invalid indexedSearch query")

        else:
            if self.accountingItems is not None:
                self.accountingItems["fb-cached"] = self.accountingItems.get("fb-cached", 0) + 1

            # Log extended item
            if self.logItems is not None:
                self.logItems["fb-cached"] = self.logItems.get("fb-cached", 0) + 1

            # Determine appropriate timezone (UTC is the default)
            tzinfo = tz.gettimezone() if tz is not None else Timezone.UTCTimezone
            filter = None

        returnValue((aggregated_resources, tzinfo, filter,))


    @inlineCallbacks
    def _testIgnoreExcludeUID(self, uid, test_organizer, recordUIDCache, dirservice):
        """
        Check whether the event with the specified UID can be correctly excluded from the
        freebusy result.

        @param uid: UID to test
        @type uid: L{str}
        @param test_organizer: organizer cu-address of the event
        @type test_organizer: L{str}
        @param recordUIDCache: cache of directory records
        @type recordUIDCache: L{dict}
        @param dirservice: directory service to use for record lookups
        @type dirservice: L{DirectoryService}
        """

        # See if we have a UID match
        if self.excludeuid == uid:
            if test_organizer:
                test_uid = recordUIDCache.get(test_organizer)
                if test_uid is None:
                    test_record = (yield dirservice.recordWithCalendarUserAddress(test_organizer))
                    test_uid = test_record.uid if test_record else ""
                    recordUIDCache[test_organizer] = test_uid
            else:
                test_uid = ""

            # Check that ORGANIZER's match (security requirement)
            if (self.organizer is None) or (self.organizer_uid == test_uid):
                returnValue(True)
            # Check for no ORGANIZER and check by same calendar user
            elif (test_uid == "") and self.same_calendar_user:
                returnValue(True)

        returnValue(False)


    def _addEventDetails(self, calendar, rich_options, tzinfo):
        """
        Expand events within the specified time range and limit the set of properties to those allowed for
        delegate extended free busy.

        @param calendar: the calendar object to expand
        @type calendar: L{Component}
        @param event_details: list to append VEVENT components to
        @type event_details: C{list}
        @param tzinfo: timezone for floating time calculations
        @type tzinfo: L{Timezone}
        """

        # First expand the component
        expanded = calendar.expand(self.timerange.getStart(), self.timerange.getEnd(), timezone=tzinfo)

        keep_props = (
            "UID",
            "RECURRENCE-ID",
            "DTSTAMP",
            "DTSTART",
            "DTEND",
            "DURATION",
        )

        if rich_options["organizer"] or rich_options["delegate"]:
            keep_props += ("SUMMARY",)

        if rich_options["organizer"] or rich_options["resource"]:
            keep_props += ("ORGANIZER",)

        # Remove all but essential properties
        expanded.filterProperties(keep=keep_props)

        # Need to remove all child components of VEVENT
        for subcomponent in expanded.subcomponents():
            if subcomponent.name() == "VEVENT":
                for sub in tuple(subcomponent.subcomponents()):
                    subcomponent.removeComponent(sub)

        self.event_details.extend([subcomponent for subcomponent in expanded.subcomponents() if subcomponent.name() == "VEVENT"])


    def processEventFreeBusy(self, calendar, fbinfo, tzinfo):
        """
        Extract free busy data from a VEVENT component.
        @param calendar: the L{Component} that is the VCALENDAR containing the VEVENT's.
        @param fbinfo: the tuple used to store the three types of fb data.
        @param tzinfo: the L{Timezone} for the timezone to use for floating/all-day events.
        """

        # Expand out the set of instances for the event with in the required range
        instances = calendar.expandTimeRanges(self.timerange.getEnd(), lowerLimit=self.timerange.getStart(), ignoreInvalidInstances=True)

        # Can only do timed events
        for key in instances:
            instance = instances[key]
            if instance.start.isDateOnly():
                return
            break
        else:
            return

        for key in instances:
            instance = instances[key]

            # Apply a timezone to any floating times
            fbstart = instance.start
            if fbstart.floating():
                fbstart.setTimezone(tzinfo)
            fbend = instance.end
            if fbend.floating():
                fbend.setTimezone(tzinfo)

            # Check TRANSP property of underlying component
            if instance.component.hasProperty("TRANSP"):
                # If its TRANSPARENT we always ignore it
                if instance.component.propertyValue("TRANSP") == "TRANSPARENT":
                    continue

            # Determine status
            if instance.component.hasProperty("STATUS"):
                status = instance.component.propertyValue("STATUS")
            else:
                status = "CONFIRMED"

            # Ignore cancelled
            if status == "CANCELLED":
                continue

            # Clip period for this instance - use duration for period end if that
            # is what original component used
            if instance.component.hasProperty("DURATION"):
                period = Period(fbstart, duration=fbend - fbstart)
            else:
                period = Period(fbstart, fbend)
            clipped = clipPeriod(period, self.timerange)

            # Double check for overlap
            if clipped:
                if status == "TENTATIVE":
                    fbinfo.tentative.append(clipped)
                else:
                    fbinfo.busy.append(clipped)


    def processFreeBusyFreeBusy(self, calendar, fbinfo):
        """
        Extract FREEBUSY data from a VFREEBUSY component.
        @param calendar: the L{Component} that is the VCALENDAR containing the VFREEBUSY's.
        @param fbinfo: the tuple used to store the three types of fb data.
        """

        for vfb in [x for x in calendar.subcomponents() if x.name() == "VFREEBUSY"]:
            # First check any start/end in the actual component
            start = vfb.getStartDateUTC()
            end = vfb.getEndDateUTC()
            if start and end:
                if not timeRangesOverlap(start, end, self.timerange.getStart(), self.timerange.getEnd()):
                    continue

            # Now look at each FREEBUSY property
            for fb in vfb.properties("FREEBUSY"):
                # Check the type
                fbtype = fb.parameterValue("FBTYPE", default="BUSY")
                if fbtype == "FREE":
                    continue

                # Look at each period in the property
                assert isinstance(fb.value(), list), "FREEBUSY property does not contain a list of values: %r" % (fb,)
                for period in fb.value():
                    # Clip period for this instance
                    clipped = clipPeriod(period.getValue(), self.timerange)
                    if clipped:
                        getattr(fbinfo, self.FBInfo_mapper.get(fbtype, "busy")).append(clipped)


    def buildFreeBusyResult(self, fbinfo, method=None):
        """
        Generate a VCALENDAR object containing a single VFREEBUSY that is the
        aggregate of the free busy info passed in.

        @param fbinfo:        the array of busy periods to use.
        @param method:        the METHOD property value to insert.
        @return:              the L{Component} containing the calendar data.
        """

        # Merge overlapping time ranges in each fb info section
        normalizePeriodList(fbinfo.busy)
        normalizePeriodList(fbinfo.tentative)
        normalizePeriodList(fbinfo.unavailable)

        # Now build a new calendar object with the free busy info we have
        fbcalendar = Component("VCALENDAR")
        fbcalendar.addProperty(Property("VERSION", "2.0"))
        fbcalendar.addProperty(Property("PRODID", iCalendarProductID))
        if method:
            fbcalendar.addProperty(Property("METHOD", method))
        fb = Component("VFREEBUSY")
        fbcalendar.addComponent(fb)
        if self.organizerProp is not None:
            fb.addProperty(self.organizerProp)
        if self.attendeeProp is not None:
            fb.addProperty(self.attendeeProp)
        fb.addProperty(Property("DTSTART", self.timerange.getStart()))
        fb.addProperty(Property("DTEND", self.timerange.getEnd()))
        fb.addProperty(Property("DTSTAMP", DateTime.getNowUTC()))
        if len(fbinfo.busy) != 0:
            fb.addProperty(Property("FREEBUSY", fbinfo.busy, {"FBTYPE": "BUSY"}))
        if len(fbinfo.tentative) != 0:
            fb.addProperty(Property("FREEBUSY", fbinfo.tentative, {"FBTYPE": "BUSY-TENTATIVE"}))
        if len(fbinfo.unavailable) != 0:
            fb.addProperty(Property("FREEBUSY", fbinfo.unavailable, {"FBTYPE": "BUSY-UNAVAILABLE"}))
        if self.uid is not None:
            fb.addProperty(Property("UID", self.uid))
        else:
            uid = str(uuid.uuid4())
            fb.addProperty(Property("UID", uid))

        if self.event_details:
            for vevent in self.event_details:
                fbcalendar.addComponent(vevent)

        return fbcalendar
