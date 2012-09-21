##
# Copyright (c) 2005-2012 Apple Inc. All rights reserved.
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
##

from twistedcaldav.test.util import TestCase
from calendarserver.tools.changeip_calendar import updatePlist

class ChangeIPTestCase(TestCase):

    def test_updatePlist(self):

        plist = {
            "Authentication" : {
                "Wiki" : {
                    "Hostname" : "original_hostname",
                    "Other" : "should_be_untouched",
                },
            },
            "Untouched" : "dont_change_me",
            "BindAddresses" : [
                "10.1.1.1",
                "192.168.1.1",
                "original_hostname",
            ],
            "ServerHostName" : "",
            "Notifications" : {
                "Services" : {
                    "XMPPNotifier" : {
                        "Host" : "original_hostname",
                        "JID" : "com.apple.notificationuser@original_hostname",
                    },
                },
            },
            "Scheduling" : {
                "iMIP" : {
                    "Receiving" : {
                        "Server" : "original_hostname",
                    },
                    "Sending" : {
                        "Server" : "original_hostname",
                        "Address" : "user@original_hostname",
                    },
                },
            },
        }

        updatePlist(plist, "10.1.1.1", "10.1.1.2", "original_hostname",
            "new_hostname")

        self.assertEquals(plist,
            {
                "Authentication" : {
                    "Wiki" : {
                        "Hostname" : "new_hostname",
                        "Other" : "should_be_untouched",
                    },
                },
                "Untouched" : "dont_change_me",
                "BindAddresses" : [
                    "10.1.1.2",
                    "192.168.1.1",
                    "new_hostname",
                ],
                "ServerHostName" : "",
                "Notifications" : {
                    "Services" : {
                        "XMPPNotifier" : {
                            "Host" : "new_hostname",
                            "JID" : "com.apple.notificationuser@new_hostname",
                        },
                    },
                },
                "Scheduling" : {
                    "iMIP" : {
                        "Receiving" : {
                            "Server" : "new_hostname",
                        },
                        "Sending" : {
                            "Server" : "new_hostname",
                            "Address" : "user@new_hostname",
                        },
                    },
                },
            }
        )
