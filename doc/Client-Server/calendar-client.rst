==========================================
Using Calendar client with Calendar Server
==========================================

OS X includes a CalDAV client called "Calendar", formerly known as iCal. As of this writing, the current OS X version is 10.8.2 Mountain Lion, and modern Calendar Server versions support old Calendar or iCal versions going back to Mac OS X 10.6.x Snow Leopard. iCal in 10.5.x Leopard and prior does not support implicit scheduling, and will not function correctly with Calendar Server 3 or later.

---------------------
Account Setup
---------------------

New CalDAV accounts for Calendar can be created either in the Calendar preferences, or in the "Mail, Contacts & Calendars" prefpane. The latter method is preferred, as it consolidates various account types into a single interface.

To add a CalDAV account using the Mail, Contacts & Calendars prefpane, follow these steps:

#. Open System Preferences and select the "Mail, Contacts & Calendars" prefpane.
#. Scroll to the bottom of the list of account types and click "Add Other Account".
#. Select "Add a CalDAV account", then click "Create...".
#. Supply a valid username, password, and server address, then click "Create".

To add a CalDAV account using Calendar preferences, follow these steps:

#. In Calendar, choose "Preferences..." from the Calendar menu.
#. Click the plus button at the bottom of the accounts list to add a new account.
#. Set the Account Type to CalDAV. Automatic might work depending on your configuration (see Discovery section), but CalDAV should always work.
#. Supply a valid user name, password, and server address.

Alternatively, CalDAV accounts for Calendar may be provisioned using the Profile Manager service in `OS X Server <http://www.apple.com/osx/server/>`_.

------------------------------------
Account Discovery Details
------------------------------------

When adding a CalDAV account in "Automatic" mode using Calendar preferences, the client looks for a `DNS SRV record for the _caldavs_tcp or _caldav_tcp services <http://tools.ietf.org/html/draft-daboo-srv-caldav-10>`_, to discover the CalDAV server for the provided domain name. If such a record is not available, Automatic setup can still succeed if the CalDAV server name is the same as the provided domain name.

Regardless of which setup mode is used, Calendar will attempt an https connection first on port 8443, and if that fails, will then attempt to connect using http on port 8008. To see a detailed log of exactly what Calendar does when discovering a new account, enable all debug logging (see below) and filter the results for "discovery".

----------------------
Push Notifications
----------------------

Calendar supports two options for push notifications: `Apple Push Notification Service <http://developer.apple.com/library/mac/#documentation/NetworkingInternet/Conceptual/RemoteNotificationsPG/ApplePushService/ApplePushService.html>`_ (APNS), or `XMPP+pubsub <https://github.com/apple/ccs-calendarserver/blob/master/doc/Extensions/caldav-pubsubdiscovery.txt>`_. Calendar will look for both of these at setup time, and will prefer APNS. Calendar Server officially supports only the XMPP+pubsub method, hosted by an external service. This configuration was commonly used in older versions of OS X Server, which includes an XMPP service.

-----------------
Troubleshooting
-----------------

Additional debug logging is available by setting the CalLogSimpleConfiguration NSUserDefaults key in the global domain. This key supports an array of values that specify different kinds of calendar logging to collect. Starting in macOS 10.12, logs are collected and managed with the `Unified Logging System <https://developer.apple.com/reference/os/1891852-logging>`_. Prior to macOS 10.12, logs are managed by `ASL <https://developer.apple.com/library/mac/#documentation/Darwin/Reference/ManPages/man3/asl.3.html>`_. In either case, these logs may be viewed with the Console utility, or the "log" command line tool (or "syslog" in <= 10.11).

To enable complete protocol logging, open Terminal and run the command:

::

  defaults write -g CalLogSimpleConfiguration -array com.apple.calendar.store.log.caldav.http

To activate the logging configuration change, quit and relaunch Calendar. For versions of OS X older than 10.12, instead of quitting and relaunching, run this command:

::

  notifyutil -p com.apple.calendar.foundation.notification.logConfigUpdated

The debug logging domains are specified using a reverse-dns style hierarchy, so to enable all Calendar logging (includes logging of account discovery), use the value 'com.apple.calendar'

To disable Calendar debug logging, run the command:

::

  defaults delete -g CalLogSimpleConfiguration

... then either restart Calendar (macOS 10.12 or newer), or run the notifyutil command again.

To view calendar debug logs collected in macOS 10.12 or newer, run the command:

::

  log show --predicate 'eventMessage contains "com.apple.calendar.store.log.caldav.http"'

For OS X 10.11 or older, use the command:

::

  syslog -k Sender CalendarAgent -o -k Sender Calendar

