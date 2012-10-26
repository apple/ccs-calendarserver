example.com.		  10800 IN SOA	ns.example.com. 	admin.example.com. (
                                                        2012090810 ; serial
                                                        3600       ; refresh (1 hour)
                                                        900        ; retry (15 minutes)
                                                        1209600    ; expire (2 weeks)
                                                        86400      ; minimum (1 day)
							)
									10800 IN NS		ns.example.com.
									10800 IN A		127.0.0.1
ns.example.com.						10800 IN A		127.0.0.1

_caldavs._tcp.example.com.			10800 IN SRV	0	0	8443	example.com.
_ischedules._tcp.example.com.		10800 IN SRV	0	0	8443	example.com.

_ischedule._domainkey.example.com.	10800 IN TXT	"v=DKIM1; p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDjUfDqd8ICAL0dyq2KdjKN6LS8O/Y4yMxOxgATqtSIMi7baKXEs1w5Wj9efOC2nU+aqyhP2/J6AzfFJfSB+GV5gcIT+LAC4btJKPGjPUyXcQFJV4a73y0jIgCTBzWxdaP6qD9P9rzYlvMPcdrrKiKoAOtI3JZqAAdZudOmGlc4QQIDAQAB"
_revoked._domainkey.example.com.	10800 IN TXT	"v=DKIM1; p="

_domainkey._tcp.example.com.		10800 IN SRV	0	0	8443	key.example.com.
_domainkey._tcp.www.example.com.	10800 IN SRV	0	0	80		key.example.com.
