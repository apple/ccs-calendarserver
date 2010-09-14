
"""
Benchmark a change in the date boundaries of an event.
"""


import datetime

import _event_change

TIME_FORMAT = '%Y%m%dT%H%M%S'

def _increment(event, marker, amount):
    # Find the last occurrence of the marker
    dtstart = event.rfind(marker)
    # Find the end of that line
    eol = event.find('\n', dtstart)
    # Find the : preceding the date on that line
    colon = event.find(':', dtstart)
    # Replace the text between the colon and the eol with the new timestamp
    old = datetime.datetime.strptime(event[colon + 1:eol], TIME_FORMAT)
    new = old + amount
    return event[:colon + 1] + new.strftime(TIME_FORMAT) + event[eol:]


def replaceTimestamp(event, i):
    offset = datetime.timedelta(hours=i)
    return _increment(
        _increment(event, 'DTSTART', offset),
        'DTEND', offset)


def measure(host, port, dtrace, attendeeCount, samples):
    return _event_change.measure(
        host, port, dtrace, attendeeCount, samples, "date", replaceTimestamp)
