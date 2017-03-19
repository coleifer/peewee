import threading

from peewee import attrdict
from peewee import *

from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import get_in_memory_db
from .base_models import User


class TestDatabase(DatabaseTestCase):
    database = get_in_memory_db()

    def test_pragmas(self):
        self.assertEqual(self.database.page_size, 4096)
        self.database.page_size = 1024
        self.assertEqual(self.database.page_size, 1024)

        self.database.foreign_keys = 'on'
        self.assertEqual(self.database.foreign_keys, 1)
        self.database.foreign_keys = 'off'
        self.assertEqual(self.database.foreign_keys, 0)

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


class TestThreadSafety(ModelTestCase):
    requires = [User]

    def test_multiple_writers(self):
        def create_users(idx):
            n = 10
            for i in range(idx * n, (idx + 1) * n):
                User.create(username='u%d' % i)

        threads = []
        for i in range(4):
            threads.append(threading.Thread(target=create_users, args=(i,)))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(User.select().count(), 40)
