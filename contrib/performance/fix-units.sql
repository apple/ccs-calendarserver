-- Set the units of all of the benchmarks to what they really are.

update codespeed_benchmark set units_title = 'Statements' where name like '%-SQLcount';
update codespeed_benchmark set units_title = 'Bytes' where name like '%-read';
update codespeed_benchmark set units_title = 'Bytes' where name like '%-write';
update codespeed_benchmark set units_title = 'Bytes' where name like '%-pagein';
update codespeed_benchmark set units_title = 'Bytes' where name like '%-pageout';

update codespeed_benchmark set units = 'statements' where name like '%-SQLcount';
update codespeed_benchmark set units = 'bytes' where name like '%-read'; 
update codespeed_benchmark set units = 'bytes' where name like '%-write';
update codespeed_benchmark set units = 'bytes' where name like '%-pagein';
update codespeed_benchmark set units = 'bytes' where name like '%-pageout';
