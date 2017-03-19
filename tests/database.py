try:
    from Queue import Queue
except ImportError:
    from queue import Queue
import threading

from peewee import attrdict
from peewee import *

from .base import BaseTestCase
from .base import DatabaseTestCase
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import db_loader
from .base import skip_case_unless
from .base_models import User


class TestDatabase(DatabaseTestCase):
    database = db_loader('sqlite3')

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

    def test_connection_state(self):
        conn = self.database.connection()
        self.assertFalse(self.database.is_closed())
        self.database.close()
        self.assertTrue(self.database.is_closed())
        conn = self.database.connection()
        self.assertFalse(self.database.is_closed())

    def test_connection_initialization(self):
        state = {'count': 0}
        class TestDatabase(SqliteDatabase):
            def _initialize_connection(self, conn):
                state['count'] += 1

        db = TestDatabase(':memory:')
        self.assertEqual(state['count'], 0)

        conn = db.connection()
        self.assertEqual(state['count'], 1)

        # Since already connected, nothing happens here.
        conn = db.connection()
        self.assertEqual(state['count'], 1)

        db.close()
        db.connect()
        self.assertEqual(state['count'], 2)


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

        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(User.select().count(), 40)

    def test_multiple_readers(self):
        data = Queue()
        def read_user_count(n):
            for i in range(n):
                data.put(User.select().count())

        threads = []
        for i in range(4):
            threads.append(threading.Thread(target=read_user_count,
                                            args=(10,)))

        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(data.qsize(), 40)


class TestDeferredDatabase(BaseTestCase):
    def test_deferred_database(self):
        deferred_db = SqliteDatabase(None)
        self.assertTrue(deferred_db.deferred)

        class DeferredModel(Model):
            class Meta:
                database = deferred_db

        self.assertRaises(Exception, deferred_db.connect)
        query = DeferredModel.select()
        self.assertRaises(Exception, query.execute)

        deferred_db.init(':memory:')
        self.assertFalse(deferred_db.deferred)

        conn = deferred_db.connect()
        self.assertFalse(deferred_db.is_closed())
        DeferredModel._schema.create_all()
        self.assertEqual(list(DeferredModel.select()), [])

        deferred_db.init(None)
        self.assertTrue(deferred_db.deferred)

        # The connection was automatically closed.
        self.assertTrue(deferred_db.is_closed())


class CatToy(TestModel):
    description = TextField()

    class Meta:
        schema = 'huey'


@skip_case_unless(isinstance(db, PostgresqlDatabase))
class TestSchemaNamespace(ModelTestCase):
    requires = [CatToy]

    def setUp(self):
        with self.database:
            self.execute('CREATE SCHEMA huey;')
        super(TestSchemaNamespace, self).setUp()

    def tearDown(self):
        super(TestSchemaNamespace, self).tearDown()
        with self.database:
            self.execute('DROP SCHEMA huey;')

    def test_schema(self):
        toy = CatToy.create(description='fur mouse')
        toy_db = CatToy.select().where(CatToy.id == toy.id).get()
        self.assertEqual(toy.id, toy_db.id)
        self.assertEqual(toy.description, toy_db.description)


class TestSqliteIsolation(ModelTestCase):
    database = db_loader('sqlite3')
    requires = [User]

    def test_sqlite_isolation(self):
        for username in ('u1', 'u2', 'u3'): User.create(username=username)

        new_db = db_loader('sqlite3')
        curs = new_db.execute_sql('SELECT COUNT(*) FROM users')
        self.assertEqual(curs.fetchone()[0], 3)

        self.assertEqual(User.select().count(), 3)
        self.assertEqual(User.delete().execute(), 3)

        with self.database.atomic():
            User.create(username='u4')
            User.create(username='u5')

            # Second conn does not see the changes.
            curs = new_db.execute_sql('SELECT COUNT(*) FROM users')
            self.assertEqual(curs.fetchone()[0], 0)

            # Third conn does not see the changes.
            new_db2 = db_loader('sqlite3')
            curs = new_db2.execute_sql('SELECT COUNT(*) FROM users')
            self.assertEqual(curs.fetchone()[0], 0)

            # Original connection sees its own changes.
            self.assertEqual(User.select().count(), 2)

        curs = new_db.execute_sql('SELECT COUNT(*) FROM users')
        self.assertEqual(curs.fetchone()[0], 2)
