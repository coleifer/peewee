import psycopg2  # Trigger import error if not installed.
import threading
import time
from unittest import TestCase

from peewee import *
from playhouse.pool import *

class FakeDatabase(SqliteDatabase):
    def __init__(self, *args, **kwargs):
        self.counter = 0
        self.closed_counter = 0
        super(FakeDatabase, self).__init__(*args, **kwargs)

    def _connect(self, *args, **kwargs):
        """
        Return increasing integers instead of actual database connections.
        """
        self.counter += 1
        return self.counter

    def _close(self, conn):
        self.closed_counter += 1

class TestDB(PooledDatabase, FakeDatabase):
    pass

pooled_db = PooledPostgresqlDatabase('peewee_test')
normal_db = PostgresqlDatabase('peewee_test')

class Number(Model):
    value = IntegerField()

    class Meta:
        database = pooled_db

class TestPooledDatabase(TestCase):
    def setUp(self):
        self.db = TestDB('testing')

    def test_connection_pool(self):
        # Ensure that a connection is created and accessible.
        self.assertEqual(self.db.get_conn(), 1)
        self.assertEqual(self.db.get_conn(), 1)

        # Ensure that closing and reopening will return the same connection.
        self.db.close()
        self.db.connect()
        self.assertEqual(self.db.get_conn(), 1)

    def test_concurrent_connections(self):
        db = TestDB('testing', threadlocals=True)
        signal = threading.Event()

        def open_conn():
            db.connect()
            signal.wait()
            db.close()

        # Simulate 5 concurrent connections.
        threads = [threading.Thread(target=open_conn) for i in range(5)]
        for thread in threads:
            thread.start()
        signal.set()
        [t.join() for t in threads]

        self.assertEqual(db.counter, 5)
        self.assertEqual(db.in_use, {})

    def test_max_conns(self):
        for i in range(self.db.max_connections):
            self.db.connect()
            self.assertEqual(self.db.get_conn(), i + 1)
        self.assertRaises(ValueError, self.db.connect)

    def test_stale_timeout(self):
        # Create a test database with a very short stale timeout.
        db = TestDB('testing', stale_timeout=.01)
        self.assertEqual(db.get_conn(), 1)

        # Return the connection to the pool.
        db.close()

        # Sleep long enough for the connection to be considered stale.
        time.sleep(.01)

        # A new connection will be returned.
        self.assertEqual(db.get_conn(), 2)


class TestConnectionPool(TestCase):
    def setUp(self):
        # Use an un-pooled database to drop/create the table.
        if Number._meta.db_table in normal_db.get_tables():
            normal_db.drop_table(Number)
        normal_db.create_table(Number)

    def test_reuse_connection(self):
        for i in range(5):
            Number.create(value=i)
        conn_id = id(pooled_db.get_conn())
        pooled_db.close()

        for i in range(5, 10):
            Number.create(value=i)
        self.assertEqual(id(pooled_db.get_conn()), conn_id)

        self.assertEqual(
            [x.value for x in Number.select().order_by(Number.id)],
            range(10))
