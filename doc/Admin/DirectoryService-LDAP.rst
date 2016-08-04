=======================
 LDAP Directory Service
=======================

The LDAP directory service allows CalendarServer to query an LDAP
server to retrieve principal information for users, groups,
locations, resources, and addresses. This service is implemented by
`twext.who.ldap`_.

  .. _twext.who.ldap: https://github.com/apple/ccs-twistedextensions/tree/master/twext/who/ldap

When using this service, a separate process called the Directory Proxy Service (DPS)
is instantiated to handle interactions with the LDAP server. This process
maintains an in-memory cache of directory services data. Worker processes
communicate with the DPS over an AMP socket. Each worker process also maintains
an in-memory cache of directory services data. Each cache TTL can be configured
separately.



Configuring the Calendar Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A sample caldavd.plist configuration is shown below. To use LDAP with CalendarServer,
you will almost certainly have to customize at least some of the config
options, due to the nature of LDAP's arbitrary and often site-specific
nomenclature. Anyone familiar with LDAP in general should have no
problem understanding how to configure CalendarServer to use LDAP.

Note that although multiple directory services may be used concurrently,
a given record type may only be handled by one directory service.

Sample LDAP configuration:

::

   <key>DirectoryService</key>
   <dict>
     <key>type</key>
     <string>ldap</string>

     <key>params</key>
     <dict>
       <key>recordTypes</key>
       <array>
          <string>users</string>
          <string>groups</string>
          <string>locations</string>
          <string>resources</string>
          <string>addresses</string>
       </array>
       <key>uri</key>
       <string>ldap://ldap.example.com/</string>
       <key>credentials</key>
       <dict>
         <key>dn</key>
         <string>uid=caladmin,ou=people,o=example.com</string>
         <key>password</key>
         <string>xyzzy</string>
       </dict>
       <key>rdnSchema</key>
       <dict>
         <key>base</key>
         <string>o=example.com</string>
         <key>users</key>
         <string>ou=people</string>
         <key>groups</key>
         <string>ou=groups</string>
         <key>locations</key>
         <string>ou=places</string>
         <key>resources</key>
         <string>ou=resources</string>
         <key>addresses</key>
         <string>ou=buildings</string>
       </dict>
       <key>mapping</key>
       <dict>
         <key>uid</key>
         <array>
           <string>apple-generateduid</string>
         </array>
         <key>guid</key>
         <array>
           <string>apple-generateduid</string>
         </array>
         <key>shortNames</key>
         <array>
           <string>uid</string>
         </array>
         <key>fullNames</key>
         <array>
           <string>cn</string>
         </array>
         <key>emailAddresses</key>
         <array>
           <string>mail</string>
         </array>
         <key>memberDNs</key>
         <array>
           <string>uniqueMember</string>
         </array>
         <key>hasCalendars</key>
         <array>
           <string>calStatus:active</string>
         </array>
         <key>autoScheduleMode</key>
         <array>
           <string>icsAutoaccept:true:acceptIfFreeDeclineIfBusy</string>
           <string>icsAutoaccept:false:none</string>
         </array>
         <key>autoAcceptGroup</key>
         <array>
           <string>autoAcceptGroup</string>
         </array>
         <key>readWriteProxy</key>
         <array>
           <string>calRWProxy</string>
         </array>
         <key>readOnlyProxy</key>
         <array>
           <string>calROProxy</string>
         </array>
       </dict>
       <key>extraFilters</key>
       <dict>
         <key>users</key>
         <string>(calStatus=active)</string>
         <key>groups</key>
         <string></string>
         <key>locations</key>
         <string>(calStatus=active)</string>
         <key>resources</key>
         <string>(calStatus=active)</string>
         <key>addresses</key>
         <string></string>
       </dict>
     </dict>
   </dict>



Configuring Principals
~~~~~~~~~~~~~~~~~~~~~~~

The "mapping" section of the above configuration defines the mapping
between record attributes used by CalendarServer and the LDAP
attribute used to store this information in the configured LDAP
server. The mapping 'key' is the CalendarServer name for the
attribute, and the string value is the associated LDAP attribute name.
extraFilters specifies, for each record type, an LDAP query predicate
that will be applied to all queries on that record type.

``uid``

  Typically equivalent to short name or login name. Single value.

``guid``

  A globally unique identifier for the principal. Must be a UUID
  string that complies with `RFC 4122`_.

  .. _RFC 4122: http://tools.ietf.org/html/rfc4122

``shortNames``

  The principal's short names (typically equivalent to login names).
  Multiple values allowed.

``fullNames``

  The principal's full name (or description).

``emailAddresses``

  The principal's email address(es).

``memberDNs``

  Valid only for groups, this is a list of DNs of group members. Valid
  group member record types are: users, groups, resources. One should
  avoid creating "loops" by having two groups include each other.

``hasCalendars``

  The value of this config key is used to control whether a principal is
  allowed to participate in calendaring on this server. The value is a
  two part string delimited by a colon. The first part is the LDAP
  attribute name to query, and the second part is the LDAP value of this
  attribute that indicates a principal is allowed to do calendaring.

``AutoScheduleMode``

  This configures how (or whether) the server will automatically
  process scheduling messages for the corresponding principal. For
  example, when a
  scheduling message arrives, if it does not conflict with an existing
  meeting it can be automatically accepted into the principal's main
  calendar; if it does conflict it can be automatically declined. The
  available modes can be seen here:
  https://github.com/apple/ccs-calendarserver/blob/master/calendarserver/tools/principals.py#L48

``autoAcceptGroup``

  Specifies the uid of a group whose members will be excempt from any
  AutoScheduleMode setting on the corresponding principal. For example,
  if a location is configured with an AutoScheduleMode of 'none' with
  the intention that a read-write delegate will manually accept or deny
  invitations to that location, invitations from members of the autoAcceptGroup
  will be automatically accepted if the requested time slot is free.

``readWriteProxy``

  Specifies the attribute used to store the uid of a group  
  whose members are granted read-write proxy (delegate) access to the
  corresponding principal.

``readOnlyProxy``

  Specifies the attribute used to store the uid of a group  
  whose members are granted read-only proxy (delegate) access to the
  corresponding principal.



Other LDAP params
~~~~~~~~~~~~~~~~~~

The following settings are available in the 'params' dictionary of the LDAP configuration.

``threadPoolmax``
``connectionMax``

  These two settings are integers used to limit the concurrency of LDAP query handling in the DPS.
  There is a subtle but important difference between these two options: threadPoolMax
  applies to all LDAP interactions INCLUDING authentication, while connectionMax
  applies to all LDAP interactions EXCEPT authentication. threadPoolMax should always be
  set to a value greater than connectionMax to prevent LDAP authentications from becomming
  starved if the LDAP connection pool is full (i.e. connectionMax has been reached).

``tries``

  Specifies the number of times an LDAP query should be retried if it fails for unexpected reasons.

``warningThresholdSeconds``

  Specifies the duration of an LDAP query in seconds above which a warning will be logged.

``useTLS``

  A boolean that instructs the DPS to connect to the LDAP service using TLS.



Related settings
~~~~~~~~~~~~~~~~~

The following settings are available *outside* the LDAP directory service configuration (i.e.
the DirectoryProxy dict is a top-level dict in caldavd.plist):

::

    <key>DirectoryProxy</key>
    <dict>
        <key>SocketPath</key>
        <string>directory-proxy.sock</string>

        <key>InProcessCachingSeconds</key>
        <integer>60</integer>

        <key>InSidecarCachingSeconds</key>
        <integer>120</integer>
    </dict>

``SocketPath``

  The unix domain socket used by AMP for communication between the DPS and workers

``InProcessCachingSeconds``
``InSidecarCachingSeconds``

  The TTL of directory services data in worker processes and the DPS, respectively.



LDAP attribute indexing
~~~~~~~~~~~~~~~~~~~~~~~~~

Use the following guidance to properly configure attribute indexing on the LDAP server.

+------------+-----------------------+
| Attribute  | Search type           | 
+============+=======================+ 
| fullName   | substring (subany)    |
+------------+-----------------------+
| guid       | exact                 |
+------------+-----------------------+
| shortName  | exact                 |
+------------+-----------------------+
| mail       | substring (subfinal)  |
+------------+-----------------------+
