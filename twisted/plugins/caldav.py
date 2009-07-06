from zope.interface import implements
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker

from twisted.python import reflect

from twisted.internet.protocol import Factory
Factory.noisy = False


def serviceMakerProperty(propname):
    def getProperty(self):
        return getattr(reflect.namedClass(self.serviceMakerClass), propname)

    return property(getProperty)


class TAP(object):
    implements(IPlugin, IServiceMaker)

    def __init__(self, serviceMakerClass):
        self.serviceMakerClass = serviceMakerClass
        self._serviceMaker = None

    options     = serviceMakerProperty("options")
    tapname     = serviceMakerProperty("tapname")
    description = serviceMakerProperty("description")

    def makeService(self, options):
        if self._serviceMaker is None:
            self._serviceMaker = reflect.namedClass(self.serviceMakerClass)()

        return self._serviceMaker.makeService(options)


TwistedCalDAV     = TAP("calendarserver.tap.caldav.CalDAVServiceMaker")
CalDAVTask        = TAP("calendarserver.sidecar.task.CalDAVTaskServiceMaker")
CalDAVNotifier    = TAP("twistedcaldav.notify.NotificationServiceMaker")
CalDAVMailGateway = TAP("twistedcaldav.mail.MailGatewayServiceMaker")
