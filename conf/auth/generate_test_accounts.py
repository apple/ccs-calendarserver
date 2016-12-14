#!/usr/bin/env python

# Generates test directory records in accounts-test.xml, resources-test.xml,
# augments-test.xml and proxies-test.xml (overwriting them if they exist in
# the current directory).

prefix = """<?xml version="1.0" encoding="utf-8"?>

<!--
Copyright (c) 2006-2016 Apple Inc. All rights reserved.

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
USERGUIDS = "10000000-0000-0000-0000-000000000{ctr:03d}"
GROUPGUIDS = "20000000-0000-0000-0000-000000000{ctr:03d}"
LOCATIONGUIDS = "30000000-0000-0000-0000-000000000{ctr:03d}"
RESOURCEGUIDS = "40000000-0000-0000-0000-000000000{ctr:03d}"
PUBLICGUIDS = "50000000-0000-0000-0000-000000000{ctr:03d}"
PUSERGUIDS = "60000000-0000-0000-0000-000000000{ctr:03d}"
S2SUSERGUIDS = "70000000-0000-0000-0000-000000000{ctr:03d}"


# Generic accounts
def accounts(out, record_type, name, guid, count, domain="example.com"):
    for i in xrange(1, count + 1):
        name_ctr = "{name}{ctr:02d}".format(name=name, ctr=i)
        fullname_ctr = "{name} {ctr:02d}".format(name=name.capitalize(), ctr=i)
        guid_ctr = guid.format(ctr=i)
        out.write("""<record type="{rtype}">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>{name}</short-name>
    <password>{name}</password>
    <full-name>{fullname}</full-name>
    <email>{name}@{domain}</email>
</record>
""".format(rtype=record_type, guid=guid_ctr, name=name_ctr, fullname=fullname_ctr, domain=domain))


def resource_accounts(out, record_type, name, guid, count):
    for i in xrange(1, count + 1):
        name_ctr = "{name}{ctr:02d}".format(name=name, ctr=i)
        fullname_ctr = "{name} {ctr:02d}".format(name=name.capitalize(), ctr=i)
        guid_ctr = guid.format(ctr=i)
        out.write("""<record type="{rtype}">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>{name}</short-name>
    <full-name>{fullname}</full-name>
</record>
""".format(rtype=record_type, guid=guid_ctr, name=name_ctr, fullname=fullname_ctr))


def group_accounts(out, count, extras=False):
    members = {
        GROUPGUIDS.format(ctr=1): (USERGUIDS.format(ctr=1),),
        GROUPGUIDS.format(ctr=2): (USERGUIDS.format(ctr=6), USERGUIDS.format(ctr=7)),
        GROUPGUIDS.format(ctr=3): (USERGUIDS.format(ctr=8), USERGUIDS.format(ctr=9)),
        GROUPGUIDS.format(ctr=4): (GROUPGUIDS.format(ctr=2), GROUPGUIDS.format(ctr=3), USERGUIDS.format(ctr=10)),
        GROUPGUIDS.format(ctr=5): (GROUPGUIDS.format(ctr=6), USERGUIDS.format(ctr=20)),
        GROUPGUIDS.format(ctr=6): (USERGUIDS.format(ctr=21),),
        GROUPGUIDS.format(ctr=7): (USERGUIDS.format(ctr=22), USERGUIDS.format(ctr=23), USERGUIDS.format(ctr=24)),
    }

    if extras:
        members.update({
            GROUPGUIDS.format(ctr=8): (
                USERGUIDS.format(ctr=1),
                USERGUIDS.format(ctr=2),
                USERGUIDS.format(ctr=3),
                USERGUIDS.format(ctr=4),
                USERGUIDS.format(ctr=5),
            ),
            GROUPGUIDS.format(ctr=9): (
                USERGUIDS.format(ctr=1),
                USERGUIDS.format(ctr=2),
                USERGUIDS.format(ctr=3),
                USERGUIDS.format(ctr=4),
                USERGUIDS.format(ctr=5),
                USERGUIDS.format(ctr=6),
                USERGUIDS.format(ctr=7),
                USERGUIDS.format(ctr=8),
                USERGUIDS.format(ctr=9),
                USERGUIDS.format(ctr=10),
                USERGUIDS.format(ctr=11),
                USERGUIDS.format(ctr=12),
                USERGUIDS.format(ctr=13),
                USERGUIDS.format(ctr=14),
                USERGUIDS.format(ctr=15),
                USERGUIDS.format(ctr=16),
                USERGUIDS.format(ctr=17),
                USERGUIDS.format(ctr=18),
                USERGUIDS.format(ctr=19),
                USERGUIDS.format(ctr=20),
                USERGUIDS.format(ctr=21),
                USERGUIDS.format(ctr=22),
                USERGUIDS.format(ctr=23),
                USERGUIDS.format(ctr=24),
                USERGUIDS.format(ctr=25),
                USERGUIDS.format(ctr=26),
                USERGUIDS.format(ctr=27),
                USERGUIDS.format(ctr=28),
                USERGUIDS.format(ctr=29),
                USERGUIDS.format(ctr=30),
                USERGUIDS.format(ctr=31),
                USERGUIDS.format(ctr=32),
                USERGUIDS.format(ctr=33),
                USERGUIDS.format(ctr=34),
                USERGUIDS.format(ctr=35),
                USERGUIDS.format(ctr=36),
                USERGUIDS.format(ctr=37),
                USERGUIDS.format(ctr=38),
                USERGUIDS.format(ctr=39),
                USERGUIDS.format(ctr=40),
                USERGUIDS.format(ctr=41),
                USERGUIDS.format(ctr=42),
                USERGUIDS.format(ctr=43),
                USERGUIDS.format(ctr=44),
                USERGUIDS.format(ctr=45),
                USERGUIDS.format(ctr=46),
                USERGUIDS.format(ctr=47),
                USERGUIDS.format(ctr=48),
                USERGUIDS.format(ctr=49),
                USERGUIDS.format(ctr=50),
                USERGUIDS.format(ctr=51),
                USERGUIDS.format(ctr=52),
                USERGUIDS.format(ctr=53),
                USERGUIDS.format(ctr=54),
                USERGUIDS.format(ctr=55),
                USERGUIDS.format(ctr=56),
                USERGUIDS.format(ctr=57),
                USERGUIDS.format(ctr=58),
                USERGUIDS.format(ctr=59),
                USERGUIDS.format(ctr=60),
                USERGUIDS.format(ctr=61),
                USERGUIDS.format(ctr=62),
                USERGUIDS.format(ctr=63),
                USERGUIDS.format(ctr=64),
                USERGUIDS.format(ctr=65),
                USERGUIDS.format(ctr=66),
                USERGUIDS.format(ctr=67),
                USERGUIDS.format(ctr=68),
                USERGUIDS.format(ctr=69),
                USERGUIDS.format(ctr=70),
                USERGUIDS.format(ctr=71),
                USERGUIDS.format(ctr=72),
                USERGUIDS.format(ctr=73),
                USERGUIDS.format(ctr=74),
                USERGUIDS.format(ctr=75),
                USERGUIDS.format(ctr=76),
                USERGUIDS.format(ctr=77),
                USERGUIDS.format(ctr=78),
                USERGUIDS.format(ctr=79),
                USERGUIDS.format(ctr=80),
                USERGUIDS.format(ctr=81),
                USERGUIDS.format(ctr=82),
                USERGUIDS.format(ctr=83),
                USERGUIDS.format(ctr=84),
                USERGUIDS.format(ctr=85),
                USERGUIDS.format(ctr=86),
                USERGUIDS.format(ctr=87),
                USERGUIDS.format(ctr=88),
                USERGUIDS.format(ctr=89),
                USERGUIDS.format(ctr=90),
                USERGUIDS.format(ctr=91),
                USERGUIDS.format(ctr=92),
                USERGUIDS.format(ctr=93),
                USERGUIDS.format(ctr=94),
                USERGUIDS.format(ctr=95),
                USERGUIDS.format(ctr=96),
                USERGUIDS.format(ctr=97),
                USERGUIDS.format(ctr=98),
                USERGUIDS.format(ctr=99),
                USERGUIDS.format(ctr=100),
            ),
            GROUPGUIDS.format(ctr=10): (
                USERGUIDS.format(ctr=1),
                USERGUIDS.format(ctr=2),
                USERGUIDS.format(ctr=3),
                USERGUIDS.format(ctr=4),
                USERGUIDS.format(ctr=5),
                USERGUIDS.format(ctr=6),
                USERGUIDS.format(ctr=7),
                USERGUIDS.format(ctr=8),
                USERGUIDS.format(ctr=9),
                USERGUIDS.format(ctr=10),
                USERGUIDS.format(ctr=11),
                USERGUIDS.format(ctr=12),
                USERGUIDS.format(ctr=13),
                USERGUIDS.format(ctr=14),
                USERGUIDS.format(ctr=15),
                USERGUIDS.format(ctr=16),
                USERGUIDS.format(ctr=17),
                USERGUIDS.format(ctr=18),
                USERGUIDS.format(ctr=19),
                USERGUIDS.format(ctr=20),
                USERGUIDS.format(ctr=21),
                USERGUIDS.format(ctr=22),
                USERGUIDS.format(ctr=23),
                USERGUIDS.format(ctr=24),
                USERGUIDS.format(ctr=25),
                USERGUIDS.format(ctr=26),
                USERGUIDS.format(ctr=27),
                USERGUIDS.format(ctr=28),
                USERGUIDS.format(ctr=29),
                USERGUIDS.format(ctr=30),
                USERGUIDS.format(ctr=31),
                USERGUIDS.format(ctr=32),
                USERGUIDS.format(ctr=33),
                USERGUIDS.format(ctr=34),
                USERGUIDS.format(ctr=35),
                USERGUIDS.format(ctr=36),
                USERGUIDS.format(ctr=37),
                USERGUIDS.format(ctr=38),
                USERGUIDS.format(ctr=39),
                USERGUIDS.format(ctr=40),
                USERGUIDS.format(ctr=41),
                USERGUIDS.format(ctr=42),
                USERGUIDS.format(ctr=43),
                USERGUIDS.format(ctr=44),
                USERGUIDS.format(ctr=45),
                USERGUIDS.format(ctr=46),
                USERGUIDS.format(ctr=47),
                USERGUIDS.format(ctr=48),
                USERGUIDS.format(ctr=49),
                USERGUIDS.format(ctr=50),
                USERGUIDS.format(ctr=51),
                USERGUIDS.format(ctr=52),
                USERGUIDS.format(ctr=53),
                USERGUIDS.format(ctr=54),
                USERGUIDS.format(ctr=55),
                USERGUIDS.format(ctr=56),
                USERGUIDS.format(ctr=57),
                USERGUIDS.format(ctr=58),
                USERGUIDS.format(ctr=59),
                USERGUIDS.format(ctr=60),
                USERGUIDS.format(ctr=61),
                USERGUIDS.format(ctr=62),
                USERGUIDS.format(ctr=63),
                USERGUIDS.format(ctr=64),
                USERGUIDS.format(ctr=65),
                USERGUIDS.format(ctr=66),
                USERGUIDS.format(ctr=67),
                USERGUIDS.format(ctr=68),
                USERGUIDS.format(ctr=69),
                USERGUIDS.format(ctr=70),
                USERGUIDS.format(ctr=71),
                USERGUIDS.format(ctr=72),
                USERGUIDS.format(ctr=73),
                USERGUIDS.format(ctr=74),
                USERGUIDS.format(ctr=75),
                USERGUIDS.format(ctr=76),
                USERGUIDS.format(ctr=77),
                USERGUIDS.format(ctr=78),
                USERGUIDS.format(ctr=79),
                USERGUIDS.format(ctr=80),
                USERGUIDS.format(ctr=81),
                USERGUIDS.format(ctr=82),
                USERGUIDS.format(ctr=83),
                USERGUIDS.format(ctr=84),
                USERGUIDS.format(ctr=85),
                USERGUIDS.format(ctr=86),
                USERGUIDS.format(ctr=87),
                USERGUIDS.format(ctr=88),
                USERGUIDS.format(ctr=89),
                USERGUIDS.format(ctr=90),
                USERGUIDS.format(ctr=91),
                USERGUIDS.format(ctr=92),
                USERGUIDS.format(ctr=93),
                USERGUIDS.format(ctr=94),
                USERGUIDS.format(ctr=95),
                USERGUIDS.format(ctr=96),
                USERGUIDS.format(ctr=97),
                USERGUIDS.format(ctr=98),
                USERGUIDS.format(ctr=99),
                USERGUIDS.format(ctr=100),
                USERGUIDS.format(ctr=101),
                USERGUIDS.format(ctr=102),
                USERGUIDS.format(ctr=103),
                USERGUIDS.format(ctr=104),
                USERGUIDS.format(ctr=105),
                USERGUIDS.format(ctr=106),
                USERGUIDS.format(ctr=107),
                USERGUIDS.format(ctr=108),
                USERGUIDS.format(ctr=109),
                USERGUIDS.format(ctr=110),
                USERGUIDS.format(ctr=111),
                USERGUIDS.format(ctr=112),
                USERGUIDS.format(ctr=113),
                USERGUIDS.format(ctr=114),
                USERGUIDS.format(ctr=115),
                USERGUIDS.format(ctr=116),
                USERGUIDS.format(ctr=117),
                USERGUIDS.format(ctr=118),
                USERGUIDS.format(ctr=119),
                USERGUIDS.format(ctr=120),
                USERGUIDS.format(ctr=121),
                USERGUIDS.format(ctr=122),
                USERGUIDS.format(ctr=123),
                USERGUIDS.format(ctr=124),
                USERGUIDS.format(ctr=125),
                USERGUIDS.format(ctr=126),
                USERGUIDS.format(ctr=127),
                USERGUIDS.format(ctr=128),
                USERGUIDS.format(ctr=129),
                USERGUIDS.format(ctr=130),
                USERGUIDS.format(ctr=131),
                USERGUIDS.format(ctr=132),
                USERGUIDS.format(ctr=133),
                USERGUIDS.format(ctr=134),
                USERGUIDS.format(ctr=135),
                USERGUIDS.format(ctr=136),
                USERGUIDS.format(ctr=137),
                USERGUIDS.format(ctr=138),
                USERGUIDS.format(ctr=139),
                USERGUIDS.format(ctr=140),
                USERGUIDS.format(ctr=141),
                USERGUIDS.format(ctr=142),
                USERGUIDS.format(ctr=143),
                USERGUIDS.format(ctr=144),
                USERGUIDS.format(ctr=145),
                USERGUIDS.format(ctr=146),
                USERGUIDS.format(ctr=147),
                USERGUIDS.format(ctr=148),
                USERGUIDS.format(ctr=149),
                USERGUIDS.format(ctr=150),
                USERGUIDS.format(ctr=151),
                USERGUIDS.format(ctr=152),
                USERGUIDS.format(ctr=153),
                USERGUIDS.format(ctr=154),
                USERGUIDS.format(ctr=155),
                USERGUIDS.format(ctr=156),
                USERGUIDS.format(ctr=157),
                USERGUIDS.format(ctr=158),
                USERGUIDS.format(ctr=159),
                USERGUIDS.format(ctr=160),
                USERGUIDS.format(ctr=161),
                USERGUIDS.format(ctr=162),
                USERGUIDS.format(ctr=163),
                USERGUIDS.format(ctr=164),
                USERGUIDS.format(ctr=165),
                USERGUIDS.format(ctr=166),
                USERGUIDS.format(ctr=167),
                USERGUIDS.format(ctr=168),
                USERGUIDS.format(ctr=169),
                USERGUIDS.format(ctr=170),
                USERGUIDS.format(ctr=171),
                USERGUIDS.format(ctr=172),
                USERGUIDS.format(ctr=173),
                USERGUIDS.format(ctr=174),
                USERGUIDS.format(ctr=175),
                USERGUIDS.format(ctr=176),
                USERGUIDS.format(ctr=177),
                USERGUIDS.format(ctr=178),
                USERGUIDS.format(ctr=179),
                USERGUIDS.format(ctr=180),
                USERGUIDS.format(ctr=181),
                USERGUIDS.format(ctr=182),
                USERGUIDS.format(ctr=183),
                USERGUIDS.format(ctr=184),
                USERGUIDS.format(ctr=185),
                USERGUIDS.format(ctr=186),
                USERGUIDS.format(ctr=187),
                USERGUIDS.format(ctr=188),
                USERGUIDS.format(ctr=189),
                USERGUIDS.format(ctr=190),
                USERGUIDS.format(ctr=191),
                USERGUIDS.format(ctr=192),
                USERGUIDS.format(ctr=193),
                USERGUIDS.format(ctr=194),
                USERGUIDS.format(ctr=195),
                USERGUIDS.format(ctr=196),
                USERGUIDS.format(ctr=197),
                USERGUIDS.format(ctr=198),
                USERGUIDS.format(ctr=199),
                USERGUIDS.format(ctr=200),
                USERGUIDS.format(ctr=201),
                USERGUIDS.format(ctr=202),
                USERGUIDS.format(ctr=203),
                USERGUIDS.format(ctr=204),
                USERGUIDS.format(ctr=205),
                USERGUIDS.format(ctr=206),
                USERGUIDS.format(ctr=207),
                USERGUIDS.format(ctr=208),
                USERGUIDS.format(ctr=209),
                USERGUIDS.format(ctr=210),
                USERGUIDS.format(ctr=211),
                USERGUIDS.format(ctr=212),
                USERGUIDS.format(ctr=213),
                USERGUIDS.format(ctr=214),
                USERGUIDS.format(ctr=215),
                USERGUIDS.format(ctr=216),
                USERGUIDS.format(ctr=217),
                USERGUIDS.format(ctr=218),
                USERGUIDS.format(ctr=219),
                USERGUIDS.format(ctr=220),
                USERGUIDS.format(ctr=221),
                USERGUIDS.format(ctr=222),
                USERGUIDS.format(ctr=223),
                USERGUIDS.format(ctr=224),
                USERGUIDS.format(ctr=225),
                USERGUIDS.format(ctr=226),
                USERGUIDS.format(ctr=227),
                USERGUIDS.format(ctr=228),
                USERGUIDS.format(ctr=229),
                USERGUIDS.format(ctr=230),
                USERGUIDS.format(ctr=231),
                USERGUIDS.format(ctr=232),
                USERGUIDS.format(ctr=233),
                USERGUIDS.format(ctr=234),
                USERGUIDS.format(ctr=235),
                USERGUIDS.format(ctr=236),
                USERGUIDS.format(ctr=237),
                USERGUIDS.format(ctr=238),
                USERGUIDS.format(ctr=239),
                USERGUIDS.format(ctr=240),
                USERGUIDS.format(ctr=241),
                USERGUIDS.format(ctr=242),
                USERGUIDS.format(ctr=243),
                USERGUIDS.format(ctr=244),
                USERGUIDS.format(ctr=245),
                USERGUIDS.format(ctr=246),
                USERGUIDS.format(ctr=247),
                USERGUIDS.format(ctr=248),
                USERGUIDS.format(ctr=249),
                USERGUIDS.format(ctr=250),
                USERGUIDS.format(ctr=251),
                USERGUIDS.format(ctr=252),
                USERGUIDS.format(ctr=253),
                USERGUIDS.format(ctr=254),
                USERGUIDS.format(ctr=255),
                USERGUIDS.format(ctr=256),
                USERGUIDS.format(ctr=257),
                USERGUIDS.format(ctr=258),
                USERGUIDS.format(ctr=259),
                USERGUIDS.format(ctr=260),
                USERGUIDS.format(ctr=261),
                USERGUIDS.format(ctr=262),
                USERGUIDS.format(ctr=263),
                USERGUIDS.format(ctr=264),
                USERGUIDS.format(ctr=265),
                USERGUIDS.format(ctr=266),
                USERGUIDS.format(ctr=267),
                USERGUIDS.format(ctr=268),
                USERGUIDS.format(ctr=269),
                USERGUIDS.format(ctr=270),
                USERGUIDS.format(ctr=271),
                USERGUIDS.format(ctr=272),
                USERGUIDS.format(ctr=273),
                USERGUIDS.format(ctr=274),
                USERGUIDS.format(ctr=275),
                USERGUIDS.format(ctr=276),
                USERGUIDS.format(ctr=277),
                USERGUIDS.format(ctr=278),
                USERGUIDS.format(ctr=279),
                USERGUIDS.format(ctr=280),
                USERGUIDS.format(ctr=281),
                USERGUIDS.format(ctr=282),
                USERGUIDS.format(ctr=283),
                USERGUIDS.format(ctr=284),
                USERGUIDS.format(ctr=285),
                USERGUIDS.format(ctr=286),
                USERGUIDS.format(ctr=287),
                USERGUIDS.format(ctr=288),
                USERGUIDS.format(ctr=289),
                USERGUIDS.format(ctr=290),
                USERGUIDS.format(ctr=291),
                USERGUIDS.format(ctr=292),
                USERGUIDS.format(ctr=293),
                USERGUIDS.format(ctr=294),
                USERGUIDS.format(ctr=295),
                USERGUIDS.format(ctr=296),
                USERGUIDS.format(ctr=297),
                USERGUIDS.format(ctr=298),
                USERGUIDS.format(ctr=299),
                USERGUIDS.format(ctr=300),
                USERGUIDS.format(ctr=301),
                USERGUIDS.format(ctr=302),
                USERGUIDS.format(ctr=303),
                USERGUIDS.format(ctr=304),
                USERGUIDS.format(ctr=305),
                USERGUIDS.format(ctr=306),
                USERGUIDS.format(ctr=307),
                USERGUIDS.format(ctr=308),
                USERGUIDS.format(ctr=309),
                USERGUIDS.format(ctr=310),
                USERGUIDS.format(ctr=311),
                USERGUIDS.format(ctr=312),
                USERGUIDS.format(ctr=313),
                USERGUIDS.format(ctr=314),
                USERGUIDS.format(ctr=315),
                USERGUIDS.format(ctr=316),
                USERGUIDS.format(ctr=317),
                USERGUIDS.format(ctr=318),
                USERGUIDS.format(ctr=319),
                USERGUIDS.format(ctr=320),
                USERGUIDS.format(ctr=321),
                USERGUIDS.format(ctr=322),
                USERGUIDS.format(ctr=323),
                USERGUIDS.format(ctr=324),
                USERGUIDS.format(ctr=325),
                USERGUIDS.format(ctr=326),
                USERGUIDS.format(ctr=327),
                USERGUIDS.format(ctr=328),
                USERGUIDS.format(ctr=329),
                USERGUIDS.format(ctr=330),
                USERGUIDS.format(ctr=331),
                USERGUIDS.format(ctr=332),
                USERGUIDS.format(ctr=333),
                USERGUIDS.format(ctr=334),
                USERGUIDS.format(ctr=335),
                USERGUIDS.format(ctr=336),
                USERGUIDS.format(ctr=337),
                USERGUIDS.format(ctr=338),
                USERGUIDS.format(ctr=339),
                USERGUIDS.format(ctr=340),
                USERGUIDS.format(ctr=341),
                USERGUIDS.format(ctr=342),
                USERGUIDS.format(ctr=343),
                USERGUIDS.format(ctr=344),
                USERGUIDS.format(ctr=345),
                USERGUIDS.format(ctr=346),
                USERGUIDS.format(ctr=347),
                USERGUIDS.format(ctr=348),
                USERGUIDS.format(ctr=349),
                USERGUIDS.format(ctr=350),
                USERGUIDS.format(ctr=351),
                USERGUIDS.format(ctr=352),
                USERGUIDS.format(ctr=353),
                USERGUIDS.format(ctr=354),
                USERGUIDS.format(ctr=355),
                USERGUIDS.format(ctr=356),
                USERGUIDS.format(ctr=357),
                USERGUIDS.format(ctr=358),
                USERGUIDS.format(ctr=359),
                USERGUIDS.format(ctr=360),
                USERGUIDS.format(ctr=361),
                USERGUIDS.format(ctr=362),
                USERGUIDS.format(ctr=363),
                USERGUIDS.format(ctr=364),
                USERGUIDS.format(ctr=365),
                USERGUIDS.format(ctr=366),
                USERGUIDS.format(ctr=367),
                USERGUIDS.format(ctr=368),
                USERGUIDS.format(ctr=369),
                USERGUIDS.format(ctr=370),
                USERGUIDS.format(ctr=371),
                USERGUIDS.format(ctr=372),
                USERGUIDS.format(ctr=373),
                USERGUIDS.format(ctr=374),
                USERGUIDS.format(ctr=375),
                USERGUIDS.format(ctr=376),
                USERGUIDS.format(ctr=377),
                USERGUIDS.format(ctr=378),
                USERGUIDS.format(ctr=379),
                USERGUIDS.format(ctr=380),
                USERGUIDS.format(ctr=381),
                USERGUIDS.format(ctr=382),
                USERGUIDS.format(ctr=383),
                USERGUIDS.format(ctr=384),
                USERGUIDS.format(ctr=385),
                USERGUIDS.format(ctr=386),
                USERGUIDS.format(ctr=387),
                USERGUIDS.format(ctr=388),
                USERGUIDS.format(ctr=389),
                USERGUIDS.format(ctr=390),
                USERGUIDS.format(ctr=391),
                USERGUIDS.format(ctr=392),
                USERGUIDS.format(ctr=393),
                USERGUIDS.format(ctr=394),
                USERGUIDS.format(ctr=395),
                USERGUIDS.format(ctr=396),
                USERGUIDS.format(ctr=397),
                USERGUIDS.format(ctr=398),
                USERGUIDS.format(ctr=399),
                USERGUIDS.format(ctr=400),
                USERGUIDS.format(ctr=401),
                USERGUIDS.format(ctr=402),
                USERGUIDS.format(ctr=403),
                USERGUIDS.format(ctr=404),
                USERGUIDS.format(ctr=405),
                USERGUIDS.format(ctr=406),
                USERGUIDS.format(ctr=407),
                USERGUIDS.format(ctr=408),
                USERGUIDS.format(ctr=409),
                USERGUIDS.format(ctr=410),
                USERGUIDS.format(ctr=411),
                USERGUIDS.format(ctr=412),
                USERGUIDS.format(ctr=413),
                USERGUIDS.format(ctr=414),
                USERGUIDS.format(ctr=415),
                USERGUIDS.format(ctr=416),
                USERGUIDS.format(ctr=417),
                USERGUIDS.format(ctr=418),
                USERGUIDS.format(ctr=419),
                USERGUIDS.format(ctr=420),
                USERGUIDS.format(ctr=421),
                USERGUIDS.format(ctr=422),
                USERGUIDS.format(ctr=423),
                USERGUIDS.format(ctr=424),
                USERGUIDS.format(ctr=425),
                USERGUIDS.format(ctr=426),
                USERGUIDS.format(ctr=427),
                USERGUIDS.format(ctr=428),
                USERGUIDS.format(ctr=429),
                USERGUIDS.format(ctr=430),
                USERGUIDS.format(ctr=431),
                USERGUIDS.format(ctr=432),
                USERGUIDS.format(ctr=433),
                USERGUIDS.format(ctr=434),
                USERGUIDS.format(ctr=435),
                USERGUIDS.format(ctr=436),
                USERGUIDS.format(ctr=437),
                USERGUIDS.format(ctr=438),
                USERGUIDS.format(ctr=439),
                USERGUIDS.format(ctr=440),
                USERGUIDS.format(ctr=441),
                USERGUIDS.format(ctr=442),
                USERGUIDS.format(ctr=443),
                USERGUIDS.format(ctr=444),
                USERGUIDS.format(ctr=445),
                USERGUIDS.format(ctr=446),
                USERGUIDS.format(ctr=447),
                USERGUIDS.format(ctr=448),
                USERGUIDS.format(ctr=449),
                USERGUIDS.format(ctr=450),
                USERGUIDS.format(ctr=451),
                USERGUIDS.format(ctr=452),
                USERGUIDS.format(ctr=453),
                USERGUIDS.format(ctr=454),
                USERGUIDS.format(ctr=455),
                USERGUIDS.format(ctr=456),
                USERGUIDS.format(ctr=457),
                USERGUIDS.format(ctr=458),
                USERGUIDS.format(ctr=459),
                USERGUIDS.format(ctr=460),
                USERGUIDS.format(ctr=461),
                USERGUIDS.format(ctr=462),
                USERGUIDS.format(ctr=463),
                USERGUIDS.format(ctr=464),
                USERGUIDS.format(ctr=465),
                USERGUIDS.format(ctr=466),
                USERGUIDS.format(ctr=467),
                USERGUIDS.format(ctr=468),
                USERGUIDS.format(ctr=469),
                USERGUIDS.format(ctr=470),
                USERGUIDS.format(ctr=471),
                USERGUIDS.format(ctr=472),
                USERGUIDS.format(ctr=473),
                USERGUIDS.format(ctr=474),
                USERGUIDS.format(ctr=475),
                USERGUIDS.format(ctr=476),
                USERGUIDS.format(ctr=477),
                USERGUIDS.format(ctr=478),
                USERGUIDS.format(ctr=479),
                USERGUIDS.format(ctr=480),
                USERGUIDS.format(ctr=481),
                USERGUIDS.format(ctr=482),
                USERGUIDS.format(ctr=483),
                USERGUIDS.format(ctr=484),
                USERGUIDS.format(ctr=485),
                USERGUIDS.format(ctr=486),
                USERGUIDS.format(ctr=487),
                USERGUIDS.format(ctr=488),
                USERGUIDS.format(ctr=489),
                USERGUIDS.format(ctr=490),
                USERGUIDS.format(ctr=491),
                USERGUIDS.format(ctr=492),
                USERGUIDS.format(ctr=493),
                USERGUIDS.format(ctr=494),
                USERGUIDS.format(ctr=495),
                USERGUIDS.format(ctr=496),
                USERGUIDS.format(ctr=497),
                USERGUIDS.format(ctr=498),
                USERGUIDS.format(ctr=499),
                USERGUIDS.format(ctr=500),
            ),
        })

    name = "group"
    for i in xrange(1, count + 1):

        memberElements = []
        groupUID = GROUPGUIDS.format(ctr=i)
        if groupUID in members:
            for uid in members[groupUID]:
                memberElements.append("<member-uid>{}</member-uid>".format(uid))
            memberString = "    " + "\n    ".join(memberElements) + "\n"
        else:
            memberString = ""

        name_ctr = "{name}{ctr:02d}".format(name=name, ctr=i)
        fullname_ctr = "{name} {ctr:02d}".format(name=name.capitalize(), ctr=i)
        guid_ctr = GROUPGUIDS.format(ctr=i)

        out.write("""<record type="group">
    <uid>{guid}</uid>
    <guid>{guid}</guid>
    <short-name>{name}</short-name>
    <full-name>{fullname}</full-name>
    <email>{name}@example.com</email>
{members}</record>
""".format(guid=guid_ctr, name=name_ctr, fullname=fullname_ctr, members=memberString))


def admin_user(out):
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


def admin_user_s2s(out):
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


def extra_users(out):
    for uid, fullName, guid in (
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


# accounts-test.xml
def accounts_test():
    out = file("accounts-test.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
    out.write('<directory realm="Test Realm">\n')

    admin_user(out)
    extra_users(out)

    # user01-101
    accounts(out, "user", "user", USERGUIDS, 101)

    # public01-10
    accounts(out, "user", "public", PUBLICGUIDS, 10)

    # group01-100
    group_accounts(out, 100)

    out.write("</directory>\n")
    out.close()


# accounts-test-large.xml
def accounts_test_large():
    out = file("accounts-test-large.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
    out.write('<directory realm="Test Realm">\n')

    admin_user(out)

    # user01-101
    accounts(out, "user", "user", USERGUIDS, 500)

    # public01-10
    accounts(out, "user", "public", PUBLICGUIDS, 10)

    # group01-100
    group_accounts(out, 100, extras=True)

    out.write("</directory>\n")
    out.close()


# accounts-test-pod.xml
def accounts_test_pod():
    out = file("accounts-test-pod.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
    out.write('<directory realm="Test Realm">\n')

    admin_user(out)

    # user01-100
    accounts(out, "user", "user", USERGUIDS, 100)

    # puser01-100
    accounts(out, "user", "puser", PUSERGUIDS, 100)

    # group01-100
    group_accounts(out, 100)

    out.write("</directory>\n")
    out.close()


# accounts-test-s2s.xml
def accounts_test_s2s():
    out = file("accounts-test-s2s.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
    out.write('<directory realm="Test Realm 2">\n')

    admin_user_s2s(out)

    # other01-100
    accounts(out, "user", "other", S2SUSERGUIDS, 100, domain="example.org")

    out.write("</directory>\n")
    out.close()


# resources-test.xml
def resource_test():
    out = file("resources-test.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
    out.write('<directory realm="Test Realm Resources">\n')

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

    resource_accounts(out, "location", "location", LOCATIONGUIDS, 100)
    resource_accounts(out, "resource", "resource", RESOURCEGUIDS, 100)

    out.write("</directory>\n")
    out.close()


# resources-test-pod.xml
def resource_test_pod():
    out = file("resources-test-pod.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
    out.write('<directory realm="Test Realm Resources">\n')

    resource_accounts(out, "location", "location", LOCATIONGUIDS, 5)

    out.write("</directory>\n")
    out.close()

# resources-test-s2s.xml


def resource_test_s2s():
    out = file("resources-test-s2s.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE accounts SYSTEM "accounts.dtd">\n\n')
    out.write('<directory realm="Test Realm Resources 2" />\n')
    out.close()


# augments-test.xml
def augments_test():
    out = file("augments-test.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE augments SYSTEM "augments.dtd">\n\n')
    out.write("<augments>\n")

    augments = (
        # resource05
        (RESOURCEGUIDS.format(ctr=5), (
            ("enable-calendar", "true"),
            ("enable-addressbook", "true"),
            ("auto-schedule-mode", "none"),
        )),
        # resource06
        (RESOURCEGUIDS.format(ctr=6), (
            ("enable-calendar", "true"),
            ("enable-addressbook", "true"),
            ("auto-schedule-mode", "accept-always"),
        )),
        # resource07
        (RESOURCEGUIDS.format(ctr=7), (
            ("enable-calendar", "true"),
            ("enable-addressbook", "true"),
            ("auto-schedule-mode", "decline-always"),
        )),
        # resource08
        (RESOURCEGUIDS.format(ctr=8), (
            ("enable-calendar", "true"),
            ("enable-addressbook", "true"),
            ("auto-schedule-mode", "accept-if-free"),
        )),
        # resource09
        (RESOURCEGUIDS.format(ctr=9), (
            ("enable-calendar", "true"),
            ("enable-addressbook", "true"),
            ("auto-schedule-mode", "decline-if-busy"),
        )),
        # resource10
        (RESOURCEGUIDS.format(ctr=10), (
            ("enable-calendar", "true"),
            ("enable-addressbook", "true"),
            ("auto-schedule-mode", "automatic"),
        )),
        # resource11
        (RESOURCEGUIDS.format(ctr=11), (
            ("enable-calendar", "true"),
            ("enable-addressbook", "true"),
            ("auto-schedule-mode", "decline-always"),
            ("auto-accept-group", GROUPGUIDS.format(ctr=1)),
        )),
    )

    out.write("""<record>
    <uid>Default</uid>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
</record>
""")

    out.write("""<record>
    <uid>Location-Default</uid>
    <enable-calendar>true</enable-calendar>
    <enable-addressbook>true</enable-addressbook>
    <auto-schedule-mode>automatic</auto-schedule-mode>
</record>
""")

    out.write("""<record>
    <uid>Resource-Default</uid>
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
def augments_test_pod():
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
""".format(guid=PUSERGUIDS.format(ctr=i)))

    out.write("</augments>\n")
    out.close()


# augments-test-s2s.xml
def augments_test_s2s():
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
def proxies_test():
    out = file("proxies-test.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE proxies SYSTEM "proxies.dtd">\n\n')
    out.write("<proxies>\n")

    proxies = (
        (RESOURCEGUIDS.format(ctr=1), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=2), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=3), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=4), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=5), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=6), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=7), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=8), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=9), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        (RESOURCEGUIDS.format(ctr=10), {
            "write-proxies": (USERGUIDS.format(ctr=1),),
            "read-proxies": (USERGUIDS.format(ctr=3),),
        }),
        ("delegatedroom", {
            "write-proxies": (GROUPGUIDS.format(ctr=5),),
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


# proxies-test-large.xml
def proxies_test_large():
    out = file("proxies-test-large.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE proxies SYSTEM "proxies.dtd">\n\n')
    out.write("<proxies>\n")

    proxies = (
        (USERGUIDS.format(ctr=9), {
            "write-proxies": (),
            "read-proxies": (GROUPGUIDS.format(ctr=9),),
        }),
        (USERGUIDS.format(ctr=10), {
            "write-proxies": (),
            "read-proxies": (GROUPGUIDS.format(ctr=10),),
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
def proxies_test_pod():
    out = file("proxies-test-pod.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE proxies SYSTEM "proxies.dtd">\n\n')
    out.write("<proxies />\n")
    out.close()


# proxies-test-s2s.xml
def proxies_test_s2s():
    out = file("proxies-test-s2s.xml", "w")
    out.write(prefix)
    out.write('<!DOCTYPE proxies SYSTEM "proxies.dtd">\n\n')
    out.write("<proxies />\n")
    out.close()

if __name__ == '__main__':
    accounts_test()
    accounts_test_large()
    accounts_test_pod()
    accounts_test_s2s()
    resource_test()
    resource_test_pod()
    resource_test_s2s()
    augments_test()
    augments_test_pod()
    augments_test_s2s()
    proxies_test()
    proxies_test_large()
    proxies_test_pod()
    proxies_test_s2s()
