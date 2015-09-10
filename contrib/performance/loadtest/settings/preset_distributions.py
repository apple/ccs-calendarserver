from contrib.performance.loadtest.distributions import WorkDistribution, RecurrenceDistribution

STANDARD_WORK_DISTRIBUTION = WorkDistribution(
    daysOfWeek=["mon", "tue", "wed", "thu", "fri"],
    beginHour=8,
    endHour=16,
    tzname="America/Los_Angeles"
)

LOW_RECURRENCE_DISTRIBUTION = RecurrenceDistribution(
    allowRecurrence=True,
    weights={
        "none": 50,
        "daily": 25,
        "weekly": 25,
        "monthly": 0,
        "yearly": 0,
        "dailylimit": 0,
        "weeklylimit": 0,
        "workdays": 0
    }
)

MEDIUM_RECURRENCE_DISTRIBUTION = RecurrenceDistribution(
    allowRecurrence=True,
    weights={
        "none": 50,
        "daily": 10,
        "weekly": 20,
        "monthly": 2,
        "yearly": 1,
        "dailylimit": 2,
        "weeklylimit": 5,
        "workdays": 10
    }
)