#define READ(fname) \
syscall::fname:return, syscall::fname ## _nocancel:return \
/execname == "postgres"/ \
{ \
	printf("READ %d\n\1", arg0); \
}

READ(read)
READ(readv)
READ(pread)

#define WRITE(fname) \
syscall::fname:entry, syscall::fname ## _nocancel:entry \
/execname == "postgres"/ \
{ \
	printf("WRITE %d\n\1", arg2); \
}

WRITE(write)
WRITE(writev)
WRITE(pwrite)

dtrace:::BEGIN
{
	/* Let the watcher know things are alright.
	 */
	printf("READY\n");
}

syscall::execve:entry
/copyinstr(arg0) == "CalendarServer dtrace benchmarking signal"/
{
	printf("MARK x\n\1");
}
