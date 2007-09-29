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

        plist_duplicate = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>ReplicaName</key>
        <string>Master</string>

        <key>com.apple.od.role</key>
        <string>master</string>

        <key>com.apple.macosxserver.virtualhosts</key>
        <dict>
            <key>F4088107-51FD-4DE5-904D-C20AD9C6C893</key>
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

            <key>1C8C34AC-3D9E-403C-8A33-FBC303F3840E</key>
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

        def test_plist_errors(self):
            def _doParse(plist, title):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                if service._parseServiceInfo("calendar.apple.com", "recordit", {
                'dsAttrTypeNative:apple-serviceinfo'  : plist,
                dsattributes.kDS1AttrGeneratedUID:      "GUIDIFY",
                dsattributes.kDSNAttrMetaNodeLocation:  "/LDAPv3/127.0.0.1"}) and service.servicetags:
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
            if not service._parseServiceInfo("calendar.apple.com", "recordit", {
                'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_good,
                dsattributes.kDS1AttrGeneratedUID:      "GUIDIFY",
                dsattributes.kDSNAttrMetaNodeLocation:  "/LDAPv3/127.0.0.1"}):
                self.fail(msg="Plist parse should not have failed")
            else:
                # Verify that we extracted the proper items
                self.assertEqual(service.servicetags.pop(), "GUIDIFY:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar")

        def test_expandcuaddrs(self):
            def _doTest(recordName, record, result, title):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                if not service._parseServiceInfo("calendar.apple.com", recordName, {
                'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_good,
                dsattributes.kDS1AttrGeneratedUID:      "GUIDIFY",
                dsattributes.kDSNAttrMetaNodeLocation:  "/LDAPv3/127.0.0.1"}):
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

        record_localod_good = ("computer1.apple.com", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID1",
            dsattributes.kDSNAttrRecordName       : "computer1.apple.com",
            'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_good,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
        })
        record_localod_good_other = ("computer2.apple.com", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID1",
            dsattributes.kDSNAttrRecordName       : "computer2.apple.com",
            'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_good_other,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
        })
        record_localod_duplicate = ("computer1", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID1_bad",
            dsattributes.kDSNAttrRecordName       : "computer1",
            'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_duplicate,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/127.0.0.1",
        })
        record_remoteod_good = ("computer3.apple.com", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID2",
            dsattributes.kDSNAttrRecordName       : "computer3.apple.com",
            'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_good,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/directory.apple.com",
        })
        record_remoteod_duplicate = ("computer3", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID2",
            dsattributes.kDSNAttrRecordName       : "computer3",
            'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_duplicate,
            dsattributes.kDSNAttrMetaNodeLocation : "/LDAPv3/directory.apple.com",
        })
        record_default_good = ("computer4.apple.com", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID3",
            dsattributes.kDSNAttrRecordName       : "computer4.apple.com",
            'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_good,
            dsattributes.kDSNAttrMetaNodeLocation : "/Local/Default",
        })
        record_default_duplicate = ("computer4", {
            dsattributes.kDS1AttrGeneratedUID     : "GUID3",
            dsattributes.kDSNAttrRecordName       : "computer4",
            'dsAttrTypeNative:apple-serviceinfo'  : PlistParse.plist_duplicate,
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
                ((), "no records found"),
                ((
                      (ODRecordsParse.record_localod_good_other[0], ODRecordsParse.record_localod_good_other[1]),
                 ), "non-matching record found"),
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
                ((
                      (ODRecordsParse.record_localod_good[0],       ODRecordsParse.record_localod_good[1]),
                 ), "single good plist"),
                ((
                      (ODRecordsParse.record_localod_good[0],       ODRecordsParse.record_localod_good[1]),
                      (ODRecordsParse.record_localod_good_other[0], ODRecordsParse.record_localod_good_other[1]),
                 ), "multiple plists"),
            )

            for recordlist, title in records:
                _doParseRecords(recordlist, title)

        def test_odrecords_multiple(self):
            def _doParseRecords(recordlist, title, tags):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                service._parseComputersRecords(recordlist, "calendar.apple.com")

                self.assertEquals(service.servicetags, set(tags),
                                  "Got wrong service tags: %s and %s" % (service.servicetags, set(tags),))

            records = (
                (((ODRecordsParse.record_remoteod_good[0],  ODRecordsParse.record_remoteod_good[1]),
                  (ODRecordsParse.record_localod_good[0],   ODRecordsParse.record_localod_good[1]),
                  (ODRecordsParse.record_default_good[0],   ODRecordsParse.record_default_good[1])),
                 "Three records",
                 ("GUID2:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",
                  "GUID1:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",
                  "GUID3:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar")),
                (((ODRecordsParse.record_localod_good[0],   ODRecordsParse.record_localod_good[1]),
                  (ODRecordsParse.record_default_good[0],   ODRecordsParse.record_default_good[1])),
                 "Two records",
                 ("GUID1:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",
                  "GUID3:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar")),
                (((ODRecordsParse.record_default_good[0],   ODRecordsParse.record_default_good[1]),),
                 "One record",
                 ("GUID3:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",)),
            )

            for recordlist, title, tags in records:
                _doParseRecords(recordlist, title, tags)

        def test_odrecords_duplicates(self):
            def _doParseRecords(recordlist, title, items, tags):
                service = OpenDirectoryService(node="/Search", dosetup=False)
                service._parseComputersRecords(recordlist, "calendar.apple.com")
                self.assertEquals(service.servicetags, set(tags))

            records = (
                (((ODRecordsParse.record_remoteod_good[0],       ODRecordsParse.record_remoteod_good[1]),
                  (ODRecordsParse.record_remoteod_duplicate[0],  ODRecordsParse.record_remoteod_duplicate[1]),
                  (ODRecordsParse.record_localod_good[0],        ODRecordsParse.record_localod_good[1]),
                  (ODRecordsParse.record_default_good[0],        ODRecordsParse.record_default_good[1])),
                 "Remote Record Duplicated", ("computer3.apple.com", "computer3",),
                 ("GUID2:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",
                  "GUID2:1C8C34AC-3D9E-403C-8A33-FBC303F3840E:calendar",
                  "GUID1:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",
                  "GUID3:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar")),
                (((ODRecordsParse.record_localod_good[0],        ODRecordsParse.record_localod_good[1]),
                  (ODRecordsParse.record_localod_duplicate[0],   ODRecordsParse.record_localod_duplicate[1]),
                  (ODRecordsParse.record_default_good[0],        ODRecordsParse.record_default_good[1])),
                 "Local OD Duplicated", ("computer1.apple.com", "computer1",),
                 ("GUID1:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",
                  "GUID1_bad:1C8C34AC-3D9E-403C-8A33-FBC303F3840E:calendar",
                  "GUID3:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar")),
                (((ODRecordsParse.record_default_good[0],        ODRecordsParse.record_default_good[1]),
                  (ODRecordsParse.record_default_duplicate[0],   ODRecordsParse.record_default_duplicate[1])),
                 "Local Node Duplicated", ("computer4.apple.com", "computer4",),
                 ("GUID3:C18C34AC-3D9E-403C-8A33-BFC303F3840E:calendar",
                  "GUID3:1C8C34AC-3D9E-403C-8A33-FBC303F3840E:calendar")),
            )

            for recordlist, title, items, tags in records:
                _doParseRecords(recordlist, title, items, tags)

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
