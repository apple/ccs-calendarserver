create sequence RESOURCE_ID_SEQ;
create sequence JOB_SEQ;
create sequence INSTANCE_ID_SEQ;
create sequence ATTACHMENT_ID_SEQ;
create sequence REVISION_SEQ;
create sequence WORKITEM_SEQ;
create table NODE_INFO (
    "HOSTNAME" nvarchar2(255),
    "PID" integer not null,
    "PORT" integer not null,
    "TIME" timestamp default CURRENT_TIMESTAMP at time zone 'UTC' not null, 
    primary key ("HOSTNAME", "PORT")
);

create table NAMED_LOCK (
    "LOCK_NAME" nvarchar2(255) primary key
);

create table JOB (
    "JOB_ID" integer primary key not null,
    "WORK_TYPE" nvarchar2(255),
    "PRIORITY" integer default 0,
    "WEIGHT" integer default 0,
    "NOT_BEFORE" timestamp not null,
    "ASSIGNED" timestamp default null,
    "OVERDUE" timestamp default null,
    "FAILED" integer default 0
);

create table CALENDAR_HOME (
    "RESOURCE_ID" integer primary key,
    "OWNER_UID" nvarchar2(255) unique,
    "STATUS" integer default 0 not null,
    "DATAVERSION" integer default 0 not null
);

create table HOME_STATUS (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into HOME_STATUS (DESCRIPTION, ID) values ('normal', 0);
insert into HOME_STATUS (DESCRIPTION, ID) values ('external', 1);
insert into HOME_STATUS (DESCRIPTION, ID) values ('purging', 2);
create table CALENDAR (
    "RESOURCE_ID" integer primary key
);

create table CALENDAR_HOME_METADATA (
    "RESOURCE_ID" integer primary key references CALENDAR_HOME on delete cascade,
    "QUOTA_USED_BYTES" integer default 0 not null,
    "DEFAULT_EVENTS" integer default null references CALENDAR on delete set null,
    "DEFAULT_TASKS" integer default null references CALENDAR on delete set null,
    "DEFAULT_POLLS" integer default null references CALENDAR on delete set null,
    "ALARM_VEVENT_TIMED" nclob default null,
    "ALARM_VEVENT_ALLDAY" nclob default null,
    "ALARM_VTODO_TIMED" nclob default null,
    "ALARM_VTODO_ALLDAY" nclob default null,
    "AVAILABILITY" nclob default null,
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table CALENDAR_METADATA (
    "RESOURCE_ID" integer primary key references CALENDAR on delete cascade,
    "SUPPORTED_COMPONENTS" nvarchar2(255) default null,
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table NOTIFICATION_HOME (
    "RESOURCE_ID" integer primary key,
    "OWNER_UID" nvarchar2(255) unique,
    "STATUS" integer default 0 not null,
    "DATAVERSION" integer default 0 not null
);

create table NOTIFICATION (
    "RESOURCE_ID" integer primary key,
    "NOTIFICATION_HOME_RESOURCE_ID" integer not null references NOTIFICATION_HOME,
    "NOTIFICATION_UID" nvarchar2(255),
    "NOTIFICATION_TYPE" nvarchar2(255),
    "NOTIFICATION_DATA" nclob,
    "MD5" nchar(32),
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    unique ("NOTIFICATION_UID", "NOTIFICATION_HOME_RESOURCE_ID")
);

create table CALENDAR_BIND (
    "CALENDAR_HOME_RESOURCE_ID" integer not null references CALENDAR_HOME,
    "CALENDAR_RESOURCE_ID" integer not null references CALENDAR on delete cascade,
    "EXTERNAL_ID" integer default null,
    "CALENDAR_RESOURCE_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "BIND_REVISION" integer default 0 not null,
    "MESSAGE" nclob,
    "TRANSP" integer default 0 not null,
    "ALARM_VEVENT_TIMED" nclob default null,
    "ALARM_VEVENT_ALLDAY" nclob default null,
    "ALARM_VTODO_TIMED" nclob default null,
    "ALARM_VTODO_ALLDAY" nclob default null,
    "TIMEZONE" nclob default null, 
    primary key ("CALENDAR_HOME_RESOURCE_ID", "CALENDAR_RESOURCE_ID"), 
    unique ("CALENDAR_HOME_RESOURCE_ID", "CALENDAR_RESOURCE_NAME")
);

create table CALENDAR_BIND_MODE (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('own', 0);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('read', 1);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('write', 2);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('direct', 3);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('indirect', 4);
create table CALENDAR_BIND_STATUS (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('invited', 0);
insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('accepted', 1);
insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('declined', 2);
insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('invalid', 3);
insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('deleted', 4);
create table CALENDAR_TRANSP (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CALENDAR_TRANSP (DESCRIPTION, ID) values ('opaque', 0);
insert into CALENDAR_TRANSP (DESCRIPTION, ID) values ('transparent', 1);
create table CALENDAR_OBJECT (
    "RESOURCE_ID" integer primary key,
    "CALENDAR_RESOURCE_ID" integer not null references CALENDAR on delete cascade,
    "RESOURCE_NAME" nvarchar2(255),
    "ICALENDAR_TEXT" nclob,
    "ICALENDAR_UID" nvarchar2(255),
    "ICALENDAR_TYPE" nvarchar2(255),
    "ATTACHMENTS_MODE" integer default 0 not null,
    "DROPBOX_ID" nvarchar2(255),
    "ORGANIZER" nvarchar2(255),
    "RECURRANCE_MIN" date,
    "RECURRANCE_MAX" date,
    "ACCESS" integer default 0 not null,
    "SCHEDULE_OBJECT" integer default 0,
    "SCHEDULE_TAG" nvarchar2(36) default null,
    "SCHEDULE_ETAGS" nclob default null,
    "PRIVATE_COMMENTS" integer default 0 not null,
    "MD5" nchar(32),
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    unique ("CALENDAR_RESOURCE_ID", "RESOURCE_NAME")
);

create table CALENDAR_OBJ_ATTACHMENTS_MODE (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CALENDAR_OBJ_ATTACHMENTS_MODE (DESCRIPTION, ID) values ('none', 0);
insert into CALENDAR_OBJ_ATTACHMENTS_MODE (DESCRIPTION, ID) values ('read', 1);
insert into CALENDAR_OBJ_ATTACHMENTS_MODE (DESCRIPTION, ID) values ('write', 2);
create table CALENDAR_ACCESS_TYPE (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(32) unique
);

insert into CALENDAR_ACCESS_TYPE (DESCRIPTION, ID) values ('', 0);
insert into CALENDAR_ACCESS_TYPE (DESCRIPTION, ID) values ('public', 1);
insert into CALENDAR_ACCESS_TYPE (DESCRIPTION, ID) values ('private', 2);
insert into CALENDAR_ACCESS_TYPE (DESCRIPTION, ID) values ('confidential', 3);
insert into CALENDAR_ACCESS_TYPE (DESCRIPTION, ID) values ('restricted', 4);
create table TIME_RANGE (
    "INSTANCE_ID" integer primary key,
    "CALENDAR_RESOURCE_ID" integer not null references CALENDAR on delete cascade,
    "CALENDAR_OBJECT_RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "FLOATING" integer not null,
    "START_DATE" timestamp not null,
    "END_DATE" timestamp not null,
    "FBTYPE" integer not null,
    "TRANSPARENT" integer not null
);

create table FREE_BUSY_TYPE (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into FREE_BUSY_TYPE (DESCRIPTION, ID) values ('unknown', 0);
insert into FREE_BUSY_TYPE (DESCRIPTION, ID) values ('free', 1);
insert into FREE_BUSY_TYPE (DESCRIPTION, ID) values ('busy', 2);
insert into FREE_BUSY_TYPE (DESCRIPTION, ID) values ('busy-unavailable', 3);
insert into FREE_BUSY_TYPE (DESCRIPTION, ID) values ('busy-tentative', 4);
create table PERUSER (
    "TIME_RANGE_INSTANCE_ID" integer not null references TIME_RANGE on delete cascade,
    "USER_ID" nvarchar2(255),
    "TRANSPARENT" integer not null,
    "ADJUSTED_START_DATE" timestamp default null,
    "ADJUSTED_END_DATE" timestamp default null
);

create table ATTACHMENT (
    "ATTACHMENT_ID" integer primary key,
    "CALENDAR_HOME_RESOURCE_ID" integer not null references CALENDAR_HOME,
    "DROPBOX_ID" nvarchar2(255),
    "CONTENT_TYPE" nvarchar2(255),
    "SIZE" integer not null,
    "MD5" nchar(32),
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "PATH" nvarchar2(1024)
);

create table ATTACHMENT_CALENDAR_OBJECT (
    "ATTACHMENT_ID" integer not null references ATTACHMENT on delete cascade,
    "MANAGED_ID" nvarchar2(255),
    "CALENDAR_OBJECT_RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade, 
    primary key ("ATTACHMENT_ID", "CALENDAR_OBJECT_RESOURCE_ID"), 
    unique ("MANAGED_ID", "CALENDAR_OBJECT_RESOURCE_ID")
);

create table RESOURCE_PROPERTY (
    "RESOURCE_ID" integer not null,
    "NAME" nvarchar2(255),
    "VALUE" nclob,
    "VIEWER_UID" nvarchar2(255), 
    primary key ("RESOURCE_ID", "NAME", "VIEWER_UID")
);

create table ADDRESSBOOK_HOME (
    "RESOURCE_ID" integer primary key,
    "ADDRESSBOOK_PROPERTY_STORE_ID" integer not null,
    "OWNER_UID" nvarchar2(255) unique,
    "STATUS" integer default 0 not null,
    "DATAVERSION" integer default 0 not null
);

create table ADDRESSBOOK_HOME_METADATA (
    "RESOURCE_ID" integer primary key references ADDRESSBOOK_HOME on delete cascade,
    "QUOTA_USED_BYTES" integer default 0 not null,
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table SHARED_ADDRESSBOOK_BIND (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "OWNER_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "EXTERNAL_ID" integer default null,
    "ADDRESSBOOK_RESOURCE_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "BIND_REVISION" integer default 0 not null,
    "MESSAGE" nclob, 
    primary key ("ADDRESSBOOK_HOME_RESOURCE_ID", "OWNER_HOME_RESOURCE_ID"), 
    unique ("ADDRESSBOOK_HOME_RESOURCE_ID", "ADDRESSBOOK_RESOURCE_NAME")
);

create table ADDRESSBOOK_OBJECT (
    "RESOURCE_ID" integer primary key,
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "RESOURCE_NAME" nvarchar2(255),
    "VCARD_TEXT" nclob,
    "VCARD_UID" nvarchar2(255),
    "KIND" integer not null,
    "MD5" nchar(32),
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    unique ("ADDRESSBOOK_HOME_RESOURCE_ID", "RESOURCE_NAME"), 
    unique ("ADDRESSBOOK_HOME_RESOURCE_ID", "VCARD_UID")
);

create table ADDRESSBOOK_OBJECT_KIND (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('person', 0);
insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('group', 1);
insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('resource', 2);
insert into ADDRESSBOOK_OBJECT_KIND (DESCRIPTION, ID) values ('location', 3);
create table ABO_MEMBERS (
    "GROUP_ID" integer not null,
    "ADDRESSBOOK_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "MEMBER_ID" integer not null,
    "REVISION" integer not null,
    "REMOVED" integer default 0 not null,
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    primary key ("GROUP_ID", "MEMBER_ID", "REVISION")
);

create table ABO_FOREIGN_MEMBERS (
    "GROUP_ID" integer not null references ADDRESSBOOK_OBJECT on delete cascade,
    "ADDRESSBOOK_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "MEMBER_ADDRESS" nvarchar2(255), 
    primary key ("GROUP_ID", "MEMBER_ADDRESS")
);

create table SHARED_GROUP_BIND (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "GROUP_RESOURCE_ID" integer not null references ADDRESSBOOK_OBJECT on delete cascade,
    "EXTERNAL_ID" integer default null,
    "GROUP_ADDRESSBOOK_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "BIND_REVISION" integer default 0 not null,
    "MESSAGE" nclob, 
    primary key ("ADDRESSBOOK_HOME_RESOURCE_ID", "GROUP_RESOURCE_ID"), 
    unique ("ADDRESSBOOK_HOME_RESOURCE_ID", "GROUP_ADDRESSBOOK_NAME")
);

create table CALENDAR_OBJECT_REVISIONS (
    "CALENDAR_HOME_RESOURCE_ID" integer not null references CALENDAR_HOME,
    "CALENDAR_RESOURCE_ID" integer references CALENDAR,
    "CALENDAR_NAME" nvarchar2(255) default null,
    "RESOURCE_NAME" nvarchar2(255),
    "REVISION" integer not null,
    "DELETED" integer not null,
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table ADDRESSBOOK_OBJECT_REVISIONS (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "OWNER_HOME_RESOURCE_ID" integer references ADDRESSBOOK_HOME,
    "ADDRESSBOOK_NAME" nvarchar2(255) default null,
    "OBJECT_RESOURCE_ID" integer default 0,
    "RESOURCE_NAME" nvarchar2(255),
    "REVISION" integer not null,
    "DELETED" integer not null,
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table NOTIFICATION_OBJECT_REVISIONS (
    "NOTIFICATION_HOME_RESOURCE_ID" integer not null references NOTIFICATION_HOME on delete cascade,
    "RESOURCE_NAME" nvarchar2(255),
    "REVISION" integer not null,
    "DELETED" integer not null,
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    unique ("NOTIFICATION_HOME_RESOURCE_ID", "RESOURCE_NAME")
);

create table APN_SUBSCRIPTIONS (
    "TOKEN" nvarchar2(255),
    "RESOURCE_KEY" nvarchar2(255),
    "MODIFIED" integer not null,
    "SUBSCRIBER_GUID" nvarchar2(255),
    "USER_AGENT" nvarchar2(255) default null,
    "IP_ADDR" nvarchar2(255) default null, 
    primary key ("TOKEN", "RESOURCE_KEY")
);

create table IMIP_TOKENS (
    "TOKEN" nvarchar2(255),
    "ORGANIZER" nvarchar2(255),
    "ATTENDEE" nvarchar2(255),
    "ICALUID" nvarchar2(255),
    "ACCESSED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    primary key ("ORGANIZER", "ATTENDEE", "ICALUID")
);

create table IMIP_INVITATION_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "FROM_ADDR" nvarchar2(255),
    "TO_ADDR" nvarchar2(255),
    "ICALENDAR_TEXT" nclob
);

create table IMIP_POLLING_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB
);

create table IMIP_REPLY_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "ORGANIZER" nvarchar2(255),
    "ATTENDEE" nvarchar2(255),
    "ICALENDAR_TEXT" nclob
);

create table PUSH_NOTIFICATION_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "PUSH_ID" nvarchar2(255),
    "PUSH_PRIORITY" integer not null
);

create table GROUP_CACHER_POLLING_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB
);

create table GROUP_REFRESH_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "GROUP_UID" nvarchar2(255)
);

create table GROUP_ATTENDEE_RECONCILE_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "RESOURCE_ID" integer,
    "GROUP_ID" integer
);

create table GROUPS (
    "GROUP_ID" integer primary key,
    "NAME" nvarchar2(255),
    "GROUP_UID" nvarchar2(255),
    "MEMBERSHIP_HASH" nvarchar2(255),
    "EXTANT" integer default 1,
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table GROUP_MEMBERSHIP (
    "GROUP_ID" integer not null references GROUPS on delete cascade,
    "MEMBER_UID" nvarchar2(255), 
    primary key ("GROUP_ID", "MEMBER_UID")
);

create table GROUP_ATTENDEE (
    "GROUP_ID" integer not null references GROUPS on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "MEMBERSHIP_HASH" nvarchar2(255), 
    primary key ("GROUP_ID", "RESOURCE_ID")
);

create table DELEGATES (
    "DELEGATOR" nvarchar2(255),
    "DELEGATE" nvarchar2(255),
    "READ_WRITE" integer not null, 
    primary key ("DELEGATOR", "READ_WRITE", "DELEGATE")
);

create table DELEGATE_GROUPS (
    "DELEGATOR" nvarchar2(255),
    "GROUP_ID" integer not null references GROUPS on delete cascade,
    "READ_WRITE" integer not null,
    "IS_EXTERNAL" integer not null, 
    primary key ("DELEGATOR", "READ_WRITE", "GROUP_ID")
);

create table EXTERNAL_DELEGATE_GROUPS (
    "DELEGATOR" nvarchar2(255) primary key,
    "GROUP_UID_READ" nvarchar2(255),
    "GROUP_UID_WRITE" nvarchar2(255)
);

create table CALENDAR_OBJECT_SPLITTER_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade
);

create table FIND_MIN_VALID_REVISION_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB
);

create table REVISION_CLEANUP_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB
);

create table INBOX_CLEANUP_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB
);

create table CLEANUP_ONE_INBOX_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "HOME_ID" integer not null unique references CALENDAR_HOME on delete cascade
);

create table SCHEDULE_REFRESH_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "ICALENDAR_UID" nvarchar2(255),
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "ATTENDEE_COUNT" integer
);

create table SCHEDULE_REFRESH_ATTENDEES (
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "ATTENDEE" nvarchar2(255), 
    primary key ("RESOURCE_ID", "ATTENDEE")
);

create table SCHEDULE_AUTO_REPLY_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "ICALENDAR_UID" nvarchar2(255),
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "PARTSTAT" nvarchar2(255)
);

create table SCHEDULE_ORGANIZER_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "ICALENDAR_UID" nvarchar2(255),
    "SCHEDULE_ACTION" integer not null,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer,
    "ICALENDAR_TEXT_OLD" nclob,
    "ICALENDAR_TEXT_NEW" nclob,
    "ATTENDEE_COUNT" integer,
    "SMART_MERGE" integer
);

create table SCHEDULE_ACTION (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into SCHEDULE_ACTION (DESCRIPTION, ID) values ('create', 0);
insert into SCHEDULE_ACTION (DESCRIPTION, ID) values ('modify', 1);
insert into SCHEDULE_ACTION (DESCRIPTION, ID) values ('modify-cancelled', 2);
insert into SCHEDULE_ACTION (DESCRIPTION, ID) values ('remove', 3);
create table SCHEDULE_REPLY_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "ICALENDAR_UID" nvarchar2(255),
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade,
    "CHANGED_RIDS" nclob
);

create table SCHEDULE_REPLY_CANCEL_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "ICALENDAR_UID" nvarchar2(255),
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade,
    "ICALENDAR_TEXT" nclob
);

create table PRINCIPAL_PURGE_POLLING_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB
);

create table PRINCIPAL_PURGE_CHECK_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "UID" nvarchar2(255)
);

create table PRINCIPAL_PURGE_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "UID" nvarchar2(255)
);

create table PRINCIPAL_PURGE_HOME_WORK (
    "WORK_ID" integer primary key not null,
    "JOB_ID" integer not null references JOB,
    "HOME_RESOURCE_ID" integer not null references CALENDAR_HOME on delete cascade
);

create table CALENDARSERVER (
    "NAME" nvarchar2(255) primary key,
    "VALUE" nvarchar2(255)
);

insert into CALENDARSERVER (NAME, VALUE) values ('VERSION', '44');
insert into CALENDARSERVER (NAME, VALUE) values ('CALENDAR-DATAVERSION', '6');
insert into CALENDARSERVER (NAME, VALUE) values ('ADDRESSBOOK-DATAVERSION', '2');
insert into CALENDARSERVER (NAME, VALUE) values ('NOTIFICATION-DATAVERSION', '1');
insert into CALENDARSERVER (NAME, VALUE) values ('MIN-VALID-REVISION', '1');
create index CALENDAR_HOME_METADAT_3cb9049e on CALENDAR_HOME_METADATA (
    DEFAULT_EVENTS
);

create index CALENDAR_HOME_METADAT_d55e5548 on CALENDAR_HOME_METADATA (
    DEFAULT_TASKS
);

create index CALENDAR_HOME_METADAT_910264ce on CALENDAR_HOME_METADATA (
    DEFAULT_POLLS
);

create index NOTIFICATION_NOTIFICA_f891f5f9 on NOTIFICATION (
    NOTIFICATION_HOME_RESOURCE_ID
);

create index CALENDAR_BIND_RESOURC_e57964d4 on CALENDAR_BIND (
    CALENDAR_RESOURCE_ID
);

create index CALENDAR_OBJECT_CALEN_a9a453a9 on CALENDAR_OBJECT (
    CALENDAR_RESOURCE_ID,
    ICALENDAR_UID
);

create index CALENDAR_OBJECT_CALEN_96e83b73 on CALENDAR_OBJECT (
    CALENDAR_RESOURCE_ID,
    RECURRANCE_MAX
);

create index CALENDAR_OBJECT_ICALE_82e731d5 on CALENDAR_OBJECT (
    ICALENDAR_UID
);

create index CALENDAR_OBJECT_DROPB_de041d80 on CALENDAR_OBJECT (
    DROPBOX_ID
);

create index TIME_RANGE_CALENDAR_R_beb6e7eb on TIME_RANGE (
    CALENDAR_RESOURCE_ID
);

create index TIME_RANGE_CALENDAR_O_acf37bd1 on TIME_RANGE (
    CALENDAR_OBJECT_RESOURCE_ID
);

create index PERUSER_TIME_RANGE_IN_5468a226 on PERUSER (
    TIME_RANGE_INSTANCE_ID
);

create index ATTACHMENT_CALENDAR_H_0078845c on ATTACHMENT (
    CALENDAR_HOME_RESOURCE_ID
);

create index ATTACHMENT_DROPBOX_ID_5073cf23 on ATTACHMENT (
    DROPBOX_ID
);

create index ATTACHMENT_CALENDAR_O_81508484 on ATTACHMENT_CALENDAR_OBJECT (
    CALENDAR_OBJECT_RESOURCE_ID
);

create index SHARED_ADDRESSBOOK_BI_e9a2e6d4 on SHARED_ADDRESSBOOK_BIND (
    OWNER_HOME_RESOURCE_ID
);

create index ABO_MEMBERS_ADDRESSBO_4effa879 on ABO_MEMBERS (
    ADDRESSBOOK_ID
);

create index ABO_MEMBERS_MEMBER_ID_8d66adcf on ABO_MEMBERS (
    MEMBER_ID
);

create index ABO_FOREIGN_MEMBERS_A_1fd2c5e9 on ABO_FOREIGN_MEMBERS (
    ADDRESSBOOK_ID
);

create index SHARED_GROUP_BIND_RES_cf52f95d on SHARED_GROUP_BIND (
    GROUP_RESOURCE_ID
);

create index CALENDAR_OBJECT_REVIS_3a3956c4 on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_HOME_RESOURCE_ID,
    CALENDAR_RESOURCE_ID
);

create index CALENDAR_OBJECT_REVIS_6d9d929c on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_RESOURCE_ID,
    RESOURCE_NAME,
    DELETED,
    REVISION
);

create index CALENDAR_OBJECT_REVIS_265c8acf on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_RESOURCE_ID,
    REVISION
);

create index ADDRESSBOOK_OBJECT_RE_2bfcf757 on ADDRESSBOOK_OBJECT_REVISIONS (
    ADDRESSBOOK_HOME_RESOURCE_ID,
    OWNER_HOME_RESOURCE_ID
);

create index ADDRESSBOOK_OBJECT_RE_00fe8288 on ADDRESSBOOK_OBJECT_REVISIONS (
    OWNER_HOME_RESOURCE_ID,
    RESOURCE_NAME,
    DELETED,
    REVISION
);

create index ADDRESSBOOK_OBJECT_RE_45004780 on ADDRESSBOOK_OBJECT_REVISIONS (
    OWNER_HOME_RESOURCE_ID,
    REVISION
);

create index NOTIFICATION_OBJECT_R_036a9cee on NOTIFICATION_OBJECT_REVISIONS (
    NOTIFICATION_HOME_RESOURCE_ID,
    REVISION
);

create index APN_SUBSCRIPTIONS_RES_9610d78e on APN_SUBSCRIPTIONS (
    RESOURCE_KEY
);

create index IMIP_TOKENS_TOKEN_e94b918f on IMIP_TOKENS (
    TOKEN
);

create index IMIP_INVITATION_WORK__586d064c on IMIP_INVITATION_WORK (
    JOB_ID
);

create index IMIP_POLLING_WORK_JOB_d5535891 on IMIP_POLLING_WORK (
    JOB_ID
);

create index IMIP_REPLY_WORK_JOB_I_bf4ae73e on IMIP_REPLY_WORK (
    JOB_ID
);

create index PUSH_NOTIFICATION_WOR_8bbab117 on PUSH_NOTIFICATION_WORK (
    JOB_ID
);

create index GROUP_CACHER_POLLING__6eb3151c on GROUP_CACHER_POLLING_WORK (
    JOB_ID
);

create index GROUP_REFRESH_WORK_JO_717ede20 on GROUP_REFRESH_WORK (
    JOB_ID
);

create index GROUP_ATTENDEE_RECONC_da73d3c2 on GROUP_ATTENDEE_RECONCILE_WORK (
    JOB_ID
);

create index GROUPS_GROUP_UID_b35cce23 on GROUPS (
    GROUP_UID
);

create index GROUP_MEMBERSHIP_MEMB_0ca508e8 on GROUP_MEMBERSHIP (
    MEMBER_UID
);

create index GROUP_ATTENDEE_RESOUR_855124dc on GROUP_ATTENDEE (
    RESOURCE_ID
);

create index DELEGATE_TO_DELEGATOR_5e149b11 on DELEGATES (
    DELEGATE,
    READ_WRITE,
    DELEGATOR
);

create index DELEGATE_GROUPS_GROUP_25117446 on DELEGATE_GROUPS (
    GROUP_ID
);

create index CALENDAR_OBJECT_SPLIT_af71dcda on CALENDAR_OBJECT_SPLITTER_WORK (
    RESOURCE_ID
);

create index CALENDAR_OBJECT_SPLIT_33603b72 on CALENDAR_OBJECT_SPLITTER_WORK (
    JOB_ID
);

create index FIND_MIN_VALID_REVISI_78d17400 on FIND_MIN_VALID_REVISION_WORK (
    JOB_ID
);

create index REVISION_CLEANUP_WORK_eb062686 on REVISION_CLEANUP_WORK (
    JOB_ID
);

create index INBOX_CLEANUP_WORK_JO_799132bd on INBOX_CLEANUP_WORK (
    JOB_ID
);

create index CLEANUP_ONE_INBOX_WOR_375dac36 on CLEANUP_ONE_INBOX_WORK (
    JOB_ID
);

create index SCHEDULE_REFRESH_WORK_26084c7b on SCHEDULE_REFRESH_WORK (
    HOME_RESOURCE_ID
);

create index SCHEDULE_REFRESH_WORK_989efe54 on SCHEDULE_REFRESH_WORK (
    RESOURCE_ID
);

create index SCHEDULE_REFRESH_WORK_3ffa2718 on SCHEDULE_REFRESH_WORK (
    JOB_ID
);

create index SCHEDULE_REFRESH_ATTE_83053b91 on SCHEDULE_REFRESH_ATTENDEES (
    RESOURCE_ID,
    ATTENDEE
);

create index SCHEDULE_AUTO_REPLY_W_0256478d on SCHEDULE_AUTO_REPLY_WORK (
    HOME_RESOURCE_ID
);

create index SCHEDULE_AUTO_REPLY_W_0755e754 on SCHEDULE_AUTO_REPLY_WORK (
    RESOURCE_ID
);

create index SCHEDULE_AUTO_REPLY_W_4d7bb5a8 on SCHEDULE_AUTO_REPLY_WORK (
    JOB_ID
);

create index SCHEDULE_ORGANIZER_WO_18ce4edd on SCHEDULE_ORGANIZER_WORK (
    HOME_RESOURCE_ID
);

create index SCHEDULE_ORGANIZER_WO_14702035 on SCHEDULE_ORGANIZER_WORK (
    RESOURCE_ID
);

create index SCHEDULE_ORGANIZER_WO_1e9f246d on SCHEDULE_ORGANIZER_WORK (
    JOB_ID
);

create index SCHEDULE_REPLY_WORK_H_745af8cf on SCHEDULE_REPLY_WORK (
    HOME_RESOURCE_ID
);

create index SCHEDULE_REPLY_WORK_R_11bd3fbb on SCHEDULE_REPLY_WORK (
    RESOURCE_ID
);

create index SCHEDULE_REPLY_WORK_J_5913b4a4 on SCHEDULE_REPLY_WORK (
    JOB_ID
);

create index SCHEDULE_REPLY_CANCEL_dab513ef on SCHEDULE_REPLY_CANCEL_WORK (
    HOME_RESOURCE_ID
);

create index SCHEDULE_REPLY_CANCEL_94a0c766 on SCHEDULE_REPLY_CANCEL_WORK (
    JOB_ID
);

create index PRINCIPAL_PURGE_POLLI_6383e68a on PRINCIPAL_PURGE_POLLING_WORK (
    JOB_ID
);

create index PRINCIPAL_PURGE_CHECK_b0c024c1 on PRINCIPAL_PURGE_CHECK_WORK (
    JOB_ID
);

create index PRINCIPAL_PURGE_WORK__7a8141a3 on PRINCIPAL_PURGE_WORK (
    JOB_ID
);

create index PRINCIPAL_PURGE_HOME__f35eea7a on PRINCIPAL_PURGE_HOME_WORK (
    JOB_ID
);

create index PRINCIPAL_PURGE_HOME__967e4480 on PRINCIPAL_PURGE_HOME_WORK (
    HOME_RESOURCE_ID
);

-- Skipped Function next_job

-- Extras

create or replace function next_job return integer is
declare
  cursor c1 is select JOB_ID from JOB for update skip locked;
  result integer;
begin
  open c1;
  fetch c1 into result;
  select JOB_ID from JOB where ID = result for update;
  return result;
end;
/
