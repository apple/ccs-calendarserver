---
title: QuickStart
---

**WARNING** these instructions are for running a server from the source tree, which is useful for development. These are not the correct steps for running the server in deployment or as part of an OS install. You should not be using the run script in system startup files (eg. /etc/init.d); it does things (like download software) that you don't want to happen in that context.

Begin by creating a directory to contain Calendar and Contacts Server and all its dependencies:

	mkdir ~/CalendarServer
	cd CalendarServer

Next, check out the source code from GIT. To check out the latest master code:

	git clone https://github.com/apple/ccs-calendarserver.git master

The server requires various external libraries in order to operate. The bin/develop script in the sources will retrieve these dependencies and install them to the .develop directory. Note that this behavior is currently also a side-effect of bin/run, but that is likely to change in the future:

	cd master
	bin/develop
		<<build will take place>>
	...

Pip is used to retrieve the python dependencies and stage them for use by virtualenv, however if your system does not have pip (and virtualenv), you can use bin/install_pip (or your installation / upgrade method of choice).

Before you can run the server, you need to set up a configuration file for development. There is a provided test configuration that you can use to start with, conf/caldavd-test.plist, which can be copied to conf/caldavd-dev.plist (the default config file used by the bin/run script). If conf/caldavd-dev.plist is not present when the server starts, you will be prompted to create a new one from conf/caldavd-test.plist.

You will need to choose a directory service to use to populate your server's principals (users, groups, resources, and locations). A directory service provides the Calendar and Contacts Server with information about these principals. The directory services supported by Calendar and Contacts Server are:

* XMLDirectoryService: this service is configurable via an XML file that contains principal information. The file conf/auth/accounts.xml provides an example principals configuration.

* OpenDirectoryService: this service uses Apple's OpenDirectory client, the bulk of the configuration for which is handled external to Calendar and Contacts Server (e.g. System Preferences &rarr; Users & Groups &rarr; Login Options &rarr; Network Account Server).

* LdapDirectoryService: a highly flexible LDAP client that can leverage existing LDAP servers. See twistedcaldav/stdconfig.py for the available LdapDirectoryService options and their defaults.
The caldavd-test.plist configuration uses XMLDirectoryService by default, set up to use conf/auth/accounts-test.xml. This is a generally useful configuration for development and testing.

This file contains a user principal, named admin, with password admin, which is set up (in caldavd-test.plist) to have administrative permissions on the server.

Start the server using the bin/run script, and use the -n option to bypass dependency setup:

	bin/run -n
	Using /Users/andre/CalendarServer/master/.develop/roots/py_modules/bin/python as Python
	
	Missing config file: /Users/andre/CalendarServer/master/conf/caldavd-dev.plist
	You might want to start by copying the test configuration:
	
		cp conf/caldavd-test.plist conf/caldavd-dev.plist
	
	Would you like to copy the test configuration now? [y/n]y
	Copying test cofiguration...
	
	Starting server...

The server should then start up and bind to port 8008 for HTTP and 8443 for HTTPS. You should then be able to connect to the server using your web browser (eg. Safari, Firefox) or with a CalDAV client (eg. Calendar).