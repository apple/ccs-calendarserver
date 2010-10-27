
from event import SUMMARY

import _event_change

def replaceSummary(event, i):
    return event.replace(SUMMARY, 'Replacement summary %d' % (i,))


def measure(host, port, dtrace, attendeeCount, samples):
    return _event_change.measure(
        host, port, dtrace, attendeeCount, samples, "change-summary",
        replaceSummary)
