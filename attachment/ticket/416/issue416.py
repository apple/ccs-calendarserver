#!/usr/bin/python
import email.utils

mymail="""
Return-Path: <felix@derklecks.de>
Received: from compute2.internal (compute2.nyi.mail.srv.osa [10.202.2.42])
        by store71 (Cyrus git2.5.0+0-git-fastmail-6410) with LMTPA;
        Thu, 17 Feb 2011 12:54:26 -0500
X-Sieve: CMU Sieve 2.4
X-Spam-charsets: from='UTF-8', plain='UTF-8'
X-Resolved-to: felixcaldav+f70331ea-93eb-46c1-b2ef-242e497b245d@fastmail.fm
X-Delivered-to: felixcaldav+f70331ea-93eb-46c1-b2ef-242e497b245d@fastmail.fm
X-Mail-from: felix@derklecks.de
Received: from mx2.messagingengine.com ([10.202.2.201])
        by compute2.internal (LMTPProxy); Thu, 17 Feb 2011 12:54:26 -0500
Received: from smtprelay03.ispgateway.de (smtprelay03.ispgateway.de
        [80.67.29.7])
        by mx2.messagingengine.com (Postfix) with ESMTP id 67AD278017E
        for <felixcaldav+f70331ea-93eb-46c1-b2ef-242e497b245d@fastmail.fm>;
        Thu, 17 Feb 2011 12:54:25 -0500 (EST)
Received: from [92.201.66.28] (helo=[192.168.178.22])
        by smtprelay03.ispgateway.de with esmtpsa (TLSv1:AES256-SHA:256)
        (Exim 4.68) (envelope-from <felix@derklecks.de>) id 1Pq83b-00072a-OG
        for felixcaldav+f70331ea-93eb-46c1-b2ef-242e497b245d@fastmail.fm;
        Thu, 17 Feb 2011 18:54:23 +0100
Message-ID: <4D5D60CF.2070205@derklecks.de>
Date: Thu, 17 Feb 2011 18:54:23 +0100
From: =?UTF-8?B?RmVsaXggTcO2bGxlcg==?= <felix@derklecks.de>
User-Agent: Mozilla/5.0 (X11; U; Linux i686; en-US;
        rv:1.9.2.13) Gecko/20101209 Fedora/3.1.7-0.35.b3pre.fc14
        Lightning/1.0b3pre Thunderbird/3.1.7
MIME-Version: 1.0
To: felixcaldav+f70331ea-93eb-46c1-b2ef-242e497b245d@fastmail.fm
Subject: Re: Aktualisierung: New Event
References: <20110216211842.28004.188035797.1@km30208-01.keymachine.de>
In-Reply-To: <20110216211842.28004.188035797.1@km30208-01.keymachine.de>
Content-Type: text/plain; charset=UTF-8; format=flowed
Content-Transfer-Encoding: 7bit
X-Df-Sender: mail@felixmoeller.de
X-Truedomain-Domain: derklecks.de
X-Truedomain-SPF: No Record
X-Truedomain-DKIM: No Signature
X-Truedomain-ID: 9927CFA1343E43E5D5B7CB5289A8E9D5
X-Truedomain: Neutral

This is a reply

Am 16.02.2011 22:18, schrieb Felix Moeller:
> Aktualisierung
> [...]
>
"""

msg = email.message_from_string(mymail)
del msg["From"]
msg["From"] = "Felix Moeller <test@example.com>"
print msg
