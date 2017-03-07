from peewee import *

from .base import DatabaseTestCase
from .base import db


class TestDatabase(DatabaseTestCase):
    def test_pragmas(self):
        self.assertEqual(db.page_size, 4096)
        db.page_size = 1024
        self.assertEqual(db.page_size, 1024)

        db.foreign_keys = 'on'
        self.assertEqual(db.foreign_keys, 1)
        db.foreign_keys = 'off'
        self.assertEqual(db.foreign_keys, 0)
