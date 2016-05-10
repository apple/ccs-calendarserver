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

The sim should begin logging its activity to stdout, a sample of which is shown in the next section.

- To stop the sim, type control-c.

---------------------
Reporting
---------------------

Runtime Reporting
-----------------

While running, the sim will log its activity to stdout. Simulator activity is organized into a two-level hierarchy: client behaviors (e.g. create event, poll, respond to events) which are composed of individual HTTP requests (e.g. GET, PUT, DELETE, etc).

For example, the sim logs the following right at startup as it initializes the users:

::

 Loaded 99 accounts.
 user01 - - - - - - - - - - - startup: 10.11 BEGIN 
 user02 - - - - - - - - - - - startup: 10.11 BEGIN 
 user02 request 207✓[ 0.10 s] PROPFIND{principal} /principals/__uids__/10000000-0000-0000-0000-000000000002/
 user01 request 207✓[ 0.11 s] PROPFIND{principal} /principals/__uids__/10000000-0000-0000-0000-000000000001/
 user02 request 200✓[ 0.03 s] REPORT{pset} /principals/
 user02 - - - - - - - - - - -     poll BEGIN 
 user01 request 200✓[ 0.03 s] REPORT{pset} /principals/
 user01 - - - - - - - - - - -     poll BEGIN 
 user02 request 207✓[ 0.20 s] PROPFIND{home} /calendars/__uids__/10000000-0000-0000-0000-000000000002/
 user01 request 207✓[ 0.20 s] PROPFIND{home} /calendars/__uids__/10000000-0000-0000-0000-000000000001/
 user02 request 207✓[ 0.07 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000002/tasks/
 user01 request 207✓[ 0.07 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000001/calendar/
 user02 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000002/tasks/
 user01 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000001/calendar/
 user02 request 207✓[ 0.06 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000002/tasks/
 user01 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000001/calendar/
 user02 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000002/calendar/
 user01 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000001/tasks/
 user02 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000002/calendar/
 user01 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000001/tasks/
 user02 request 207✓[ 0.05 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000002/calendar/
 user02 request 403✓[ 0.04 s] REPORT{sync-init} /calendars/__uids__/10000000-0000-0000-0000-000000000002/notification/
 user02 - - - - - - - - - - -     poll END [ 0.59 s]
 user02 - - - - - - - - - - - startup: 10.11 END [ 0.71 s]
 user01 request 207✓[ 0.09 s] PROPPATCH{calendar} /calendars/__uids__/10000000-0000-0000-0000-000000000001/tasks/
 user01 request 403✓[ 0.04 s] REPORT{sync-init} /calendars/__uids__/10000000-0000-0000-0000-000000000001/notification/
 user01 - - - - - - - - - - -     poll END [ 0.63 s]
 user01 - - - - - - - - - - - startup: 10.11 END [ 0.77 s]

The first token on each line is the username associated with the activity. Note that client activity is highly interleaved during normal operation.

Client operations are groups of requests that are delimited by lines with many dashes, either BEGIN or END. 'END' lines also include the overall duration of the operation, which is the elapsed wall clock time since the operation started.

Above, we see two behaviors that are nested; the 'startup' operation starts which includes a few requests and also triggers the 'poll' operation.

Individual requests are logged with the word 'request', followed by the HTTP status code, the request duration, the HTTP method of the request, some additional info about the request in curly braces (for example 'principal' refers to the target of a PROPFIND, and sync-init is a type of REPORT), and the URI that is being targeted. Successful requests are indicated by a ✓ while failed requests are indicated with ✗.

Most client operations also log a 'lag' time when they start, e.g.

::

 user18 - - - - - - - - - - -   invite BEGIN {lag  2.32 ms}

'lag' in this context specifies the time elapsed between when the sim should have started this operation (based on the sim configuration) and when it actually started. This is used as a measure of client sim health; if the lag values begin to grow too high, that indicates that the client sim is 'slipping' and is unable to perform its various activities at the rates specified in the config file. This is python 2.x, so a single instance of the client sim is limited to one CPU core. See the `Scalability`_ section for information about how to scale the load sim by combining multiple instances.

Summary Reports
---------------
When the sim stops or is killed, it emits a summary report that displays the total number of users that were active in this run, and overall counts for both individual requests and also the higher-level client operations. Also we display quality of service information used to grade the run as PASS or FAIL. An example report is shown below::

 ** REPORT **
 
 * Client
   Cpu Time : user 29.01 sys 4.34  total 00:00:33
    Clients : 20
        Qos : 0.7060  
   Run Time : 00:15:59
 Start Time : 01/21 14:19:05
      Users : 20
 
 * Details
 request                           count   failed   >0.1 sec   >0.5 sec     >1 sec     >3 sec     >5 sec    >10 sec    >30 sec     mean   median   stddev      QoS   STATUS
 --------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 DELETE{event}                         3        0          0          0          0          0          0          0          0   0.0715   0.0771   0.0101   0.3573         
 GET                                   3        0          2          0          0          0          0          0          0   0.1330   0.1381   0.0259   0.0000         
 GET{event}                          219        0        117          1          0          0          0          0          0   0.1454   0.1056   0.0987   1.4541         
 POST{attach}                        138        0        138         19          0          0          0          0          0   0.3243   0.2871   0.1502   0.0000         
 POST{fb-small}                     1279        0        664         10          0          0          0          0          0   0.1299   0.1026   0.0807   0.2598         
 POST{share-calendar}                 60        0         60          5          0          0          0          0          0   0.2990   0.2686   0.1206   0.0000         
 PROPFIND{home}                       20        0         20          0          0          0          0          0          0   0.1534   0.1454   0.0204   0.6136         
 PROPFIND{principal}                  20        0          1          0          0          0          0          0          0   0.0798   0.0829   0.0125   0.9319         
 PROPPATCH{calendar}                 120        0          2          0          0          0          0          0          0   0.0608   0.0569   0.0124   0.6216         
 PUT{attendee-medium}                  2        0          2          0          0          0          0          0          0   0.1585   0.1628   0.0044   0.2426         
 PUT{attendee-small}                   1        0          1          1          0          0          0          0          0   0.6156   0.6156   0.0000   1.2312         
 PUT{event}                          220        0        220         40         10          0          0          0          0   0.3760   0.2587   0.3363   1.5041         
 PUT{organizer-large}                  7        0          6          1          0          0          0          0          0   0.2066   0.1865   0.1353   0.4050         
 PUT{organizer-medium}               111        0         81          8          2          0          0          0          0   0.2419   0.1381   0.2725   0.5354         
 PUT{organizer-small}                 22        0         13          1          0          0          0          0          0   0.1792   0.1091   0.1762   0.7168         
 PUT{update}                          78        0         78          6          0          0          0          0          0   0.3087   0.2923   0.1048   1.2346         
 REPORT{cpsearch}                   1279        0         63          0          0          0          0          0          0   0.0482   0.0378   0.0385   0.0000         
 REPORT{multiget-small}               15        0          0          0          0          0          0          0          0   0.0510   0.0496   0.0052   0.2039         
 REPORT{pset}                         20        0          0          0          0          0          0          0          0   0.0300   0.0302   0.0008   0.9120         
 REPORT{sync-init}                    20        0          0          0          0          0          0          0          0   0.0427   0.0394   0.0099   0.5854         
 REPORT{sync}                         15        0          0          0          0          0          0          0          0   0.0481   0.0471   0.0032   0.1925         
 
 operation                         count   failed   >0.1 sec   >0.5 sec     >1 sec     >3 sec     >5 sec    >10 sec    >30 sec     mean   median   stddev  avglag (ms)   STATUS
 ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 accept                                3        0          3          1          0          0          0          0          0   0.4447   0.2947   0.2365       7.8805         
 create                              220        0        220         40         10          0          0          0          0   0.3780   0.2615   0.3363      13.1159         
 download                              3        0          3          0          0          0          0          0          0   0.1515   0.1647   0.0343       0.0000         
 invite                              140        0        140        136        105         22          3          0          0   1.8759   1.5909   1.1846       2.3190         
 poll                                 20       20         20         20          0          0          0          0          0   0.6612   0.6573   0.0878       0.0000     FAIL
 push                                447        0          0          0          0          0          0          0          0   0.0002   0.0001   0.0004       0.0000         
 startup: 10.11                       20        0         20         20          0          0          0          0          0   0.7734   0.7687   0.0903       0.0000         
 update{description}                  38        0         38         19          0          0          0          0          0   0.5170   0.5315   0.1834      41.3110         
 update{title}                        40        0         40         17          1          0          0          0          0   0.5271   0.4719   0.1920      28.1850         
 
 *** FAIL
 Greater than 1% POLL failed
 Exit code: 1
 


The pass / fail criteria are defined in `contrib/performance/loadtest/thresholds.json <http://trac.calendarserver.org/browser/CalendarServer/trunk/contrib/performance/loadtest/thresholds.json>`_. This json data describes the maximum percentage ("thresholds") of each request and operation type that are allowed in each time bucket ("limits"), which if exceeded will cause that type to be failed. For example, the configuration for requests uses the following buckets, which correspond to the time buckets in the report: (values in seconds)

``[   0.1,   0.5,   1.0,   3.0,   5.0,  10.0,  30.0]``

The PUT{event} threshold configuration states:

``[ 100.0, 100.0, 100.0,  75.0,  50.0,  25.0,   0.5]``

This means the PUT{event} type is considered too slow if more than 75% of them take longer than 3 seconds, or more than 50% take longer than 5 seconds, or more than 25% take longer than 10 seconds, or more than .5% take longer than 30 seconds. Setting a bucket to 100% effectively ignores that bucket in calculating the pass / fail judgement. If it seems like these values might be somewhat arbitrary, that's because they are.

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

The client sim supports testing of 'podded' environments. If you aren't using pods, not to worry, the default configuration still works. For each pod, define the uri and other server-specific attributes such as the amp push host and port (used for client notifications in lieu of APNS), and the stats socket port (if enabled in the server config).

::

  <key>servers</key>
  <dict>
      <key>PodA</key>
      <dict>
          <key>enabled</key>
          <true/>
 
          <!-- Identify the server to be load tested. -->
          <key>uri</key>
          <string>https://localhost:8443</string>
 
          <key>ampPushHosts</key>
          <array>
              <string>localhost</string>
          </array>
          <key>ampPushPort</key>
          <integer>62311</integer>
 
          <!--  Define whether server supports stats socket. -->
          <key>stats</key>
          <dict>
              <key>enabled</key>
              <true/>
              <key>Port</key>
              <integer>8100</integer>
          </dict>
      </dict>
      ...

User Accounts
-------------

User accounts are defined in the 'accounts' key of the plist:

::

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

                <!-- When there are accounts for multiple pods, interleave the accounts for each
                    pod so that the arrival mechanism will cycle clients between each pod. -->
                <key>interleavePods</key>
                <true/>
            </dict>
        </dict>


The accounts.csv file has lines like shown below::

 user01,user01,User 01,user01@example.com,10000000-0000-0000-0000-000000000001,PodA

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
         <integer>10</integer>

         <!-- groupSize is the number of clients in each group of clients. It's
             really only a "smooth" ramp up if this is pretty small. -->
         <key>groupSize</key>
         <integer>2</integer>

         <!-- Number of seconds between the introduction of each group. -->
         <key>interval</key>
         <integer>3</integer>

         <!-- Number of clients each user is assigned to. -->
         <!-- Set weight of clients to 1 if this is > 1. Number of clients must match this value if > 1. -->
         <key>clientsPerUser</key>
         <integer>1</integer>
     </dict>

 </dict>


In the default configuration, three clients are initialized every 3 seconds, until 30 clients are initialized (groups * groupSize). As soon as a client is initialized, it begins to perform its specified behaviors at the configured rates (see "Client Behaviors").

To increase the client load, increase the number of groups and / or groupSize. Take care not to exceed the number of accounts defined in accounts.csv.

To increase the rate at which clients are initialized, reduce 'interval'.

Client Behaviors
----------------

Client behaviors are defined in `contrib/performance/loadtest/clients.plist <http://trac.calendarserver.org/browser/CalendarServer/trunk/contrib/performance/loadtest/clients.plist>`_.  The 'clients' plist key is an array of dictionaries describing the client. The clients.plist is well commented, so no need to repeat those details here.

'profiles' is an array of dictionaries specifying individual behaviors of each client. Each dict has a 'class' key which specifies the implementation class for this behavior, and a 'params' dict with options specific to that behavior. See the plist for more information.

Some parameters may be safely modified to suit your purposes, for example you might choose to disable certain profiles (by setting 'enabled' to false) in order to simulate only specific types of activity. Also, you can edit the params for the various distributions to configure how often things happen.

This sim is designed to facilitate easy integration of new behaviors for existing clients, or even entirely new clients. An example of adding a new behavior to an existing client can be found here: http://trac.calendarserver.org/changeset/8428.

---------------------
Scalability
---------------------

A good amount of activity can be generated by a single client sim instance, and that should be suitable for most cases. However, if your task is performance or scalability testing, you will likely want to generate more load than can be presented by a single CPU core (which is all you can get from a single Python process). By adding a 'workers' array to the sim's config file you can specify the use of additional sim instances on the local host, and / or remote hosts. In this configuration, the master process will distribute work across all the workers. In general, you shouldn't need additional workers unless you are approaching CPU saturation for your existing sim instance(s). The "lag" statistic is another useful metric for determining whether the client sim is hitting its targets - if it gets too high, consider adding workers.

The specific approach you take when configuring a high load depends on your goals and available resources. If your goal is to beat down a server until it melts into the floor, it is legitimate to use a less accurate simulation by reducing the timers and intervals in the client sim's behavior configuration. If instead you wish to see how many 'realistic' clients your server can service, you will want to stick with reasonable values for timers and intervals, and instead increase load by configuring more user accounts (in the 'arrival' section of the config file, and the separate user accounts file).

To use four instances on the local host::

        <key>workers</key>
        <array>
            <string>./bin/python contrib/performance/loadtest/ampsim.py</string>
            <string>./bin/python contrib/performance/loadtest/ampsim.py</string>
            <string>./bin/python contrib/performance/loadtest/ampsim.py</string>
            <string>./bin/python contrib/performance/loadtest/ampsim.py</string>
        </array>

To use two instances each on two different remote hosts, use something like::

 <key>workers</key>
 <array>
     <string>exec ssh blade2 'cd ~/ccs/CalendarServer ; exec ./bin/python contrib/performance/loadtest/ampsim.py'</string>
     <string>exec ssh blade3 'cd ~/ccs/CalendarServer ; exec ./bin/python contrib/performance/loadtest/ampsim.py'</string>
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

