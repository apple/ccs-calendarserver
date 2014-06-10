#!/usr/bin/env python

# Generates test directory records in accounts-test.xml, resources-test.xml,
# augments-test.xml and proxies-test.xml (overwriting them if they exist in
# the current directory).

prefix = """<?xml version="1.0" encoding="utf-8"?>

<!--
Copyright (c) 2006-2014 Apple Inc. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
 -->

"""

# The uids and guids for CDT test accounts are the same
# The short name is of the form userNN
USERGUIDS = "10000000-0000-0000-0000-000000000%03d"
GROUPGUIDS = "20000000-0000-0000-0000-000000000%03d"
LOCATIONGUIDS = "30000000-0000-0000-0000-000000000%03d"
RESOURCEGUIDS = "40000000-0000-0000-0000-000000000%03d"
PUBLICGUIDS = "50000000-0000-0000-0000-0000000000%02d"
PUSERGUIDS = "60000000-0000-0000-0000-000000000%03d"
S2SUSERGUIDS = "70000000-0000-0000-0000-000000000%03d"

# accounts-test.xml

out = file("accounts-test.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
out.write('<directory realm="Test Realm">\n')


for uid, fullName, guid in (
    ("admin", "Super User", "0C8BDE62-E600-4696-83D3-8B5ECABDFD2E"),
    ("apprentice", "Apprentice Super User", "29B6C503-11DF-43EC-8CCA-40C7003149CE"),
    ("i18nuser", u"\u307e\u3060".encode("utf-8"), "860B3EE9-6D7C-4296-9639-E6B998074A78"),
):
    out.write("""<record>
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>{uid}</short-name>
    <password>{uid}</password>
    <full-name>{fullName}</full-name>
    <email>{uid}@example.com</email>
</record>
""".format(uid=uid, guid=guid, fullName=fullName))

# user01-100
for i in xrange(1, 101):
    out.write("""<record type="user">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>user{ctr:02d}</short-name>
    <password>user{ctr:02d}</password>
    <full-name>User {ctr:02d}</full-name>
    <email>user{ctr:02d}@example.com</email>
</record>
""".format(guid=(USERGUIDS % i), ctr=i))

# public01-10
for i in xrange(1, 11):
    out.write("""<record type="user">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>public{ctr:02d}</short-name>
    <password>public{ctr:02d}</password>
    <full-name>Public {ctr:02d}</full-name>
    <email>public{ctr:02d}@example.com</email>
</record>
""".format(guid=PUBLICGUIDS % i, ctr=i))

# group01-100
members = {
    GROUPGUIDS % 1: (USERGUIDS % 1,),
    GROUPGUIDS % 2: (USERGUIDS % 6, USERGUIDS % 7),
    GROUPGUIDS % 3: (USERGUIDS % 8, USERGUIDS % 9),
    GROUPGUIDS % 4: (GROUPGUIDS % 2, GROUPGUIDS % 3, USERGUIDS % 10),
    GROUPGUIDS % 5: (GROUPGUIDS % 6, USERGUIDS % 20),
    GROUPGUIDS % 6: (USERGUIDS % 21,),
    GROUPGUIDS % 7: (USERGUIDS % 22, USERGUIDS % 23, USERGUIDS % 24),
}

for i in xrange(1, 101):

    memberElements = []
    groupUID = GROUPGUIDS % i
    if groupUID in members:
        for uid in members[groupUID]:
            memberElements.append("<member-uid>{}</member-uid>".format(uid))
        memberString = "    " + "\n    ".join(memberElements) + "\n"
    else:
        memberString = ""

    out.write("""<record type="group">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>group{ctr:02d}</short-name>
    <full-name>Group {ctr:02d}</full-name>
    <email>group{ctr:02d}@example.com</email>
{members}</record>
""".format(guid=GROUPGUIDS % i, ctr=i, members=memberString))

out.write("</directory>\n")
out.close()


# accounts-test-pod.xml

out = file("accounts-test-pod.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
out.write('<directory realm="Test Realm">\n')


for uid, fullName, guid in (
    ("admin", "Super User", "0C8BDE62-E600-4696-83D3-8B5ECABDFD2E"),
):
    out.write("""<record>
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>{uid}</short-name>
    <password>{uid}</password>
    <full-name>{fullName}</full-name>
    <email>{uid}@example.com</email>
</record>
""".format(uid=uid, guid=guid, fullName=fullName))

# user01-100
for i in xrange(1, 101):
    out.write("""<record type="user">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>user{ctr:02d}</short-name>
    <password>user{ctr:02d}</password>
    <full-name>User {ctr:02d}</full-name>
    <email>user{ctr:02d}@example.com</email>
</record>
""".format(guid=USERGUIDS % i, ctr=i))

# puser01-100
for i in xrange(1, 101):
    out.write("""<record type="user">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>puser{ctr:02d}</short-name>
    <password>puser{ctr:02d}</password>
    <full-name>Puser {ctr:02d}</full-name>
    <email>puser{ctr:02d}@example.com</email>
</record>
""".format(guid=PUSERGUIDS % i, ctr=i))

out.write("</directory>\n")
out.close()


# accounts-test-s2s.xml

out = file("accounts-test-s2s.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
out.write('<directory realm="Test Realm 2">\n')


for uid, fullName, guid in (
    ("admin", "Super User", "82A5A2FA-F8FD-4761-B1CB-F1664C1F376A"),
):
    out.write("""<record>
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>{uid}</short-name>
    <password>{uid}</password>
    <full-name>{fullName}</full-name>
    <email>{uid}@example.org</email>
</record>
""".format(uid=uid, guid=guid, fullName=fullName))

# other01-100
for i in xrange(1, 101):
    out.write("""<record type="user">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>other{ctr:02d}</short-name>
    <password>other{ctr:02d}</password>
    <full-name>Other {ctr:02d}</full-name>
    <email>other{ctr:02d}@example.org</email>
</record>
""".format(guid=S2SUSERGUIDS % i, ctr=i))

out.write("</directory>\n")
out.close()


# resources-test.xml

out = file("resources-test.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
out.write('<directory realm="Test Realm">\n')

out.write("""<record type="location">
  <uid>pretend</uid>
  <short-name>pretend</short-name>
  <full-name>Pretend Conference Room</full-name>
  <associated-address>il1</associated-address>
</record>
<record type="address">
  <uid>il1</uid>
  <short-name>il1</short-name>
  <full-name>IL1</full-name>
  <street-address>1 Infinite Loop, Cupertino, CA 95014</street-address>
  <geographic-location>geo:37.331741,-122.030333</geographic-location>
</record>
<record type="location">
  <uid>fantastic</uid>
  <short-name>fantastic</short-name>
  <full-name>Fantastic Conference Room</full-name>
  <associated-address>il2</associated-address>
</record>
<record type="address">
  <uid>il2</uid>
  <short-name>il2</short-name>
  <full-name>IL2</full-name>
  <street-address>2 Infinite Loop, Cupertino, CA 95014</street-address>
  <geographic-location>geo:37.332633,-122.030502</geographic-location>
</record>
<record type="location">
  <uid>delegatedroom</uid>
  <short-name>delegatedroom</short-name>
  <full-name>Delegated Conference Room</full-name>
</record>
""")

for i in xrange(1, 101):
    out.write("""<record type="location">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>location{ctr:02d}</short-name>
    <full-name>Location {ctr:02d}</full-name>
</record>
""".format(guid=LOCATIONGUIDS % i, ctr=i))


for i in xrange(1, 101):
    out.write("""<record type="resource">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>resource{ctr:02d}</short-name>
    <full-name>Resource {ctr:02d}</full-name>
</record>
""".format(guid=RESOURCEGUIDS % i, ctr=i))

out.write("</directory>\n")
out.close()


# resources-test-pod.xml

out = file("resources-test-pod.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
out.write('<directory realm="Test Realm" />\n')
out.close()

# resources-test-s2s.xml

out = file("resources-test-s2s.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
out.write('<directory realm="Test Realm 2" />\n')
out.close()


# augments-test.xml

out = file("augments-test.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE augments SYSTEM "augments.dtd">\n\n')
out.write("<augments>\n")

augments = (
    # resource05
    (RESOURCEGUIDS % 5, (
        ("enable-calendar", "true"),
        ("enable-addressbook", "true"),
        ("auto-schedule-mode", "none"),
    )),
    # resource06
    (RESOURCEGUIDS % 6, (
        ("enable-calendar", "true"),
        ("enable-addressbook", "true"),
        ("auto-schedule-mode", "accept-always"),
    )),
    # resource07
    (RESOURCEGUIDS % 7, (
        ("enable-calendar", "true"),
        ("enable-addressbook", "true"),
        ("auto-schedule-mode", "decline-always"),
    )),
    # resource08
    (RESOURCEGUIDS % 8, (
        ("enable-calendar", "true"),
        ("enable-addressbook", "true"),
        ("auto-schedule-mode", "accept-if-free"),
    )),
    # resource09
    (RESOURCEGUIDS % 9, (
        ("enable-calendar", "true"),
        ("enable-addressbook", "true"),
        ("auto-schedule-mode", "decline-if-busy"),
    )),
    # resource10
    (RESOURCEGUIDS % 10, (
        ("enable-calendar", "true"),
        ("enable-addressbook", "true"),
        ("auto-schedule-mode", "automatic"),
    )),
    # resource11
    (RESOURCEGUIDS % 11, (
        ("enable-calendar", "true"),
        ("enable-addressbook", "true"),
        ("auto-schedule-mode", "decline-always"),
        ("auto-accept-group", GROUPGUIDS % 1),
    )),
)

out.write("""<record>
    <uid>Default</uid>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""")

out.write("""<record>
    <uid>Default-Location</uid>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
    <auto-schedule-mode>automatic</auto-schedule-mode>
</record>
""")

out.write("""<record>
    <uid>Default-Resource</uid>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
    <auto-schedule-mode>automatic</auto-schedule-mode>
</record>
""")

for uid, settings in augments:
    elements = []
    for key, value in settings:
        elements.append("<{key}>{value}</{key}>".format(key=key, value=value))
    elementsString = "\n    ".join(elements)

    out.write("""<record>
    <uid>{uid}</uid>
    {elements}
</record>
""".format(uid=uid, elements=elementsString))

out.write("</augments>\n")
out.close()


# augments-test-pod.xml

out = file("augments-test-pod.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE augments SYSTEM "augments.dtd">\n\n')
out.write("<augments>\n")

out.write("""<record>
    <uid>Default</uid>
    <server-id>A</server-id>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""")

# puser01-100
for i in xrange(1, 101):
    out.write("""<record>
    <uid>{guid}</uid>
    <server-id>B</server-id>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""".format(guid=PUSERGUIDS % i))

out.write("</augments>\n")
out.close()


# augments-test-s2s.xml

out = file("augments-test-s2s.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE augments SYSTEM "augments.dtd">\n\n')
out.write("<augments>\n")

out.write("""<record>
    <uid>Default</uid>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""")

out.write("</augments>\n")
out.close()


# proxies-test.xml

out = file("proxies-test.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE proxies SYSTEM "proxies.dtd">\n\n')
out.write("<proxies>\n")

proxies = (
    (RESOURCEGUIDS % 1, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 2, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 3, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 4, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 5, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 6, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 7, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 8, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 9, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    (RESOURCEGUIDS % 10, {
        "write-proxies": (USERGUIDS % 1,),
        "read-proxies": (USERGUIDS % 3,),
    }),
    ("delegatedroom", {
        "write-proxies": (GROUPGUIDS % 5,),
        "read-proxies": (),
    }),
)

for uid, settings in proxies:
    elements = []
    for key, values in settings.iteritems():
        elements.append("<{key}>".format(key=key))
        for value in values:
            elements.append("<member>{value}</member>".format(value=value))
        elements.append("</{key}>".format(key=key))
    elementsString = "\n    ".join(elements)

    out.write("""<record>
    <guid>{uid}</guid>
    {elements}
</record>
""".format(uid=uid, elements=elementsString))

out.write("</proxies>\n")
out.close()


# proxies-test-pod.xml

out = file("proxies-test-pod.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE proxies SYSTEM "proxies.dtd">\n\n')
out.write("<proxies />\n")
out.close()


# proxies-test-s2s.xml

out = file("proxies-test-s2s.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE proxies SYSTEM "proxies.dtd">\n\n')
out.write("<proxies />\n")
out.close()
