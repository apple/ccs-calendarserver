
class Subscription(object):
    def __init__(self, periodical, subscriber):
        self.periodical = periodical
        self.subscriber = subscriber


    def cancel(self):
        self.periodical.subscriptions.remove(self)


    def issue(self, issue):
        self.subscriber(issue)



class Periodical(object):
    def __init__(self):
        self.subscriptions = []


    def subscribe(self, who):
        subscription = Subscription(self, who)
        self.subscriptions.append(subscription)
        return subscription


    def issue(self, issue):
        for subscr in self.subscriptions:
            subscr.issue(issue)
