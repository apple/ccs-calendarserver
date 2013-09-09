create sequence RESOURCE_ID_SEQ;
create sequence INSTANCE_ID_SEQ;
create sequence ATTACHMENT_ID_SEQ;
create sequence REVISION_SEQ;
create sequence WORKITEM_SEQ;
create table NODE_INFO (
    "HOSTNAME" nvarchar2(255),
    "PID" integer not null,
    "PORT" integer not null,
    "TIME" timestamp default CURRENT_TIMESTAMP at time zone 'UTC' not null, 
    primary key("HOSTNAME", "PORT")
);

create table NAMED_LOCK (
    "LOCK_NAME" nvarchar2(255) primary key
);

create table CALENDAR_HOME (
    "RESOURCE_ID" integer primary key,
    "OWNER_UID" nvarchar2(255) unique,
    "DATAVERSION" integer default 0 not null
);

create table CALENDAR (
    "RESOURCE_ID" integer primary key
);

create table CALENDAR_HOME_METADATA (
    "RESOURCE_ID" integer primary key references CALENDAR_HOME on delete cascade,
    "QUOTA_USED_BYTES" integer default 0 not null,
    "DEFAULT_EVENTS" integer default null references CALENDAR on delete set null,
    "DEFAULT_TASKS" integer default null references CALENDAR on delete set null,
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
    "OWNER_UID" nvarchar2(255) unique
);

create table NOTIFICATION (
    "RESOURCE_ID" integer primary key,
    "NOTIFICATION_HOME_RESOURCE_ID" integer not null references NOTIFICATION_HOME,
    "NOTIFICATION_UID" nvarchar2(255),
    "XML_TYPE" nvarchar2(255),
    "XML_DATA" nclob,
    "MD5" nchar(32),
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    unique("NOTIFICATION_UID", "NOTIFICATION_HOME_RESOURCE_ID")
);

create table CALENDAR_BIND (
    "CALENDAR_HOME_RESOURCE_ID" integer not null references CALENDAR_HOME,
    "CALENDAR_RESOURCE_ID" integer not null references CALENDAR on delete cascade,
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
    primary key("CALENDAR_HOME_RESOURCE_ID", "CALENDAR_RESOURCE_ID"), 
    unique("CALENDAR_HOME_RESOURCE_ID", "CALENDAR_RESOURCE_NAME")
);

create table CALENDAR_BIND_MODE (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('own', 0);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('read', 1);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('write', 2);
insert into CALENDAR_BIND_MODE (DESCRIPTION, ID) values ('direct', 3);
create table CALENDAR_BIND_STATUS (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('invited', 0);
insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('accepted', 1);
insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('declined', 2);
insert into CALENDAR_BIND_STATUS (DESCRIPTION, ID) values ('invalid', 3);
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
    unique("CALENDAR_RESOURCE_ID", "RESOURCE_NAME")
);

create table CALENDAR_OBJECT_ATTACHMENTS_MO (
    "ID" integer primary key,
    "DESCRIPTION" nvarchar2(16) unique
);

insert into CALENDAR_OBJECT_ATTACHMENTS_MO (DESCRIPTION, ID) values ('none', 0);
insert into CALENDAR_OBJECT_ATTACHMENTS_MO (DESCRIPTION, ID) values ('read', 1);
insert into CALENDAR_OBJECT_ATTACHMENTS_MO (DESCRIPTION, ID) values ('write', 2);
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
create table TRANSPARENCY (
    "TIME_RANGE_INSTANCE_ID" integer not null references TIME_RANGE on delete cascade,
    "USER_ID" nvarchar2(255),
    "TRANSPARENT" integer not null
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
    primary key("ATTACHMENT_ID", "CALENDAR_OBJECT_RESOURCE_ID"), 
    unique("MANAGED_ID", "CALENDAR_OBJECT_RESOURCE_ID")
);

create table RESOURCE_PROPERTY (
    "RESOURCE_ID" integer not null,
    "NAME" nvarchar2(255),
    "VALUE" nclob,
    "VIEWER_UID" nvarchar2(255), 
    primary key("RESOURCE_ID", "NAME", "VIEWER_UID")
);

create table ADDRESSBOOK_HOME (
    "RESOURCE_ID" integer primary key,
    "ADDRESSBOOK_PROPERTY_STORE_ID" integer not null,
    "OWNER_UID" nvarchar2(255) unique,
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
    "OWNER_ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "ADDRESSBOOK_RESOURCE_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "BIND_REVISION" integer default 0 not null,
    "MESSAGE" nclob, 
    primary key("ADDRESSBOOK_HOME_RESOURCE_ID", "OWNER_ADDRESSBOOK_HOME_RESOURCE_ID"), 
    unique("ADDRESSBOOK_HOME_RESOURCE_ID", "ADDRESSBOOK_RESOURCE_NAME")
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
    unique("ADDRESSBOOK_HOME_RESOURCE_ID", "RESOURCE_NAME"), 
    unique("ADDRESSBOOK_HOME_RESOURCE_ID", "VCARD_UID")
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
    primary key("GROUP_ID", "MEMBER_ID")
);

create table ABO_FOREIGN_MEMBERS (
    "GROUP_ID" integer not null references ADDRESSBOOK_OBJECT on delete cascade,
    "ADDRESSBOOK_ID" integer not null references ADDRESSBOOK_HOME on delete cascade,
    "MEMBER_ADDRESS" nvarchar2(255), 
    primary key("GROUP_ID", "MEMBER_ADDRESS")
);

create table SHARED_GROUP_BIND (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "GROUP_RESOURCE_ID" integer not null references ADDRESSBOOK_OBJECT on delete cascade,
    "GROUP_ADDRESSBOOK_RESOURCE_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "BIND_REVISION" integer default 0 not null,
    "MESSAGE" nclob, 
    primary key("ADDRESSBOOK_HOME_RESOURCE_ID", "GROUP_RESOURCE_ID"), 
    unique("ADDRESSBOOK_HOME_RESOURCE_ID", "GROUP_ADDRESSBOOK_RESOURCE_NAME")
);

create table CALENDAR_OBJECT_REVISIONS (
    "CALENDAR_HOME_RESOURCE_ID" integer not null references CALENDAR_HOME,
    "CALENDAR_RESOURCE_ID" integer references CALENDAR,
    "CALENDAR_NAME" nvarchar2(255) default null,
    "RESOURCE_NAME" nvarchar2(255),
    "REVISION" integer not null,
    "DELETED" integer not null
);

create table ADDRESSBOOK_OBJECT_REVISIONS (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "OWNER_ADDRESSBOOK_HOME_RESOURCE_ID" integer references ADDRESSBOOK_HOME,
    "ADDRESSBOOK_NAME" nvarchar2(255) default null,
    "RESOURCE_NAME" nvarchar2(255),
    "REVISION" integer not null,
    "DELETED" integer not null
);

create table NOTIFICATION_OBJECT_REVISIONS (
    "NOTIFICATION_HOME_RESOURCE_ID" integer not null references NOTIFICATION_HOME on delete cascade,
    "RESOURCE_NAME" nvarchar2(255),
    "REVISION" integer not null,
    "DELETED" integer not null, 
    unique("NOTIFICATION_HOME_RESOURCE_ID", "RESOURCE_NAME")
);

create table APN_SUBSCRIPTIONS (
    "TOKEN" nvarchar2(255),
    "RESOURCE_KEY" nvarchar2(255),
    "MODIFIED" integer not null,
    "SUBSCRIBER_GUID" nvarchar2(255),
    "USER_AGENT" nvarchar2(255) default null,
    "IP_ADDR" nvarchar2(255) default null, 
    primary key("TOKEN", "RESOURCE_KEY")
);

create table IMIP_TOKENS (
    "TOKEN" nvarchar2(255),
    "ORGANIZER" nvarchar2(255),
    "ATTENDEE" nvarchar2(255),
    "ICALUID" nvarchar2(255),
    "ACCESSED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    primary key("ORGANIZER", "ATTENDEE", "ICALUID")
);

create table IMIP_INVITATION_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "FROM_ADDR" nvarchar2(255),
    "TO_ADDR" nvarchar2(255),
    "ICALENDAR_TEXT" nclob
);

create table IMIP_POLLING_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table IMIP_REPLY_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "ORGANIZER" nvarchar2(255),
    "ATTENDEE" nvarchar2(255),
    "ICALENDAR_TEXT" nclob
);

create table PUSH_NOTIFICATION_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "PUSH_ID" nvarchar2(255)
);

create table GROUP_CACHER_POLLING_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table CALENDAR_OBJECT_SPLITTER_WORK (
    "WORK_ID" integer primary key not null,
    "NOT_BEFORE" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "RESOURCE_ID" integer not null references CALENDAR_OBJECT on delete cascade
);

create table CALENDARSERVER (
    "NAME" nvarchar2(255) primary key,
    "VALUE" nvarchar2(255)
);

insert into CALENDARSERVER (NAME, VALUE) values ('VERSION', '25');
insert into CALENDARSERVER (NAME, VALUE) values ('CALENDAR-DATAVERSION', '5');
insert into CALENDARSERVER (NAME, VALUE) values ('ADDRESSBOOK-DATAVERSION', '2');
create index CALENDAR_HOME_METADAT_3cb9049e on CALENDAR_HOME_METADATA (
    DEFAULT_EVENTS
);

create index CALENDAR_HOME_METADAT_d55e5548 on CALENDAR_HOME_METADATA (
    DEFAULT_TASKS
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

create index TRANSPARENCY_TIME_RAN_5f34467f on TRANSPARENCY (
    TIME_RANGE_INSTANCE_ID
);

create index ATTACHMENT_CALENDAR_H_0078845c on ATTACHMENT (
    CALENDAR_HOME_RESOURCE_ID
);

create index ATTACHMENT_CALENDAR_O_81508484 on ATTACHMENT_CALENDAR_OBJECT (
    CALENDAR_OBJECT_RESOURCE_ID
);

create index SHARED_ADDRESSBOOK_BI_e9a2e6d4 on SHARED_ADDRESSBOOK_BIND (
    OWNER_ADDRESSBOOK_HOME_RESOURCE_ID
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

create index CALENDAR_OBJECT_REVIS_2643d556 on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_RESOURCE_ID,
    RESOURCE_NAME
);

create index CALENDAR_OBJECT_REVIS_265c8acf on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_RESOURCE_ID,
    REVISION
);

create index ADDRESSBOOK_OBJECT_RE_40cc2d73 on ADDRESSBOOK_OBJECT_REVISIONS (
    ADDRESSBOOK_HOME_RESOURCE_ID,
    OWNER_ADDRESSBOOK_HOME_RESOURCE_ID
);

create index ADDRESSBOOK_OBJECT_RE_980b9872 on ADDRESSBOOK_OBJECT_REVISIONS (
    OWNER_ADDRESSBOOK_HOME_RESOURCE_ID,
    RESOURCE_NAME
);

create index ADDRESSBOOK_OBJECT_RE_45004780 on ADDRESSBOOK_OBJECT_REVISIONS (
    OWNER_ADDRESSBOOK_HOME_RESOURCE_ID,
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

create index CALENDAR_OBJECT_SPLIT_af71dcda on CALENDAR_OBJECT_SPLITTER_WORK (
    RESOURCE_ID
);

