create or replace function next_job return integer is
  cursor c1 is select JOB_ID from JOB for update skip locked;
  result integer;
begin
  open c1;
  fetch c1 into result;
  select JOB_ID from JOB where ID = result for update;
  return result;
end;
/
