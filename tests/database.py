from itertools import permutations
try:
    from Queue import Queue
except ImportError:
    from queue import Queue
import re
import threading

from peewee import *
from peewee import Database
from peewee import FIELD
from peewee import attrdict
from peewee import sort_models

from .base import BaseTestCase
from .base import DatabaseTestCase
from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import TestModel
from .base import db
from .base import db_loader
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_postgresql
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

    def test_timeout_semantics(self):
        self.assertEqual(self.database.timeout, 5)
        self.assertEqual(self.database.pragma('busy_timeout'), 5000)

        self.database.timeout = 2.5
        self.assertEqual(self.database.timeout, 2.5)
        self.assertEqual(self.database.pragma('busy_timeout'), 2500)

        self.database.close()
        self.database.connect()

        self.assertEqual(self.database.timeout, 2.5)
        self.assertEqual(self.database.pragma('busy_timeout'), 2500)

    def test_pragmas_deferred(self):
        pragmas = (('journal_mode', 'wal'),)
        db = SqliteDatabase(None, pragmas=pragmas)
        self.assertEqual(db._pragmas, pragmas)

        # Test pragmas preserved after initializing.
        db.init(':memory:')
        self.assertEqual(db._pragmas, pragmas)

        db = SqliteDatabase(None)
        self.assertEqual(db._pragmas, ())

        # Test pragmas are set and subsequently overwritten.
        db.init(':memory:', pragmas=pragmas)
        self.assertEqual(db._pragmas, pragmas)

        db.init(':memory:', pragmas=())
        self.assertEqual(db._pragmas, ())

        # Test when specified twice, the previous value is overwritten.
        db = SqliteDatabase(None, pragmas=pragmas)
        db.init(':memory:', pragmas=(('cache_size', -8000),))
        self.assertEqual(db._pragmas, (('cache_size', -8000),))

    def test_pragmas_as_dict(self):
        pragmas = {'journal_mode': 'wal'}
        pragma_list = [('journal_mode', 'wal')]

        db = SqliteDatabase(':memory:', pragmas=pragmas)
        self.assertEqual(db._pragmas, pragma_list)

        # Test deferred databases correctly handle pragma dicts.
        db = SqliteDatabase(None, pragmas=pragmas)
        self.assertEqual(db._pragmas, pragma_list)

        db.init(':memory:')
        self.assertEqual(db._pragmas, pragma_list)

        db.init(':memory:', pragmas={})
        self.assertEqual(db._pragmas, [])

    def test_pragmas_permanent(self):
        db = SqliteDatabase(':memory:')
        db.execute_sql('pragma foreign_keys=0')
        self.assertEqual(db.foreign_keys, 0)

        db.pragma('foreign_keys', 1, True)
        self.assertEqual(db.foreign_keys, 1)

        db.close()
        db.connect()
        self.assertEqual(db.foreign_keys, 1)

    def test_context_settings(self):
        class TestDatabase(Database):
            field_types = {'BIGINT': 'TEST_BIGINT', 'TEXT': 'TEST_TEXT'}
            operations = {'LIKE': '~', 'NEW': '->>'}
            param = '$'

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
        self.assertEqual(state.quote, '""')

        test_db2 = TestDatabase(None, field_types={'BIGINT': 'XXX_BIGINT',
                                                   'INT': 'XXX_INT'})
        state = test_db2.get_sql_context().state
        self.assertEqual(state.field_types['BIGINT'], 'XXX_BIGINT')
        self.assertEqual(state.field_types['TEXT'], 'TEST_TEXT')
        self.assertEqual(state.field_types['INT'], 'XXX_INT')
        self.assertEqual(state.field_types['VARCHAR'], FIELD.VARCHAR)

    def test_connection_state(self):
        conn = self.database.connection()
        self.assertFalse(self.database.is_closed())
        self.database.close()
        self.assertTrue(self.database.is_closed())
        conn = self.database.connection()
        self.assertFalse(self.database.is_closed())

    def test_db_context_manager(self):
        self.database.close()
        self.assertTrue(self.database.is_closed())

        with self.database:
            self.assertFalse(self.database.is_closed())

        self.assertTrue(self.database.is_closed())
        self.database.connect()
        self.assertFalse(self.database.is_closed())

        # Enter context with an already-open db.
        with self.database:
            self.assertFalse(self.database.is_closed())

        # Closed after exit.
        self.assertTrue(self.database.is_closed())

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

    def test_bind_helpers(self):
        db = get_in_memory_db()
        alt_db = get_in_memory_db()

        class Base(Model):
            class Meta:
                database = db

        class A(Base):
            a = TextField()
        class B(Base):
            b = TextField()

        db.create_tables([A, B])

        # Temporarily bind A to alt_db.
        with alt_db.bind_ctx([A]):
            self.assertFalse(A.table_exists())
            self.assertTrue(B.table_exists())

        self.assertTrue(A.table_exists())
        self.assertTrue(B.table_exists())

        alt_db.bind([A])
        self.assertFalse(A.table_exists())
        self.assertTrue(B.table_exists())
        db.close()
        alt_db.close()

    def test_batch_commit(self):
        class PatchCommitDatabase(SqliteDatabase):
            commits = 0
            def begin(self): pass
            def commit(self):
                self.commits += 1

        db = PatchCommitDatabase(':memory:')

        def assertBatches(n_objs, batch_size, n_commits):
            accum = []
            source = range(n_objs)
            db.commits = 0
            for item in db.batch_commit(source, batch_size):
                accum.append(item)

            self.assertEqual(accum, list(range(n_objs)))
            self.assertEqual(db.commits, n_commits)

        assertBatches(12, 1, 12)
        assertBatches(12, 2, 6)
        assertBatches(12, 3, 4)
        assertBatches(12, 4, 3)
        assertBatches(12, 5, 3)
        assertBatches(12, 6, 2)
        assertBatches(12, 7, 2)
        assertBatches(12, 11, 2)
        assertBatches(12, 12, 1)
        assertBatches(12, 13, 1)

    def test_server_version(self):
        class FakeDatabase(Database):
            server_version = None
            def _connect(self):
                return 1
            def _close(self, conn):
                pass
            def _set_server_version(self, conn):
                self.server_version = (1, 33, 7)

        db = FakeDatabase(':memory:')
        self.assertTrue(db.server_version is None)
        db.connect()
        self.assertEqual(db.server_version, (1, 33, 7))
        db.close()
        self.assertEqual(db.server_version, (1, 33, 7))

        db.server_version = (1, 2, 3)
        db.connect()
        self.assertEqual(db.server_version, (1, 2, 3))
        db.close()

    def test_explicit_connect(self):
        db = get_in_memory_db(autoconnect=False)
        self.assertRaises(InterfaceError, db.execute_sql, 'pragma cache_size')
        with db:
            db.execute_sql('pragma cache_size')
        self.assertRaises(InterfaceError, db.cursor)


class TestThreadSafety(ModelTestCase):
    nthreads = 4
    nrows = 10
    requires = [User]

    def test_multiple_writers(self):
        def create_users(idx):
            for i in range(idx * self.nrows, (idx + 1) * self.nrows):
                User.create(username='u%d' % i)

        threads = []
        for i in range(self.nthreads):
            threads.append(threading.Thread(target=create_users, args=(i,)))

        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(User.select().count(), self.nrows * self.nthreads)

    def test_multiple_readers(self):
        data = Queue()
        def read_user_count(n):
            for i in range(n):
                data.put(User.select().count())

        threads = []
        for i in range(self.nthreads):
            threads.append(threading.Thread(target=read_user_count,
                                            args=(self.nrows,)))

        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(data.qsize(), self.nrows * self.nthreads)


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


@requires_postgresql
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


class Note(TestModel):
    content = TextField()
    ts = DateTimeField()
    status = IntegerField()

    class Meta:
        table_name = 'notes'


class TestIntrospection(ModelTestCase):
    requires = [Category, User, UniqueModel, IndexedModel]

    def test_table_exists(self):
        self.assertTrue(self.database.table_exists(User._meta.table_name))
        self.assertFalse(self.database.table_exists('nuggies'))

    def test_get_tables(self):
        tables = self.database.get_tables()
        required = set(m._meta.table_name for m in self.requires)
        self.assertTrue(required.issubset(set(tables)))

        UniqueModel._schema.drop_all()
        tables = self.database.get_tables()
        self.assertFalse(UniqueModel._meta.table_name in tables)

    def test_get_indexes(self):
        indexes = self.database.get_indexes('unique_model')
        data = [(index.name, index.columns, index.unique, index.table)
                for index in indexes
                if index.name not in ('unique_model_pkey', 'PRIMARY')]
        self.assertEqual(data, [
            ('unique_model_name', ['name'], True, 'unique_model')])

        indexes = self.database.get_indexes('indexed_model')
        data = [(index.name, index.columns, index.unique, index.table)
                for index in indexes
                if index.name not in ('indexed_model_pkey', 'PRIMARY')]
        self.assertEqual(sorted(data), [
            ('indexed_model_first_last', ['first', 'last'], False,
             'indexed_model'),
            ('indexed_model_first_last_dob', ['first', 'last', 'dob'], True,
             'indexed_model')])

    def test_get_columns(self):
        columns = self.database.get_columns('indexed_model')
        data = [(c.name, c.null, c.primary_key, c.table)
                for c in columns]
        self.assertEqual(data, [
            ('id', False, True, 'indexed_model'),
            ('first', False, False, 'indexed_model'),
            ('last', False, False, 'indexed_model'),
            ('dob', False, False, 'indexed_model')])

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

    @requires_models(Note)
    def test_get_views(self):
        def normalize_view_meta(view_meta):
            sql_ws_norm = re.sub('\n\s+', ' ', view_meta.sql)
            return view_meta.name, (sql_ws_norm
                                    .replace('`peewee_test`.', '')
                                    .replace('`notes`.', '')
                                    .replace('`', ''))

        def assertViews(expected):
            # Create two sample views.
            self.database.execute_sql('CREATE VIEW notes_public AS '
                                      'SELECT content, ts FROM notes '
                                      'WHERE status = 1 ORDER BY ts DESC')
            self.database.execute_sql('CREATE VIEW notes_deleted AS '
                                      'SELECT content FROM notes '
                                      'WHERE status = 9 ORDER BY id DESC')
            try:
                views = self.database.get_views()
                normalized = sorted([normalize_view_meta(v) for v in views])
                self.assertEqual(normalized, expected)

                # Ensure that we can use get_columns to introspect views.
                columns = self.database.get_columns('notes_deleted')
                self.assertEqual([c.name for c in columns], ['content'])

                columns = self.database.get_columns('notes_public')
                self.assertEqual([c.name for c in columns], ['content', 'ts'])
            finally:
                self.database.execute_sql('DROP VIEW notes_public;')
                self.database.execute_sql('DROP VIEW notes_deleted;')

        # Unfortunately, all databases seem to represent VIEW definitions
        # differently internally.
        if IS_SQLITE:
            assertViews([
                ('notes_deleted', ('CREATE VIEW notes_deleted AS '
                                   'SELECT content FROM notes '
                                   'WHERE status = 9 ORDER BY id DESC')),
                ('notes_public', ('CREATE VIEW notes_public AS '
                                  'SELECT content, ts FROM notes '
                                  'WHERE status = 1 ORDER BY ts DESC'))])
        elif IS_MYSQL:
            assertViews([
                ('notes_deleted',
                 ('select content AS content from notes '
                  'where status = 9 order by id desc')),
                ('notes_public',
                 ('select content AS content,ts AS ts from notes '
                  'where status = 1 order by ts desc'))])
        elif IS_POSTGRESQL:
            assertViews([
                ('notes_deleted',
                 ('SELECT notes.content FROM notes '
                  'WHERE (notes.status = 9) ORDER BY notes.id DESC;')),
                ('notes_public',
                 ('SELECT notes.content, notes.ts FROM notes '
                  'WHERE (notes.status = 1) ORDER BY notes.ts DESC;'))])

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
    def test_proxy_context_manager(self):
        db = Proxy()
        class User(Model):
            username = TextField()

            class Meta:
                database = db

        self.assertRaises(AttributeError, User.create_table)

        sqlite_db = SqliteDatabase(':memory:')
        db.initialize(sqlite_db)
        User.create_table()
        with db:
            self.assertFalse(db.is_closed())
        self.assertTrue(db.is_closed())

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

    def test_proxy_decorator(self):
        db = DatabaseProxy()

        @db.connection_context()
        def with_connection():
            self.assertFalse(db.is_closed())

        @db.atomic()
        def with_transaction():
            self.assertTrue(db.in_transaction())

        @db.manual_commit()
        def with_manual_commit():
            self.assertTrue(db.in_transaction())

        db.initialize(SqliteDatabase(':memory:'))
        with_connection()
        self.assertTrue(db.is_closed())
        with_transaction()
        self.assertFalse(db.in_transaction())
        with_manual_commit()
        self.assertFalse(db.in_transaction())


class Data(TestModel):
    key = TextField()
    value = TextField()

    class Meta:
        schema = 'main'


class TestAttachDatabase(ModelTestCase):
    database = db_loader('sqlite3')
    requires = [Data]

    def test_attach(self):
        database = self.database
        Data.create(key='k1', value='v1')
        Data.create(key='k2', value='v2')

        # Attach an in-memory cache database.
        database.attach(':memory:', 'cache')

        # Clone data into the in-memory cache.
        class CacheData(Data):
            class Meta:
                schema = 'cache'

        self.assertFalse(CacheData.table_exists())
        CacheData.create_table(safe=False)
        self.assertTrue(CacheData.table_exists())

        (CacheData
         .insert_from(Data.select(), fields=[Data.id, Data.key, Data.value])
         .execute())

        # Update the source data.
        query = Data.update({Data.value: Data.value + '-x'})
        self.assertEqual(query.execute(), 2)

        # Verify the source data was updated.
        query = Data.select(Data.key, Data.value).order_by(Data.key)
        self.assertSQL(query, (
            'SELECT "t1"."key", "t1"."value" '
            'FROM "main"."data" AS "t1" '
            'ORDER BY "t1"."key"'), [])
        self.assertEqual([v for k, v in query.tuples()], ['v1-x', 'v2-x'])

        # Verify the cached data reflects the original data, pre-update.
        query = (CacheData
                 .select(CacheData.key, CacheData.value)
                 .order_by(CacheData.key))
        self.assertSQL(query, (
            'SELECT "t1"."key", "t1"."value" '
            'FROM "cache"."cache_data" AS "t1" '
            'ORDER BY "t1"."key"'), [])
        self.assertEqual([v for k, v in query.tuples()], ['v1', 'v2'])

        database.close()

        # On re-connecting, the in-memory database will re-attached.
        database.connect()

        # Cache-Data table does not exist.
        self.assertFalse(CacheData.table_exists())

        # Double-check the sqlite master table.
        curs = database.execute_sql('select * from cache.sqlite_master;')
        self.assertEqual(curs.fetchall(), [])

        # Because it's in-memory, the table needs to be re-created.
        CacheData.create_table(safe=False)
        self.assertEqual(CacheData.select().count(), 0)

        # Original data is still there.
        self.assertEqual(Data.select().count(), 2)

    def test_attach_detach(self):
        database = self.database
        Data.create(key='k1', value='v1')
        Data.create(key='k2', value='v2')

        # Attach an in-memory cache database.
        database.attach(':memory:', 'cache')
        curs = database.execute_sql('select * from cache.sqlite_master')
        self.assertEqual(curs.fetchall(), [])

        self.assertFalse(database.attach(':memory:', 'cache'))
        self.assertRaises(OperationalError, database.attach, 'foo.db', 'cache')

        self.assertTrue(database.detach('cache'))
        self.assertFalse(database.detach('cache'))
        self.assertRaises(OperationalError, database.execute_sql,
                          'select * from cache.sqlite_master')

    def test_sqlite_schema_support(self):
        class CacheData(Data):
            class Meta:
                schema = 'cache'

        # Attach an in-memory cache database and create the cache table.
        self.database.attach(':memory:', 'cache')
        CacheData.create_table()

        tables = self.database.get_tables()
        self.assertEqual(tables, ['data'])

        tables = self.database.get_tables(schema='cache')
        self.assertEqual(tables, ['cache_data'])


class TestDatabaseConnection(DatabaseTestCase):
    def test_is_connection_usable(self):
        # Ensure a connection is open.
        conn = self.database.connection()
        self.assertTrue(self.database.is_connection_usable())

        self.database.close()
        self.assertFalse(self.database.is_connection_usable())
        self.database.connect()
        self.assertTrue(self.database.is_connection_usable())

    @requires_postgresql
    def test_is_connection_usable_pg(self):
        self.database.execute_sql('drop table if exists foo')
        self.database.execute_sql('create table foo (data text not null)')
        self.assertTrue(self.database.is_connection_usable())

        with self.assertRaises(IntegrityError):
            self.database.execute_sql('insert into foo (data) values (NULL)')

        self.assertFalse(self.database.is_closed())
        self.assertFalse(self.database.is_connection_usable())
        self.database.rollback()
        self.assertTrue(self.database.is_connection_usable())

        curs = self.database.execute_sql('select * from foo')
        self.assertEqual(list(curs), [])
        self.database.execute_sql('drop table foo')
