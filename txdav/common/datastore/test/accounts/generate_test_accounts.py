#!/usr/bin/env python

# Generates test directory records in accounts-test.xml,
# (overwriting it if it exists in the current directory).

prefix = """<?xml version="1.0" encoding="utf-8"?>

<!--
Copyright (c) 2006-2015 Apple Inc. All rights reserved.

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
out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
out.write('<directory realm="Test Realm">\n')



# user01-100
for i in xrange(1, 101):
    out.write("""<record type="user">
    <uid>user{ctr:02d}</uid>
    <short-name>user{ctr:02d}</short-name>
    <password>user{ctr:02d}</password>
    <full-name>User {ctr:02d}</full-name>
    <email>user{ctr:02d}@example.com</email>
</record>
""".format(ctr=i))
for i in xrange(1, 101):
    out.write("""<record type="user">
    <uid>puser{ctr:02d}</uid>
    <short-name>puser{ctr:02d}</short-name>
    <password>puser{ctr:02d}</password>
    <full-name>Puser {ctr:02d}</full-name>
    <email>puser{ctr:02d}@example.com</email>
</record>
""".format(ctr=i))
out.write("</directory>\n")
out.close()



out = file("augments-test.xml", "w")
out.write(prefix)
out.write('<!DOCTYPE augments SYSTEM "augments.dtd">\n\n')
out.write("<augments>\n")

for i in xrange(1, 101):
    out.write("""<record>
    <uid>user{ctr:02d}</uid>
    <server-id>A</server-id>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""".format(ctr=i))

for i in xrange(1, 101):
    out.write("""<record>
    <uid>puser{ctr:02d}</uid>
    <server-id>B</server-id>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""".format(ctr=i))

out.close()
