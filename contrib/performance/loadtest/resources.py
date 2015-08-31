from twistedcaldav.ical import Component

from urlparse import urljoin

from caldavclientlibrary.protocol.caldav.definitions import caldavxml

from caldavclientlibrary.protocol.calendarserver.invite import AddInvitees, RemoveInvitee, InviteUser
from caldavclientlibrary.protocol.webdav.proppatch import PropPatch

import os

from xml.etree import ElementTree

def u2str(data):
    return data.encode("utf-8") if type(data) is unicode else data


class Event(object):
    def __init__(self, serializeBasePath, url, etag, component=None):
        self.serializeBasePath = serializeBasePath
        self.url = url
        self.etag = etag
        self.scheduleTag = None
        if component is not None:
            self.component = component
        self.uid = component.resourceUID() if component is not None else None

    def getUID(self):
        """
        Return the UID of the calendar resource.
        """
        return self.uid


    def serializePath(self):
        if self.serializeBasePath:
            calendar = os.path.join(self.serializeBasePath, self.url.split("/")[-2])
            if not os.path.exists(calendar):
                os.makedirs(calendar)
            return os.path.join(calendar, self.url.split("/")[-1])
        else:
            return None


    def serialize(self):
        """
        Create a dict of the data so we can serialize as JSON.
        """

        result = {}
        for attr in ("url", "etag", "scheduleTag", "uid",):
            result[attr] = getattr(self, attr)
        return result


    @staticmethod
    def deserialize(serializeLocation, data):
        """
        Convert dict (deserialized from JSON) into an L{Event}.
        """

        event = Event(serializeLocation, None, None)
        for attr in ("url", "etag", "scheduleTag", "uid",):
            setattr(event, attr, u2str(data[attr]))
        return event


    @property
    def component(self):
        """
        Data always read from disk - never cached in the object.
        """
        path = self.serializePath()
        if path and os.path.exists(path):
            f = open(path)
            comp = Component.fromString(f.read())
            f.close()
            return comp
        else:
            return None


    @component.setter
    def component(self, component):
        """
        Data always written to disk - never cached on the object.
        """
        path = self.serializePath()
        if path:
            if component is None:
                os.remove(path)
            else:
                f = open(path, "w")
                f.write(str(component))
                f.close()
        self.uid = component.resourceUID() if component is not None else None


    def removed(self):
        """
        Resource no longer exists on the server - remove associated data.
        """
        path = self.serializePath()
        if path and os.path.exists(path):
            os.remove(path)



class Calendar(object):
    def __init__(self, resourceType, componentTypes, name, url, changeToken):
        self.resourceType = resourceType
        self.componentTypes = componentTypes
        self.name = name
        self.url = url
        self.changeToken = changeToken
        self.events = {}


    def serialize(self):
        """
        Create a dict of the data so we can serialize as JSON.
        """

        result = {}
        for attr in ("resourceType", "name", "url", "changeToken"):
            result[attr] = getattr(self, attr)
        result["componentTypes"] = list(sorted(self.componentTypes))
        result["events"] = sorted(self.events.keys())
        return result


    @staticmethod
    def deserialize(data, events):
        """
        Convert dict (deserialized from JSON) into an L{Calendar}.
        """

        calendar = Calendar(None, None, None, None, None)
        for attr in ("resourceType", "name", "url", "changeToken"):
            setattr(calendar, attr, u2str(data[attr]))
        calendar.componentTypes = set(map(u2str, data["componentTypes"]))

        for event in data["events"]:
            url = urljoin(calendar.url, event)
            if url in events:
                calendar.events[event] = events[url]
            else:
                # Ughh - an event is missing - force changeToken to empty to trigger full resync
                calendar.changeToken = ""
        return calendar


    @staticmethod
    def addInviteeXML(uid, summary, readwrite=True):
        return AddInvitees(None, '/', [uid], readwrite, summary=summary).request_data.text


    @staticmethod
    def removeInviteeXML(uid):
        invitee = InviteUser()
        # Usually an InviteUser is populated through .parseFromUser, but we only care about a uid
        invitee.user_uid = uid
        return RemoveInvitee(None, '/', invitee).request_data.text


    @staticmethod
    def _buildPropPatchXML(element):
        """
        Change the specified element on the calendar given by href.
        """
        return PropPatch(None, '/', [element]).request_data.text


    # def setCalendarDisplayName(self, calendar, displayname):
    #     self._calendars[calendar.url].displayname = displayname # Update the cached copy
    #     qn = davxml.displayname
    #     el = ElementTree.Element(qn)
    #     el.text = displayname
    #     yield self._property_update(el)

    @staticmethod
    def setCalendarDescriptionXML(calendar, description):
        qn = caldavxml.calendar_description
        el = ElementTree.Element(qn)
        el.text = description
        return Calendar._buildPropPatchXML(el)


    @staticmethod
    def setCalendarTransparencyXML(calendar, isTransparent):
        qn = caldavxml.schedule_calendar_transp
        el = ElementTree.Element(qn)
        transp_qn = caldavxml.transparent if isTransparent else caldavxml.opaque
        ElementTree.SubElement(el, transp_qn)
        return Calendar._buildPropPatchXML(el)


    @staticmethod
    def setCalendarColorXML(calendar, color):
        """ color is an RGBA string, e.g. "#FF0088FF" """
        qn = ElementTree.QName('http://apple.com/ns/ical/', 'calendar-color')
        el = ElementTree.Element(qn)
        el.text = color
        el.set('symbolic-color', 'custom')
        return Calendar._buildPropPatchXML(el)


    @staticmethod
    def setCalendarOrder(self, calendar, order):
        qn = ElementTree.QName('http://apple.com/ns/ical/', 'calendar-order')
        el = ElementTree.Element(qn)
        el.text = order
        return Calendar._buildPropPatchXML(el)
