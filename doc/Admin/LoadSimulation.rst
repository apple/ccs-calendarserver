==========================
Load Simulation
==========================

Calendar Server includes a flexible, scalable, and easy to use `client simulator <http://trac.calendarserver.org/browser/CalendarServer/trunk/contrib/performance/loadtest>`_ that provides behaviors modeled after Apple's iCal client in Mac OS X 10.6. This sim has a highly modular architecture with the goal of making it as easy as possible to add new behaviors, or entirely new clients. The sim can be used to validate server correctness, and also for performance and scalability testing.

This document contains the following sections:

* `Quick Start`_: Instructions to get the sim up and running from an SVN checkout of Calendar Server

* `Reporting`_: The sim emits both real-time logging during runtime, and also a summary at the end that includes quality of service evaluations

* `Configuration`_: Describes the load sim's configuration options, how to enable / disable certain behaviors, adjust frequency of events, etc

* `Scalability`_: Through the use of an AMP harness, you may easily add additional sim instances on the local host and / or remote hosts

---------------------
Quick Start
---------------------

The sim's default config is pre-configured to work against the Calendar Server's default config (caldavd-test.plist), so we'll use that for this quick start.

- Start Calendar Server using the -test configuration. For further detail on this, see: http://trac.calendarserver.org/wiki/QuickStart
- Open another shell and cd into the Calendar Server SVN root
- Start the sim:

::

 ./bin/sim

The sim should begin logging its activity, which might look something like:

::

 Loaded 99 accounts.
 user01 - - - - - - - - - - -  startup BEGIN 
 user01 request 207✓[ 0.04 s] PROPFIND /principals/users/user01/
 user01 request 207✓[ 0.02 s] PROPFIND /principals/__uids__/user01/
 user01 request 200✓[ 0.01 s]   REPORT /principals/
 user01 - - - - - - - - - - -     poll BEGIN 
 user01 request 207✓[ 0.19 s] PROPFIND /calendars/__uids__/user01/
 ...

- To stop the sim, simply cntrl-c it.

---------------------
Reporting
---------------------

Runtime Reporting
-----------------

While running, the sim will log its activity to stdout. Simulator activity is organized into a two-level hierarchy: client behaviors (e.g. create event, poll, respond to events) which are composed of individual HTTP requests (e.g. GET, PUT, DELETE, etc).

For example, the sim logs the following right at startup as it initializes the users:

::

 user01 - - - - - - - - - - -  startup BEGIN 
 user01 request 207✓[ 0.04 s] PROPFIND /principals/users/user01/
 user01 request 207✓[ 0.02 s] PROPFIND /principals/__uids__/user01/
 user01 request 200✓[ 0.01 s]   REPORT /principals/
 user01 - - - - - - - - - - -     poll BEGIN 
 user01 request 207✓[ 0.29 s] PROPFIND /calendars/__uids__/user01/
 user01 request 207✓[ 0.04 s] PROPFIND /calendars/__uids__/user01/calendar/
 user01 request 207✓[ 0.04 s] PROPFIND /calendars/__uids__/user01/inbox/
 user01 request 207✓[ 0.05 s] PROPFIND /calendars/__uids__/user01/tasks/
 user01 request 207✓[ 0.02 s] PROPFIND /calendars/__uids__/user01/outbox/
 user01 request 207✓[ 0.03 s] PROPFIND /calendars/__uids__/user01/dropbox/
 user01 request 207✓[ 0.03 s] PROPFIND /calendars/__uids__/user01/notification/
 user01 - - - - - - - - - - -     poll END [ 0.51 s]
 user01 - - - - - - - - - - -  startup END [ 0.59 s]

The first token on each line is the username associated with the activity. Most of the time, client activity is interleaved, so to trace a specific client you may wish to filter for a specific username.

Client operations are groups of requests that are surrounded by lines with many dashes, either BEGIN or END. 'END' lines also include the overall duration of the operation, which is the elapsed wall clock time since the operation started.

Above, we see two behaviors that are nested; the 'startup' operation starts which includes a few requests and also triggers the 'poll' operation.

Individual requests are logged with the word 'request', followed by the HTTP status, the request duration, the HTTP method of the request, and the URI that is being targeted. Successful requests are indicated by a ✓ while failed requests are indicated with ✗.

Most client operations also log a 'lag' time when they start, e.g.

::

 user12 - - - - - - - - - - -   create BEGIN {lag  0.80 ms}

'lag' in this context specifies the time elapsed between when the sim should have started this operation (based on internal timers / activity distributions) and when it actually did. This is intended to be a measure of client sim health; if the lag values begin to grow too high, that indicates that the client sim is 'slipping' and doesn't have enough CPU to perform its various activities at the rates specified in the config file. This is python, so a single instance of the client sim is limited to one CPU core. See the `Scalability`_ section for information about how to scale the load sim by combining multiple instances.

Summary Reports
---------------
When the sim stops or is killed, it emits a summary report that displays the total number of users that were active in this run, and overall counts for both individual requests and also the higher-level client operations. Also we display quality of service information used to grade the run as PASS or FAIL. An example report is shown below::

 Users : 20
    request    count   failed    >3sec     mean   median
     DELETE       21        0        0   0.0186   0.0184
        GET       27        0        0   0.0341   0.0223
       POST       17        0        0   0.0709   0.0523
   PROPFIND      265        0        0   0.0593   0.0262
        PUT       44        0        2   0.3544   0.1735
     REPORT      107        0        0   0.0599   0.0280

  operation    count   failed    >3sec     mean   median avglag (ms)
     accept       10        0        0   0.2808   0.2942   0.8490
     create       17        0        0   0.0560   0.0484   1.0024
     invite       17        0        2   0.8713   0.4774   0.9585
       poll       64        0        0   0.3856   0.3234   0.0000
 reply done       12        0        0   0.0177   0.0174   1.9181
    startup       20        0        0   0.7369   0.6023   0.0000
 PASS

The pass / fail criteria are defined in `contrib/performance/loadtest/profiles.py <http://trac.calendarserver.org/browser/CalendarServer/trunk/contrib/performance/loadtest/profiles.py>`_ for operations and `contrib/performance/loadtest/population.py <http://trac.calendarserver.org/browser/CalendarServer/trunk/contrib/performance/loadtest/population.py>`_ for individual requests, and are generally derived from execution time and failure rate.

---------------------
Configuration
---------------------

The client sim's default configuration file is found here::

 contrib/performance/loadtest/config.plist

The config file defines

- how to connect to the server
- which user accounts to use
- client 'arrival' policy, which specifies how many of the available accounts to use, and how quickly they are initialized
- which client behaviors are performed, along with optional configuration of each behavior

Server Specification
---------------------

Specify the URI to which the client sim should connect, e.g::

                <!-- Identify the server to be load tested. -->
                <key>server</key>
                <string>https://127.0.0.1:8443/</string>

User Accounts
-------------

User accounts are defined in the 'accounts' key of the plist:

::

                <!-- Define the credentials of the clients which will be used to load test 
                        the server. These credentials must already be valid on the server. -->
                <key>accounts</key>
                <dict>
                        <!-- The loader is the fully-qualified Python name of a callable which 
                                returns a list of directory service records defining all of the client accounts 
                                to use. contrib.performance.loadtest.sim.recordsFromCSVFile reads username, 
                                password, mailto triples from a CSV file and returns them as a list of faked 
                                directory service records. -->
                        <key>loader</key>
                        <string>contrib.performance.loadtest.sim.recordsFromCSVFile</string>

                        <!-- Keyword arguments may be passed to the loader. -->
                        <key>params</key>
                        <dict>
                                <!-- recordsFromCSVFile interprets the path relative to the config.plist, 
                                        to make it independent of the script's working directory while still allowing 
                                        a relative path. This isn't a great solution. -->
                                <key>path</key>
                                <string>contrib/performance/loadtest/accounts.csv</string>
                        </dict>
                </dict>

The accounts.csv file has lines like shown below::

 user01,user01,User 01,user01@example.com

Client Arrival
----------------

This section configures the number of accounts to use, and defines how quickly clients are initialized when the sim starts::

                <!-- Define how many clients will participate in the load test and how 
                        they will show up. -->
                <key>arrival</key>
                <dict>

                        <!-- Specify a class which creates new clients and introduces them into 
                                the test. contrib.performance.loadtest.population.SmoothRampUp introduces 
                                groups of new clients at fixed intervals up to a maximum. The size of the 
                                group, interval, and maximum are configured by the parameters below. The 
                                total number of clients is groups * groupSize, which needs to be no larger 
                                than the number of credentials created in the accounts section. -->
                        <key>factory</key>
                        <string>contrib.performance.loadtest.population.SmoothRampUp</string>

                        <key>params</key>
                        <dict>
                                <!-- groups gives the total number of groups of clients to introduce. -->
                                <key>groups</key>
                                <integer>20</integer>

                                <!-- groupSize is the number of clients in each group of clients. It's 
                                        really only a "smooth" ramp up if this is pretty small. -->
                                <key>groupSize</key>
                                <integer>1</integer>

                                <!-- Number of seconds between the introduction of each group. -->
                                <key>interval</key>
                                <integer>3</integer>
                        </dict>

                </dict>

In the default configuration, one client is initialized every 3 seconds, until 20 clients are initialized. As soon as a client is initialized, it begins to perform its specified behaviors at the configured rates (see "Client Behaviors").

To increase the client load, increase the number of groups.

To increase the rate at which clients are initialized, reduce 'interval' and / or increase 'groupSize'

Remember: **The total number of clients is groups * groupSize, which needs to be no larger than the number of credentials created in the accounts section**

Client Behaviors
----------------

The 'clients' plist key is an array of dictionaries, where each dict has the keys:

- 'software', which specifies the implementation class for this client. For example:

::

 <key>software</key>
 <string>contrib.performance.loadtest.ical.SnowLeopard</string>

- 'params', optionally specifying parameters accepted by this software. For example:

::

  <!-- Arguments to use to initialize the SnowLeopard instance. -->
  <key>params</key>
  <dict>
          <!-- SnowLeopard can poll the calendar home at some interval. This is 
                  in seconds. -->
          <key>calendarHomePollInterval</key>
          <integer>30</integer>

          <!-- If the server advertises xmpp push, SnowLeopard can wait for notifications 
                  about calendar home changes instead of polling for them periodically. If 
                  this option is true, then look for the server advertisement for xmpp push 
                  and use it if possible. Still fall back to polling if there is no xmpp push 
                  advertised. -->
          <key>supportPush</key>
          <false />
  </dict>

- 'profiles' is an array of dictionaries specifying individual behaviors of this software. Each dict has a 'class' key which specifies the implementation class for this behavior, and a 'params' dict with options specific to that behavior. For example:

::

 <!-- This profile accepts invitations to events, handles cancels, and
      handles replies received. -->
 <dict>
         <key>class</key>
         <string>contrib.performance.loadtest.profiles.Accepter</string>

         <key>params</key>
         <dict>
                 <key>enabled</key>
                 <true/>

                 <!-- Define how long to wait after seeing a new invitation before 
                         accepting it. -->
                 <key>acceptDelayDistribution</key>
                 <dict>
                         <key>type</key>
                         <string>contrib.performance.stats.NormalDistribution</string>
                         <key>params</key>
                         <dict>
                                 <!-- mean -->
                                 <key>mu</key>
                                 <integer>60</integer>
                                 <!-- standard deviation -->
                                 <key>sigma</key>
                                 <integer>60</integer>
                         </dict>
                 </dict>
         </dict>
 </dict>

Some parameters may be safely modified to suit your purposes, for example you might choose to disable certain profiles (by setting 'enabled' to false) in order to simulate only specific types of activity. Also, you can edit the params for the various distributions to configure how often things happen.

Motivated readers may also develop new behaviors for existing clients, or even entirely new clients. An example of adding a new behavior to an existing client can be found here: http://trac.calendarserver.org/changeset/8428. As of this writing, we have only the one Snow Leopard client simulator, and would happily accept patches that implement additional clients!

---------------------
Scalability
---------------------

A good amount of activity can be generated by a single client sim instance, and that should be suitable for most cases. However, if your task is performance or scalability testing, you will likely want to generate more load than can be presented by a single CPU core (which is all you can get from a single Python process). By adding a 'workers' array to the sim's config file you can specify the use of additional sim instances on the local host, and / or remote hosts. In this configuration, the master process will distribute work across all the workers. In general, you shouldn't need additional workers unless you are approaching CPU saturation for your existing sim instance(s). The "lag" statistic is another useful metric for determining whether the client sim is hitting its targets - if it gets too high, consider adding workers.

The specific approach you take when configuring a high load depends on your goals and available resources. If your goal is to beat down a server until it melts into the floor, it is legitimate to use a less accurate simulation by reducing the timers and intervals in the client sim's behavior configuration. If instead you wish to see how many 'realistic' clients your server can service, you will want to stick with reasonable values for timers and intervals, and instead increase load by configuring more user accounts (in the 'arrival' section of the config file, and the separate user accounts file).

To use four instances on the local host::

 <key>workers</key>
 <array>
     <string>./python contrib/performance/loadtest/ampsim.py</string>
     <string>./python contrib/performance/loadtest/ampsim.py</string>
     <string>./python contrib/performance/loadtest/ampsim.py</string>
     <string>./python contrib/performance/loadtest/ampsim.py</string>
 </array>

To use four instances each on two different remote hosts, use something like::

 <key>workers</key>
 <array>
     <string>exec ssh blade2 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade2 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade2 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade2 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade3 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade3 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade3 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade3 'cd ~/ccs/CalendarServer ; exec ./python contrib/performance/loadtest/ampsim.py'</string>
 </array>

**When using remote hosts, the ssh commands must work in an unattended fashion, so configure SSH keys as needed**. Also, each remote host needs to have a Calendar Server SVN checkout. In this example, the hosts blade2 and blade3 need to have an SVN checkout of Calendar Server at ~/ccs/CalendarServer.

Configuration of the additional workers is handled by the master, so you need not distribute the sim's config file to the other hosts. Each instance gets an identical copy of the config. The amount of work attempted by the sim is not changed by adding workers; instead, the master distributes work (i.e. user accounts) across the workers. To do more work, add user accounts.

When running the sim using multiple instances, the standard output of each child instance is sent to the master. For example, when starting with four instances::

 Loaded 99 accounts.
 Initiating worker configuration
 Initiating worker configuration
 Initiating worker configuration
 Initiating worker configuration
 Worker configuration complete.
 Worker configuration complete.
 Worker configuration complete.
 Worker configuration complete.
 user01 - - - - - - - - - - -  startup BEGIN 
 ...


