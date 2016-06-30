# Local Oracle Development

## Setup

### Oracle instantclient

Download instantclient locally from "http://www.oracle.com/technetwork/topics/intel-macsoft-096467.html"

* instantclient-basic-macos.x64-11.2.0.4.0.zip
* instantclient-sdk-macos.x64-11.2.0.4.0.zip

Then run:

	mkdir .oracle
	cd .oracle
	<<copy instantclient zips here>>
	unzip instantclient-basic-macos.x64-11.2.0.4.0.zip
	unzip instantclient-sdk-macos.x64-11.2.0.4.0.zip
	ln -sf . lib
	ln -sf libclntsh.dylib.11.1 libclntsh.dylib
	cd ~
	cat >> .bash_profile
    function oracle_11 () {
        export ORACLE_HOME="$HOME/.oracle/instantclient_11_2";
    
        # make sure we can find the client libraries
        export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$ORACLE_HOME";
        export DYLD_LIBRARY_PATH="$DYLD_LIBRARY_PATH:$ORACLE_HOME";
    }
    ^D

### Local Oracle Database
If you want to run your own Oracle database rather than use an existing one:

* Get VirtualBox
* Install OTN\_Developer\_Day\_VM\_12c.otn

## Run

### VM
* Run VirtualBox
* Add the rebuild.sql script to the VM shell
* Copy the current_oracle.sql to the VM shell
* Run sqlplus (`user: hr` `pswd:oracle`)
* In sqlplus: `@rebuild;`

### CS
* Run the `oracle_11` alias to make sure paths are setup.
* Rebuild the server with `bin/develop` to ensure the `cx_Oracle` module is built
* Configure the DB in caldav-dev.plist:

    endpoint: tcp:192.168.56.101:1521
    database: orcl
    user: hr
    password: oracle

* Run server
