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


# accounts-test.xml

out = file("accounts-test.xml", "w")
out.write(prefix)
out.write('<directory realm="Test Realm">\n')


for uid, fullName in (
    ("admin", "Super User"),
    ("apprentice", "Apprentice Super User"),
    ("i18nuser", u"\ud83d\udca3".encode("utf-8")),
):
    out.write("""<record>
    <uid>{uid}</uid>
    <short-name>{uid}</short-name>
    <password>{uid}</password>
    <full-name>{fullName}</full-name>
    <email>{uid}@example.com</email>
</record>
""".format(uid=uid, fullName=fullName))

# user01-100
for i in xrange(1, 101):
    out.write("""<record type="user">
    <short-name>user%02d</short-name>
    <uid>user%02d</uid>
    <guid>708C5C91-082E-4DEB-ADD3-7CFB19ADF%03d</guid>
    <password>user%02d</password>
    <full-name>User %02d</full-name>
    <email>user%02d@example.com</email>
</record>
""" % (i, i, i, i, i, i))

# public01-10
for i in xrange(1, 11):
    out.write("""<record type="user">
    <short-name>public%02d</short-name>
    <uid>public%02d</uid>
    <guid>42DCA7BD-588A-458F-A1B6-1F778A85DF%02d</guid>
    <password>public%02d</password>
    <full-name>Public %02d</full-name>
    <email>public%02d@example.com</email>
</record>
""" % (i, i, i, i, i, i))

# group01-100
members = {
    "group01": ("user01",),
    "group02": ("user06", "user07"),
    "group03": ("user08", "user09"),
    "group04": ("group02", "group03", "user10"),
    "group05": ("group06", "user20"),
    "group06": ("user21",),
    "group07": ("user22", "user23", "user24"),
    "disabledgroup": ("user01",),
}

for i in xrange(1, 101):

    memberElements = []
    groupUID = "group%02d" % i
    if groupUID in members:
        for uid in members[groupUID]:
            memberElements.append("<member-uid>{}</member-uid>".format(uid))
        memberString = "\n    ".join(memberElements)
    else:
        memberString = ""

    out.write("""<record type="group">
    <short-name>group%02d</short-name>
    <uid>group%02d</uid>
    <guid>97C1351D-35E7-41E9-8F6F-72DDB9136%03d</guid>
    <full-name>Group %02d</full-name>
    <email>group%02d@example.com</email>
    %s
</record>
""" % (i, i, i, i, i, memberString))

out.write("</directory>\n")
out.close()


# resources-test.xml

out = file("resources-test.xml", "w")
out.write(prefix)
out.write('<directory realm="Test Realm">\n')

out.write("""
  <record type="location">
    <short-name>pretend</short-name>
    <uid>pretend</uid>
    <full-name>Pretend Conference Room</full-name>
    <associatedAddress>il1</associatedAddress>
  </record>
  <record type="address">
    <short-name>il1</short-name>
    <uid>il1</uid>
    <full-name>IL1</full-name>
    <streetAddress>1 Infinite Loop, Cupertino, CA 95014</streetAddress>
    <geographicLocation>37.331741,-122.030333</geographicLocation>
  </record>
  <record type="location">
    <short-name>fantastic</short-name>
    <uid>fantastic</uid>
    <full-name>Fantastic Conference Room</full-name>
    <associatedAddress>il2</associatedAddress>
  </record>
  <record type="address">
    <short-name>il2</short-name>
    <uid>il2</uid>
    <full-name>IL2</full-name>
    <streetAddress>2 Infinite Loop, Cupertino, CA 95014</streetAddress>
    <geographicLocation>37.332633,-122.030502</geographicLocation>
  </record>
""")

for i in xrange(1, 101):
    out.write("""<record type="location">
    <short-name>location%02d</short-name>
    <uid>location%02d</uid>
    <guid>34EB6DBA-B94C-4F82-8FEF-EB2C19258%03d</guid>
    <full-name>Location %02d</full-name>
</record>
""" % (i, i, i, i))


for i in xrange(1, 101):
    out.write("""<record type="resource">
    <short-name>resource%02d</short-name>
    <uid>resource%02d</uid>
    <guid>9DD5F2A5-DAA7-4CEB-825C-2EEB458C1%03d</guid>
    <full-name>Resource %02d</full-name>
</record>
""" % (i, i, i, i))

out.write("</directory>\n")
out.close()


# augments-test.xml

out = file("augments-test.xml", "w")
out.write(prefix)
out.write("<augments>\n")

augments = (
    ("resource04", {
        "auto-schedule-mode": "none",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
    ("resource05", {
        "auto-schedule-mode": "none",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
    ("resource06", {
        "auto-schedule-mode": "accept-always",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
    ("resource07", {
        "auto-schedule-mode": "decline-always",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
    ("resource08", {
        "auto-schedule-mode": "accept-if-free",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
    ("resource09", {
        "auto-schedule-mode": "decline-if-busy",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
    ("resource10", {
        "auto-schedule-mode": "automatic",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
    ("resource11", {
        "auto-schedule-mode": "automatic",
        "auto-accept-group": "group01",
        "enable-calendar": "true",
        "enable-addressbook": "true",
    }),
)

out.write("""<record>
    <uid>Default</uid>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""")

for uid, settings in augments:
    elements = []
    for key, value in settings.iteritems():
        elements.append("<{key}>{value}</{key}>".format(key=key, value=value))
    elementsString = "\n    ".join(elements)

    out.write("""<record>
    <uid>{uid}</uid>
    {elements}
</record>
""".format(uid=uid, elements=elementsString))

out.write("</augments>\n")
out.close()


# proxies-test.xml

out = file("proxies-test.xml", "w")
out.write(prefix)
out.write("<proxies>\n")

proxies = (
    ("resource01", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource02", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource03", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource04", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource05", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource06", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource07", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource08", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource09", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
    }),
    ("resource10", {
        "proxies": ("user01",),
        "read-only-proxies": ("user03",),
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
