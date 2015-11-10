import os
import shutil

from peewee import IntegrityError
from playhouse.berkeleydb import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import ModelTestCase
from playhouse.tests.base import skip_unless

database = database_initializer.get_database('berkeleydb')

class BaseModel(Model):
    class Meta:
        database = database

class Person(BaseModel):
    name = CharField(unique=True)

class Message(BaseModel):
    person = ForeignKeyField(Person, related_name='messages')
    body = TextField()


@skip_unless(BerkeleyDatabase.check_pysqlite)
class TestBerkeleyDatabase(ModelTestCase):
    requires = [Person, Message]

    def setUp(self):
        self.remove_db_files()
        super(TestBerkeleyDatabase, self).setUp()

    def tearDown(self):
        super(TestBerkeleyDatabase, self).tearDown()
        if not database.is_closed():
            database.close()

    def remove_db_files(self):
        filename = database.database
        if os.path.exists(filename):
            os.unlink(filename)
        if os.path.exists(filename + '-journal'):
            shutil.rmtree(filename + '-journal')

    def test_storage_retrieval(self):
        pc = Person.create(name='charlie')
        ph = Person.create(name='huey')

        for i in range(3):
            Message.create(person=pc, body='message-%s' % i)

        self.assertEqual(Message.select().count(), 3)
        self.assertEqual(Person.select().count(), 2)
        self.assertEqual(
            [msg.body for msg in pc.messages.order_by(Message.body)],
            ['message-0', 'message-1', 'message-2'])
        self.assertEqual(list(ph.messages), [])

    def test_transaction(self):
        with database.transaction():
            Person.create(name='charlie')

        self.assertEqual(Person.select().count(), 1)

        @database.commit_on_success
        def rollback():
            Person.create(name='charlie')

        self.assertRaises(IntegrityError, rollback)
        self.assertEqual(Person.select().count(), 1)

    def _test_pragmas(self, db):
        class PragmaTest(Model):
            data = TextField()
            class Meta:
                database = db

        sql = lambda q: db.execute_sql(q).fetchone()[0]

        with db.execution_context() as ctx:
            PragmaTest.create_table()

        # Use another connection to check the pragma values.
        with db.execution_context() as ctx:
            conn = db.get_conn()
            cache = sql('PRAGMA cache_size;')
            page = sql('PRAGMA page_size;')
            mvcc = sql('PRAGMA multiversion;')
            self.assertEqual(cache, 1000)
            self.assertEqual(page, 2048)
            self.assertEqual(mvcc, 1)

        # Now, use two connections. This tests the weird behavior of the
        # BTree cache.
        conn = db.get_conn()
        self.assertEqual(sql('PRAGMA multiversion;'), 1)

        with db.execution_context():
            conn2 = db.get_conn()
            self.assertTrue(id(conn) != id(conn2))
            self.assertEqual(sql('PRAGMA cache_size;'), 1000)
            self.assertEqual(sql('PRAGMA multiversion;'), 1)
            self.assertEqual(sql('PRAGMA page_size;'), 2048)

    def test_pragmas(self):
        database.close()
        self.remove_db_files()

        db = BerkeleyDatabase(
            database.database,
            cache_size=1000,
            page_size=2048,
            multiversion=True)

        try:
            self._test_pragmas(db)
        finally:
            if not db.is_closed():
                db.close()

    def test_udf(self):
        @database.func()
        def title(s):
            return s.title()

        with database.execution_context():
            res = database.execute_sql('select title(?)', ('whats up',))
            self.assertEqual(res.fetchone(), ('Whats Up',))
