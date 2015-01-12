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
