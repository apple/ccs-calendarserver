---
title: Frequently Asked Questions
---

## Scheduling over Email (iMIP)

Q: _How do I configure Calendar Server to send email invitations?_

Calendar Server can send invitations to "external" users (i.e., those without an account on the server) via email, using the iCalendar Message-Based Interoperability Protocol (iMIP - ​http://tools.ietf.org/html/rfc2447 ). If you create an event and add an attendee which has an email address but does not have a local account, the server will generate an email message with a icalendar attachment containing the event details and a request for response. If the attendee uses an iMIP-compatible client to respond to the invitation, the server will parse the reply and update the organizer's copy of the event accordingly.

What is required to set up iMIP:

* An SMTP server
* An IMAP or POP server
* An email account dedicated to the calendar server -- it is important that you not use your own email account for this because the server will delete any messages that appear in this account

Steps:

1. Create an IMAP or POP account on your mail server solely for use by the calendar server (used to send a receive email)
2. Create a user account on the calendar server (used to do authentication between calendar server and mail gateway process)
3. Edit caldavd.plist:
  * iMIP
    * Enabled = true
    * Username = username for account you created in step 2
    * Password = password for account you created in step 2
    * Sending
      * Server = your SMTP server name
      * Port = the port your SMTP server is listening on
      * UseSSL = true/false depending on whether your SMTP server is using SSL
      * Username = username to log in to SMTP (leave empty if no authentication is required by your SMTP server)
      * Password = password to log in to SMTP (leave empty if no authentication is required by your SMTP server)
      * Address = used as the From: address
    * Receiving
      * Server = your inbound (IMAP/POP) server name
      * Port = the port your IMAP/POP server is listening on
      * Type = either pop or imap
      * UseSSL = true/false depending on whether your IMAP/POP server is using SSL
      * Username = username to log in to IMAP/POP (do not use your own email account for this or your inbox will be wiped out)
      * Password = password to log in to IMAP/POP
      * PollingSeconds = how often to poll for incoming replies
    * AddressPatterns = an array of regular expressions defining which email addresses to send iMIP messages to -- if an external attendee's email address does not match these patterns, no invitation will be sent to them.
4. Restart calendar server

### Troubleshooting iMIP

Mail gateway didn't find a token in message -- Calendar Server uses "plus addressing" to encode a token into the reply-to address for email invitations. That way, when a reply comes back, the token can be used to look up the appropriate organizer, attendee, and event to update. This special tokenized email address is not only in the reply-to field, but also substituted for the organizer's email address within the embedded icalendar body attached to the invitation. So iMIP-aware clients should direct the reply to the email address including the token. If that token is missing, the iMIP reply is not processed.

iMIP injection principal not found: com.apple.calendarserver -- By default, Calendar Server assumes there is a user named com.apple.calendarserver on the system and it uses that account to authenticate requests between the calendar server processes and the mail gateway process. If you're not on an OS X server, you'll need to create a user account for this purpose, and put its username and password into the caldavd.plist as described in the steps above.

## Configuring for LDAP

Q: _How do I configure Calendar Server to use LDAP for users, groups, locations, and resources?_

See [LDAP directory service](https://github.com/apple/ccs-calendarserver/blob/master/doc/Admin/DirectoryService-LDAP.rst)
