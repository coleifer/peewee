from itertools import permutations
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
from .base import get_in_memory_db
from .base import requires_models
from .base import skip_case_unless
from .base_models import Category
from .base_models import Tweet
from .base_models import User


class TestDatabase(DatabaseTestCase):
    database = db_loader('sqlite3')

    def test_pragmas(self):
        self.database.cache_size = -2048
        self.assertEqual(self.database.cache_size, -2048)
        self.database.cache_size = -4096
        self.assertEqual(self.database.cache_size, -4096)

        self.database.foreign_keys = 'on'
        self.assertEqual(self.database.foreign_keys, 1)
        self.database.foreign_keys = 'off'
        self.assertEqual(self.database.foreign_keys, 0)

    def test_context_settings(self):
        class TestDatabase(Database):
            options = attrdict(
                field_types={'BIGINT': 'TEST_BIGINT', 'TEXT': 'TEST_TEXT'},
                operations={'LIKE': '~', 'NEW': '->>'},
                param='$')

        test_db = TestDatabase(None)
        state = test_db.get_sql_context().state

        self.assertEqual(state.field_types['BIGINT'], 'TEST_BIGINT')
        self.assertEqual(state.field_types['TEXT'], 'TEST_TEXT')
        self.assertEqual(state.field_types['INT'], FIELD.INT)
        self.assertEqual(state.field_types['VARCHAR'], FIELD.VARCHAR)

        self.assertEqual(state.operations['LIKE'], '~')
        self.assertEqual(state.operations['NEW'], '->>')
        self.assertEqual(state.operations['ILIKE'], 'ILIKE')

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

    def test_connect_semantics(self):
        state = {'count': 0}
        class TestDatabase(SqliteDatabase):
            def _initialize_connection(self, conn):
                state['count'] += 1
        db = TestDatabase(':memory:')

        db.connect()
        self.assertEqual(state['count'], 1)
        self.assertRaises(OperationalError, db.connect)
        self.assertEqual(state['count'], 1)

        self.assertFalse(db.connect(reuse_if_open=True))
        self.assertEqual(state['count'], 1)

        with db:
            self.assertEqual(state['count'], 1)
            self.assertFalse(db.is_closed())

        self.assertTrue(db.is_closed())
        with db:
            self.assertEqual(state['count'], 2)

    def test_execute_sql(self):
        self.database.execute_sql('CREATE TABLE register (val INTEGER);')
        self.database.execute_sql('INSERT INTO register (val) VALUES (?), (?)',
                                  (1337, 31337))
        cursor = self.database.execute_sql(
            'SELECT val FROM register ORDER BY val')
        self.assertEqual(cursor.fetchall(), [(1337,), (31337,)])
        self.database.execute_sql('DROP TABLE register;')


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


class UniqueModel(TestModel):
    name = CharField(unique=True)


class IndexedModel(TestModel):
    first = CharField()
    last = CharField()
    dob = DateField()

    class Meta:
        indexes = (
            (('first', 'last', 'dob'), True),
            (('first', 'last'), False),
        )


class TestIntrospection(ModelTestCase):
    requires = [Category, User, UniqueModel, IndexedModel]

    def test_table_exists(self):
        self.assertTrue(self.database.table_exists(User._meta.table))
        self.assertFalse(self.database.table_exists(Table('nuggies')))

    def test_get_tables(self):
        tables = self.database.get_tables()
        required = set(m._meta.table_name for m in self.requires)
        self.assertTrue(required.issubset(set(tables)))

        UniqueModel._schema.drop_all()
        tables = self.database.get_tables()
        self.assertFalse(UniqueModel._meta.table_name in tables)

    def test_get_indexes(self):
        indexes = self.database.get_indexes('uniquemodel')
        data = [(index.name, index.columns, index.unique, index.table)
                for index in indexes if index.name != 'uniquemodel_pkey']
        self.assertEqual(data, [
            ('uniquemodel_name', ['name'], True, 'uniquemodel')])

        indexes = self.database.get_indexes('indexedmodel')
        data = [(index.name, index.columns, index.unique, index.table)
                for index in indexes if index.name != 'indexedmodel_pkey']
        self.assertEqual(sorted(data), [
            ('indexedmodel_first_last', ['first', 'last'], False,
             'indexedmodel'),
            ('indexedmodel_first_last_dob', ['first', 'last', 'dob'], True,
             'indexedmodel')])

    def test_get_columns(self):
        columns = self.database.get_columns('indexedmodel')
        data = [(c.name, c.null, c.primary_key, c.table)
                for c in columns]
        self.assertEqual(data, [
            ('id', False, True, 'indexedmodel'),
            ('first', False, False, 'indexedmodel'),
            ('last', False, False, 'indexedmodel'),
            ('dob', False, False, 'indexedmodel')])

        columns = self.database.get_columns('category')
        data = [(c.name, c.null, c.primary_key, c.table)
                for c in columns]
        self.assertEqual(data, [
            ('name', False, True, 'category'),
            ('parent_id', True, False, 'category')])

    def test_get_primary_keys(self):
        primary_keys = self.database.get_primary_keys('users')
        self.assertEqual(primary_keys, ['id'])

        primary_keys = self.database.get_primary_keys('category')
        self.assertEqual(primary_keys, ['name'])

    @requires_models(User, Tweet, Category)
    def test_get_foreign_keys(self):
        foreign_keys = self.database.get_foreign_keys('tweet')
        data = [(fk.column, fk.dest_table, fk.dest_column, fk.table)
                for fk in foreign_keys]
        self.assertEqual(data, [
            ('user_id', 'users', 'id', 'tweet')])

        foreign_keys = self.database.get_foreign_keys('category')
        data = [(fk.column, fk.dest_table, fk.dest_column, fk.table)
                for fk in foreign_keys]
        self.assertEqual(data, [
            ('parent_id', 'category', 'name', 'category')])


class TestSortModels(BaseTestCase):
    def test_sort_models(self):
        class A(Model):
            pass
        class B(Model):
            a = ForeignKeyField(A)
        class C(Model):
            b = ForeignKeyField(B)
        class D(Model):
            c = ForeignKeyField(C)
        class E(Model):
            pass

        models = [A, B, C, D, E]
        for list_of_models in permutations(models):
            sorted_models = sort_models(list_of_models)
            self.assertEqual(sorted_models, models)


class TestDBProxy(BaseTestCase):
    def test_db_proxy(self):
        db = Proxy()
        class BaseModel(Model):
            class Meta:
                database = db

        class User(BaseModel):
            username = TextField()

        class Tweet(BaseModel):
            user = ForeignKeyField(User, backref='tweets')
            message = TextField()

        sqlite_db = SqliteDatabase(':memory:')
        db.initialize(sqlite_db)

        self.assertEqual(User._meta.database.database, ':memory:')
        self.assertEqual(Tweet._meta.database.database, ':memory:')

        self.assertTrue(User._meta.database.is_closed())
        self.assertTrue(Tweet._meta.database.is_closed())
        sqlite_db.connect()
        self.assertFalse(User._meta.database.is_closed())
        self.assertFalse(Tweet._meta.database.is_closed())
        sqlite_db.close()
