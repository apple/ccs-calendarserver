
/*
 * Trace information about I/O and SQL events.
 */

#pragma D option switchrate=10hz

#include "sql_measure.d"

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

#define READ(fname) \
pid$target::fname:return \
{ \
	printf("READ %d\n\1", arg1); \
}

READ(read)
READ(pread)
READ(readv)

#define WRITE(fname) \
pid$target::fname:return \
{ \
	printf("WRITE %d\n\1", arg1); \
}

WRITE(write)
WRITE(pwrite)
WRITE(writev)

syscall::execve:entry
/copyinstr(arg0) == "CalendarServer dtrace benchmarking signal"/
{
	printf("MARK x\n\1");
}
