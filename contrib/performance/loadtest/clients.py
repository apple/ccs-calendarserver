from caldavclientlibrary.protocol.webdav.definitions import davxml

from contrib.performance.loadtest.ical import BaseAppleClient

from pycalendar.datetime import DateTime

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from twisted.python.filepath import FilePath

def loadRequestBody(clientType, label):
    return FilePath(__file__).sibling('request-data').child(clientType).child(label + '.request').getContent()

class iOS_5(BaseAppleClient):
    """
    Implementation of the iOS 5 network behavior.
    """

    _client_type = "iOS 5"

    USER_AGENT = "iOS/5.1 (9B179) dataaccessd/1.0"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by Snow
    # Leopard iCal.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60

    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 50

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = False

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = False

    # Request body data
    _LOAD_PATH = "iOS_5"

    _STARTUP_WELL_KNOWN = loadRequestBody(_LOAD_PATH, 'startup_well_known')
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind_initial')
    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody(_LOAD_PATH, 'startup_principals_report')
    _STARTUP_PROPPATCH_CALENDAR_COLOR = loadRequestBody(_LOAD_PATH, 'startup_calendar_color_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_ORDER = loadRequestBody(_LOAD_PATH, 'startup_calendar_order_proppatch')

    _POLL_CALENDARHOME_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendarhome_propfind')
    _POLL_CALENDAR_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_CALENDAR_VEVENT_TR_QUERY = loadRequestBody(_LOAD_PATH, 'poll_calendar_vevent_tr_query')
    _POLL_CALENDAR_VTODO_QUERY = loadRequestBody(_LOAD_PATH, 'poll_calendar_vtodo_query')
    _POLL_CALENDAR_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind_d1')
    _POLL_CALENDAR_MULTIGET_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget')
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget_hrefs')

    @inlineCallbacks
    def _pollFirstTime1(self, homeNode, calendars):
        # Patch calendar properties
        for cal in calendars:
            if cal.name != "inbox":
                yield self._proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_COLOR,
                    method_label="PROPPATCH{calendar}",
                )
                yield self._proppatch(
                    cal.url,
                    self._STARTUP_PROPPATCH_CALENDAR_ORDER,
                    method_label="PROPPATCH{calendar}",
                )


    def _pollFirstTime2(self):
        # Nothing here
        return succeed(None)


    def _updateCalendar(self, calendar, newToken):
        """
        Update the local cached data for a calendar in an appropriate manner.
        """
        if calendar.name == "inbox":
            # Inbox is done as a PROPFIND Depth:1
            return self._updateCalendar_PROPFIND(calendar, newToken)
        elif "VEVENT" in calendar.componentTypes:
            # VEVENTs done as time-range VEVENT-only queries
            return self._updateCalendar_VEVENT(calendar, newToken)
        elif "VTODO" in calendar.componentTypes:
            # VTODOs done as VTODO-only queries
            return self._updateCalendar_VTODO(calendar, newToken)


    @inlineCallbacks
    def _updateCalendar_VEVENT(self, calendar, newToken):
        """
        Sync all locally cached VEVENTs using a VEVENT-only time-range query.
        """

        # Grab old hrefs prior to the PROPFIND so we sync with the old state. We need this because
        # the sim can fire a PUT between the PROPFIND and when process the removals.
        old_hrefs = set([calendar.url + child for child in calendar.events.keys()])

        now = DateTime.getNowUTC()
        now.setDateOnly(True)
        now.offsetMonth(-1) # 1 month back default
        result = yield self._report(
            calendar.url,
            self._POLL_CALENDAR_VEVENT_TR_QUERY % {"start-date": now.getText()},
            depth='1',
            method_label="REPORT{vevent}",
        )

        yield self._updateApplyChanges(calendar, result, old_hrefs)

        # Now update calendar to the new token
        self._calendars[calendar.url].changeToken = newToken


    @inlineCallbacks
    def _updateCalendar_VTODO(self, calendar, newToken):
        """
        Sync all locally cached VTODOs using a VTODO-only query.
        """

        # Grab old hrefs prior to the PROPFIND so we sync with the old state. We need this because
        # the sim can fire a PUT between the PROPFIND and when process the removals.
        old_hrefs = set([calendar.url + child for child in calendar.events.keys()])

        result = yield self._report(
            calendar.url,
            self._POLL_CALENDAR_VTODO_QUERY,
            depth='1',
            method_label="REPORT{vtodo}",
        )

        yield self._updateApplyChanges(calendar, result, old_hrefs)

        # Now update calendar to the new token
        self._calendars[calendar.url].changeToken = newToken


    @inlineCallbacks
    def startup(self):

        # Try to read data from disk - if it succeeds self.principalURL will be set
        self.deserialize()

        if self.principalURL is None:
            # PROPFIND well-known with redirect
            response = yield self._startupPropfindWellKnown()
            hrefs = response.getHrefProperties()
            if davxml.current_user_principal in hrefs:
                self.principalURL = hrefs[davxml.current_user_principal].toString()
            elif davxml.principal_URL in hrefs:
                self.principalURL = hrefs[davxml.principal_URL].toString()
            else:
                # PROPFIND principal path to retrieve actual principal-URL
                response = yield self._principalPropfindInitial(self.record.uid)
                hrefs = response.getHrefProperties()
                self.principalURL = hrefs[davxml.principal_URL].toString()

        # Using the actual principal URL, retrieve principal information
        principal = yield self._extractPrincipalDetails()
        returnValue(principal)



class OS_X_10_6(BaseAppleClient):
    """
    Implementation of the OS X 10.6 iCal network behavior.

    Anything OS X 10.6 iCal does on its own, or any particular
    network behaviors it takes in response to a user action, belong on
    this class.

    Usage-profile based behaviors ("the user modifies an event every
    3.2 minutes") belong elsewhere.
    """

    _client_type = "OS X 10.6"

    USER_AGENT = "DAVKit/4.0.3 (732); CalendarStore/4.0.3 (991); iCal/4.0.3 (1388); Mac OS X/10.6.4 (10F569)"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by Snow
    # Leopard iCal.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60

    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 200

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = False

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = True

    # Request body data
    _LOAD_PATH = "OS_X_10_6"

    _STARTUP_WELL_KNOWN = loadRequestBody(_LOAD_PATH, 'startup_well_known')
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind_initial')
    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody(_LOAD_PATH, 'startup_principals_report')
    _STARTUP_PRINCIPAL_EXPAND = loadRequestBody(_LOAD_PATH, 'startup_principal_expand')
    _STARTUP_PROPPATCH_CALENDAR_COLOR = loadRequestBody(_LOAD_PATH, 'startup_calendar_color_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_ORDER = loadRequestBody(_LOAD_PATH, 'startup_calendar_order_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_TIMEZONE = loadRequestBody(_LOAD_PATH, 'startup_calendar_timezone_proppatch')

    _POLL_CALENDARHOME_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendarhome_propfind')
    _POLL_CALENDAR_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_CALENDAR_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind_d1')
    _POLL_CALENDAR_MULTIGET_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget')
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget_hrefs')
    _POLL_CALENDAR_SYNC_REPORT = None
    _POLL_NOTIFICATION_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_NOTIFICATION_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_notification_propfind_d1')

    _USER_LIST_PRINCIPAL_PROPERTY_SEARCH = loadRequestBody(_LOAD_PATH, 'user_list_principal_property_search')
    _POST_AVAILABILITY = loadRequestBody(_LOAD_PATH, 'post_availability')

    @inlineCallbacks
    def startup(self):

        # Try to read data from disk - if it succeeds self.principalURL will be set
        self.deserialize()

        if self.principalURL is None:
            # PROPFIND principal path to retrieve actual principal-URL
            response = yield self._principalPropfindInitial(self.record.uid)
            hrefs = response.getHrefProperties()
            self.principalURL = hrefs[davxml.principal_URL].toString()

        # Using the actual principal URL, retrieve principal information
        principal = (yield self._extractPrincipalDetails())
        returnValue(principal)



class OS_X_10_7(BaseAppleClient):
    """
    Implementation of the OS X 10.7 iCal network behavior.
    """

    _client_type = "OS X 10.7"

    USER_AGENT = "CalendarStore/5.0.2 (1166); iCal/5.0.2 (1571); Mac OS X/10.7.3 (11D50)"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by Snow
    # Leopard iCal.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60

    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 50

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = True

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = True

    # Request body data
    _LOAD_PATH = "OS_X_10_7"

    _STARTUP_WELL_KNOWN = loadRequestBody(_LOAD_PATH, 'startup_well_known')
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind_initial')
    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody(_LOAD_PATH, 'startup_principals_report')
    _STARTUP_PRINCIPAL_EXPAND = loadRequestBody(_LOAD_PATH, 'startup_principal_expand')
    _STARTUP_PROPPATCH_CALENDAR_COLOR = loadRequestBody(_LOAD_PATH, 'startup_calendar_color_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_ORDER = loadRequestBody(_LOAD_PATH, 'startup_calendar_order_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_TIMEZONE = loadRequestBody(_LOAD_PATH, 'startup_calendar_timezone_proppatch')

    _POLL_CALENDARHOME_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendarhome_propfind')
    _POLL_CALENDAR_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_CALENDAR_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind_d1')
    _POLL_CALENDAR_MULTIGET_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget')
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = loadRequestBody(_LOAD_PATH, 'poll_calendar_multiget_hrefs')
    _POLL_CALENDAR_SYNC_REPORT = loadRequestBody(_LOAD_PATH, 'poll_calendar_sync')
    _POLL_NOTIFICATION_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_NOTIFICATION_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_notification_propfind_d1')

    _USER_LIST_PRINCIPAL_PROPERTY_SEARCH = loadRequestBody(_LOAD_PATH, 'user_list_principal_property_search')
    _POST_AVAILABILITY = loadRequestBody(_LOAD_PATH, 'post_availability')


    @inlineCallbacks
    def startup(self):

        # Try to read data from disk - if it succeeds self.principalURL will be set
        self.deserialize()

        if self.principalURL is None:
            # PROPFIND well-known with redirect
            response = yield self._startupPropfindWellKnown()
            hrefs = response.getHrefProperties()
            if davxml.current_user_principal in hrefs:
                self.principalURL = hrefs[davxml.current_user_principal].toString()
            elif davxml.principal_URL in hrefs:
                self.principalURL = hrefs[davxml.principal_URL].toString()
            else:
                # PROPFIND principal path to retrieve actual principal-URL
                response = yield self._principalPropfindInitial(self.record.uid)
                hrefs = response.getHrefProperties()
                self.principalURL = hrefs[davxml.principal_URL].toString()

        # Using the actual principal URL, retrieve principal information
        principal = yield self._extractPrincipalDetails()
        returnValue(principal)



class OS_X_10_11(BaseAppleClient):
    """
    Implementation of the OS X 10.11 Calendar.app network behavior.
    """

    _client_type = "OS X 10.11"

    USER_AGENT = "Mac+OS+X/10.11 (15A216g) CalendarAgent/353"

    # The default interval, used if none is specified in external
    # configuration.  This is also the actual value used by El
    # Capital Calendar.app.
    CALENDAR_HOME_POLL_INTERVAL = 15 * 60  # in seconds

    # The maximum number of resources to retrieve in a single multiget
    MULTIGET_BATCH_SIZE = 50

    # Override and turn on if client supports Sync REPORT
    _SYNC_REPORT = True

    # Override and turn off if client does not support attendee lookups
    _ATTENDEE_LOOKUPS = True

    # Request body data
    _LOAD_PATH = "OS_X_10_11"

    _STARTUP_WELL_KNOWN = loadRequestBody(_LOAD_PATH, 'startup_well_known_propfind')
    _STARTUP_PRINCIPAL_PROPFIND_INITIAL = loadRequestBody(_LOAD_PATH, 'startup_principal_initial_propfind')
    _STARTUP_PRINCIPAL_PROPFIND = loadRequestBody(_LOAD_PATH, 'startup_principal_propfind')
    _STARTUP_PRINCIPALS_REPORT = loadRequestBody(_LOAD_PATH, 'startup_principals_report')
    # _STARTUP_PRINCIPAL_EXPAND = loadRequestBody(_LOAD_PATH, 'startup_principal_expand')

    _STARTUP_CREATE_CALENDAR = loadRequestBody(_LOAD_PATH, 'startup_create_calendar')
    _STARTUP_PROPPATCH_CALENDAR_COLOR = loadRequestBody(_LOAD_PATH, 'startup_calendar_color_proppatch')
    # _STARTUP_PROPPATCH_CALENDAR_NAME = loadRequestBody(_LOAD_PATH, 'startup_calendar_displayname_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_ORDER = loadRequestBody(_LOAD_PATH, 'startup_calendar_order_proppatch')
    _STARTUP_PROPPATCH_CALENDAR_TIMEZONE = loadRequestBody(_LOAD_PATH, 'startup_calendar_timezone_proppatch')

    _POLL_CALENDARHOME_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendarhome_depth1_propfind')
    _POLL_CALENDAR_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_CALENDAR_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_calendar_depth1_propfind')
    _POLL_CALENDAR_MULTIGET_REPORT = loadRequestBody('OS_X_10_7', 'poll_calendar_multiget')
    _POLL_CALENDAR_MULTIGET_REPORT_HREF = loadRequestBody('OS_X_10_7', 'poll_calendar_multiget_hrefs')
    _POLL_CALENDAR_SYNC_REPORT = loadRequestBody('OS_X_10_7', 'poll_calendar_sync')
    _POLL_NOTIFICATION_PROPFIND = loadRequestBody(_LOAD_PATH, 'poll_calendar_propfind')
    _POLL_NOTIFICATION_PROPFIND_D1 = loadRequestBody(_LOAD_PATH, 'poll_notification_depth1_propfind')

    _USER_LIST_PRINCIPAL_PROPERTY_SEARCH = loadRequestBody('OS_X_10_7', 'user_list_principal_property_search')
    _POST_AVAILABILITY = loadRequestBody('OS_X_10_7', 'post_availability')

    _CALENDARSERVER_PRINCIPAL_SEARCH_REPORT = loadRequestBody(_LOAD_PATH, 'principal_search_report')

    @inlineCallbacks
    def startup(self):
        # Try to read data from disk - if it succeeds self.principalURL will be set
        self.deserialize()

        if self.principalURL is None:
            # print("No cached principal URL found - starting from scratch")
            # PROPFIND well-known with redirect
            response = yield self._startupPropfindWellKnown()
            hrefs = response.getHrefProperties()
            if davxml.current_user_principal in hrefs:
                self.principalURL = hrefs[davxml.current_user_principal].toString()
            elif davxml.principal_URL in hrefs:
                self.principalURL = hrefs[davxml.principal_URL].toString()
            else:
                # PROPFIND principal path to retrieve actual principal-URL
                response = yield self._principalPropfindInitial(self.record.uid)
                hrefs = response.getHrefProperties()
                self.principalURL = hrefs[davxml.principal_URL].toString()
        # print("Principal URL: " + self.principalURL)

        # Using the actual principal URL, retrieve principal information
        principal = yield self._extractPrincipalDetails()
        # print("Principal: " + str(principal))
        returnValue(principal)
