from peewee import attrdict
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

    def test_context_settings(self):
        class TestDatabase(Database):
            options = Database.options + attrdict(
                field_types={
                    FIELD.BIGINT: 'TEST_BIGINT',
                    FIELD.TEXT: 'TEST_TEXT'},
                param='$')

        test_db = TestDatabase(None)
        state = test_db.get_sql_context().state

        self.assertEqual(state.field_types[FIELD.BIGINT], 'TEST_BIGINT')
        self.assertEqual(state.field_types[FIELD.TEXT], 'TEST_TEXT')
        self.assertEqual(state.field_types['INT'], FIELD.INT)
        self.assertEqual(state.field_types['VARCHAR'], FIELD.VARCHAR)

        self.assertEqual(state.param, '$')
        self.assertEqual(state.quote, '"')
