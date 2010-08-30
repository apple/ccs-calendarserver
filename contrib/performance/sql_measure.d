
/*
 * Make almost all query strings fit.  Please don't have SQL longer than this. :(
 */
#pragma D option strsize=32768

dtrace:::BEGIN
{
	/* Let the watcher know things are alright.
	 */
	printf("READY\n");
}

/*
 * SQLite3 stuff
 */

pid$target:_sqlite3.so:_pysqlite_query_execute:entry
{
	self->executing = 1;
	self->sql = "";
	printf("EXECUTE ENTRY %d\n\1", timestamp);
}

pid$target:_sqlite3.so:_pysqlite_query_execute:return
{
	self->executing = 0;
	printf("EXECUTE SQL %s\n\1", self->sql);
	printf("EXECUTE RETURN %d\n\1", timestamp);
}

pid$target::PyString_AsString:return
/self->executing/
{
	self->sql = copyinstr(arg1);
	self->executing = 0;
}

pid$target:_sqlite3.so:pysqlite_cursor_iternext:entry
{
	printf("ITERNEXT ENTRY %d\n\1", timestamp);
}

pid$target:_sqlite3.so:pysqlite_cursor_iternext:return
{
	printf("ITERNEXT RETURN %d\n\1", timestamp);
}

/*
 * PyGreSQL stuff
 */

pid$target::PQexec:entry
{
	printf("EXECUTE ENTRY %d\n\1", timestamp);
	printf("EXECUTE SQL %s\n\1", copyinstr(arg1));
}

pid$target::PQexec:return
{
	printf("EXECUTE RETURN %d\n\1", timestamp);
}

pid$target::pgsource_fetch:entry
{
	printf("ITERNEXT ENTRY %d\n\1", timestamp);
}

pid$target::pgsource_fetch:return
{
	printf("ITERNEXT RETURN %d\n\1", timestamp);
}
