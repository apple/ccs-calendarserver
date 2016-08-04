---
title: Calendar and Contacts Server
---

Calendar and Contacts Server
============================

The open source Calendar and Contacts Server project is a standards-compliant server implementing the CalDAV and CardDAV protocols. It provides a shared location on the network allowing multiple users to store and edit calendaring and contact information.

[CalDAV](http://caldav.calconnect.org/) is an Internet standard allowing a client to access scheduling information on a remote server. It extends the WebDAV (an HTTP-based protocol for data manipulation) specification and uses the iCalendar format for the data. The protocol is defined by [RFC 4791](http://www.ietf.org/rfc/rfc4791.txt). It allows multiple clients access to the same information thus allowing cooperative planning and information sharing. Many server and client applications support the protocol.

[CardDAV](http://carddav.calconnect.org/) is an address book client/server protocol designed to allow users to access and share contact data on a server. The CardDAV protocol is defined by [RFC 6352](http://www.ietf.org/rfc/rfc6352.txt).

The sources are available under the terms of the [Apache License, Version 2.0](http://www.apache.org/licenses/LICENSE-2.0.html).

Sub-projects
============

The following sub-projects are hosted with CalendarServer:

-   [CalDAVClientLibrary](https://trac.calendarserver.org/wiki/CalDAVClientLibrary)
-   [CalDAVTester](https://trac.calendarserver.org/wiki/CalDAVTester)
-   [PyCalendar](https://trac.calendarserver.org/wiki/PyCalendar)
-   [PyKerberos](https://trac.calendarserver.org/wiki/PyKerberos)
-   [twext](https://trac.calendarserver.org/wiki/twext)

What To Download
================

-   If you would like to get involved with Calendar and Contacts Server development, see the [QuickStart](https://trac.calendarserver.org/wiki/QuickStart) page for how to check out trunk. All submitted diffs should be against current trunk.
-   If you would like to download a version of Calendar and Contacts Server to run on a server, look at this list of [release branches](https://svn.calendarserver.org/repository/calendarserver/CalendarServer/tags/release/). Find the most recent branch in the list, and then download it by running:

        $ svn checkout https://svn.calendarserver.org/repository/calendarserver/CalendarServer/tags/release/CalendarServer-X.Y

    in a shell.

Documentation
=============

-   [FAQ](https://trac.calendarserver.org/wiki/FAQ)

<!-- -->

-   [CalendarServer trunk (current development branch)](https://trac.calendarserver.org/wiki/docs-trunk)

<!-- -->

-   [Client and Admin tool Library](https://trac.calendarserver.org/wiki/CalDAVClientLibrary)

<!-- -->

-   [Configuring clients for use with the Calendar Server](https://trac.calendarserver.org/wiki/CalendarClients)
-   [Other CalDAV Server Implementations](https://trac.calendarserver.org/wiki/CalDAVServers)
-   [CalDAV Server Test & Performance Suite](https://trac.calendarserver.org/wiki/CalDAVTester)

Getting Involved
================

-   [Mailing lists](https://trac.calendarserver.org/wiki/MailLists)
-   [IRC channels](https://trac.calendarserver.org/wiki/IRC)
-   [Twitter](http://twitter.com/calendarserver/)

External Links
==============

-   [The CalDAV Home Page](http://caldav.calconnect.org)
-   [The CardDAV Home Page](http://carddav.calconnect.org)
-   [The Calendaring and Scheduling Consortium](http://calconnect.org)
-   [IETF Calendaring and Scheduling Standards Simplification Working Group](http://tools.ietf.org/wg/calsify/)
-   [IETF vCard and CardDAV Working Group](http://tools.ietf.org/wg/vcarddav/)
