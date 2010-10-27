
import _event_change

from event import makeAttendees


def measure(host, port, dtrace, attendeeCount, samples):
    attendees = makeAttendees(attendeeCount)

    def addAttendees(event, i):
        """
        Add C{i} new attendees to the given event.
        """
        # Find the last CREATED line
        created = event.rfind('CREATED')
        # Insert the attendees before it.
        return event[:created] + attendees + event[created:]

    return _event_change.measure(
        host, port, dtrace, 0, samples, "add-attendee",
        addAttendees, eventPerSample=True)
