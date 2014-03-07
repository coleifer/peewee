import heapq
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
    def __init__(self, *args, **kwargs):
        super(TestDB, self).__init__(*args, **kwargs)
        self.conn_key = lambda conn: conn

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

        # Wait for all connections to be opened.
        while db.counter < 5:
            time.sleep(.01)

        # Signal threads to close connections and join threads.
        signal.set()
        [t.join() for t in threads]

        self.assertEqual(db.counter, 5)
        self.assertEqual(db._in_use, {})

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

    def test_manual_close(self):
        conn = self.db.get_conn()
        self.assertEqual(conn, 1)

        self.db.manual_close()
        conn = self.db.get_conn()
        self.assertEqual(conn, 2)

        self.db.close()
        conn = self.db.get_conn()
        self.assertEqual(conn, 2)

    def test_stale_timeout_cascade(self):
        now = time.time()
        db = TestDB('testing', stale_timeout=10)
        conns = [
            (now - 20, 1),
            (now - 15, 2),
            (now - 5, 3),
            (now, 4),
        ]
        for ts_conn in conns:
            heapq.heappush(db._connections, ts_conn)

        self.assertEqual(db.get_conn(), 3)
        self.assertEqual(db._in_use, {3: now - 5})
        self.assertEqual(db._connections, [(now, 4)])

    def test_connect_cascade(self):
        now = time.time()
        db = TestDB('testing', stale_timeout=10)

        conns = [
            (now - 15, 1),  # Skipped due to being stale.
            (now - 5, 2),  # In the 'closed' set.
            (now - 3, 3),
            (now, 4),  # In the 'closed' set.
        ]
        db._closed.add(2)
        db._closed.add(4)
        db.counter = 4  # The next connection we create will have id=5.
        for ts_conn in conns:
            heapq.heappush(db._connections, ts_conn)

        # Conn 3 is not stale or closed, so we will get it.
        self.assertEqual(db.get_conn(), 3)
        self.assertEqual(db._in_use, {3: now - 3})
        self.assertEqual(db._connections, [(now, 4)])

        # Since conn 4 is closed, we will open a new conn.
        db.connect()
        self.assertEqual(db.get_conn(), 5)
        self.assertEqual(sorted(db._in_use.keys()), [3, 5])
        self.assertEqual(db._connections, [])


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
            list(range(10)))
