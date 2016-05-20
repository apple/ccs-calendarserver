
SET FEEDBACK 1
SET ECHO OFF


Prompt Connecting as SYSTEM to create hr
Connect system/oracle@localhost:1521/orcl

spool cre_hr.log


Prompt Dropping user hr
DROP USER hr CASCADE;

Prompt Creating user hr
CREATE USER hr IDENTIFIED BY oracle
 DEFAULT TABLESPACE users
 TEMPORARY TABLESPACE temp
 QUOTA UNLIMITED ON users;

Prompt Setting permissions for user hr
GRANT create session
    , create table
    , create procedure
    , create sequence
    , create trigger
    , create view
    , create synonym
    , alter session
    , create type
    , create materialized view
    , query rewrite
    , create dimension
    , create any directory
    , alter user
    , resumable
    , ALTER ANY TABLE  -- These
    , DROP ANY TABLE   -- five are
    , LOCK ANY TABLE   -- needed
    , CREATE ANY TABLE -- to use
    , SELECT ANY TABLE -- DBMS_REDEFINITION
TO hr;

GRANT select_catalog_role
    , execute_catalog_role
TO hr;

Prompt Connecting as user hr
CONNECT hr/oracle@localhost:1521/orcl

Prompt Installing current_oracle.sql
@current_oracle.sql

spool off
