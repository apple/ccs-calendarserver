-----------------
-- Resource ID --
-----------------

create sequence RESOURCE_ID_SEQ;


-------------------
-- Calendar Home --
-------------------

create table CALENDAR_HOME (
  RESOURCE_ID integer      primary key default nextval('RESOURCE_ID_SEQ'),
  OWNER_UID   varchar(255) not null unique
);


--------------
-- Calendar --
--------------

create table CALENDAR (
  RESOURCE_ID integer      primary key default nextval('RESOURCE_ID_SEQ'),
  SYNC_TOKEN  varchar(255)
);


------------------------
-- Sharing Invitation --
------------------------

create table INVITE (
    INVITE_UID         varchar(255) not null,
    NAME               varchar(255) not null,
    SENDER_ADDRESS     varchar(255) not null,
    HOME_RESOURCE_ID   integer      not null,
    RESOURCE_ID        integer      not null
);


---------------------------
-- Sharing Notifications --
---------------------------

create table NOTIFICATION_HOME (
  RESOURCE_ID integer      primary key default nextval('RESOURCE_ID_SEQ'),
  OWNER_UID   varchar(255) not null unique
);


create table NOTIFICATION (
  RESOURCE_ID                   integer      primary key default nextval('RESOURCE_ID_SEQ'),
  NOTIFICATION_HOME_RESOURCE_ID integer      not null references NOTIFICATION_HOME,
  NOTIFICATION_UID              varchar(255) not null,
  XML_TYPE                      varchar      not null,
  XML_DATA                      varchar      not null
);


-------------------
-- Calendar Bind --
-------------------

-- Joins CALENDAR_HOME and CALENDAR

create table CALENDAR_BIND (
  CALENDAR_HOME_RESOURCE_ID integer      not null references CALENDAR_HOME,
  CALENDAR_RESOURCE_ID      integer      not null references CALENDAR,
  
  -- An invitation which hasn't been accepted yet will not yet have a resource
  -- name, so this field may be null.
  
  CALENDAR_RESOURCE_NAME    varchar(255),
  BIND_MODE                 integer      not null, -- enum CALENDAR_BIND_MODE
  BIND_STATUS               integer      not null, -- enum CALENDAR_BIND_STATUS
  SEEN_BY_OWNER             boolean      not null,
  SEEN_BY_SHAREE            boolean      not null,
  MESSAGE                   text,

  primary key(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID),
  unique(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_NAME)
);

-- Enumeration of calendar bind modes

create table CALENDAR_BIND_MODE (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_BIND_MODE values (0, 'own'  );
insert into CALENDAR_BIND_MODE values (1, 'read' );
insert into CALENDAR_BIND_MODE values (2, 'write');

-- Enumeration of statuses

create table CALENDAR_BIND_STATUS (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_BIND_STATUS values (0, 'invited' );
insert into CALENDAR_BIND_STATUS values (1, 'accepted');
insert into CALENDAR_BIND_STATUS values (2, 'declined');
insert into CALENDAR_BIND_STATUS values (3, 'invalid');


---------------------
-- Calendar Object --
---------------------

create table CALENDAR_OBJECT (
  RESOURCE_ID          integer      primary key default nextval('RESOURCE_ID_SEQ'),
  CALENDAR_RESOURCE_ID integer      not null references CALENDAR,
  RESOURCE_NAME        varchar(255) not null,
  ICALENDAR_TEXT       text         not null,
  ICALENDAR_UID        varchar(255) not null,
  ICALENDAR_TYPE       varchar(255) not null,
  ATTACHMENTS_MODE     integer      not null, -- enum CALENDAR_OBJECT_ATTACHMENTS_MODE
  ORGANIZER            varchar(255),
  ORGANIZER_OBJECT     integer      references CALENDAR_OBJECT,
  RECURRANCE_MAX       date,        -- maximum date that recurrences have been expanded to.

  unique(CALENDAR_RESOURCE_ID, RESOURCE_NAME)

  -- since the 'inbox' is a 'calendar resource' for the purpose of storing
  -- calendar objects, this constraint has to be selectively enforced by the
  -- application layer.

  -- unique(CALENDAR_RESOURCE_ID, ICALENDAR_UID)
);

-- Enumeration of attachment modes

create table CALENDAR_OBJECT_ATTACHMENTS_MODE (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (0, 'read' );
insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (1, 'write');


-----------------
-- Instance ID --
-----------------

create sequence INSTANCE_ID_SEQ;


----------------
-- Time Range --
----------------

create table TIME_RANGE (
  INSTANCE_ID                 integer        primary key default nextval('INSTANCE_ID_SEQ'),
  CALENDAR_RESOURCE_ID        integer        not null references CALENDAR,
  CALENDAR_OBJECT_RESOURCE_ID integer        not null references CALENDAR_OBJECT on delete cascade,
  FLOATING                    boolean        not null,
  START_DATE                  timestamp      not null,
  END_DATE                    timestamp      not null,
  FBTYPE                      integer        not null,
  TRANSPARENT                 boolean        not null
);

-- Enumeration of free/busy types

create table FREE_BUSY_TYPE (
  ID          integer     primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into FREE_BUSY_TYPE values (0, 'unknown'         );
insert into FREE_BUSY_TYPE values (1, 'free'            );
insert into FREE_BUSY_TYPE values (2, 'busy'            );
insert into FREE_BUSY_TYPE values (3, 'busy-unavailable');
insert into FREE_BUSY_TYPE values (4, 'busy-tentative'  );


------------------
-- Transparency --
------------------

create table TRANSPARENCY (
  TIME_RANGE_INSTANCE_ID      integer      not null references TIME_RANGE on delete cascade,
  USER_ID                     varchar(255) not null,
  TRANSPARENT                 boolean      not null
);


----------------
-- Attachment --
----------------

create table ATTACHMENT (
  CALENDAR_OBJECT_RESOURCE_ID integer       not null references CALENDAR_OBJECT,
  CONTENT_TYPE                varchar(255)  not null,
  SIZE                        integer       not null,
  MD5                         char(32)      not null,
  PATH                        varchar(1024) not null unique
);


------------------
-- iTIP Message --
------------------

create table ITIP_MESSAGE (
  CALENDAR_RESOURCE_ID integer      not null references CALENDAR,
  ICALENDAR_TEXT       text         not null,
  ICALENDAR_UID        varchar(255) not null,
  MD5                  char(32)     not null,
  CHANGES              text         not null
);


-----------------------
-- Resource Property --
-----------------------

create table RESOURCE_PROPERTY (
  RESOURCE_ID integer      not null, -- foreign key: *.RESOURCE_ID
  NAME        varchar(255) not null,
  VALUE       text         not null, -- FIXME: xml?
  VIEWER_UID  varchar(255),

  primary key(RESOURCE_ID, NAME, VIEWER_UID)
);


----------------------
-- AddressBook Home --
----------------------

create table ADDRESSBOOK_HOME (
  RESOURCE_ID integer      primary key default nextval('RESOURCE_ID_SEQ'),
  OWNER_UID   varchar(255) not null unique
);


-----------------
-- AddressBook --
-----------------

create table ADDRESSBOOK (
  RESOURCE_ID integer      primary key default nextval('RESOURCE_ID_SEQ'),
  SYNC_TOKEN  varchar(255)
);


----------------------
-- AddressBook Bind --
----------------------

-- Joins ADDRESSBOOK_HOME and ADDRESSBOOK

create table ADDRESSBOOK_BIND (
  ADDRESSBOOK_HOME_RESOURCE_ID integer      not null references ADDRESSBOOK_HOME,
  ADDRESSBOOK_RESOURCE_ID      integer      not null references ADDRESSBOOK,
  ADDRESSBOOK_RESOURCE_NAME    varchar(255) not null,
  BIND_MODE                    integer      not null, -- enum CALENDAR_BIND_MODE
  BIND_STATUS                  integer      not null, -- enum CALENDAR_BIND_STATUS
  SEEN_BY_OWNER                boolean      not null,
  SEEN_BY_SHAREE               boolean      not null,
  MESSAGE                      text,                  -- FIXME: xml?

  primary key(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_ID),
  unique(ADDRESSBOOK_HOME_RESOURCE_ID, ADDRESSBOOK_RESOURCE_NAME)
);


create table ADDRESSBOOK_OBJECT (
  RESOURCE_ID             integer      primary key default nextval('RESOURCE_ID_SEQ'),
  ADDRESSBOOK_RESOURCE_ID integer      not null references ADDRESSBOOK,
  RESOURCE_NAME           varchar(255) not null,
  VCARD_TEXT              text         not null,
  VCARD_UID               varchar(255) not null,
  VCARD_TYPE              varchar(255) not null,

  unique(ADDRESSBOOK_RESOURCE_ID, RESOURCE_NAME),
  unique(ADDRESSBOOK_RESOURCE_ID, VCARD_UID)
);
