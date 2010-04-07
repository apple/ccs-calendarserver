from twisted.application.reactors import Reactor

caldav_kqueue = Reactor(
    'caldav_kqueue', 'twext.internet.kqreactor',
    'kqueue(2)-based reactor.')
