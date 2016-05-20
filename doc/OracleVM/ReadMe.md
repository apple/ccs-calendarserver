# Local Oracle Development

## Setup

* Get VirtualBox
* Install OTN\_Developer\_Day\_VM\_12c.otn
* Install instantclient locally

## Run

### VM
* Run VirtualBox
* Add the rebuild.sql script to the VM shell
* Copy the current_oracle.sql to the VM shell
* Run sqlplus (`user: hr` `pswd:oracle`)
* In sqlplus: `@rebuild;`

### CS
* Configure the DB:

    endpoint: tcp:192.168.56.101:1521
    database: orcl
    user: hr
    password: oracle

* Paths: ensure that `~/.oracle/instantclient_xxx` is in `LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`, and `ORACLE_HOME`

* Run server
