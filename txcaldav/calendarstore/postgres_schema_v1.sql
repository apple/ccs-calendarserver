-----------------
-- Resource ID --
-----------------

create sequence RESOURCE_ID_SEQ;


-------------------
-- Calendar Home --
-------------------

create table CALENDAR_HOME (
  RESOURCE_ID varchar(255) primary key default nextval('RESOURCE_ID_SEQ'),
  OWNER_UID   varchar(255) not null unique
);


--------------
-- Calendar --
--------------

create table CALENDAR (
  RESOURCE_ID varchar(255) primary key default nextval('RESOURCE_ID_SEQ'),
  SYNC_TOKEN  varchar(255)
);


-------------------
-- Calendar Bind --
-------------------

-- Joins CALENDAR_HOME and CALENDAR

create table CALENDAR_BIND (
  CALENDAR_HOME_RESOURCE_ID varchar(255) not null references CALENDAR_HOME,
  CALENDAR_RESOURCE_ID      varchar(255) not null references CALENDAR,
  CALENDAR_RESOURCE_NAME    varchar(255) not null,
  BIND_MODE                 integer      not null, -- enum CALENDAR_BIND_MODE
  BIND_STATUS               integer      not null, -- enum CALENDAR_BIND_STATUS
  SEEN_BY_OWNER             bool         not null,
  SEEN_BY_SHAREE            bool         not null,
  MESSAGE                   text,                  -- FIXME: xml?

  primary key(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_ID),
  unique(CALENDAR_HOME_RESOURCE_ID, CALENDAR_RESOURCE_NAME)
);

-- Enumeration of calendar bind modes

create table CALENDAR_BIND_MODE (
  ID          int         primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_BIND_MODE values (0, 'own'  );
insert into CALENDAR_BIND_MODE values (1, 'read' );
insert into CALENDAR_BIND_MODE values (2, 'write');

-- Enumeration of statuses

create table CALENDAR_BIND_STATUS (
  ID          int         primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_BIND_STATUS values (0, 'invited' );
insert into CALENDAR_BIND_STATUS values (1, 'accepted');
insert into CALENDAR_BIND_STATUS values (2, 'declined');


---------------------
-- Calendar Object --
---------------------

create table CALENDAR_OBJECT (
  RESOURCE_ID          varchar(255) primary key default nextval('RESOURCE_ID_SEQ'),
  CALENDAR_RESOURCE_ID varchar(255) not null references CALENDAR,
  RESOURCE_NAME        varchar(255) not null,
  ICALENDAR_TEXT       text         not null,
  ICALENDAR_UID        varchar(255) not null,
  ICALENDAR_TYPE       varchar(255) not null,
  ATTACHMENTS_MODE     int          not null, -- enum CALENDAR_OBJECT_ATTACHMENTS_MODE
  ORGANIZER            varchar(255),
  ORGANIZER_OBJECT     varchar(255) references CALENDAR_OBJECT,

  unique(CALENDAR_RESOURCE_ID, RESOURCE_NAME),
  unique(CALENDAR_RESOURCE_ID, ICALENDAR_UID)
);

-- Enumeration of attachment modes

create table CALENDAR_OBJECT_ATTACHMENTS_MODE (
  ID          int         primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (0, 'read' );
insert into CALENDAR_OBJECT_ATTACHMENTS_MODE values (1, 'write');


----------------
-- Time Range --
----------------

create table TIME_RANGE (
  CALENDAR_OBJECT_RESOURCE_ID varchar(255) not null references CALENDAR_OBJECT,
  FLOATING                    bool         not null,
  START_DATE                  date         not null,
  END_DATE                    date         not null,
  FBTYPE                      integer      not null, -- enum FREE_BUSY_TYPE
  TRANSPARENT                 bool         not null
);

-- Enumeration of free/busy types

create table FREE_BUSY_TYPE (
  ID          int         primary key,
  DESCRIPTION varchar(16) not null unique
);

insert into FREE_BUSY_TYPE values (0, 'unknown'         );
insert into FREE_BUSY_TYPE values (1, 'free'            );
insert into FREE_BUSY_TYPE values (2, 'busy'            );
insert into FREE_BUSY_TYPE values (3, 'busy-unavailable');
insert into FREE_BUSY_TYPE values (4, 'busy-tentative'  );


----------------
-- Attachment --
----------------

create table ATTACHMENT (
  CALENDAR_OBJECT_RESOURCE_ID varchar(255) not null references CALENDAR_OBJECT,
  CONTENT_TYPE                varchar(255) not null,
  SIZE                        int          not null,
  MD5                         char(32)     not null,
  PATH                        varchar(255) not null unique
);


------------------
-- iTIP Message --
------------------

create table ITIP_MESSAGE (
  CALENDAR_RESOURCE_ID varchar(255) not null references CALENDAR,
  ICALENDAR_TEXT       text         not null,
  ICALENDAR_UID        varchar(255) not null,
  MD5                  char(32)     not null,
  CHANGES              text         not null
);


-----------------------
-- Resource Property --
-----------------------

create table RESOURCE_PROPERTY (
  RESOURCE_ID varchar(255) not null, -- foreign key: *.RESOURCE_ID
  NAME        varchar(255) not null,
  VALUE       text         not null, -- FIXME: xml?
  VIEWER_UID  varchar(255),

  primary key(RESOURCE_ID, NAME, VIEWER_UID)
);
