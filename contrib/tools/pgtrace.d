#!/usr/sbin/dtrace -qs 

/* 
 * USAGE      : postgresql_stat.d 
 * 
 * DESCRIPTION: 
 *   Count postgres operations over time 
 * 
## 
# Copyright (c) 2011-2015 Apple Inc. All rights reserved. 
# 
# Licensed under the Apache License, Version 2.0 (the "License"); 
# you may not use this file except in compliance with the License. 
# You may obtain a copy of the License at 
# 
# http://www.apache.org/licenses/LICENSE-2.0 
# 
# Unless required by applicable law or agreed to in writing, software 
# distributed under the License is distributed on an "AS IS" BASIS, 
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. 
# See the License for the specific language governing permissions and 
# limitations under the License. 
## 
 */ 

dtrace:::BEGIN  
{ 
    /* starting values */ 
    txnstart = 0; 
    txncommit = 0; 
    txnabort = 0; 
    querystart = 0; 
    querydone = 0; 
    lwacquire = 0; 
    lwwait = 0; 
    lockstart = 0; 
    deadlock = 0; 
    checkpt = 0; 
    bufferread = 0; 
    bufferflush = 0; 
    bufferwrite = 0; 
    walwrite = 0; 

    txnoutstanding = 0; 
    queryoutstanding = 0; 
     
    txntime = 0; 
    querytime = 0; 

    txnstart_total = 0; 
    txncommit_total = 0; 
    txnabort_total = 0; 
    querystart_total = 0; 
    querydone_total = 0; 
    lwacquire_total = 0; 
    lwwait_total = 0; 
    lockstart_total = 0; 
    deadlock_total = 0; 
    checkpt_total = 0; 
    bufferread_total = 0; 
    bufferflush_total = 0; 
    bufferwrite_total = 0; 
    walwrite_total = 0; 
    seconds_total = 0; 
} 

postgresql*:::transaction-start 
{ 
    txnstart++; 
    txnoutstanding++; 
    self->tstxn = timestamp; 
} 

postgresql*:::transaction-commit 
/self->tstxn/ 
{ 
    txncommit++; 
    txnoutstanding--; 
    difftime = timestamp - self->tstxn; 
    txntime += difftime; 
    self->tstxn=0; 
} 

postgresql*:::transaction-abort 
/self->tstxn/ 
{ 
    txnabort++; 
    txnoutstanding--; 
    txntime += timestamp - self->tstxn; 
    self->tstxn=0; 
} 

postgresql*:::query-start 
{ 
    querystart++; 
    queryoutstanding++; 
    self->tsq = timestamp; 
} 

postgresql*:::query-done 
/self->tsq/ 
{ 
    querydone++; 
    queryoutstanding--; 
    querytime += timestamp - self->tsq; 
    self->tsq=0; 
} 

postgresql*:::lwlock-acquire 
/arg0 < 27/ 
{ 
    lwacquire++; 
} 

postgresql*:::lwlock-wait-start 
/arg0 < 27/ 
{ 
    lwwait++; 
} 

postgresql*:::lock-wait-start 
/arg0 < 27/ 
{ 
    lockstart++; 
} 

postgresql*:::deadlock-found 
/arg0 < 27/ 
{ 
    deadlock++; 
} 

postgresql*:::checkpoint-start 
{ 
    checkpt++; 
} 

postgresql*:::buffer-read-start 
{ 
    bufferread++; 
} 

postgresql*:::buffer-flush-start 
{ 
    bufferflush++; 
} 

postgresql*:::buffer-write-dirty-start 
{ 
    bufferwrite++; 
} 

postgresql*:::wal-buffer-write-dirty-start 
{ 
    walwrite++; 
} 

profile:::tick-1s 
/seconds_total % 25 == 0/ 
{ 
    printf("\n%34s %27s %13s %6s %6s %6s %20s %6s\n", "<-----------Transaction---------->", "<----------Query---------->", "<-LW Locks-->", "Lock", "Dead", "Check", "<------Buffers----->", "WAL"); 
    printf("%6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s\n", "Start", "Commit", "Abort", "Active", "Time", "Start", "Done", "Active", "Time", "Acq", "Wait", "Acq", "lock", "point", "Read", "Flush", "Write", "Write"); 
} 

profile:::tick-1s 
/txnoutstanding < 0/ 
{ 
    txnoutstanding = 0; 
} 

profile:::tick-1s 
/queryoutstanding < 0/ 
{ 
    queryoutstanding = 0; 
} 

profile:::tick-1s 
{ 

    avtxtime = (txntime / ((txncommit + txnabort) != 0 ? (txncommit + txnabort) : 1))/1000000; 
    avtxtime = (avtxtime >= 1000000) ? -1 : avtxtime; 
    avquerytime = (querytime / (querydone != 0 ? querydone : 1))/1000; 
    avquerytime = (avquerytime >= 1000000) ? -1 : avquerytime; 
    printf("%6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d\n", txnstart, txncommit, txnabort, txnoutstanding, avtxtime, querystart, querydone, queryoutstanding, avquerytime, lwacquire, lwwait, lockstart, deadlock, checkpt, bufferread, bufferflush, bufferwrite, walwrite); 

    txnstart_total += txnstart; 
    txncommit_total += txncommit; 
    txnabort_total += txnabort; 
    querystart_total += querystart; 
    querydone_total += querydone; 
    lwacquire_total += lwacquire; 
    lwwait_total += lwwait; 
    lockstart_total += lockstart; 
    deadlock_total += deadlock; 
    checkpt_total += checkpt; 
    bufferread_total += bufferread; 
    bufferflush_total += bufferflush; 
    bufferwrite_total += bufferwrite; 
    walwrite_total += walwrite; 
    seconds_total++; 

    txnstart = 0; 
    txncommit = 0; 
    txnabort = 0; 
    querystart = 0; 
    querydone = 0; 
    lwacquire = 0; 
    lwwait = 0; 
    lockstart = 0; 
    deadlock = 0; 
    checkpt = 0; 
    bufferread = 0; 
    bufferflush = 0; 
    bufferwrite = 0; 
    walwrite = 0; 
     
    txntime = 0; 
    querytime = 0; 
} 

dtrace:::END  
{ 
    printf("\nAverage count/sec\n"); 

    printf("\n%20s %13s %13s %6s %6s %6s %20s %6s\n", "<----Transaction--->", "<---Query--->", "<-LW Locks-->", "Lock", "Dead", "Check", "<------Buffers----->", "WAL"); 
    printf("%6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s\n", "Start", "Commit", "Abort", "Start", "Done", "Acq", "Wait", "Acq", "lock", "point", "Read", "Flush", "Write", "Write"); 
    printf("%6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d %6d\n", txnstart_total/seconds_total, txncommit_total/seconds_total, txnabort_total/seconds_total, querystart_total/seconds_total, querydone_total/seconds_total, lwacquire_total/seconds_total, lwwait_total/seconds_total, lockstart_total/seconds_total, deadlock_total/seconds_total, checkpt_total/seconds_total, bufferread_total/seconds_total, bufferflush_total/seconds_total, bufferwrite_total/seconds_total, walwrite_total/seconds_total);
} 
