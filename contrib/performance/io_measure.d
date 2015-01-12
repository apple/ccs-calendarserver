/*
 * Copyright (c) 2010-2015 Apple Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
