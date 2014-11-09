**************************************************
Calendar and Contacts Server Administrator's Guide
**************************************************

#. Install_

     #) Requirements_
     #) Local or system installation

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
* C compiler
* subversion client
* curl
* OpenSSL libraries and development files
* Readline libraries and development files
* Kerberos libraries and development files


The exact process for installing the above is beyond the scope of this document,
and varies by platform. Try to use a package management system if you can. As a
convenience, the following command will install the missing dependencies on
Ubuntu 13.10 server:

::

 sudo apt-get install build-essential subversion python-setuptools curl \
 libssl-dev libreadline6-dev python-dev libkrb5-dev

Next, run ``bin/develop`` to get the remaining dependencies

(to be continued...)

