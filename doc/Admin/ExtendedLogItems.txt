Apache-style Access Log Extensions
==================================

Calendar Server extends the Apache log file format it uses by:

 * Adding a "sub-method" to the HTTP method field.
 * Adding key-value pairs at the end of log lines.

The sub-method is adding by appending the name of the sub-method in
parentheses to the original HTTP request method.  This is used to
clarify what operation is going on for HTTP methods that are commonly
used to tunnel other operations, such as ``POST`` and ``REPORT``.  For
example, CalDAV uses ``POST`` for free/busy lookups, and ``REPORT``
can be used to make any sort of query.

Key-value pairs are used to provide additional details about the
request.  They are added to the end of the line as new fields in the
form ``key=value``.

These keys are always emitted:

  ``i``

    the port number of the server instance emitting the log

  ``t``

    the amount of time spent processing the request (in milliseconds).

  ``or``

    the number of outstanding requests enqueued for the server
    instance emitting the log entry.

Keys that may be emitted depending on the client request and server
response include:

  ``rcount``

    the number of resources specified in a ``MULTIGET`` request.

  ``responses``

    the number of responses included in a ``multi-status`` response to
    a ``PROPFIND`` request or a CalDAV ``calendar-query`` request.

  ``recipients``

    the number of recipients in a CalDAV scheduling request via
    ``POST`` (which are typically only free/busy requests).

  ``itip.requests``

    the number of attendees in a scheduling operation triggered by an
    Organizer.

  ``itip.refreshes``

    the number of attendee refreshes completed after a scheduling
    operation.

  ``itip.auto``

    the number of auto-accept attendees specified

  ``itip.reply``

    Either ``reply`` or ``cancel`` depending on...???

  ``fwd``

    the value of the X-Forwarded-For header, if present

In the following example, we see a ``CalDAV:calendar-multiget``
``REPORT`` for 32 resources in a user's calendar, which was handled by
instance ``8459`` in 183.0ms, with one outstanding request (the one
being logged):

::

  17.108.160.37 - scastillo [15/Sep/2009:20:10:23 +0000] "REPORT(CalDAV:calendar-multiget) /calendars/__uids__/B8CE9430-965B-11DE-B626-EC2E9DB52B69/calendar/ HTTP/1.1" 207 149285 "-" "DAVKit/4.0 (729); CalendarStore/4.0 (965); iCal/4.0 (1362); Mac OS X/10.6.1 (10B504)" i=8459 t=183.0 or=1 rcount=32



**Fine-grained request time logging**

If the configuration key EnableExtendedTimingAccessLog is set to true, additional key-value pairs will be logged with each request. The overall request time "t" is broken into four phases, and the elapsed time for each phase is logged. The new keys representing the four request phases are:

  ``t-req-proc``

    time elapsed from when a request object is created up until renderHTTP is about to be called.
    This is the overhead of parsing the request headers and locating the target resource.

  ``t-resp-gen``

    time elapsed from t-req-proc up until the response is ready to write

  ``t-resp-wr``

    time elapsed from t-resp-gen up until response is written

  ``t-log``

    time from t-resp-wr up until log entry is ready to write to master

A sample log line with EnableExtendedTimingAccessLog enabled is shown below:

::

  17.209.103.42 - wsanchez [24/Jul/2012:17:51:29 +0000] "REPORT(CalDAV:calendar-multiget) /calendars/__uids__/F114CA1D-295F-42A5-A5BD-D1A1B19FC049/60E68E32-4C87-4E63-9BF2-12A25E8F2623/ HTTP/1.1" 207 114349 "-" "CalendarStore/5.0.2 (1166); iCal/5.0.2 (1571); Mac OS X/10.7.3 (11D50d)" i=7 or=1 t=764.7 t-req-proc=4.8 t-resp-gen=754.5 t-resp-wr=5.1 t-log=0.2 rcount=2