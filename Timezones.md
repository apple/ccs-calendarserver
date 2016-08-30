---
title: Time zones
---

Time Zones
==========

CalendarServer makes use of [IANA standard time zone data](https://www.iana.org/time-zones) for processing iCalendar data. CalendarServer itself ships with a set of time zones stored in the `twistedcaldav/zoneinfo` directory. However, that data is not always the most recent available. So, by default, CalendarServer actually uses time zone data stored in `data/zoneinfo` (where `data` is the config.DataRoot directory). When CalendarServer starts up, it does the following:

1. Checks to see if `data/zoneinfo` is present - if not it creates it, and copies over all the data in `twistedcaldav/zoneinfo`.
2. Checks to see if the version of the time zone data in `data/zoneinfo` is older than the version in `twistedcaldav/zoneinfo` - if so, it replaces the data in `data/zoneinfo` with that in `twistedcaldav/zoneinfo`.

Alternatively, if the `config.UsePackageTimezones` value is set to `<true/>`, then CalendarServer will always use the time zone data from `twistedcaldav/zoneinfo`.

## Keeping Time Zone Data Up to Date

### Admins

When using the default mode, the time zone data in `data/zoneinfo` can be kept up to date, independent of whatever is in `twistedcaldav/zoneinfo`, using the `calendarserver_manage_timezones` tool. The following command will do an in-place update of the `data/zoneinfo` data by checking the IANA site to see if a more recent version is available, and if so, downloading it, converting it, and copying it to `data/zoneinfo`:

	calendarserver_manage_timezones --refresh

Note that CalendarServer will need to be restarted in order for any updated data to be used. When using multiple app-servers to host a calendaring service, all the app-servers in the cluster should be updated and restarted at the same time.

### Developers

CalendarServer developers should ensure that the data in `twistedcaldav/zoneinfo` in the the git repository is up to date. The current version of the data can be found in the file `twistedcaldav/zoneinfo/version.txt`. The latest version available at IANA can be seen [here](https://www.iana.org/time-zones). If the repository data needs to be updated, run the following command:

	calendarserver_manage_timezones --refreshpkg

Double-check the resulting differences, run tests, and commit the changes.

Time zone data from IANA comes in its own special format. The [PyCalendar](PyCalendar.html) project includes a `zonal` Python module that is used for converting the IANA time zone data into iCalendar format. In addition, the `calendarserver_manage_timezones` tool also downloads data from unicode.org that defines how Windows time zone names map to IANA names, and the tool will generate a set of iCalendar time zones for those too.

## Time Zone Service

CalendarServer includes a standard time zone service using the standard IETF [Time Zone Data Distribution Service - RFC7808](https://tools.ietf.org/html/rfc7808) protocol. This is controlled by the settings under the `config.TimezoneService` key, and is on by default. This service can be used by 3rd party apps interacting with CalendarServer to ensure those apps have the same time zone data as CalendarServer, as well as to provide UTC offset expansion calculations for those apps, so they don't have to handle any complicated calculations. The time zone service can either be a _primary_ service (one which is authoritative for the time zone data), or a _secondary_ service (one which fetches its time zone data from a _primary_ service). By default CalendarServer acts as a _primary_ service.

An older version of the time zone service is controlled by the `config.EnableTimezoneService` key (off by default). This is only used by macOS Server's wiki calendar.

## Time Zones by Reference

Time zone data in iCalendar format can grow very large, but usually changes very little. As a result, it is not efficient for such data to always be sent between client and server - in some cases it can be a lot larger than the actual event data that uses it. As a result, CalendarServer supports the IETF [Time Zones by Reference - RFC7809](https://tools.ietf.org/html/rfc7809) extension to CalDAV to allow the server and clients to skip including time zone data in the iCalendar data they exchange with each other, under the assumption that they are all using the same data for the time zones as identified by the time zone ids in the iCalendar data. This significantly reduces the network I/O and storage requirements for iCalendar data. This feature is controlled by the `config.EnableTimezonesByReference` key and is on by default.
