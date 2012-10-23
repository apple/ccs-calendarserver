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

    the index number of the server instance emitting the log; corresponds to the slave number shown in process title.

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

  ``fb-cached``

    When doing free-busy queries, this is the number of calendars queried for which free-busy info was already cached

  ``fb-uncached``

    When doing free-busy queries, this is the number of calendars queried for which free-busy info was NOT already cached

  ``cl``

    Content length, in bytes

In the following example, we see a free-busy ``POST``
requesting availability for two users, which was handled by
instance ``1`` in 782.6i ms. This instance was only processing one request at the time this was logged (or=1). Of the two calendars targeted by the free-busy query, one already had free-busy info cached, while the other was not cached. (fb-cached=1, fb-uncached=1)

::

  10.1.5.43 - user5 [23/Oct/2012:13:42:56 -0700] "POST /calendars/__uids__/B2302CB9-D28F-4CB4-B3D9-0AF0FEDB8110/outbox/ HTTP/1.1" 200 1490 "-" "CalendarStore/5.0.2 (1166); iCal/5.0.2 (1571); Mac OS X/10.7.3 (11D50)" i=1 or=1 t=782.6 fb-uncached=1 fb-cached=1 recipients=2 cl=577


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
