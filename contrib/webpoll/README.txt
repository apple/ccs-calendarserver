WebPoll Package for CalendarServer
==================================

*** IMPORTANT: this a prototype/demo and is not intended for production use
 
WebPoll is a set of webbrowser javascript files that implement a prototype webapp for
a client that supports the new iCalendar VPOLL component for doing "consensus" scheduling
- i.e., a scheduling process where users can vote on which of a series of potential events
are best for them. The VPOLL technology has been developed by CalConnect to open up new
methods of scheduling with iCalendar that allows for not only polls, but potentially
booking systems and much more.

The WebPoll webapp uses jQuery and jQueryUI (which have to be downloaded separately). It
uses AJAX calls to make CalDAV queries to the server hosting the webapp. The CalDAV server
must support jCal (iCalendar-in-JSON) format calendar data.

Use with CalendarServer
=======================

Use "make webpoll" in this directory to download all the relevant dependencies.

In the CalendarServer directory do "./run -f ./contrib/webpoll/caldavd-test-webpoll.plist" to run the server.

In a browser navigate to "/webpoll".

Using the webapp
================

TBD
