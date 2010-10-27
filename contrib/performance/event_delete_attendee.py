
import _event_change

def measure(host, port, dtrace, attendeeCount, samples):
    def deleteAttendees(event, i):
        """
        Add C{i} new attendees to the given event.
        """
        for n in range(attendeeCount):
            # Find the beginning of an ATTENDEE line
            attendee = event.find('ATTENDEE')
            # And the end of it
            eol = event.find('\n', attendee)
            # And remove it
            event = event[:attendee] + event[eol:]
        return event

    return _event_change.measure(
        host, port, dtrace, attendeeCount, samples, "delete-attendee",
        deleteAttendees, eventPerSample=True)
