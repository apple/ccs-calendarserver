from twisted.application.reactors import Reactor

caldav_kqueue = Reactor(
    'caldav_kqueue', 'kqreactor',
    'kqueue(2)-based reactor.')
