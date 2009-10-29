Open Directory Service
======================

The Open Directory directory service provides principal information
that is obtained using Apple's Open Directory service.

Open Directory provides principal information for users, groups,
locations, and resources.

For more information about configuring Open Directory and running Open
Directory services, see Apple's `Open Directory Administration`_
document.

.. _Open Directory Administration: http://images.apple.com/server/macosx/docs/Open_Directory_Admin_v10.6.pdf

Configuring the Calendar Server
-------------------------------

The full name of the service is
``twistedcaldav.directory.appleopendirectory.OpenDirectoryService``
and the service takes a ``node`` parameter which contains the name of
the directory node to bind to.

For example:

::

  <!-- Open Directory Service -->
  <key>DirectoryService</key>
  <dict>
    <key>type</key>
    <string>twistedcaldav.directory.appleopendirectory.OpenDirectoryService</string>
  
    <key>params</key>
    <dict>
      <key>node</key>
      <string>/Search</string>
    </dict>
  </dict>

The special Open Directory node ``/Search`` causes the server to use
the default directory search path that the host system the server is
running on is configured to use. To bind to a specific LDAP service, a
node in the form ``/LDAPv3/ldapserver.example.com`` may be specified.
