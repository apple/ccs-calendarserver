README for testcaldav.py

INTRODUCTION

testcaldav.py is a Python app that will run a series of scripted tests
against a CalDAV server and verify the output, and optionally measure
the time taken to complete one or more repeated requests. The tests are
defined by XML files and ancillary HTTP request body files. A number of
different verification options are provided.

Many tests are included in this package.

COMMAND LINE OPTIONS

testcaldav.py \
	[-s filename] \
	[-x dirpath] \
	[--ssl] \
	[--all] \
	[--random] \
	[--random-seed SEED] \
	[--stop] \
	[--print-details-onfail] \
	[--always-print-request] \
	[--always-print-response] \
	[--exclude filename] \
	[--observer OBSERVER] \
	file1 file2 ...

	-s : filename specifies the file to use for server information
	(default is 'serverinfo.xml').

	-x : directory path for test scripts
	(default is 'scripts/tests').

	-p : filename specifies the file to use to populate the server with
	data. Server data population only occurs when this option is
	present.

	-d : in conjunction with -p, if present specifies that the populated
	data be removed after all tests have completed.

	--ssl : run tests using SSL/https connections to the server.

	--all : execute all tests found in the working directory. Each .xml
	file in that directory is examined and those corresponding to the
	caldavtest.dtd are executed.

	--random : randomize the order in which the tests are run.
	
	--random-seed SEED : a specific random seed to use.
	
	--stop : stop running all tests after one test file fails.

	--print-details-onfail : print HTTP request/response when a test fails.
	
	--always-print-request : always print HTTP request.
	
	--always-print-response : always print HTTP response.
	
	--exclude FILE : when running with --all, exclude the file from the test run. 

	--observer OBSEREVER : specify one or more times to change which classes are
	used to process log and trace messages during a test. The OBSERVER name must
	be the name of a module in the observers package. The default observer is the
	"log" observer. Available observers are:
		
		"log" - produces an output similar to Python unit tests.
		"trace" - produces an output similar to the original output format.
		"loadfiles" - prints each test file as it is loaded.
		"jsondump" - prints a JSON representation of the test results.
 
	file1 file2 ...: a list of test files to execute tests from.

QUICKSTART

Edit the serverinfo.xml file to run the test against your server setup.

Run 'testcaldav.py --all' on the command line to run the tests. The app
will print its progress through the tests.

EXECUTION PROCESS

1. Read in XML config.
2. Execute <start> requests.
3. For each <test-suite>, run each <test> the specified number of times,
   executing each <request> in the test and verifying them.
4. Delete any resources from requests marked with 'end-delete'.
5. Execute <end> requests.

XML SCRIPT FILES

serverinfo.dtd

	Defines the XML DTD for the server information XML file:

	ELEMENT <host>
		host name for server to test.

	ELEMENT <nonsslport>
		port to use to connect to server (non-SSL).

	ELEMENT <sslport>
		port to use to connect to server (SSL).

	ELEMENT <authtype>
		HTTP authentication method to use.

	ELEMENT <waitcount>
		For requests that wait, defines how many iterations to wait for
		[Default: 120].

	ELEMENT <waitdelay>
		For requests that wait, defines how long between iterations to
		wait for in seconds [Default: 0.25].

	ELEMENT <waitsuccess>
		For requests with the wait-for-success options, defines how many
		seconds to wait [Default: 10].

	ELEMENT <features>
		list of features for the server under test.

		ELEMENT <feature>
			specific feature supported by the server under test,
			used to do conditional testing.

	ELEMENT <substitutions>
		used to encapsulate all variable substitutions.

		ELEMENT <substitution>
			a variable substitution - the repeat attribute can
			be used to repeat the substitution a set number of
			times whilst generating different substitutions.

			ELEMENT <key>
				the substitution key (usually '$xxx:').

			ELEMENT <value>
				the substitution value.

		ELEMENT <repeat>
			allow repeating substitutions for the specified count.


caldavtest.dtd:

	Defines the XML DTD for test script files:
	
	ATTRIBUTE ignore-all
		used on the top-level XML element to indicate whether this test
		is run when the --all command line switch for testcaldav.py is
		used. When set to 'no' the test is not run unless the file is
		explicitly specified on the command line.

	ELEMENT <description>
		a description for this test script.

	ELEMENT <require-feature>
		set of features.

		ELEMENT <feature>
			feature that server must support for this entire test
			script to run.

	ELEMENT <exclude-feature>
		set of features.

		ELEMENT <feature>
			feature that server must not support for this entire test
			script to run.

	ELEMENT <start>
		defines a series of requests that are executed before testing
		starts. This can be used to initialize a set of calendar
		resources on which tests can be run.

	ELEMENT <end>
		defines a series of requests that are executed after testing is
		complete. This can be used to clean-up the server after testing.
		Note that there are special mechanisms in place to allow
		resources created during testing to be automatically deleted
		after testing, so there is no need to explicitly delete those
		resources here.

	ELEMENT <test-suite>
		defines a group of tests to be run. The suite is given a name
		and has an 'ignore' attribute that can be used to disable it.

		ATTRIBUTE name
			name/description of test-suite.
		ATTRIBUTE ignore
			if set to 'yes' then the entire test-suite will be skipped.
		ATTRIBUTE only
			if set to 'yes' then all other test-suites (except others with
			the same attribute value set) will be skipped.

		ELEMENT <require-feature>
			set of features.
	
			ELEMENT <feature>
				feature that server must support for this test
				suite to run.

		ELEMENT <exclude-feature>
			set of features.
	
			ELEMENT <feature>
				feature that server must not support for this test
				suite to run.

	ELEMENT <test>
		defines a single test within a test suite. A test has a name,
		description and one or more requests associated with it. There
		is also an 'ignore' attribute to disable the test. Tests can be
		executed multiple times by setting the 'count' attribute to a
		value greater than 1. Timing information about the test can be
		printed out by setting the 'stats' attribute to 'yes'.

		ATTRIBUTE name
			name of test.
		ATTRIBUTE count
			number of times to run the test. This allows tests to be
			easily repeated.
		ATTRIBUTE stats
			if set to 'yes' then timing information for the test will be
			printed.
		ATTRIBUTE ignore
			if set to 'yes' then the entire test will be skipped.

		ELEMENT <require-feature>
			set of features.
	
			ELEMENT <feature>
				feature that server must support for this test
				to run.

		ELEMENT <exclude-feature>
			set of features.
	
			ELEMENT <feature>
				feature that server must not support for this test
				to run.

	ELEMENT <description>
		detailed description of the test.

	ELEMENT <pause>
		halt tests and wait for user input. Useful for stopping tests to set a
		break point or examine server state, and then continue on.

	ELEMENT <request>
		defines an HTTP request to send to the server. Attributes on the
		element are:

		ATTRIBUTE auth
			if 'yes', HTTP Basic authentication is done in the request.
		ATTRIBUTE user
			if provided this value is used as the user id for HTTP Basic
			authentication instead of the one in the serverinfo
			file.
		ATTRIBUTE pswd
			if provided this value is used as the password for HTTP
			Basic authentication instead of the one in the serverinfo
			file.
		ATTRIBUTE end-delete
			if set to 'yes', then the resource targeted by the request
			is deleted after testing is complete, but before the
			requests in the <end> element are run. This allows for quick
			clean-up of resources created during testing.
		ATTRIBUTE print-response
			if set to 'yes' then the HTTP response (header and body) is
			printed along with test results.
		ATTRIBUTE wait-for-success
			if set to 'yes' then the HTTP request will repeat over and over
			for a set amount of time waiting for the verifiers to pass. If
			time expires without success then the overall request fails. The
			length of time is controlled by the <waittime> element in the
			serverinfo file (defaults to 10 seconds).

		ELEMENT <require-feature>
			set of features.
	
			ELEMENT <feature>
				feature that server must support for this request
				to run.

		ELEMENT <exclude-feature>
			set of features.
	
			ELEMENT <feature>
				feature that server must not support for this request
				to run.

		ELEMENT <method>
			the HTTP method for this request. There are some 'special' methods that do some useful 'compound' operations:
				1) DELETEALL - deletes all resources within the collections specified by the <ruri> elements.
				2) DELAY - pause for the number of seconds specified by the <ruri> element.
				3) GETNEW - get the data from the newest resource in the collection specified by the <ruri> element and put its URI
						    into the $ variable for later use in an <ruri> element.
				4) WAITCOUNT - wait until at least a certain number of resources appear in a collection.
				5) WAITDELETEALL - wait until at least a certain number of resources appear in a collection, then delete all child
								   resources in that collection.
	
		ELEMENT <ruri>
			the URI of the request. Multiple <ruri>'s are allowed with DELETEALL only.
			The characters "**" may be used to cause a random uuid to be inserted where
			those two characters appear. The characters "##" may be used to insert the
			current test count iteration where those two characters occur.
	
		ELEMENT <header>
			can be used to specify additional headers in the request.
			
			ELEMENT <name>
				the header name.
	
			ELEMENT <value>
				the header value.
	
		ELEMENT <data>
			used to specify the source and nature of data used in the
			request body, if there is one.
			
			ATTRIBUTE substitutions
				if set to 'yes' then '$xxx:' style variable substitutions
				will be performed on the data before it is sent in the request.
			ATTRIBUTE generate
				if set to 'yes' then a basic calendar data "fuzzing" is done to
				the source data to make it unique and up to date.
	
			ELEMENT <content-type>
				the MIME content type for the request body.
	
			ELEMENT <filepath>
				the relative path for the file containing the request body
				data.

		ELEMENT <verify>
			if present, used to specify a procedures for verifying that the
			request executed as expected.

			ELEMENT <require-feature>
				set of features.
		
				ELEMENT <feature>
					feature that server must support for this verification
					to be checked.
	
			ELEMENT <exclude-feature>
				set of features.
	
			ELEMENT <feature>
				feature that server must not support for this verification
				to be checked.
			
			ELEMENT <callback>
				the name of the verification method to execute.
	
			ELEMENT <arg>
				arguments sent to the verification method.
	
				ELEMENT <name>
					the name of the argument.
	
				ELEMENT <value>
					values for the argument.
	
		ELEMENT <graburi>
			if present, this stores the value of the actual request URI
			used in a named variable which can be used in subsequent requests.
			Useful for capturing URIs when the GETNEW method is used.
			
		ELEMENT <grabheader>
			if present, this stores the value of the specified header
			returned in the response in a named variable which can be used
			in subsequent requests.
			
		ELEMENT <grabproperty>
			if present, this stores the value of the specified property
			returned in a PROPFIND response in a named variable which can
			be used in subsequent requests.
			
		ELEMENT <grabelement>
			if present, this stores the text representation of an XML
			element extracted from the response body in a named variable
			which can be used in subsequent requests.
			
		ELEMENT <grabcalproperty>
			if present, this stores a calendar property value in a named
			variable which can be used in subsequent request. The syntax for
			<name> element is component/propname (e.g. "VEVENT/SUMMARY").

		ELEMENT <grabcalparameter>
			if present, this stores a calendar parameter value in a named
			variable which can be used in subsequent request. The syntax for
			<name> element is component/propname/paramname$propvalue where
			the option $propvalue allows a specific property to be selected 
			(e.g. "VEVENT/DTSTART/TZID", or
			"VEVENT/ATTENDEE/PARTSTAT$mailto:user01@example.com").


VERIFICATION Methods

acltems:
	Performs a check of multi-status response body and checks to see
	whether the specified privileges are granted or denied on each
	resource in the response for the current user (i.e. tests the
	DAV:current-user-privilege-set).

	Argument: 'granted'
		A set of privileges that must be granted.
	
	Argument: 'denied'
		A set of privileges that must be denied denied.

	Example:
	
	<verify>
		<callback>multistatusitems</callback>
		<arg>
			<name>granted</name>
			<value>DAV:read</value>
		</arg>
		<arg>
			<name>denied</name>
			<value>DAV:write</value>
			<value>DAV:write-acl</value>
		</arg>
	</verify>
	
calandarDataMatch:
	Similar to data match but tries to "normalize" the calendar data so that e.g., different
	ordering of properties is not significant.

	Argument: 'filepath'
		The file path to a file containing data to match the response body to.
	
	Example:
	
	<verify>
		<callback>dataMatch</callback>
		<arg>
			<name>filepath</name>
			<value>resources/put.ics</value>
		</arg>
	</verify>
	
dataMatch:
	Performs a check of response body and matches it against the data in the specified file.

	Argument: 'filepath'
		The file path to a file containing data to match the response body to.
	
	Example:
	
	<verify>
		<callback>dataMatch</callback>
		<arg>
			<name>filepath</name>
			<value>resources/put.ics</value>
		</arg>
	</verify>
	
dataString:
	Performs a check of response body tries to find occurrences of the specified strings or the
	absence of specified strings.

	Argument: 'contains'
		One or more strings that must be contained in the data (case-sensitive).
	
	Argument: 'notcontains'
		One or more strings that must not be contained in the data (case-sensitive).
	
	Example:
	
	<verify>
		<callback>dataString</callback>
		<arg>
			<name>contains</name>
			<value>BEGIN:VEVENT</value>
		</arg>
		<arg>
			<name>notcontains</name>
			<value>BEGIN:VTODO</value>
		</arg>
	</verify>
	
freeBusy:
	Performs a check of the response body to verify it contains an
	iCalendar VFREEBUSY object with the specified busy periods and
	types.

	Argument: 'busy'
		A set of iCalendar PERIOD values for FBTYPE=BUSY periods
		expected in the response.
	
	Argument: 'tentative'
		A set of iCalendar PERIOD values for FBTYPE=BUSY-TENTATIVE
		periods expected in the response.
	
	Argument: 'unavailable'
		A set of iCalendar PERIOD values for FBTYPE=BUSY-UNAVAILABLE
		periods expected in the response.
	
	Example:
	
	<verify>
		<callback>freeBusy</callback>
		<arg>
			<name>busy</name>
			<value>20060107T010000Z/20060107T020000Z</value>
			<value>20060107T150000Z/20060107T163000Z</value>
			<value>20060108T150000Z/20060108T180000Z</value>
		</arg>
		<arg>
			<name>unavailable</name>
			<value>20060108T130000Z/20060108T150000Z</value>
		</arg>
		<arg>
			<name>tentative</name>
			<value>20060108T160000Z/20060108T170000Z</value>
			<value>20060108T210000Z/20060108T213000Z</value>
		</arg>
	</verify>

header:
	Performs a check of response header and value. This can be used to
	test for the presence or absence of a header, or the presence of a
	header with a specific value.

	Argument: 'header'
		This can be specified in one of three forms:
		
			'headername' - will test for the presence of the response
			header named 'header name'.

			'headername$value' - will test for the presence of the
			response header named 'headername' and also check that its
			value matches 'value'.

			'!headername' - will test for the absence of a header named
			'headername' in the response header.
	
	Example:
	
	<verify>
		<callback>header</callback>
		<arg>
			<name>header</name>
			<value>Content-type$text/plain</value>
		</arg>
	</verify>

jcalDataMatch:
	Like calendarDataMatch except that comparison is done using jCal data.

jsonPointerMatch:
	Compares the response with a JSON pointer and returns TRUE if there
	is a match, otherwise False.
	The pointer is the absolute pointer from the root down. A JSON object's
	string value can be checked by append "~$" and the string value to test
	to the JSON pointer value. A single "." can be used as a reference-token
	in the JSON pointer to match against any member or array item at that
	poisition in the document.
	
	Argument: 'exists'
		JSON pointer for a JSON item to check the presence of
		in the response.
	
	Argument: 'notexists'
		JSON pointer for a JSON item to check the absence of
		in the response.
	
	Example:
	
	<verify>
		<callback>jsonPointerMatch</callback>
		<arg>
			<name>exists</name>
			<value>/responses/response</value>
		</arg>
		<arg>
			<name>notexists</name>
			<value>/responses/response/name~$ABC</value>
		</arg>
		<arg>
			<name>exists</name>
			<value>/responses/./name~$XYZ</value>
		</arg>
	</verify>
	
multistatusItems:
	Performs a check of multi-status response body and checks to see
	what hrefs were returned and whether those had a good (2xx) or bad
	(non-2xx) response code. The overall response status must be 207.

	Argument: 'okhrefs'
		A set of hrefs for which a 2xx response status is required.
	
	Argument: 'badhrefs'
		A set of hrefs for which a non-2xx response status is required.

	Argument: 'prefix'
		A prefix that is appended to all of the specified okhrefs and
		badhrefs values.
	
	Example:
	
	<verify>
		<callback>multistatusitems</callback>
		<arg>
			<name>okhrefs</name>
			<value>/calendar/test/1.ics</value>
			<value>/calendar/test/2.ics</value>
			<value>/calendar/test/3.ics</value>
		</arg>
		<arg>
			<name>badhrefs</name>
			<value>/calendar/test/4.ics</value>
			<value>/calendar/test/5.ics</value>
			<value>/calendar/test/6.ics</value>
		</arg>
	</verify>
	
postFreeBusy:
	Looks for specific FREEBUSY periods for a particular ATTENDEE.

	Argument: 'attendee'
		Calendar user address for attendee to match.
	
	Argument: 'busy'
		Period for FBTYPE=BUSY to match.
	
	Argument: 'tentative'
		Period for FBTYPE=BUSY-TENTATIVE to match.
	
	Argument: 'unavailable'
		Period for FBTYPE=BUSY-UNAVAILABLE to match.
	
	Example:
	
	<verify>
		<callback>postFreeBusy</callback>
		<arg>
			<name>attendee</name>
			<value>$cuaddr1:</value>
		</arg>
		<arg>
			<name>busy</name>
			<value>20060101T230000Z/20060102T000000Z</value>
		</arg>
	</verify>
	
prepostcondition:
	Performs a check of response body and status code to verify that a
	specific pre-/post-condition error was returned. The response status
	code has to be one of 403 or 409.

	Argument: 'error'
		The expected XML element qualified-name to match.
	
	Example:
	
	<verify>
		<callback>prepostcondition</callback>
		<arg>
			<name>error</name>
			<value>DAV:too-many-matches</value>
		</arg>
	</verify>
	
propfindItems:
	Performs a check of propfind multi-status response body and checks to see
	whether the returned properties (and optionally their values) are good (2xx) or bad
	(non-2xx) response code. The overall response status must be 207.

	Argument: 'roor-element'
		Exepected root element for the XML response. Normally this is DAV:multistatus
		but, e.g., MKCOL ext uses a different root, but mostly looks like multistatus
		otherwise.

	Argument: 'okprops'
		A set of properties for which a 2xx response status is required. Two forms can be used:
		
		'propname' - will test for the presence of the property named
		'propname'. The element data must be a qualified XML element
		name.
	
		'propname$value' - will test for the presence of the property
		named 'propname' and check that its value matches the provided
		'value'. The element data must be a qualified XML element name.
		XML elements in the property value can be tested provided proper
		XML escaping is used (see example).
	
		'propname!value' - will test for the presence of the property
		named 'propname' and check that its value does not match the provided
		'value'. The element data must be a qualified XML element name.
		XML elements in the property value can be tested provided proper
		XML escaping is used (see example).
	
	Argument: 'badhrefs'
		A set of properties for which a non-2xx response status is
		required. The same two forms as used for 'okprops' can be used
		here.

	Example:
	
	<verify>
		<callback>propfindItems</callback>
		<arg>
			<name>okprops</name>
			<value>{DAV:}getetag</value>
			<value>{DAV:}getcontenttype$text/plain</value>
			<value>{X:}getstate$&lt;X:ok/&gt;</value>
		</arg>
		<arg>
			<name>badprops</name>
			<value>{X:}nostate</value>
		</arg>
	</verify>
	
propfindValues:
	Performs a regular expression match against property values. The overall
	response status must be 207.

	Argument: 'props'
		A set of properties for which a 2xx response status is required. Two forms can be used:
		
		'propname$value' - will test for property value match
		'propname!value' - will test for property value non-match
	
	Argument: 'ignore'
		One or more href values for hrefs in the response which will be
		ignored. e.g. when doing a PROPFIND Depth:1, you may want to
		ignore the top-level resource when testing as only the
		properties on the child resources may be of interest.
	
	Example:
	
	<verify>
		<callback>propfindValues</callback>
		<arg>
			<name>props</name>
			<value>{DAV:}getcontenttype$text/.*</value>
			<value>{DAV:}getcontenttype!text/calendar</value>
		</arg>
		<arg>
			<name>ignore</name>
			<value>/calendars/test/</value>
		</arg>
	</verify>
	
statusCode:
	Performs a simple test of the response status code and returns True
	if the code matches, otherwise False.
	
	Argument: 'status'
		If the argument is not present, the any 2xx status code response
		will result in True. The status code value can be specified as
		'NNN' or 'Nxx' where 'N' is a digit and 'x' the letter x. In the
		later case, the verifier will return True if the response status
		code's 'major' digit matches the first digit.
	
	Example:
	
	<verify>
		<callback>statusCode</callback>
		<arg>
			<name>status</name>
			<value>2xx</value>
		</arg>
	</verify>
	
xmlDataMatch:
	Compares the response with an XML data file and returns TRUE if there
	is a match, otherwise False.
	
	Argument: 'filepath'
		The file path to a file containing data to match the response body to.
	
	Argument: 'filter'
		Any specified XML elements will have their content removed from the
		response XML data before the comparison with the file data is done.
		This can be used to ignore element values that change in each request,
		e.g., a timestamp.
	
	Example:
	
	<verify>
		<callback>xmlDataMatch</callback>
		<arg>
			<name>filepath</name>
			<value>resource/test.xml</value>
		</arg>
		<arg>
			<name>filter</name>
			<value>{DAV:}getlastmodified</value>
		</arg>
	</verify>
	
xmlElementMatch:
	Compares the response with an XML path and returns TRUE if there
	is a match, otherwise False.
	The path is the absolute xpath from the root element down. Attribute, attribute-value
	and text contents tests of the matched element can be done using:
	
	[@attr] - "attr" is present as an attribute
	[@attr=value] - "attr" is present as an attribute with the value "value"
	[=text] - node text is "text".
	[!text] - node text is not "text".
	[*text] - node text contains "text".
	[$text] - node text does not contain "text".
	[+text] - node text starts with "text".
	[^tag] - node has child element "tag".
	[^tag=text] - node has child element "tag" with text "text".
	[|] - node is empty.
	[json] - node contains valid JSON data.
	[icalendar] - node contains valid iCalendare data.
	
	Argument: 'parent'
		ElementTree style path for an XML element to use as the root for any
		subsequent "exists" or "notexists" tests. This is useful for targeting
		a specific resource in a Depth:1 multistatus response.
	
	Argument: 'exists'
		ElementTree style path for an XML element to check the presence of
		in the response.
	
	Argument: 'notexists'
		ElementTree style path for an XML element to check the absence of
		in the response.
	
	Example:
	
	<verify>
		<callback>xmlDataMatch</callback>
		<arg>
			<name>exists</name>
			<value>{DAV:}response/{DAV:}href</value>
		</arg>
		<arg>
			<name>notexists</name>
			<value>{DAV:}response/{DAV:}getetag</value>
		</arg>
	</verify>
	
	