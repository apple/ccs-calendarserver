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

EXTRA_GROUPS = False

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
for i in xrange(1, 501 if EXTRA_GROUPS else 101):
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

if EXTRA_GROUPS:
    members.update({
    GROUPGUIDS % 8: (
        USERGUIDS % 1,
        USERGUIDS % 2,
        USERGUIDS % 3,
        USERGUIDS % 4,
        USERGUIDS % 5,
    ),
    GROUPGUIDS % 9: (
        USERGUIDS % 1,
        USERGUIDS % 2,
        USERGUIDS % 3,
        USERGUIDS % 4,
        USERGUIDS % 5,
        USERGUIDS % 6,
        USERGUIDS % 7,
        USERGUIDS % 8,
        USERGUIDS % 9,
        USERGUIDS % 10,
        USERGUIDS % 11,
        USERGUIDS % 12,
        USERGUIDS % 13,
        USERGUIDS % 14,
        USERGUIDS % 15,
        USERGUIDS % 16,
        USERGUIDS % 17,
        USERGUIDS % 18,
        USERGUIDS % 19,
        USERGUIDS % 20,
        USERGUIDS % 21,
        USERGUIDS % 22,
        USERGUIDS % 23,
        USERGUIDS % 24,
        USERGUIDS % 25,
        USERGUIDS % 26,
        USERGUIDS % 27,
        USERGUIDS % 28,
        USERGUIDS % 29,
        USERGUIDS % 30,
        USERGUIDS % 31,
        USERGUIDS % 32,
        USERGUIDS % 33,
        USERGUIDS % 34,
        USERGUIDS % 35,
        USERGUIDS % 36,
        USERGUIDS % 37,
        USERGUIDS % 38,
        USERGUIDS % 39,
        USERGUIDS % 40,
        USERGUIDS % 41,
        USERGUIDS % 42,
        USERGUIDS % 43,
        USERGUIDS % 44,
        USERGUIDS % 45,
        USERGUIDS % 46,
        USERGUIDS % 47,
        USERGUIDS % 48,
        USERGUIDS % 49,
        USERGUIDS % 50,
        USERGUIDS % 51,
        USERGUIDS % 52,
        USERGUIDS % 53,
        USERGUIDS % 54,
        USERGUIDS % 55,
        USERGUIDS % 56,
        USERGUIDS % 57,
        USERGUIDS % 58,
        USERGUIDS % 59,
        USERGUIDS % 60,
        USERGUIDS % 61,
        USERGUIDS % 62,
        USERGUIDS % 63,
        USERGUIDS % 64,
        USERGUIDS % 65,
        USERGUIDS % 66,
        USERGUIDS % 67,
        USERGUIDS % 68,
        USERGUIDS % 69,
        USERGUIDS % 70,
        USERGUIDS % 71,
        USERGUIDS % 72,
        USERGUIDS % 73,
        USERGUIDS % 74,
        USERGUIDS % 75,
        USERGUIDS % 76,
        USERGUIDS % 77,
        USERGUIDS % 78,
        USERGUIDS % 79,
        USERGUIDS % 80,
        USERGUIDS % 81,
        USERGUIDS % 82,
        USERGUIDS % 83,
        USERGUIDS % 84,
        USERGUIDS % 85,
        USERGUIDS % 86,
        USERGUIDS % 87,
        USERGUIDS % 88,
        USERGUIDS % 89,
        USERGUIDS % 90,
        USERGUIDS % 91,
        USERGUIDS % 92,
        USERGUIDS % 93,
        USERGUIDS % 94,
        USERGUIDS % 95,
        USERGUIDS % 96,
        USERGUIDS % 97,
        USERGUIDS % 98,
        USERGUIDS % 99,
        USERGUIDS % 100,
    ),
    GROUPGUIDS % 10: (
        USERGUIDS % 1,
        USERGUIDS % 2,
        USERGUIDS % 3,
        USERGUIDS % 4,
        USERGUIDS % 5,
        USERGUIDS % 6,
        USERGUIDS % 7,
        USERGUIDS % 8,
        USERGUIDS % 9,
        USERGUIDS % 10,
        USERGUIDS % 11,
        USERGUIDS % 12,
        USERGUIDS % 13,
        USERGUIDS % 14,
        USERGUIDS % 15,
        USERGUIDS % 16,
        USERGUIDS % 17,
        USERGUIDS % 18,
        USERGUIDS % 19,
        USERGUIDS % 20,
        USERGUIDS % 21,
        USERGUIDS % 22,
        USERGUIDS % 23,
        USERGUIDS % 24,
        USERGUIDS % 25,
        USERGUIDS % 26,
        USERGUIDS % 27,
        USERGUIDS % 28,
        USERGUIDS % 29,
        USERGUIDS % 30,
        USERGUIDS % 31,
        USERGUIDS % 32,
        USERGUIDS % 33,
        USERGUIDS % 34,
        USERGUIDS % 35,
        USERGUIDS % 36,
        USERGUIDS % 37,
        USERGUIDS % 38,
        USERGUIDS % 39,
        USERGUIDS % 40,
        USERGUIDS % 41,
        USERGUIDS % 42,
        USERGUIDS % 43,
        USERGUIDS % 44,
        USERGUIDS % 45,
        USERGUIDS % 46,
        USERGUIDS % 47,
        USERGUIDS % 48,
        USERGUIDS % 49,
        USERGUIDS % 50,
        USERGUIDS % 51,
        USERGUIDS % 52,
        USERGUIDS % 53,
        USERGUIDS % 54,
        USERGUIDS % 55,
        USERGUIDS % 56,
        USERGUIDS % 57,
        USERGUIDS % 58,
        USERGUIDS % 59,
        USERGUIDS % 60,
        USERGUIDS % 61,
        USERGUIDS % 62,
        USERGUIDS % 63,
        USERGUIDS % 64,
        USERGUIDS % 65,
        USERGUIDS % 66,
        USERGUIDS % 67,
        USERGUIDS % 68,
        USERGUIDS % 69,
        USERGUIDS % 70,
        USERGUIDS % 71,
        USERGUIDS % 72,
        USERGUIDS % 73,
        USERGUIDS % 74,
        USERGUIDS % 75,
        USERGUIDS % 76,
        USERGUIDS % 77,
        USERGUIDS % 78,
        USERGUIDS % 79,
        USERGUIDS % 80,
        USERGUIDS % 81,
        USERGUIDS % 82,
        USERGUIDS % 83,
        USERGUIDS % 84,
        USERGUIDS % 85,
        USERGUIDS % 86,
        USERGUIDS % 87,
        USERGUIDS % 88,
        USERGUIDS % 89,
        USERGUIDS % 90,
        USERGUIDS % 91,
        USERGUIDS % 92,
        USERGUIDS % 93,
        USERGUIDS % 94,
        USERGUIDS % 95,
        USERGUIDS % 96,
        USERGUIDS % 97,
        USERGUIDS % 98,
        USERGUIDS % 99,
        USERGUIDS % 100,
        USERGUIDS % 101,
        USERGUIDS % 102,
        USERGUIDS % 103,
        USERGUIDS % 104,
        USERGUIDS % 105,
        USERGUIDS % 106,
        USERGUIDS % 107,
        USERGUIDS % 108,
        USERGUIDS % 109,
        USERGUIDS % 110,
        USERGUIDS % 111,
        USERGUIDS % 112,
        USERGUIDS % 113,
        USERGUIDS % 114,
        USERGUIDS % 115,
        USERGUIDS % 116,
        USERGUIDS % 117,
        USERGUIDS % 118,
        USERGUIDS % 119,
        USERGUIDS % 120,
        USERGUIDS % 121,
        USERGUIDS % 122,
        USERGUIDS % 123,
        USERGUIDS % 124,
        USERGUIDS % 125,
        USERGUIDS % 126,
        USERGUIDS % 127,
        USERGUIDS % 128,
        USERGUIDS % 129,
        USERGUIDS % 130,
        USERGUIDS % 131,
        USERGUIDS % 132,
        USERGUIDS % 133,
        USERGUIDS % 134,
        USERGUIDS % 135,
        USERGUIDS % 136,
        USERGUIDS % 137,
        USERGUIDS % 138,
        USERGUIDS % 139,
        USERGUIDS % 140,
        USERGUIDS % 141,
        USERGUIDS % 142,
        USERGUIDS % 143,
        USERGUIDS % 144,
        USERGUIDS % 145,
        USERGUIDS % 146,
        USERGUIDS % 147,
        USERGUIDS % 148,
        USERGUIDS % 149,
        USERGUIDS % 150,
        USERGUIDS % 151,
        USERGUIDS % 152,
        USERGUIDS % 153,
        USERGUIDS % 154,
        USERGUIDS % 155,
        USERGUIDS % 156,
        USERGUIDS % 157,
        USERGUIDS % 158,
        USERGUIDS % 159,
        USERGUIDS % 160,
        USERGUIDS % 161,
        USERGUIDS % 162,
        USERGUIDS % 163,
        USERGUIDS % 164,
        USERGUIDS % 165,
        USERGUIDS % 166,
        USERGUIDS % 167,
        USERGUIDS % 168,
        USERGUIDS % 169,
        USERGUIDS % 170,
        USERGUIDS % 171,
        USERGUIDS % 172,
        USERGUIDS % 173,
        USERGUIDS % 174,
        USERGUIDS % 175,
        USERGUIDS % 176,
        USERGUIDS % 177,
        USERGUIDS % 178,
        USERGUIDS % 179,
        USERGUIDS % 180,
        USERGUIDS % 181,
        USERGUIDS % 182,
        USERGUIDS % 183,
        USERGUIDS % 184,
        USERGUIDS % 185,
        USERGUIDS % 186,
        USERGUIDS % 187,
        USERGUIDS % 188,
        USERGUIDS % 189,
        USERGUIDS % 190,
        USERGUIDS % 191,
        USERGUIDS % 192,
        USERGUIDS % 193,
        USERGUIDS % 194,
        USERGUIDS % 195,
        USERGUIDS % 196,
        USERGUIDS % 197,
        USERGUIDS % 198,
        USERGUIDS % 199,
        USERGUIDS % 200,
        USERGUIDS % 201,
        USERGUIDS % 202,
        USERGUIDS % 203,
        USERGUIDS % 204,
        USERGUIDS % 205,
        USERGUIDS % 206,
        USERGUIDS % 207,
        USERGUIDS % 208,
        USERGUIDS % 209,
        USERGUIDS % 210,
        USERGUIDS % 211,
        USERGUIDS % 212,
        USERGUIDS % 213,
        USERGUIDS % 214,
        USERGUIDS % 215,
        USERGUIDS % 216,
        USERGUIDS % 217,
        USERGUIDS % 218,
        USERGUIDS % 219,
        USERGUIDS % 220,
        USERGUIDS % 221,
        USERGUIDS % 222,
        USERGUIDS % 223,
        USERGUIDS % 224,
        USERGUIDS % 225,
        USERGUIDS % 226,
        USERGUIDS % 227,
        USERGUIDS % 228,
        USERGUIDS % 229,
        USERGUIDS % 230,
        USERGUIDS % 231,
        USERGUIDS % 232,
        USERGUIDS % 233,
        USERGUIDS % 234,
        USERGUIDS % 235,
        USERGUIDS % 236,
        USERGUIDS % 237,
        USERGUIDS % 238,
        USERGUIDS % 239,
        USERGUIDS % 240,
        USERGUIDS % 241,
        USERGUIDS % 242,
        USERGUIDS % 243,
        USERGUIDS % 244,
        USERGUIDS % 245,
        USERGUIDS % 246,
        USERGUIDS % 247,
        USERGUIDS % 248,
        USERGUIDS % 249,
        USERGUIDS % 250,
        USERGUIDS % 251,
        USERGUIDS % 252,
        USERGUIDS % 253,
        USERGUIDS % 254,
        USERGUIDS % 255,
        USERGUIDS % 256,
        USERGUIDS % 257,
        USERGUIDS % 258,
        USERGUIDS % 259,
        USERGUIDS % 260,
        USERGUIDS % 261,
        USERGUIDS % 262,
        USERGUIDS % 263,
        USERGUIDS % 264,
        USERGUIDS % 265,
        USERGUIDS % 266,
        USERGUIDS % 267,
        USERGUIDS % 268,
        USERGUIDS % 269,
        USERGUIDS % 270,
        USERGUIDS % 271,
        USERGUIDS % 272,
        USERGUIDS % 273,
        USERGUIDS % 274,
        USERGUIDS % 275,
        USERGUIDS % 276,
        USERGUIDS % 277,
        USERGUIDS % 278,
        USERGUIDS % 279,
        USERGUIDS % 280,
        USERGUIDS % 281,
        USERGUIDS % 282,
        USERGUIDS % 283,
        USERGUIDS % 284,
        USERGUIDS % 285,
        USERGUIDS % 286,
        USERGUIDS % 287,
        USERGUIDS % 288,
        USERGUIDS % 289,
        USERGUIDS % 290,
        USERGUIDS % 291,
        USERGUIDS % 292,
        USERGUIDS % 293,
        USERGUIDS % 294,
        USERGUIDS % 295,
        USERGUIDS % 296,
        USERGUIDS % 297,
        USERGUIDS % 298,
        USERGUIDS % 299,
        USERGUIDS % 300,
        USERGUIDS % 301,
        USERGUIDS % 302,
        USERGUIDS % 303,
        USERGUIDS % 304,
        USERGUIDS % 305,
        USERGUIDS % 306,
        USERGUIDS % 307,
        USERGUIDS % 308,
        USERGUIDS % 309,
        USERGUIDS % 310,
        USERGUIDS % 311,
        USERGUIDS % 312,
        USERGUIDS % 313,
        USERGUIDS % 314,
        USERGUIDS % 315,
        USERGUIDS % 316,
        USERGUIDS % 317,
        USERGUIDS % 318,
        USERGUIDS % 319,
        USERGUIDS % 320,
        USERGUIDS % 321,
        USERGUIDS % 322,
        USERGUIDS % 323,
        USERGUIDS % 324,
        USERGUIDS % 325,
        USERGUIDS % 326,
        USERGUIDS % 327,
        USERGUIDS % 328,
        USERGUIDS % 329,
        USERGUIDS % 330,
        USERGUIDS % 331,
        USERGUIDS % 332,
        USERGUIDS % 333,
        USERGUIDS % 334,
        USERGUIDS % 335,
        USERGUIDS % 336,
        USERGUIDS % 337,
        USERGUIDS % 338,
        USERGUIDS % 339,
        USERGUIDS % 340,
        USERGUIDS % 341,
        USERGUIDS % 342,
        USERGUIDS % 343,
        USERGUIDS % 344,
        USERGUIDS % 345,
        USERGUIDS % 346,
        USERGUIDS % 347,
        USERGUIDS % 348,
        USERGUIDS % 349,
        USERGUIDS % 350,
        USERGUIDS % 351,
        USERGUIDS % 352,
        USERGUIDS % 353,
        USERGUIDS % 354,
        USERGUIDS % 355,
        USERGUIDS % 356,
        USERGUIDS % 357,
        USERGUIDS % 358,
        USERGUIDS % 359,
        USERGUIDS % 360,
        USERGUIDS % 361,
        USERGUIDS % 362,
        USERGUIDS % 363,
        USERGUIDS % 364,
        USERGUIDS % 365,
        USERGUIDS % 366,
        USERGUIDS % 367,
        USERGUIDS % 368,
        USERGUIDS % 369,
        USERGUIDS % 370,
        USERGUIDS % 371,
        USERGUIDS % 372,
        USERGUIDS % 373,
        USERGUIDS % 374,
        USERGUIDS % 375,
        USERGUIDS % 376,
        USERGUIDS % 377,
        USERGUIDS % 378,
        USERGUIDS % 379,
        USERGUIDS % 380,
        USERGUIDS % 381,
        USERGUIDS % 382,
        USERGUIDS % 383,
        USERGUIDS % 384,
        USERGUIDS % 385,
        USERGUIDS % 386,
        USERGUIDS % 387,
        USERGUIDS % 388,
        USERGUIDS % 389,
        USERGUIDS % 390,
        USERGUIDS % 391,
        USERGUIDS % 392,
        USERGUIDS % 393,
        USERGUIDS % 394,
        USERGUIDS % 395,
        USERGUIDS % 396,
        USERGUIDS % 397,
        USERGUIDS % 398,
        USERGUIDS % 399,
        USERGUIDS % 400,
        USERGUIDS % 401,
        USERGUIDS % 402,
        USERGUIDS % 403,
        USERGUIDS % 404,
        USERGUIDS % 405,
        USERGUIDS % 406,
        USERGUIDS % 407,
        USERGUIDS % 408,
        USERGUIDS % 409,
        USERGUIDS % 410,
        USERGUIDS % 411,
        USERGUIDS % 412,
        USERGUIDS % 413,
        USERGUIDS % 414,
        USERGUIDS % 415,
        USERGUIDS % 416,
        USERGUIDS % 417,
        USERGUIDS % 418,
        USERGUIDS % 419,
        USERGUIDS % 420,
        USERGUIDS % 421,
        USERGUIDS % 422,
        USERGUIDS % 423,
        USERGUIDS % 424,
        USERGUIDS % 425,
        USERGUIDS % 426,
        USERGUIDS % 427,
        USERGUIDS % 428,
        USERGUIDS % 429,
        USERGUIDS % 430,
        USERGUIDS % 431,
        USERGUIDS % 432,
        USERGUIDS % 433,
        USERGUIDS % 434,
        USERGUIDS % 435,
        USERGUIDS % 436,
        USERGUIDS % 437,
        USERGUIDS % 438,
        USERGUIDS % 439,
        USERGUIDS % 440,
        USERGUIDS % 441,
        USERGUIDS % 442,
        USERGUIDS % 443,
        USERGUIDS % 444,
        USERGUIDS % 445,
        USERGUIDS % 446,
        USERGUIDS % 447,
        USERGUIDS % 448,
        USERGUIDS % 449,
        USERGUIDS % 450,
        USERGUIDS % 451,
        USERGUIDS % 452,
        USERGUIDS % 453,
        USERGUIDS % 454,
        USERGUIDS % 455,
        USERGUIDS % 456,
        USERGUIDS % 457,
        USERGUIDS % 458,
        USERGUIDS % 459,
        USERGUIDS % 460,
        USERGUIDS % 461,
        USERGUIDS % 462,
        USERGUIDS % 463,
        USERGUIDS % 464,
        USERGUIDS % 465,
        USERGUIDS % 466,
        USERGUIDS % 467,
        USERGUIDS % 468,
        USERGUIDS % 469,
        USERGUIDS % 470,
        USERGUIDS % 471,
        USERGUIDS % 472,
        USERGUIDS % 473,
        USERGUIDS % 474,
        USERGUIDS % 475,
        USERGUIDS % 476,
        USERGUIDS % 477,
        USERGUIDS % 478,
        USERGUIDS % 479,
        USERGUIDS % 480,
        USERGUIDS % 481,
        USERGUIDS % 482,
        USERGUIDS % 483,
        USERGUIDS % 484,
        USERGUIDS % 485,
        USERGUIDS % 486,
        USERGUIDS % 487,
        USERGUIDS % 488,
        USERGUIDS % 489,
        USERGUIDS % 490,
        USERGUIDS % 491,
        USERGUIDS % 492,
        USERGUIDS % 493,
        USERGUIDS % 494,
        USERGUIDS % 495,
        USERGUIDS % 496,
        USERGUIDS % 497,
        USERGUIDS % 498,
        USERGUIDS % 499,
        USERGUIDS % 500,
    ),
})

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
