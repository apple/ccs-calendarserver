#!/bin/bash

echo Creating caldav database user
/usr/bin/createuser --username=_postgres caldav --no-superuser --createdb --no-createrole || exit 1

echo Creating caldav database
/usr/bin/createdb --username=caldav caldav || exit 2

echo Initializing caldav schema
/usr/bin/psql -U caldav -f /usr/share/caldavd/lib/python/txdav/common/datastore/sql_schema_v1.sql || exit 3

exit 0
