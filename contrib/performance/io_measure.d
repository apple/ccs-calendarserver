
/*
 * Report current timestamp (nanoseconds) of io and SQLite3 events.
 */

#pragma D option switchrate=10hz

/*
 * Low-level I/O stuff
 */

io:::start
/args[0]->b_flags & B_READ/
{
        printf("B_READ %d\n\1", args[0]->b_bcount);
}

io:::start
/!(args[0]->b_flags & B_READ)/
{
        printf("B_WRITE %d\n\1", args[0]->b_bcount);
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
        printf("EXECUTE RETURN %d %s\n\1", timestamp, self->sql);
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
        printf("EXECUTE ENTRY %d %s\n\1", timestamp, copyinstr(arg1));
}

pid$target::PQexec:return
{
	printf("EXECUTE RETURN %d\n\1", timestamp);
}
