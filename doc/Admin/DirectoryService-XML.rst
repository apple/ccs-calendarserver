XML Directory Service
=====================

The XML directory service provides principal information that is read
from an XML file.

The XML file provides principal information for users, groups,
locations, and resources.

One advantage to this directory service implementation is that it does
not require a networked directory server to be running somewhere,
instead simply relying on a file.

Configuring the Calendar Server
-------------------------------

The full name of the service is
``twistedcaldav.directory.xmlfile.XMLDirectoryService`` and the
service takes an ``xmlFile`` parameter which contains the name of the
XML file to read principal information from.

For example:

::

  <!--  XML File Directory Service -->
  <key>DirectoryService</key>
  <dict>
    <key>type</key>
    <string>twistedcaldav.directory.xmlfile.XMLDirectoryService</string>

    <key>params</key>
    <dict>
      <key>xmlFile</key>
      <string>/etc/caldavd/accounts.xml</string>
    </dict>
  </dict>

The service re-reads the XML file if it's timestamp changes, so edits
to the XML file do not require a server restart.

Configuring Principals
----------------------

Principals are expressed in an XML document. The root element
``accounts`` has an attribute ``realm`` which describes the
authentication realm. It contains principal elements which in turn
contain elements describing the principal. The element itself
(``user``, ``group``, ``location``, ``resource``) denotes the
principal type.

Principal elements can contain the following elements which provide
information about the principal:

``uid``

  The login identifier for the principal (ie. "user name" or "short
  name").

``guid``

  A globally unique identifier for the principal. Must be a UUID
  string that complies with `RFC 4122`_.

  .. _RFC 4122: http://tools.ietf.org/html/rfc4122

``password``

  The principal's password in plain text.

``name``

  The principal's full name (or description).

``members``

  A list of uids for the principals which are members of the principal
  being defined. Only group principals may have members. The
  ``members`` element has ``member`` sub-elements used to specify each
  member. The member element has a type attribute that defines the
  principal type of the member (one of ``users``, ``groups``,
  ``locations`` and ``resources``), and the text value inside the
  ``member`` element is the corresponding uid of the principal being
  referenced. Any principal may be a member of a group, including
  other groups. One should avoid creating "loops" by having two groups
  include each other.

``cuaddr``

  A "calendar user address" for the principal. Principals may have
  multiple calendar user addresses, but a calendar user addresses must
  be unique to one principal. A calendar user address must be a URI_.

  .. _URI: http://tools.ietf.org/html/rfc2396

  Note that calendar user addresses here supplement any calendar user
  addresses that are assigned by the server based on other principal
  information.
  
``disable-calendar``

  When present, this element indicates that the principal is able to
  login to the calendar server, but is not provided a calendar home
  and therefore cannot do scheduling. This type of principal is
  typically used to allow access to the calendars of other principals
  or other data on the server. This element may only pecified for user
  principals.

``auto-schedule``

  Indicates that the server will automatically process scheduling
  messages for the corresponding principal. For example, when a
  scheduling message arrives, if it does not conflict with an existing
  meeting it will be automatically accepted into the principal's main
  calendar; if it does conflict it will be automatically
  declined. This element can only be defined on location and resource
  principals.

``proxies``

  Contains a list of ``member`` elements that define which other
  principals have read-write proxy access to the corresponding
  principal's calendar data.

An example:

::

  <?xml version="1.0" encoding="utf-8"?>
  <accounts realm="Test Realm">
    <user>
      <uid>admin</uid>
      <password>admin</password>
      <name>Super User</name>
    </user>
    <user>
      <uid>test</uid>
      <password>test</password>
      <name>Test User</name>
      <cuaddr>mailto:testuser@example.com</cuaddr>
    </user>
    <group>
      <uid>users</uid>
      <password>users</password>
      <name>Users Group</name>
      <members>
        <member type="users">test</member>
      </members>
    </group>
    <location>
      <uid>mercury</uid>
      <password>mercury</password>
      <name>Mecury Conference Room, Building 1, 2nd Floor</name>
      <auto-schedule/>
      <proxies>
        <member type="users">test</member>
      </proxies>
    </location>
  </accounts>
