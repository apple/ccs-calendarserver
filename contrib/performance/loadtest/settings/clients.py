from contrib.performance.loadtest.clients import iOS_5, OS_X_10_6, OS_X_10_7, OS_X_10_11
from contrib.performance.loadtest.profiles import (
    Eventer, EventDeleter,
    Titler,
    Inviter, Emptier,
    Tasker, TaskDeleter,
    TaskTitler, TaskNoter, Completer, Prioritizer,

    CalendarMaker, CalendarUpdater, CalendarSharer, CalendarDeleter
)
from contrib.performance.loadtest.distributions import FixedDistribution, BernoulliDistribution, NormalDistribution


from preset_distributions import STANDARD_WORK_DISTRIBUTION, LOW_RECURRENCE_DISTRIBUTION, MEDIUM_RECURRENCE_DISTRIBUTION

config = [
    {
        "software": OS_X_10_11,
        #     title="10.11",
        #     calendarHomePollInterval=5,
        #     supportAmpPush=True,
        #     ampPushHost="localhost",
        #     ampPushPort62311
        # )
        "params": {
            "title": "10.11",
            "calendarHomePollInterval": 5,
            "supportAmpPush": True,
            "ampPushHost": "localhost",
            "ampPushPort": 62311
        },
        "profiles": [
            Eventer(enabled=True, interval=0.1, eventStartDistribution=STANDARD_WORK_DISTRIBUTION),
            Emptier(enabled=True, interval=5),
            # Titler(enabled=True, interval=1, titleLengthDistribution=FixedDistribution(10)),
            Inviter(enabled=True, interval=1, numInviteesDistribution=NormalDistribution(7, 2)),

            # Tasker(enabled=False, interval=1),
            # Completer(enabled=True, interval=0.5, completeLikelihood=BernoulliDistribution(0.5)),
            # Prioritizer(enabled=True, interval=0.1),
            # TaskTitler(enabled=True, interval=1),
            # TaskNoter(enabled=True, interval=1),
            # TaskDeleter(enabled=True, interval=1),

            # CalendarMaker(enabled=True, interval=1),
            # CalendarUpdater(enabled=True, interval=5),
            # CalendarSharer(enabled=True, interval=30),
            # CalendarDeleter(false=True, interval=30)
        ],
        "weight": 3
    }
]

# # TBD what about multiple weights?
# calendars_only_ideal = [
#     OS_X_10_11(
#         title="10.11",
#         calendarHomePollInterval=5,
#         supportAmpPush=True,
#         ampPushHost="localhost",
#         ampPushPort=62311,
#         profiles=[
#             CalendarMaker(enabled=True, interval=15),
#             # CalendarUpdater(enabled=True, interval=5),
#             # CalendarSharer(enabled=False, interval=30),
#             # CalendarDeleter(enabled=False, interval=30)
#         ]
#     )
# ]

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
