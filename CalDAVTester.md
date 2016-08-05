---
title: CalDAVTester
---

CalDAVTester
============

CalDAVTester is a test and performance application designed to work with CalDAV and / or CardDAV servers and tests various aspects of their protocol handling as well as performance.

CalDAVTester basically executes HTTP requests against a server and verifies the responses returned by the server. Suites of tests are defined in xml configuration files, and an additional xml configuration file is used to define variables used whilst running (e.g., server address, user accounts to use etc).

A test suite configuration file comprises the following items:

* A start section where resources needed for the tests can be created
* A set of test suites, comprising:
  * A set of tests, each of which can have:
    * A set of HTTP request/response/verify tests.
* An end section to do clean-up after the tests are all done.

The source code to CalDAVTester is available via GIT.

## GETTING IT

CalDAVTester is automatically retrieved by CalendarServer's `bin/develop` script during its dependency resolution phase, and is stored as a sub-project of CalendarServer, along with other externally retrieved dependencies.

Alternatively, use GIT to obtain a working copy of the source code. The following command will check out the latest version of CalDAVTester:

    git clone https://github.com/apple/ccs-caldavtester.git

Graphical clients which support GIT are also available, including Apple's ​XCode IDE. Consult the documentation for your chosen client for information on how to check out source code.

## Configuring CalDAVTester

As provided, CalDAVTester is already setup to operate with a Calendar Server running on the localhost using the caldavd-test.plist configuration. No changes are needed to the configuration files to run.

CalDAVTester uses XML files for its configuration and tests, and a series of data files for data sent to the server.

* The "serverinfo" configuration is stored in scripts/servers. That file defines details about the server being tested (its host name, port etc) as well as information about how the server is setup with user accounts for testing. CalDAVTester requires a certain number of user accounts to be present on the server being tested in order to perform the requird tests. The "serverinfo" configuration file allows you to specify the details for each account, including user name, password, path to calendars etc. These values are substituted into the tests via a string subtitution. The values can also be substituted into the data files as needed.

* The "caldavtest" test files are stored in scripts/tests. There are multiple test scripts each of which defines a set of tests to be executed against the server. Each test has a <start> section where any required setup can be done (e.g. storing resources on the server needed for the test), and an <end> section where clean-up can occur (e.g., removal of resources added during <start>). Multiple <test-suites> can be specified. Each suite can contain multiple <tests>. Each test can include one or more <request>'s. A request carries out an HTTP transaction with the server and optionally verifies the result.

## Running CalDAVTester via Calendar Server

	cd CalendarServer
	bin/testserver

This will run all CalDAV and CardDAV tests.

## Running CalDAVTester by itself

To run all scripts:

	cd CalDAVTester
	./testcaldav.py

To run specific scripts:

	./testcaldav.py <<testscriptfile>>

where <<testscriptfile>> is one of the .xml files in the CalDAVTester/scripts/test directory. For example, to run the 'well-known.xml' test for CalDAV, you would execute:

	./testcaldav.py CalDAV/well-known.xml
