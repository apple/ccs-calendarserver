---
title: CalDAVClientLibrary
---

## INTRODUCTION

CalDAVClientLibrary is a Python library and tool for CalDAV. It is comprised of four main modules:

* protocol: this implements an HTTP/WebDAV/CalDAV protocol stack, using httplib to communicate with the server.

* client: this implements a CalDAV client session, with higher level functionality than the protocol module (e.g. 'get properties on resource X and return as a dict'). There is a higher level abstraction using an object model to repesent a session, accounts, principals and calendars as objects.

* browser: this implements a shell-like browser that lets you interact with the CalDAV server directly via protocol. You can 'cd' to different parts of the repository, 'ls' to list a collection, 'cat' to read resource data, 'props' to get properties. Then there are some higher level functions such as 'proxies' which let you manage (read and edit) the proxy list for a principal, and 'acl' which lets you manage ACLs directly on resources. For those, the tool takes care of mapping from principal paths to principal URLs etc. Help is provided for each command (type '?'). It is easily extensible by adding new commands.

* ui: a PyObjC application with a WebDAV browser GUI. This provides a file system like browser that allows properties and the data for a selected WebDAV resource do be displayed.

* admin: a user account administration tool. Currently works only with the XML file directory account.

The `runshell.py` script will launch the command line browser shell. The `runadmin.py` script will run the XML directory admin tool.

## GETTING IT

Use GIT to obtain a working copy of the source code. The following command will check out the latest version of CalDAVClientLibrary:

    git clone https://github.com/apple/ccs-caldavclientlibrary.git

Graphical clients which support GIT are also available, including Apple's ​XCode IDE. Consult the documentation for your chosen client for information on how to check out source code.

## SHELL TOOL

### COMMAND LINE OPTIONS

    Usage: runshell [OPTIONS]
    
    Options:
    
    -l              start with HTTP logging on.
    
    --server=HOST   url of the server include http/https scheme and
                    port [REQUIRED].
                    
    --user=USER     user name to login as - will be prompted if not
                    present [OPTIONAL].
                    
    --pswd=PSWD     password for user - will be prompted if not
                    present [OPTIONAL].

### QUICKSTART - COMMANDLINE

To browse a calendar server on the local machine:

    ./runshell.py --server https://localhost:8443

Then type '?' followed by return to see the list of available commands.

## UI TOOL

### QUICKSTART - GUI

Build the GUI app using:

    python setup.py py2app

The application will be placed in the 'dist' directory. Double-click that to launch it. One it it running, click the 'Server' toolbar button and specify a server, user id and password.

The app will then display the top-level of the server resource hierarchy in the browser pane on the left. You can click and navigate through the resources via that pane (the 'Browser' toolbar buttons determine whether the browser uses a column or list view).

When a resource is selected in the browser pane, its properties or data are display in the right hand pane. You can toggle between viewing properties or data by using the 'View' toolbar buttons.

## ADMIN TOOL

### QUICKSTART - COMMANDLINE

To run the tool and see the list of available commands:

    ./runadmin.py --help

## TO DO

Lots of error handling and documentation.
