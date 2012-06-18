from twisted.application import service
from calendarserver.tap.caldav import ReExecService

class TestService(service.Service):
    def startService(self):
        print "START"
    def stopService(self):
        print "STOP"

application = service.Application("ReExec Tester")
reExecService = ReExecService("twistd.pid")
reExecService.setServiceParent(application)
testService = TestService()
testService.setServiceParent(reExecService)
