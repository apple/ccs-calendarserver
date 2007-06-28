##
# Copyright (c) 2005-2007 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DRI: Wilfredo Sanchez, wsanchez@apple.com
##

try:
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryService
    from twistedcaldav.directory.appleopendirectory import OpenDirectoryInitError
    import dsattributes
except ImportError:
    pass
else:
    from twistedcaldav.directory.directory import DirectoryService
    import twisted.trial.unittest

    class PlistParse (twisted.trial.unittest.TestCase):
        """
        Test Open Directory service schema.
        """

        plist_nomacosxserver_key = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>
    </dict>
</plist>
"""

        plist_nocalendarservice = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

        plist_noserviceinfo = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>

            <key>C18C34AC-3D9E-403C-8A33-BFC303F3840E</key>
            <dict>
                <key>hostname</key>
                <string>calendar.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>8008</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>8443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>calendar</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

        plist_disabledservice = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <string>443</string>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>

            <key>C18C34AC-3D9E-403C-8A33-BFC303F3840E</key>
            <dict>
                <key>hostname</key>
                <string>calendar.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>8008</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>8443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>calendar</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>calendar</key>
                    <dict>
                        <key>enabled</key>
                        <false/>
                        <key>templates</key>
                        <dict>
                            <key>principalPath</key>
                            <string>/principals/%(type)s/%(name)s</string>
                            <key>calendarUserAddresses</key>
                            <array>
                                <string>%(scheme)s://%(hostname)s:%(port)s/principals/%(type)s/%(name)s</string>
                                <string>mailto:%(email)s</string>
                                <string>urn:uuid:%(guid)s</string>
                            </array>
                        </dict>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

        plist_nohostname = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <string>443</string>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>

            <key>C18C34AC-3D9E-403C-8A33-BFC303F3840E</key>
            <dict>
                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>8008</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>8443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>calendar</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>calendar</key>
                    <dict>
                        <key>templates</key>
                        <dict>
                            <key>principalPath</key>
                            <string>/principals/%(type)s/%(name)s</string>
                            <key>calendarUserAddresses</key>
                            <array>
                                <string>%(scheme)s://%(hostname)s:%(port)s/principals/%(type)s/%(name)s</string>
                                <string>mailto:%(email)s</string>
                                <string>urn:uuid:%(guid)s</string>
                            </array>
                        </dict>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

        plist_nohostdetails = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <string>443</string>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>

            <key>C18C34AC-3D9E-403C-8A33-BFC303F3840E</key>
            <dict>
                <key>hostname</key>
                <string>calendar.apple.com</string>

                <key>serviceType</key>
                <array>
                    <string>calendar</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>calendar</key>
                    <dict>
                        <key>templates</key>
                        <dict>
                            <key>principalPath</key>
                            <string>/principals/%(type)s/%(name)s</string>
                            <key>calendarUserAddresses</key>
                            <array>
                                <string>%(scheme)s://%(hostname)s:%(port)s/principals/%(type)s/%(name)s</string>
                                <string>mailto:%(email)s</string>
                                <string>urn:uuid:%(guid)s</string>
                            </array>
                        </dict>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

        plist_good = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <string>443</string>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>

            <key>C18C34AC-3D9E-403C-8A33-BFC303F3840E</key>
            <dict>
                <key>hostname</key>
                <string>calendar.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>8008</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>8443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>calendar</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>calendar</key>
                    <dict>
                        <key>templates</key>
                        <dict>
                            <key>principalPath</key>
                            <string>/principals/%(type)s/%(name)s</string>
                            <key>calendarUserAddresses</key>
                            <array>
                                <string>%(scheme)s://%(hostname)s:%(port)s/principals/%(type)s/%(name)s</string>
                                <string>mailto:%(email)s</string>
                                <string>urn:uuid:%(guid)s</string>
                            </array>
                        </dict>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

        plist_good_other = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>4F088107-51FD-4DE5-904D-2C0AD9C6C893</key>
            <dict>
                <key>hostname</key>
                <string>foo.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>80</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <string>443</string>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>wiki</string>
                    <string>webCalendar</string>
                    <string>webMailingList</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>webCalendar</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/webcalendar</string>
                    </dict>
                    <key>wiki</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/wiki</string>
                    </dict>
                    <key>webMailingList</key>
                    <dict>
                        <key>enabled</key>
                        <true/>
                        <key>urlMask</key>
                        <string>%(scheme)s://%(hostname)s:%(port)s/groups/%(name)s/mailinglist</string>
                    </dict>
                </dict>
            </dict>

            <key>C18C34AC-3D9E-403C-8A33-BFC303F3840E</key>
            <dict>
                <key>hostname</key>
                <string>privatecalendar.apple.com</string>

                <key>hostDetails</key>
                <dict>
                    <key>access</key>
                    <dict>
                        <key>somethingorother</key>
                        <string>somethingelse</string>
                    </dict>
                    <key>http</key>
                    <dict>
                        <key>port</key>
                        <integer>8008</integer>
                    </dict>
                    <key>https</key>
                    <dict>
                        <key>port</key>
                        <integer>8443</integer>
                    </dict>
                </dict>

                <key>serviceType</key>
                <array>
                    <string>calendar</string>
                </array>

                <key>serviceInfo</key>
                <dict>
                    <key>calendar</key>
                    <dict>
                        <key>templates</key>
                        <dict>
                            <key>principalPath</key>
                            <string>/principals/%(type)s/%(name)s</string>
                            <key>calendarUserAddresses</key>
                            <array>
                                <string>%(scheme)s://%(hostname)s:%(port)s/principals/%(type)s/%(name)s</string>
                                <string>mailto:%(email)s</string>
                                <string>urn:uuid:%(guid)s</string>
                            </array>
                        </dict>
                    </dict>
                </dict>
            </dict>

        </dict>
    </dict>
</plist>
"""

        def test_plist_errors(self):
            def _doParse(plist, title):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                if service._parseXMLPlist("calendar.apple.com", "recordit", plist, "GUIDIFY"):
                    self.fail(msg="Plist parse should have failed: %s" % (title,))

            plists = (
                (PlistParse.plist_nomacosxserver_key, "nomacosxserver_key"),
                (PlistParse.plist_nocalendarservice,  "nocalendarservice"),
                (PlistParse.plist_noserviceinfo,      "noserviceinfo"),
                (PlistParse.plist_disabledservice,    "disabledservice"),
                (PlistParse.plist_nohostname,         "nohostname"),
                (PlistParse.plist_nohostdetails,      "nohostdetails"),
            )
            for plist, title in plists:
                _doParse(plist, title)

        def test_goodplist(self):
            service = OpenDirectoryService(node="/Search", dosetup=False)
            if not service._parseXMLPlist("calendar.apple.com", "recordit", PlistParse.plist_good, "GUIDIFY"):
                self.fail(msg="Plist parse should not have failed")
            else:
                # Verify that we extracted the proper items
                self.assertEqual(service.servicetag, "GUIDIFY:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar")

        def test_expandcuaddrs(self):
            def _doTest(recordName, record, result, title):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                if not service._parseXMLPlist("calendar.apple.com", recordName, PlistParse.plist_good, "GUIDIFY"):
                    self.fail(msg="Plist parse should not have failed: %s" % (recordName,))
                else:
                    expanded = service._getCalendarUserAddresses(DirectoryService.recordType_users, recordName, record)

                    # Verify that we extracted the proper items
                    self.assertEqual(expanded, result, msg=title % (expanded, result,))

            data = (
                (
                 "user01",
                 {
                    dsattributes.kDS1AttrGeneratedUID: "GUID-USER-01",
                    dsattributes.kDSNAttrEMailAddress: "user01@example.com",
                 },
                 set((
                    "mailto:user01@example.com",
                 )),
                 "User with one email address, %s != %s",
                ),
                (
                 "user02",
                 {
                    dsattributes.kDS1AttrGeneratedUID: "GUID-USER-02",
                    dsattributes.kDSNAttrEMailAddress: ["user02@example.com", "user02@calendar.example.com"],
                 },
                 set((
                    "mailto:user02@example.com",
                    "mailto:user02@calendar.example.com",
                 )),
                 "User with multiple email addresses, %s != %s",
                ),
                (
                 "user03",
                 {
                    dsattributes.kDS1AttrGeneratedUID: "GUID-USER-03",
                 },
                 set(()),
                 "User with no email addresses, %s != %s",
                ),
            )

            for recordName, record, result, title in data:
                _doTest(recordName, record, result, title)

    class ODRecordsParse (twisted.trial.unittest.TestCase):

        record_good = ("computer1.apple.com", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID1",
            dsattributes.kDSNAttrRecordName       : "computer1.apple.com",
            dsattributes.kDS1AttrXMLPlist         : PlistParse.plist_good,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
        })
        record_good_other = ("computer2.apple.com", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID1",
            dsattributes.kDSNAttrRecordName       : "computer2.apple.com",
            dsattributes.kDS1AttrXMLPlist         : PlistParse.plist_good_other,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
        })
        record_good_duplicate = ("computer3.apple.com", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID2",
            dsattributes.kDSNAttrRecordName       : "computer2.apple.com",
            dsattributes.kDS1AttrXMLPlist         : PlistParse.plist_good,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/directory.apple.com",
        })
        record_good_local_duplicate = ("ServiceInformation", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID3",
            dsattributes.kDSNAttrRecordName       : "computer2.apple.com",
            dsattributes.kDS1AttrXMLPlist         : PlistParse.plist_good,
            dsattributes.kDSNAttrMetaNodeLocation : "/Local/Default",
        })

        def test_odrecords_error(self):
            def _doParseRecords(recordlist, title):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                try:
                    service._parseComputersRecords(recordlist, "calendar.apple.com")
                    self.fail(msg="Record parse should have failed: %s" % (title,))
                except OpenDirectoryInitError:
                    pass

            records = (
                ({}, "no records found"),
                ({
                      ODRecordsParse.record_good_other[0]  : ODRecordsParse.record_good_other[1],
                 }, "non-matching record found"),
            )

            for recordlist, title in records:
                _doParseRecords(recordlist, title)

        def test_odrecords_good(self):
            def _doParseRecords(recordlist, title):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                try:
                    service._parseComputersRecords(recordlist, "calendar.apple.com")
                except OpenDirectoryInitError, ex:
                    self.fail(msg="Record parse should not have failed: \"%s\" with error: %s" % (title, ex))

            records = (
                ({
                      ODRecordsParse.record_good[0]        : ODRecordsParse.record_good[1],
                 }, "single good plist"),
                ({
                      ODRecordsParse.record_good[0]        : ODRecordsParse.record_good[1],
                      ODRecordsParse.record_good_other[0]  : ODRecordsParse.record_good_other[1],
                 }, "multiple plists"),
            )

            for recordlist, title in records:
                _doParseRecords(recordlist, title)

        def test_odrecords_multiple(self):
            def _doParseRecords(recordlist, title, guid):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                service._parseComputersRecords(recordlist, "calendar.apple.com")
                gotGuid = service.servicetag.split(':', 1)[0]

                self.assertEquals(guid, gotGuid,
                                  "Got wrong guid, %s: Expected %s not %s" % (title, guid, gotGuid))

            records = (
                ({ODRecordsParse.record_good_other[0]           : ODRecordsParse.record_good_other[1],
                  ODRecordsParse.record_good_duplicate[0]       : ODRecordsParse.record_good_duplicate[1],
                  ODRecordsParse.record_good_local_duplicate[0] :
                      ODRecordsParse.record_good_local_duplicate[1]},
                 "Remote Record Preferred", "GUID2"),
                ({ODRecordsParse.record_good[0]                 : ODRecordsParse.record_good[1],
                  ODRecordsParse.record_good_local_duplicate[0] :
                      ODRecordsParse.record_good_local_duplicate[1]},
                 "Local OD Preferred", "GUID1"),
                ({ODRecordsParse.record_good_local_duplicate[0] :
                      ODRecordsParse.record_good_local_duplicate[1]},
                 "Local Node Preferred", "GUID3"),
            )

            for recordlist, title, guid in records:
                _doParseRecords(recordlist, title, guid)

    class ODResourceInfoParse (twisted.trial.unittest.TestCase):

        plist_good_false = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <dict>
        <key>AutoAcceptsInvitation</key>
        <false/>
        <key>Label</key>
        <string>Location</string>
        <key>CalendaringDelegate</key>
        <string>1234-GUID-5678</string>
    </dict>
</dict>
</plist>
"""

        plist_good_true = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <dict>
        <key>AutoAcceptsInvitation</key>
        <true/>
        <key>Label</key>
        <string>Location</string>
        <key>CalendaringDelegate</key>
        <string></string>
    </dict>
</dict>
</plist>
"""

        plist_good_missing = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <dict>
        <key>Label</key>
        <string>Location</string>
    </dict>
</dict>
</plist>
"""

        plist_bad = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.WhitePagesFramework</key>
    <string>bogus</string>
</dict>
</plist>
"""

        plist_wrong = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.YellowPagesFramework</key>
    <dict>
        <key>AutoAcceptsInvitation</key>
        <true/>
        <key>Label</key>
        <string>Location</string>
        <key>CalendaringDelegate</key>
        <string>1234-GUID-5678</string>
    </dict>
</dict>
</plist>
"""

        test_bool = (
            (plist_good_false, False, "1234-GUID-5678"),
            (plist_good_true, True, ""),
            (plist_good_missing, False, None),
            (plist_wrong, False, None),
        )

        test_exception = (
            (plist_bad, AttributeError),
        )

        def test_plists(self):
            service = OpenDirectoryService(node="/Search", dosetup=False)
            
            for item in ODResourceInfoParse.test_bool:
                self.assertEqual(service._parseResourceInfo(item[0])[0], item[1])
                self.assertEqual(service._parseResourceInfo(item[0])[1], item[2])
            
            for item in ODResourceInfoParse.test_exception:
                self.assertRaises(item[1], service._parseResourceInfo, item[0])
