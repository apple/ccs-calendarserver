
from unittest import TestCase

from stats import SQLDuration

class SQLDurationTests(TestCase):
    def setUp(self):
        self.stat = SQLDuration('foo')


    def test_normalize_integer(self):
        self.assertEquals(
            self.stat.normalize('SELECT foo FROM bar WHERE 1'),
            'SELECT foo FROM bar WHERE ?')
        self.assertEquals(
            self.stat.normalize('SELECT foo FROM bar WHERE x = 1'),
            'SELECT foo FROM bar WHERE x = ?')
        self.assertEquals(
            self.stat.normalize('SELECT foo + 1 FROM bar'),
            'SELECT foo + ? FROM bar')

