
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
        printf("%d", args[0]->b_bcount);
}

io:::start
/!(args[0]->b_flags & B_READ)/
{
        printf("%d", args[0]->b_bcount);
}

/*
 * SQLite3 stuff
 */

pid$target:_sqlite3.so:_pysqlite_query_execute:entry
{
        self->executing = 1;
        self->sql = "";
        printf("%d", timestamp);
}

pid$target:_sqlite3.so:_pysqlite_query_execute:return
{
        self->executing = 0;
        printf("%d %s", timestamp, self->sql);
}

pid$target::PyString_AsString:return
/self->executing/
{
        self->sql = copyinstr(arg1);
        self->executing = 0;
}

pid$target:_sqlite3.so:pysqlite_cursor_iternext:entry
{
        printf("%d", timestamp);
}

pid$target:_sqlite3.so:pysqlite_cursor_iternext:return
{
        printf("%d", timestamp);
}
