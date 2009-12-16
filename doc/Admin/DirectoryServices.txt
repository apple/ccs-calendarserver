Directory Services
==================

The Calendar Server needs to be able to obtain information about the
users, groups and resources ("principals") which access and/or have a
presence on the server.

About Principals
----------------

All principals have a "principal resource" on the server which
represents the principal in the form of an HTTP resource. This is
useful for obtaining information about a principal, such as the URL of
the principal's calendar home, the principal's members and/or
memberships, and so on. This information is exposed via WebDAV
properties on the principal resource.

Principals can be used to configure access controls for resources on
the server by granting or denying various privileges to the principal.
Privileges granted or denied to group principals are also granted or
denied to all members of the group.

Some principals (often, but not necessarily all) are also given a
calendar home collection on the server, in which the principal may
have one or more calendar collections, as well as special collections
which allow the principals to schedule meetings with others, and so
on.

The Role of a Directory Service
-------------------------------

A "directory service" is simply an entity which contains information
about principals.

Directory services are interchangeable, which allows the server to
obtain this information from a variety of data stores, such as
configuration files or network directory systems like LDAP.

Most directory services refer to principals as "records" in their
databases. Internally, Calendar Server will map records from a
directory service to WebDAV principals.

A given directory service may classify records into "types" such as
users, groups, resources, and so on. Calendar Server keeps this
distinction, and some types are treated specially.

Principal types commonly provided by directory services include:

users

  Individual (typically human) users of the system.

groups

  Principals that contain other principals ("members"). Members can be
  principals of any type, including other group principals.

locations

  Locations that can be scheduled.

resources

  Other resources (eg. projectors) which can be scheduled.

For example, only user principals are allowed to authenticate with
(log into) the server. Only group principals have members, and group
principals do not have calendars.


Configuration
=============

The directory service used by the server is configured in the
``caldavd.plist`` file by specifying the directory service
implementation to use, as well as its configuration options. Options
are specified as a dictionary.

The configuration syntax looks like this:

::

  <key>DirectoryService</key>
  <dict>
    <key>type</key>
    <string>ExampleService</string>

    <key>params</key>
    <dict>
      <key>option</key>
      <string>value</string>
    </dict>
  </dict>
