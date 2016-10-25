import heapq
import psycopg2  # Trigger import error if not installed.
import threading
import time

from peewee import *
from peewee import savepoint
from peewee import transaction
from playhouse.pool import *
from playhouse.tests.base import database_initializer
from playhouse.tests.base import PeeweeTestCase


class FakeTransaction(transaction):
    def _add_history(self, message):
        self.db.transaction_history.append(
            '%s%s' % (message, self._conn))

    def __enter__(self):
        self._conn = self.db.get_conn()
        self._add_history('O')

    def commit(self, begin=True):
        self._add_history('C')

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._add_history('X')

class FakeDatabase(SqliteDatabase):
    def __init__(self, *args, **kwargs):
        self.counter = 0
        self.closed_counter = 0
        self.transaction_history = []
        super(FakeDatabase, self).__init__(*args, **kwargs)

    def _connect(self, *args, **kwargs):
        """
        Return increasing integers instead of actual database connections.
        """
        self.counter += 1
        return self.counter

    def _close(self, conn):
        self.closed_counter += 1

    def transaction(self):
        return FakeTransaction(self)

class TestDB(PooledDatabase, FakeDatabase):
    def __init__(self, *args, **kwargs):
        super(TestDB, self).__init__(*args, **kwargs)
        self.conn_key = lambda conn: conn

pooled_db = database_initializer.get_database(
    'postgres',
    db_class=PooledPostgresqlDatabase)
normal_db = database_initializer.get_database('postgres')

class Number(Model):
    value = IntegerField()

    class Meta:
        database = pooled_db


class TestPooledDatabase(PeeweeTestCase):
    def setUp(self):
        super(TestPooledDatabase, self).setUp()
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
        db = TestDB('testing')
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
        self.assertEqual(
            sorted([conn for _, conn in db._connections]),
            [1, 2, 3, 4, 5])  # All 5 are ready to be re-used.
        self.assertEqual(db._in_use, {})

    def test_max_conns(self):
        for i in range(self.db.max_connections):
            self.db._local.closed = True
            self.db.connect()
            self.assertEqual(self.db.get_conn(), i + 1)
        self.db._local.closed = True
        self.assertRaises(ValueError, self.db.connect)

    def test_stale_timeout(self):
        # Create a test database with a very short stale timeout.
        db = TestDB('testing', stale_timeout=.01)
        self.assertEqual(db.get_conn(), 1)
        self.assertTrue(1 in db._in_use)

        # Sleep long enough for the connection to be considered stale.
        time.sleep(.01)

        # When we close, since the conn is stale it won't be returned to
        # the pool.
        db.close()
        self.assertEqual(db._in_use, {})
        self.assertEqual(db._connections, [])
        self.assertEqual(db._closed, set())

        # A new connection will be returned.
        self.assertEqual(db.get_conn(), 2)

    def test_stale_on_checkout(self):
        # Create a test database with a very short stale timeout.
        db = TestDB('testing', stale_timeout=.01)
        self.assertEqual(db.get_conn(), 1)
        self.assertTrue(1 in db._in_use)

        # When we close, the conn should not be stale so it won't return to
        # the pool.
        db.close()

        # Sleep long enough for the connection to be considered stale.
        time.sleep(.01)

        self.assertEqual(db._in_use, {})
        self.assertEqual(len(db._connections), 1)

        # A new connection will be returned, as the original one is stale.
        # The stale connection (1) will be removed and not placed in the
        # "closed" set.
        self.assertEqual(db.get_conn(), 2)
        self.assertEqual(db._closed, set())

    def test_manual_close(self):
        conn = self.db.get_conn()
        self.assertEqual(conn, 1)

        self.db.manual_close()

        # When we manually close a connection that's not yet stale, we add it
        # back to the queue (because close() calls _close()), then close it
        # for real, and mark it with a tombstone. The next time it's checked
        # out, it will simply be removed and skipped over.
        self.assertEqual(self.db._closed, set([1]))
        self.assertEqual(len(self.db._connections), 1)
        self.assertEqual(self.db._in_use, {})

        conn = self.db.get_conn()
        self.assertEqual(conn, 2)
        self.assertEqual(self.db._closed, set())
        self.assertEqual(len(self.db._connections), 0)
        self.assertEqual(list(self.db._in_use.keys()), [2])

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
        db._local.closed = True  # Pretend we're in a different thread.
        db.connect()
        self.assertEqual(db.get_conn(), 5)
        self.assertEqual(sorted(db._in_use.keys()), [3, 5])
        self.assertEqual(db._connections, [])

    def test_execution_context(self):
        self.assertEqual(self.db.get_conn(), 1)
        with self.db.execution_context():
            self.assertEqual(self.db.get_conn(), 2)
            self.assertEqual(self.db.transaction_history, ['O2'])

        self.assertEqual(self.db.get_conn(), 1)
        self.assertEqual(self.db.transaction_history, ['O2', 'C2', 'X2'])

        with self.db.execution_context(with_transaction=False):
            self.assertEqual(self.db.get_conn(), 2)
            self.assertEqual(self.db.transaction_history, ['O2', 'C2', 'X2'])

        self.assertEqual(self.db.get_conn(), 1)
        self.assertEqual(self.db.transaction_history, ['O2', 'C2', 'X2'])
        self.assertEqual(len(self.db._connections), 1)
        self.assertEqual(len(self.db._in_use), 1)

    def test_execution_context_nested(self):
        def assertInUse(n):
            self.assertEqual(len(self.db._in_use), n)

        def assertFree(n):
            self.assertEqual(len(self.db._connections), n)

        def assertHistory(history):
            self.assertEqual(self.db.transaction_history, history)

        @self.db.execution_context()
        def subroutine():
            pass

        self.assertEqual(self.db.get_conn(), 1)
        assertFree(0)
        assertInUse(1)

        with self.db.execution_context(False):
            self.assertEqual(self.db.get_conn(), 2)
            assertFree(0)
            assertInUse(2)
            assertHistory([])

            with self.db.execution_context():
                self.assertEqual(self.db.get_conn(), 3)
                assertFree(0)
                assertInUse(3)
                assertHistory(['O3'])

                subroutine()
                assertFree(1)
                assertInUse(3)
                assertHistory(['O3', 'O4', 'C4', 'X4'])

            assertFree(2)
            assertInUse(2)
            assertHistory(['O3', 'O4', 'C4', 'X4', 'C3', 'X3'])

            # Since conn 3 has been returned to the pool, the subroutine
            # will use conn3 this time.
            subroutine()
            assertFree(2)
            assertInUse(2)
            assertHistory(
                ['O3', 'O4', 'C4', 'X4', 'C3', 'X3', 'O3', 'C3', 'X3'])

        self.assertEqual(self.db.get_conn(), 1)
        assertFree(3)
        assertInUse(1)
        assertHistory(['O3', 'O4', 'C4', 'X4', 'C3', 'X3', 'O3', 'C3', 'X3'])

    def test_execution_context_threads(self):
        signal = threading.Event()

        def create_context():
            with self.db.execution_context():
                signal.wait()

        # Simulate 5 concurrent connections.
        threads = [threading.Thread(target=create_context) for i in range(5)]
        for thread in threads:
            thread.start()

        # Wait for all connections to be opened.
        while len(self.db.transaction_history) < 5:
            time.sleep(.01)

        # Signal threads to close connections and join threads.
        signal.set()
        [t.join() for t in threads]

        self.assertEqual(self.db.counter, 5)
        self.assertEqual(len(self.db._connections), 5)
        self.assertEqual(len(self.db._in_use), 0)
        self.assertEqual(
            self.db.transaction_history[:5],
            ['O1', 'O2', 'O3', 'O4', 'O5'])
        rest = sorted(self.db.transaction_history[5:])
        self.assertEqual(
            rest,
            ['C1', 'C2', 'C3', 'C4', 'C5', 'X1', 'X2', 'X3', 'X4', 'X5'])

    def test_execution_context_mixed_thread(self):
        sig_sub = threading.Event()
        sig_ctx = threading.Event()
        sig_in_sub = threading.Event()
        sig_in_ctx = threading.Event()
        self.assertEqual(self.db.get_conn(), 1)

        @self.db.execution_context()
        def subroutine():
            sig_in_sub.set()
            sig_sub.wait()

        def target():
            with self.db.execution_context():
                subroutine()
                sig_in_ctx.set()
                sig_ctx.wait()

        t = threading.Thread(target=target)
        t.start()

        sig_in_sub.wait()
        self.assertEqual(len(self.db._in_use), 3)
        self.assertEqual(len(self.db._connections), 0)
        self.assertEqual(self.db.transaction_history, ['O2', 'O3'])

        sig_sub.set()
        sig_in_ctx.wait()

        self.assertEqual(len(self.db._in_use), 2)
        self.assertEqual(len(self.db._connections), 1)
        self.assertEqual(
            self.db.transaction_history,
            ['O2', 'O3', 'C3', 'X3'])

        sig_ctx.set()
        t.join()

        self.assertEqual(len(self.db._in_use), 1)
        self.assertEqual(len(self.db._connections), 2)
        self.assertEqual(
            self.db.transaction_history,
            ['O2', 'O3', 'C3', 'X3', 'C2', 'X2'])


class TestConnectionPool(PeeweeTestCase):
    def setUp(self):
        super(TestConnectionPool, self).setUp()
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

    def test_execution_context(self):
        with pooled_db.execution_context():
            Number.create(value=1)
            with pooled_db.atomic() as sp:
                self.assertTrue(isinstance(sp, savepoint))
                Number.create(value=2)
                sp.rollback()

            with pooled_db.atomic() as sp:
                self.assertTrue(isinstance(sp, savepoint))
                Number.create(value=3)

        with pooled_db.execution_context(with_transaction=False):
            with pooled_db.atomic() as txn:
                self.assertTrue(isinstance(txn, transaction))
                Number.create(value=4)

            # Executed in autocommit mode.
            Number.create(value=5)

        with pooled_db.execution_context():
            numbers = [
                number.value
                for number in Number.select().order_by(Number.value)]

        self.assertEqual(numbers, [1, 3, 4, 5])
