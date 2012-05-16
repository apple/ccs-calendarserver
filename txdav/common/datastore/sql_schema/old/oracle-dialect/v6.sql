create sequence RESOURCE_ID_SEQ;
create sequence INSTANCE_ID_SEQ;
create sequence REVISION_SEQ;
create table CALENDAR_HOME (
    "RESOURCE_ID" integer primary key,
    "OWNER_UID" nvarchar2(255) unique
);

create table CALENDAR_HOME_METADATA (
    "RESOURCE_ID" integer primary key references CALENDAR_HOME on delete cascade,
    "QUOTA_USED_BYTES" integer default 0 not null
);

create table CALENDAR (
    "RESOURCE_ID" integer primary key,
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table INVITE (
    "INVITE_UID" nvarchar2(255),
    "NAME" nvarchar2(255),
    "RECIPIENT_ADDRESS" nvarchar2(255),
    "HOME_RESOURCE_ID" integer not null,
    "RESOURCE_ID" integer not null
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
    "SEEN_BY_OWNER" integer not null,
    "SEEN_BY_SHAREE" integer not null,
    "MESSAGE" nclob, 
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
    "ORGANIZER_OBJECT" integer references CALENDAR_OBJECT,
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
    "CALENDAR_HOME_RESOURCE_ID" integer not null references CALENDAR_HOME,
    "DROPBOX_ID" nvarchar2(255),
    "CONTENT_TYPE" nvarchar2(255),
    "SIZE" integer not null,
    "MD5" nchar(32),
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "PATH" nvarchar2(1024), 
    primary key("DROPBOX_ID", "PATH")
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
    "OWNER_UID" nvarchar2(255) unique
);

create table ADDRESSBOOK_HOME_METADATA (
    "RESOURCE_ID" integer primary key references ADDRESSBOOK_HOME on delete cascade,
    "QUOTA_USED_BYTES" integer default 0 not null
);

create table ADDRESSBOOK (
    "RESOURCE_ID" integer primary key,
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC'
);

create table ADDRESSBOOK_BIND (
    "ADDRESSBOOK_HOME_RESOURCE_ID" integer not null references ADDRESSBOOK_HOME,
    "ADDRESSBOOK_RESOURCE_ID" integer not null references ADDRESSBOOK on delete cascade,
    "ADDRESSBOOK_RESOURCE_NAME" nvarchar2(255),
    "BIND_MODE" integer not null,
    "BIND_STATUS" integer not null,
    "SEEN_BY_OWNER" integer not null,
    "SEEN_BY_SHAREE" integer not null,
    "MESSAGE" nclob, 
    primary key("ADDRESSBOOK_HOME_RESOURCE_ID", "ADDRESSBOOK_RESOURCE_ID"), 
    unique("ADDRESSBOOK_HOME_RESOURCE_ID", "ADDRESSBOOK_RESOURCE_NAME")
);

create table ADDRESSBOOK_OBJECT (
    "RESOURCE_ID" integer primary key,
    "ADDRESSBOOK_RESOURCE_ID" integer not null references ADDRESSBOOK on delete cascade,
    "RESOURCE_NAME" nvarchar2(255),
    "VCARD_TEXT" nclob,
    "VCARD_UID" nvarchar2(255),
    "MD5" nchar(32),
    "CREATED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC',
    "MODIFIED" timestamp default CURRENT_TIMESTAMP at time zone 'UTC', 
    unique("ADDRESSBOOK_RESOURCE_ID", "RESOURCE_NAME"), 
    unique("ADDRESSBOOK_RESOURCE_ID", "VCARD_UID")
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
    "ADDRESSBOOK_RESOURCE_ID" integer references ADDRESSBOOK,
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
    unique("TOKEN", "RESOURCE_KEY")
);

create table CALENDARSERVER (
    "NAME" nvarchar2(255) primary key,
    "VALUE" nvarchar2(255)
);

insert into CALENDARSERVER (NAME, VALUE) values ('VERSION', '6');
create index INVITE_INVITE_UID_9b0902ff on INVITE (
    INVITE_UID
);

create index INVITE_RESOURCE_ID_b36ddc23 on INVITE (
    RESOURCE_ID
);

create index INVITE_HOME_RESOURCE__e9bdf77e on INVITE (
    HOME_RESOURCE_ID
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

create index CALENDAR_OBJECT_ORGAN_7ce24750 on CALENDAR_OBJECT (
    ORGANIZER_OBJECT
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

create index ADDRESSBOOK_BIND_RESO_205aa75c on ADDRESSBOOK_BIND (
    ADDRESSBOOK_RESOURCE_ID
);

create index CALENDAR_OBJECT_REVIS_42be4d9e on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_HOME_RESOURCE_ID
);

create index CALENDAR_OBJECT_REVIS_2643d556 on CALENDAR_OBJECT_REVISIONS (
    CALENDAR_RESOURCE_ID,
    RESOURCE_NAME
);

create index ADDRESSBOOK_OBJECT_RE_5965a9e2 on ADDRESSBOOK_OBJECT_REVISIONS (
    ADDRESSBOOK_HOME_RESOURCE_ID
);

create index ADDRESSBOOK_OBJECT_RE_9a848f39 on ADDRESSBOOK_OBJECT_REVISIONS (
    ADDRESSBOOK_RESOURCE_ID,
    RESOURCE_NAME
);

create index APN_SUBSCRIPTIONS_RES_9610d78e on APN_SUBSCRIPTIONS (
    RESOURCE_KEY
);

