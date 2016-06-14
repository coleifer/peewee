# encoding=utf-8

import sys
import threading
try:
    from Queue import Queue
except ImportError:
    from queue import Queue

from peewee import OperationalError
from peewee import SqliteDatabase
from playhouse.tests.base import compiler
from playhouse.tests.base import database_class
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import PeeweeTestCase
from playhouse.tests.base import query_db
from playhouse.tests.base import skip_unless
from playhouse.tests.base import test_db
from playhouse.tests.base import ulit
from playhouse.tests.models import *


class TestMultiThreadedQueries(ModelTestCase):
    requires = [User]
    threads = 4

    def setUp(self):
        self._orig_db = test_db
        kwargs = {}
        try:  # Some engines need the extra kwargs.
            kwargs.update(test_db.connect_kwargs)
        except:
            pass
        if isinstance(test_db, SqliteDatabase):
            # Put a very large timeout in place to avoid `database is locked`
            # when using SQLite (default is 5).
            kwargs['timeout'] = 30

        User._meta.database = self.new_connection()
        super(TestMultiThreadedQueries, self).setUp()

    def tearDown(self):
        User._meta.database = self._orig_db
        super(TestMultiThreadedQueries, self).tearDown()

    def test_multiple_writers(self):
        def create_user_thread(low, hi):
            for i in range(low, hi):
                User.create(username='u%d' % i)
            User._meta.database.close()

        threads = []

        for i in range(self.threads):
            threads.append(threading.Thread(target=create_user_thread, args=(i*10, i * 10 + 10)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(User.select().count(), self.threads * 10)

    def test_multiple_readers(self):
        data_queue = Queue()

        def reader_thread(q, num):
            for i in range(num):
                data_queue.put(User.select().count())

        threads = []

        for i in range(self.threads):
            threads.append(threading.Thread(target=reader_thread, args=(data_queue, 20)))

        [t.start() for t in threads]
        [t.join() for t in threads]

        self.assertEqual(data_queue.qsize(), self.threads * 20)


class TestDeferredDatabase(PeeweeTestCase):
    def test_deferred_database(self):
        deferred_db = SqliteDatabase(None)
        self.assertTrue(deferred_db.deferred)

        class DeferredModel(Model):
            class Meta:
                database = deferred_db

        self.assertRaises(Exception, deferred_db.connect)
        sq = DeferredModel.select()
        self.assertRaises(Exception, sq.execute)

        deferred_db.init(':memory:')
        self.assertFalse(deferred_db.deferred)

        # connecting works
        conn = deferred_db.connect()
        DeferredModel.create_table()
        sq = DeferredModel.select()
        self.assertEqual(list(sq), [])

        deferred_db.init(None)
        self.assertTrue(deferred_db.deferred)


class TestSQLAll(PeeweeTestCase):
    def setUp(self):
        super(TestSQLAll, self).setUp()
        fake_db = SqliteDatabase(':memory:')
        UniqueModel._meta.database = fake_db
        SeqModelA._meta.database = fake_db
        MultiIndexModel._meta.database = fake_db

    def tearDown(self):
        super(TestSQLAll, self).tearDown()
        UniqueModel._meta.database = test_db
        SeqModelA._meta.database = test_db
        MultiIndexModel._meta.database = test_db

    def test_sqlall(self):
        sql = UniqueModel.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "uniquemodel" ("id" INTEGER NOT NULL PRIMARY KEY, '
             '"name" VARCHAR(255) NOT NULL)'),
            'CREATE UNIQUE INDEX "uniquemodel_name" ON "uniquemodel" ("name")',
        ])

        sql = MultiIndexModel.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "multiindexmodel" ("id" INTEGER NOT NULL PRIMARY '
             'KEY, "f1" VARCHAR(255) NOT NULL, "f2" VARCHAR(255) NOT NULL, '
             '"f3" VARCHAR(255) NOT NULL)'),
            ('CREATE UNIQUE INDEX "multiindexmodel_f1_f2" ON "multiindexmodel"'
             ' ("f1", "f2")'),
            ('CREATE INDEX "multiindexmodel_f2_f3" ON "multiindexmodel" '
             '("f2", "f3")'),
        ])

        sql = SeqModelA.sqlall()
        self.assertEqual(sql, [
            ('CREATE TABLE "seqmodela" ("id" INTEGER NOT NULL PRIMARY KEY '
             'DEFAULT NEXTVAL(\'just_testing_seq\'), "num" INTEGER NOT NULL)'),
        ])


class TestLongIndexName(PeeweeTestCase):
    def test_long_index(self):
        class LongIndexModel(TestModel):
            a123456789012345678901234567890 = CharField()
            b123456789012345678901234567890 = CharField()
            c123456789012345678901234567890 = CharField()

        fields = LongIndexModel._meta.sorted_fields[1:]
        self.assertEqual(len(fields), 3)

        sql, params = compiler.create_index(LongIndexModel, fields, False)
        self.assertEqual(sql, (
            'CREATE INDEX "longindexmodel_85c2f7db" '
            'ON "longindexmodel" ('
            '"a123456789012345678901234567890", '
            '"b123456789012345678901234567890", '
            '"c123456789012345678901234567890")'
        ))


class TestDroppingIndex(ModelTestCase):
    def test_drop_index(self):
        db = database_initializer.get_in_memory_database()

        class IndexedModel(Model):
            idx = CharField(index=True)
            uniq = CharField(unique=True)
            f1 = IntegerField()
            f2 = IntegerField()

            class Meta:
                database = db
                indexes = (
                    (('f1', 'f2'), True),
                    (('idx', 'uniq'), False),
                )

        IndexedModel.create_table()
        indexes = db.get_indexes(IndexedModel._meta.db_table)

        self.assertEqual(sorted(idx.name for idx in indexes), [
            'indexedmodel_f1_f2',
            'indexedmodel_idx',
            'indexedmodel_idx_uniq',
            'indexedmodel_uniq'])

        with self.log_queries() as query_log:
            IndexedModel._drop_indexes()

        self.assertEqual(sorted(query_log.queries), sorted([
            ('DROP INDEX "%s"' % idx.name, []) for idx in indexes]))
        self.assertEqual(db.get_indexes(IndexedModel._meta.db_table), [])


class TestConnectionState(PeeweeTestCase):
    def test_connection_state(self):
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())
        test_db.close()
        self.assertTrue(test_db.is_closed())
        conn = test_db.get_conn()
        self.assertFalse(test_db.is_closed())

    def test_sql_error(self):
        bad_sql = 'select asdf from -1;'
        self.assertRaises(Exception, query_db.execute_sql, bad_sql)
        self.assertEqual(query_db.last_error, (bad_sql, None))


@skip_unless(lambda: test_db.drop_cascade)
class TestDropTableCascade(ModelTestCase):
    requires = [User, Blog]

    def test_drop_cascade(self):
        u1 = User.create(username='u1')
        b1 = Blog.create(user=u1, title='b1')

        User.drop_table(cascade=True)
        self.assertFalse(User.table_exists())

        # The constraint is dropped, we can create a blog for a non-
        # existant user.
        Blog.create(user=-1, title='b2')


@skip_unless(lambda: test_db.sequences)
class TestDatabaseSequences(ModelTestCase):
    requires = [SeqModelA, SeqModelB]

    def test_sequence_shared(self):
        a1 = SeqModelA.create(num=1)
        a2 = SeqModelA.create(num=2)
        b1 = SeqModelB.create(other_num=101)
        b2 = SeqModelB.create(other_num=102)
        a3 = SeqModelA.create(num=3)

        self.assertEqual(a1.id, a2.id - 1)
        self.assertEqual(a2.id, b1.id - 1)
        self.assertEqual(b1.id, b2.id - 1)
        self.assertEqual(b2.id, a3.id - 1)


@skip_unless(lambda: issubclass(database_class, PostgresqlDatabase))
class TestUnicodeConversion(ModelTestCase):
    requires = [User]

    def setUp(self):
        super(TestUnicodeConversion, self).setUp()

        # Create a user object with UTF-8 encoded username.
        ustr = ulit('Ísland')
        self.user = User.create(username=ustr)

    def tearDown(self):
        super(TestUnicodeConversion, self).tearDown()
        test_db.register_unicode = True
        test_db.close()

    def reset_encoding(self, encoding):
        test_db.close()
        conn = test_db.get_conn()
        conn.set_client_encoding(encoding)

    def test_unicode_conversion(self):
        # Per psycopg2's documentation, in Python2, strings are returned as
        # 8-bit str objects encoded in the client encoding. In python3,
        # the strings are automatically decoded in the connection encoding.

        # Turn off unicode conversion on a per-connection basis.
        test_db.register_unicode = False
        self.reset_encoding('LATIN1')

        u = User.get(User.id == self.user.id)
        if sys.version_info[0] < 3:
            self.assertFalse(u.username == self.user.username)
        else:
            self.assertTrue(u.username == self.user.username)

        test_db.register_unicode = True
        self.reset_encoding('LATIN1')

        u = User.get(User.id == self.user.id)
        self.assertEqual(u.username, self.user.username)


@skip_unless(lambda: issubclass(database_class, PostgresqlDatabase))
class TestPostgresqlSchema(ModelTestCase):
    requires = [PGSchema]

    def setUp(self):
        test_db.execute_sql('CREATE SCHEMA huey;')
        super(TestPostgresqlSchema,self).setUp()

    def tearDown(self):
        super(TestPostgresqlSchema,self).tearDown()
        test_db.execute_sql('DROP SCHEMA huey;')

    def test_pg_schema(self):
        pgs = PGSchema.create(data='huey')
        pgs_db = PGSchema.get(PGSchema.data == 'huey')
        self.assertEqual(pgs.id, pgs_db.id)


@skip_unless(lambda: isinstance(test_db, SqliteDatabase))
class TestOuterLoopInnerCommit(ModelTestCase):
    requires = [User, Blog]

    def tearDown(self):
        test_db.set_autocommit(True)
        super(TestOuterLoopInnerCommit, self).tearDown()

    def test_outer_loop_inner_commit(self):
        # By default we are in autocommit mode (isolation_level=None).
        self.assertEqual(test_db.get_conn().isolation_level, None)

        for username in ['u1', 'u2', 'u3']:
            User.create(username=username)

        for user in User.select():
            Blog.create(user=user, title='b-%s' % user.username)

        # These statements are auto-committed.
        new_db = self.new_connection()
        count = new_db.execute_sql('select count(*) from blog;').fetchone()
        self.assertEqual(count[0], 3)

        self.assertEqual(Blog.select().count(), 3)
        blog_titles = [b.title for b in Blog.select().order_by(Blog.title)]
        self.assertEqual(blog_titles, ['b-u1', 'b-u2', 'b-u3'])

        self.assertEqual(Blog.delete().execute(), 3)

        # If we disable autocommit, we need to explicitly call begin().
        test_db.set_autocommit(False)
        test_db.begin()

        for user in User.select():
            Blog.create(user=user, title='b-%s' % user.username)

        # These statements have not been committed.
        new_db = self.new_connection()
        count = new_db.execute_sql('select count(*) from blog;').fetchone()
        self.assertEqual(count[0], 0)

        self.assertEqual(Blog.select().count(), 3)
        blog_titles = [b.title for b in Blog.select().order_by(Blog.title)]
        self.assertEqual(blog_titles, ['b-u1', 'b-u2', 'b-u3'])

        test_db.commit()
        count = new_db.execute_sql('select count(*) from blog;').fetchone()
        self.assertEqual(count[0], 3)


class TestConnectionInitialization(PeeweeTestCase):
    def test_initialize_connection(self):
        state = {'initialized': 0}

        class TestDatabase(SqliteDatabase):
            def initialize_connection(self, conn):
                state['initialized'] += 1

                # Ensure we can execute a query at this point.
                self.execute_sql('pragma stats;').fetchone()

        db = TestDatabase(':memory:')
        self.assertFalse(state['initialized'])

        conn = db.get_conn()
        self.assertEqual(state['initialized'], 1)

        # Since a conn is already open, this will return the existing conn.
        conn = db.get_conn()
        self.assertEqual(state['initialized'], 1)

        db.close()
        db.connect()
        self.assertEqual(state['initialized'], 2)
