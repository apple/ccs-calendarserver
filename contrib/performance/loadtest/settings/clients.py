from contrib.performance.loadtest.clients import iOS_5, OS_X_10_6, OS_X_10_7, OS_X_10_11
from contrib.performance.loadtest.profiles import CalendarMaker, CalendarUpdater, CalendarSharer, CalendarDeleter
from contrib.performance.loadtest.distributions import WorkDistribution, RecurrenceDistribution

from contrib.performance.loadtest.population import ProfileType


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

# We have to roll our own deep copy method because you can't deep copy Twisted's reactor
class ClientFactory(object):

    def __init__(self, client, weight):
        pass

    @staticmethod
    def _duplicateClient(client):
        return type(client)(
            # some params
        )

    def new(reactor, ):
        pass

class ProfileFactory(object):
    def __init__(self, profile):
        pass

    @staticmethod
    def _duplicateProfile(profile):
        return type(profile)()

calendars_only = [
    {
        "software": OS_X_10_11,
        "params": {
            "title": "10.11",
            "calendarHomePollInterval": 5,
            "supportAmpPush": True,
            "ampPushHost": "localhost",
            "ampPushPort": 62311
        },
        "profiles": [
            ProfileType(CalendarMaker, dict(enabled=True, interval=15)),

            # CalendarMaker(enabled=True, interval=15),
            # CalendarUpdater(enabled=True, interval=5),
            # CalendarSharer(enabled=True, interval=30),
            # CalendarDeleter(false=True, interval=30)
        ],
        "weight": 1
    }
]

# TBD what about multiple weights?
calendars_only_ideal = [
    OS_X_10_11(
        title="10.11",
        calendarHomePollInterval=5,
        supportAmpPush=True,
        ampPushHost="localhost",
        ampPushPort=62311,
        profiles=[
            CalendarMaker(enabled=True, interval=15),
            # CalendarUpdater(enabled=True, interval=5),
            # CalendarSharer(enabled=False, interval=30),
            # CalendarDeleter(enabled=False, interval=30)
        ]
    )
]

# event_updates_only = [
#     {
#         "software": OS_X_10_11,
#         "params": {
#             "title": "10.11",
#             "calendarHomePollInterval": 5,
#             "supportAmpPush": True,
#             "ampPushHost": "localhost",
#             "ampPushPort": 62311
#         },
#         "profiles": [
#             ProfileType(Eventer, dict(
#                 enabled=False,
#                 interval=20,
#                 eventStartDistribution=STANDARD_WORK_DISTRIBUTION,
#                 recurrenceDistribution=MEDIUM_RECURRENCE_DISTRIBUTION
#             )),
#             ProfileType(EventerUpdater, dict(
#                 enabled=True,
#                 interval=5,
#                 eventStartDistribution=STANDARD_WORK_DISTRIBUTION,
#                 recurrenceDistribution=LOW_RECURRENCE_DISTRIBUTION
#             )),
#             ProfileType(RealisticInviter, dict(
#                 enabled=False,
#                 sendInvitationDistribution=LogNormalDistribution(mu=10, sigma=5),
#                 inviteeDistribution=UniformIntegerDistribution(0, 99),
#                 inviteeClumping=True,
#                 inviteeCountDistribution=LogNormalDistribution(mode=1, median=6, maximum=100),
#                 eventStartDistribution=STANDARD_WORK_DISTRIBUTION,
#                 recurrenceDistribution=MEDIUM_RECURRENCE_DISTRIBUTION
#             )),
#             ProfileType(Accepter, dict(
#                 enabled=False,
#                 acceptDelayDistribution=LogNormalDistribution(mode=300, median=1800)
#             )),
#             ProfileType(Tasker, dict(
#                 enabled=False,
#                 interval=300,
#                 taskDueDistribution=STANDARD_WORK_DISTRIBUTION
#             ))
#         ],
#         "weight": 1
#     }
# ]


# clientConfiguration = calendars_only
# __all__ = [clientConfiguration]
