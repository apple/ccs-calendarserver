##
#    Copyright (c) 2012 Cyrus Daboo. All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
##

import unittest
from src.jsonPointer import JSONPointer, JSONPointerMatchError, JSONMatcher

class TestJSONPointer(unittest.TestCase):

    def testValidPointers(self):
        data = (
            (None, False),
            ("", False),
            (1, False),
            ("/", True),
            ("//", False),
            ("/abc", True),
            ("/abc/", False),
        )

        for pointer, result in data:
            try:
                JSONPointer(pointer)
                ok = True
            except (ValueError, TypeError):
                ok = False
            self.assertEqual(ok, result, "Failed test: %s" % (pointer,))


    def testUnescape(self):
        data = (
            ("/", None),
            ("/~0", ["~", ]),
            ("/abc~1def", ["abc/def", ]),
            ("/abc/~0~1a", ["abc", "~/a", ]),
            ("/~0ab~1c/~0~1a", ["~ab/c", "~/a", ]),
        )

        for pointer, result in data:
            j = JSONPointer(pointer)
            self.assertEqual(j.segments, result, "Failed test: %s" % (pointer,))


    def testMatchOK(self):
        data = (
            # Objects
            ("/", '{"1": "foo"}', {"1": "foo"}),
            ("/1", '{"1": "foo", "2": "bar"}', "foo"),
            ("/2", '{"1": "foo", "2": "bar"}', "bar"),
            ("/1", '{"1": {"1.1": "foo"}}', {"1.1": "foo"}),
            ("/1/1.1", '{"1": {"1.1": "foo", "1.2": "bar"}}', "foo"),
            ("/1/1.2", '{"1": {"1.1": "foo", "1.2": "bar"}}', "bar"),

            # Arrays
            ("/", '["1", "2"]', ["1", "2"]),
            ("/0", '["1", "2"]', "1"),
            ("/1", '["1", "2"]', "2"),
            ("/-", '["1", "2"]', "2"),
            ("/0", '[["1", "2"]]', ["1", "2"]),
            ("/-", '[["1", "2"]]', ["1", "2"]),
            ("/0/0", '[["1", "2"]]', "1"),
            ("/0/1", '[["1", "2"]]', "2"),
            ("/0/-", '[["1", "2"]]', "2"),

            # Both
            ("/", '{"1": ["foo", "bar"]}', {"1": ["foo", "bar"]}),
            ("/1", '{"1": ["foo", "bar"]}', ["foo", "bar"]),
            ("/1/0", '{"1": ["foo", "bar"]}', "foo"),
            ("/1/1", '{"1": ["foo", "bar"]}', "bar"),
            ("/1/-", '{"1": ["foo", "bar"]}', "bar"),
            ("/", '[{"1.1": "foo", "1.2": "bar"}]', [{"1.1": "foo", "1.2": "bar"}]),
            ("/0", '[{"1.1": "foo", "1.2": "bar"}]', {"1.1": "foo", "1.2": "bar"}),
            ("/-", '[{"1.1": "foo", "1.2": "bar"}]', {"1.1": "foo", "1.2": "bar"}),
            ("/0/1.1", '[{"1.1": "foo", "1.2": "bar"}]', "foo"),
            ("/0/1.2", '[{"1.1": "foo", "1.2": "bar"}]', "bar"),
        )

        for pointer, jobj, result in data:
            j = JSONPointer(pointer)
            self.assertEqual(j.matchs(jobj), result, "Failed test: %s" % (pointer,))


    def testMatchBad(self):
        data = (
            # Objects
            ("/3", '{"1": "foo", "2": "bar"}'),
            ("/a", '{"1": "foo", "2": "bar"}'),
            ("/-", '{"1": "foo", "2": "bar"}'),
            ("/1/3", '{"1": {"1.1": "foo", "1.2": "bar"}}'),
            ("/1/a", '{"1": {"1.1": "foo", "1.2": "bar"}}'),
            ("/1/-", '{"1": {"1.1": "foo", "1.2": "bar"}}'),

            # Arrays
            ("/2", '["1", "2"]'),
            ("/0/2", '[["1", "2"]]'),

            # Both
            ("/1/3", '{"1": ["foo", "bar"]}'),
            ("/0/3", '[{"1.1": "foo", "1.2": "bar"}]'),
            ("/0/a", '[{"1.1": "foo", "1.2": "bar"}]'),
            ("/0/-", '[{"1.1": "foo", "1.2": "bar"}]'),

            # Wrong Object
            ("/1/0", '{"1": "foo"}'),
            ("/1/0", '{"1": 1}'),
            ("/1/0", '{"1": true}'),
            ("/1/0", '{"1": null}'),
        )

        for pointer, jobj in data:
            j = JSONPointer(pointer)
            self.assertRaises(JSONPointerMatchError, j.matchs, jobj)



class TestJSONMatcher(unittest.TestCase):

    def testMatchOK(self):
        data = (
            # Objects
            ("/", '{"1": "foo"}', [{"1": "foo"}]),
            ("/1", '{"1": "foo", "2": "bar"}', ["foo"]),
            ("/2", '{"1": "foo", "2": "bar"}', ["bar"]),
            ("/1", '{"1": {"1.1": "foo"}}', [{"1.1": "foo"}]),
            ("/1/1.1", '{"1": {"1.1": "foo", "1.2": "bar"}}', ["foo"]),
            ("/1/1.2", '{"1": {"1.1": "foo", "1.2": "bar"}}', ["bar"]),

            # Arrays
            ("/", '["1", "2"]', [["1", "2"]]),
            ("/0", '["1", "2"]', ["1"]),
            ("/1", '["1", "2"]', ["2"]),
            ("/-", '["1", "2"]', ["2"]),
            ("/0", '[["1", "2"]]', [["1", "2"]]),
            ("/-", '[["1", "2"]]', [["1", "2"]]),
            ("/0/0", '[["1", "2"]]', ["1"]),
            ("/0/1", '[["1", "2"]]', ["2"]),
            ("/0/-", '[["1", "2"]]', ["2"]),

            # Both
            ("/", '{"1": ["foo", "bar"]}', [{"1": ["foo", "bar"]}]),
            ("/1", '{"1": ["foo", "bar"]}', [["foo", "bar"]]),
            ("/1/0", '{"1": ["foo", "bar"]}', ["foo"]),
            ("/1/1", '{"1": ["foo", "bar"]}', ["bar"]),
            ("/1/-", '{"1": ["foo", "bar"]}', ["bar"]),
            ("/", '[{"1.1": "foo", "1.2": "bar"}]', [[{"1.1": "foo", "1.2": "bar"}]]),
            ("/0", '[{"1.1": "foo", "1.2": "bar"}]', [{"1.1": "foo", "1.2": "bar"}]),
            ("/-", '[{"1.1": "foo", "1.2": "bar"}]', [{"1.1": "foo", "1.2": "bar"}]),
            ("/0/1.1", '[{"1.1": "foo", "1.2": "bar"}]', ["foo"]),
            ("/0/1.2", '[{"1.1": "foo", "1.2": "bar"}]', ["bar"]),
        )

        for pointer, jobj, result in data:
            j = JSONMatcher(pointer)
            self.assertEqual(j.matchs(jobj), result, "Failed test: %s" % (pointer,))


    def testMatchBad(self):
        data = (
            # Objects
            ("/3", '{"1": "foo", "2": "bar"}', False),
            ("/a", '{"1": "foo", "2": "bar"}', False),
            ("/-", '{"1": "foo", "2": "bar"}', False),
            ("/1/3", '{"1": {"1.1": "foo", "1.2": "bar"}}', False),
            ("/1/a", '{"1": {"1.1": "foo", "1.2": "bar"}}', False),
            ("/1/-", '{"1": {"1.1": "foo", "1.2": "bar"}}', False),

            # Arrays
            ("/2", '["1", "2"]', False),
            ("/0/2", '[["1", "2"]]', False),

            # Both
            ("/1/3", '{"1": ["foo", "bar"]}', False),
            ("/0/3", '[{"1.1": "foo", "1.2": "bar"}]', False),
            ("/0/a", '[{"1.1": "foo", "1.2": "bar"}]', False),
            ("/0/-", '[{"1.1": "foo", "1.2": "bar"}]', False),

            # Wrong Object
            ("/1/0", '{"1": "foo"}', True),
            ("/1/0", '{"1": 1}', True),
            ("/1/0", '{"1": true}', True),
            ("/1/0", '{"1": null}', True),
        )

        for pointer, jobj, willRaise in data:
            j = JSONMatcher(pointer)
            if willRaise:
                self.assertRaises(JSONPointerMatchError, j.matchs, jobj)
            else:
                self.assertEqual(j.matchs(jobj), [], "Failed test: %s" % (pointer,))


    def testMatchingOK(self):
        data = (
            (
                "/",
                '{"1":"foo", "2": "bar"}',
                [{"1":"foo", "2": "bar"}, ],
            ),
            (
                "/.",
                '{"1":"foo", "2": "bar"}',
                ["foo", "bar", ],
            ),
            (
                "/./0",
                '{"1":["foo1", "foo2"], "2": ["bar1", "bar2"]}',
                ["foo1", "bar1", ],
            ),
            (
                "/./1",
                '{"1":["foo1", "foo2"], "2": ["bar1", "bar2"]}',
                ["foo2", "bar2", ],
            ),
            (
                "/./-",
                '{"1":["foo1", "foo2"], "2": ["bar1", "bar2"]}',
                ["foo2", "bar2", ],
            ),
            (
                "/./2",
                '{"1":["foo1", "foo2"], "2": ["bar1", "bar2"]}',
                [],
            ),
            (
                "/./foo1",
                '{"1":{"foo1": "bar1", "foo2": "bar2"}, "2": {"foo1": "bar3", "foo4": "bar4"}}',
                ["bar1", "bar3", ],
            ),
            (
                "/./foo2",
                '{"1":{"foo1": "bar1", "foo2": "bar2"}, "2": {"foo1": "bar3", "foo4": "bar4"}}',
                ["bar2", ],
            ),
            (
                "/./foo4",
                '{"1":{"foo1": "bar1", "foo2": "bar2"}, "2": {"foo1": "bar3", "foo4": "bar4"}}',
                ["bar4", ],
            ),
            (
                "/./foo3",
                '{"1":{"foo1": "bar1", "foo2": "bar2"}, "2": {"foo1": "bar3", "foo4": "bar4"}}',
                [],
            ),
        )

        for pointer, jobj, result in data:
            j = JSONMatcher(pointer)
            self.assertEqual(j.matchs(jobj), result, "Failed test: %s" % (pointer,))
