import heapq
import os
import threading
import time

from peewee import *
from peewee import _savepoint
from peewee import _transaction
from playhouse.pool import *

from .base import BaseTestCase
from .base import ModelTestCase
from .base_models import Register


class FakeTransaction(_transaction):
    def _add_history(self, message):
        self.db.transaction_history.append(
            '%s%s' % (message, self._conn))

    def __enter__(self):
        self._conn = self.db.connection()
        self._add_history('O')
        self.db.push_transaction(self)

    def __exit__(self, *args):
        self._add_history('X')
        self.db.pop_transaction()


class FakeDatabase(SqliteDatabase):
    def __init__(self, *args, **kwargs):
        self.counter = self.closed_counter = 0
        self.transaction_history = []
        super(FakeDatabase, self).__init__(*args, **kwargs)

    def _connect(self):
        self.counter += 1
        return self.counter

    def _close(self, conn):
        self.closed_counter += 1

    def transaction(self):
        return FakeTransaction(self)


class FakePooledDatabase(PooledDatabase, FakeDatabase):
    def __init__(self, *args, **kwargs):
        super(FakePooledDatabase, self).__init__(*args, **kwargs)
        self.conn_key = lambda conn: conn


class PooledTestDatabase(PooledDatabase, SqliteDatabase):
    pass


class TestPooledDatabase(BaseTestCase):
    def setUp(self):
        super(TestPooledDatabase, self).setUp()
        self.db = FakePooledDatabase('testing')

    def test_connection_pool(self):
        self.assertEqual(self.db.connection(), 1)
        self.assertEqual(self.db.connection(), 1)

        self.db.close()
        self.db.connect()
        self.assertEqual(self.db.connection(), 1)

    def test_concurrent_connections(self):
        db = FakePooledDatabase('testing')
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
        for t in threads: t.join()

        self.assertEqual(db.counter, 5)
        self.assertEqual(
            sorted([conn for _, conn in db._connections]),
            [1, 2, 3, 4, 5])  # All 5 are ready to be re-used.
        self.assertEqual(db._in_use, {})

    def test_max_conns(self):
        for i in range(self.db._max_connections):
            self.db._state.closed = True  # Hack to make it appear closed.
            self.db.connect()
            self.assertEqual(self.db.connection(), i + 1)
        self.db._state.closed = True
        self.assertRaises(ValueError, self.db.connect)

    def test_stale_timeout(self):
        # Create a test database with a very short stale timeout.
        db = FakePooledDatabase('testing', stale_timeout=.001)
        self.assertEqual(db.connection(), 1)
        self.assertTrue(1 in db._in_use)

        # Sleep long enough for the connection to be considered stale.
        time.sleep(.001)

        # When we close, since the conn is stale it won't be returned to
        # the pool.
        db.close()
        self.assertEqual(db._in_use, {})
        self.assertEqual(db._connections, [])
        self.assertEqual(db._closed, set())

        # A new connection will be returned.
        self.assertEqual(db.connection(), 2)

    def test_stale_on_checkout(self):
        # Create a test database with a very short stale timeout.
        db = FakePooledDatabase('testing', stale_timeout=.005)
        self.assertEqual(db.connection(), 1)
        self.assertTrue(1 in db._in_use)

        # When we close, the conn should not be stale so it won't return to
        # the pool.
        db.close()
        assert len(db._connections) == 1, 'Test runner too slow!'

        # Sleep long enough for the connection to be considered stale.
        time.sleep(.005)
        self.assertEqual(db._in_use, {})
        self.assertEqual(len(db._connections), 1)

        # A new connection will be returned, as the original one is stale.
        # The stale connection (1) will be removed and not placed in the
        # "closed" set.
        self.assertEqual(db.connection(), 2)
        self.assertEqual(db._closed, set())

    def test_manual_close(self):
        self.assertEqual(self.db.connection(), 1)
        self.db.manual_close()

        # When we manually close a connection that's not yet stale, we add it
        # back to the queue (because close() calls _close()), then close it
        # for real, and mark it with a tombstone. The next time it's checked
        # out, it will simply be removed and skipped over.
        self.assertEqual(self.db._closed, set([1]))
        self.assertEqual(len(self.db._connections), 1)
        self.assertEqual(self.db._in_use, {})

        self.assertEqual(self.db.connection(), 2)
        self.assertEqual(self.db._closed, set())
        self.assertEqual(len(self.db._connections), 0)
        self.assertEqual(list(self.db._in_use.keys()), [2])

        self.db.close()
        self.assertEqual(self.db.connection(), 2)

    def test_stale_timeout_cascade(self):
        now = time.time()
        db = FakePooledDatabase('testing', stale_timeout=10)
        conns = [
            (now - 20, 1),
            (now - 15, 2),
            (now - 5, 3),
            (now, 4),
        ]
        for ts_conn in conns:
            heapq.heappush(db._connections, ts_conn)

        self.assertEqual(db.connection(), 3)
        self.assertEqual(db._in_use, {3: now - 5})
        self.assertEqual(db._connections, [(now, 4)])

    def test_connect_cascade(self):
        now = time.time()
        db = FakePooledDatabase('testing', stale_timeout=10)

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
        self.assertEqual(db.connection(), 3)
        self.assertEqual(db._in_use, {3: now - 3})
        self.assertEqual(db._connections, [(now, 4)])

        # Since conn 4 is closed, we will open a new conn.
        db._state.closed = True  # Pretend we're in a different thread.
        db.connect()
        self.assertEqual(db.connection(), 5)
        self.assertEqual(sorted(db._in_use.keys()), [3, 5])
        self.assertEqual(db._connections, [])

    def test_db_context(self):
        self.assertEqual(self.db.connection(), 1)
        with self.db:
            self.assertEqual(self.db.connection(), 1)
            self.assertEqual(self.db.transaction_history, ['O1'])

        self.assertEqual(self.db.connection(), 1)
        self.assertEqual(self.db.transaction_history, ['O1', 'X1'])

        with self.db:
            self.assertEqual(self.db.connection(), 1)

        self.assertEqual(len(self.db._connections), 1)
        self.assertEqual(len(self.db._in_use), 0)

    def test_db_context_threads(self):
        signal = threading.Event()
        def create_context():
            with self.db:
                signal.wait()

        threads = [threading.Thread(target=create_context) for i in range(5)]
        for thread in threads: thread.start()

        while len(self.db.transaction_history) < 5:
            time.sleep(.001)

        signal.set()
        for thread in threads: thread.join()

        self.assertEqual(self.db.counter, 5)
        self.assertEqual(len(self.db._connections), 5)
        self.assertEqual(len(self.db._in_use), 0)


class TestLivePooledDatabase(ModelTestCase):
    database = PooledTestDatabase('test_pooled.db')
    requires = [Register]

    def tearDown(self):
        super(TestLivePooledDatabase, self).tearDown()
        self.database.close_all()
        if os.path.exists('test_pooled.db'):
            os.unlink('test_pooled.db')

    def test_reuse_connection(self):
        for i in range(5):
            Register.create(value=i)
        conn_id = id(self.database.connection())
        self.database.close()

        for i in range(5, 10):
            Register.create(value=i)
        self.assertEqual(id(self.database.connection()), conn_id)
        self.assertEqual(
            [x.value for x in Register.select().order_by(Register.id)],
            list(range(10)))

    def test_db_context(self):
        with self.database:
            Register.create(value=1)
            with self.database.atomic() as sp:
                self.assertTrue(isinstance(sp, _savepoint))
                Register.create(value=2)
                sp.rollback()

            with self.database.atomic() as sp:
                self.assertTrue(isinstance(sp, _savepoint))
                Register.create(value=3)

        with self.database:
            values = [r.value for r in Register.select().order_by(Register.id)]
            self.assertEqual(values, [1, 3])

    def test_bad_connection(self):
        self.database.connection()
        try:
            self.database.execute_sql('select 1/0')
        except Exception as exc:
            pass
        self.database.close()
        self.database.connect()
