**************************************************
Calendar and Contacts Server Administrator's Guide
**************************************************

#. Install_

     #) Requirements_
     #) Installation_

#. Configure

     #) Overview
     #) Sample config files
     #) Layered configuration with ``Includes``

#. Prepare database

     #) Create database and user
     #) Apply schema

#. Run

     #) Runtime dependency graph
     #) Start and stop
     #) Reload

#. Monitor

     #) Important resources
     #) Logs
     #) Processes
     #) Stats socket
     #) Included tools

#. Maintain

     #) Backup and restore
     #) Upgrade
     #) Prune and purge


Install
=======

Requirements
------------
Calendar and Contacts Server (CCS) can be used on any unix-like platform that
fulfills the below requirements, and is most commonly deployed on OS X or Linux. 
CCS is written in python, and requires various 3rd party software written in C 
and python. The external dependencies effectively limit portability of CCS to a 
smaller number of platforms than are supported by python.

Package management systems may provide an easier means for installing CCS and
its dependencies. This documentation is targeted at package authors, and anyone
else who wishes to install "from source".

Software dependencies can be classified into two groups: software that must be
available prior to using CCS, and software that can be obtained by the included 
setup script (``bin/develop``).

Before getting started with CCS, you need:

* python 2.7.x, with development files
* python setuptools
* python virtualenv
* pip
* C compiler
* git client
* curl
* OpenSSL libraries and development files
* Readline libraries and development files
* Kerberos libraries and development files


The exact process for installing the above is beyond the scope of this document,
and varies by platform. Try to use a package management system if you can. As a
convenience, the following command will install the missing dependencies on
Ubuntu 13.10 server:

::

 sudo apt-get install build-essential git python-setuptools curl \
 libssl-dev libreadline6-dev python-dev libkrb5-dev libffi-dev \
 libldap2-dev libsasl2-dev zlib1g-dev

Next, run ``bin/develop`` to get the remaining dependencies (note that for some releases on some distributions it may be necessary to run ``/bin/bash bin/develop`` to force the script to run under the bash shell)

Installation
-----------------------------

The ./bin/develop script is not intended for production use, but rather as a quick-and-dirty way to bootstrap the service for development or evaluation purposes. To perform an installation of the service and any required dependencies that aren't already provided at the system level, use the bin/package tool, which simply creates a directory at the specified location to contain all the software. 

Note that this tool does not intend to integrate with 'standard' filesystem hierarchy conventions, for example by putting executable things in '/usr/bin', data in '/var', etc. Instead, everything installed by this tool goes under a single directory, and that directory probably shouldn't be "/", "/usr", or "/usr/local". Instead, pick something like "/usr/local/CalendarServer" or "/opt/var/CalendarServer" to make sure not to interfere with anything else. As an ease-of-use convenience, one of the items emitted by the ./bin/package script in the target directory is an "environment.sh" file. This should be sourced at shell startup, and augments PATH and other environment variables that allow you to use this software without having to type absolute paths all the time.
