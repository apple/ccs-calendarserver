from Cocoa import NSDate
from CalendarStore import CalCalendarStore

store = CalCalendarStore.defaultCalendarStore()
calendars = store.calendars()
predicate = CalCalendarStore.eventPredicateWithStartDate_endDate_calendars_(
    NSDate.date(), NSDate.distantFuture(),
    [calendars[2]])
print store.eventsWithPredicate_(predicate)
