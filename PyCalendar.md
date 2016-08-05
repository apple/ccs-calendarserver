---
title: Calendar and Contacts Server
---

PyCalendar Library
==================

PyCalendar is an iCalendar [RFC 5545](http://www.ietf.org/rfc/rfc5545.txt) parser/generator library written in Python and used by CalendarServer for all its iCalendar operations. In addition, PyCalendar supports parsing IANA time zone database files to generate iCalendar **VTIMEZONE** data.

## GETTING IT

PyCalendar is automatically retrieved by CalendarServer's `bin/develop` script during its dependency resolution phase, and is stored as a sub-project of CalendarServer, along with other externally retrieved dependencies.

Alternatively, use GIT to obtain a working copy of the source code. The following command will check out the latest version of PyCalendar:

    git clone https://github.com/apple/ccs-pycalendar.git

Graphical clients which support GIT are also available, including Apple's ​XCode IDE. Consult the documentation for your chosen client for information on how to check out source code.
