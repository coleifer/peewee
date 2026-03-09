import heapq
import os
import threading
import time

from peewee import *
from peewee import _savepoint
from peewee import _transaction
from playhouse.cockroachdb import PooledCockroachDatabase
from playhouse.pool import *

from .base import BACKEND
from .base import BaseTestCase
from .base import IS_CRDB
from .base import IS_MYSQL
from .base import IS_POSTGRESQL
from .base import IS_SQLITE
from .base import ModelTestCase
from .base import db_loader
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
        self.counter = self.closed_counter = kwargs.pop('counter', 0)
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


def push_conn(db, timestamp, conn):
    # Push a connection onto the pool heap with a proper monotonic counter.
    db._heap_counter += 1
    heapq.heappush(db._connections, (timestamp, db._heap_counter, conn))


class TestPooledDatabase(BaseTestCase):
    def setUp(self):
        super(TestPooledDatabase, self).setUp()
        self.db = FakePooledDatabase('testing')

    def test_connection_pool(self):
        # Closing and reopening a connection returns us the same conn.
        self.assertEqual(self.db.connection(), 1)
        self.assertEqual(self.db.connection(), 1)

        self.db.close()
        self.db.connect()
        self.assertEqual(self.db.connection(), 1)

    def test_reuse_connection(self):
        # Verify the connection pool correctly handles calling connect twice.
        self.assertEqual(self.db.connection(), 1)
        self.assertRaises(OperationalError, self.db.connect)
        self.assertFalse(self.db.connect(reuse_if_open=True))

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
            sorted([conn for _, _, conn in db._connections]),
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
        # The stale connection (1) will be removed.
        self.assertEqual(db.connection(), 2)

    def test_manual_close(self):
        self.assertEqual(self.db.connection(), 1)
        self.db.manual_close()

        # When we manually close a connection that's not yet stale, we add it
        # back to the queue (because close() calls _close()), then close it
        # for real, and mark it with a tombstone. The next time it's checked
        # out, it will simply be removed and skipped over.
        self.assertEqual(len(self.db._connections), 0)
        self.assertEqual(self.db._in_use, {})

        self.assertEqual(self.db.connection(), 2)
        self.assertEqual(len(self.db._connections), 0)
        self.assertEqual(list(self.db._in_use.keys()), [2])

        self.db.close()
        self.assertEqual(self.db.connection(), 2)

    def test_close_idle(self):
        db = FakePooledDatabase('testing', counter=3)

        now = time.time()
        now = time.time()
        push_conn(db, now - 10, 3)
        push_conn(db, now - 5, 2)
        push_conn(db, now - 1, 1)

        self.assertEqual(db.connection(), 3)
        self.assertTrue(3 in db._in_use)

        db.close_idle()
        self.assertEqual(len(db._connections), 0)
        self.assertEqual(len(db._in_use), 1)
        self.assertTrue(3 in db._in_use)
        self.assertEqual(db.connection(), 3)

        db.manual_close()
        self.assertEqual(db.connection(), 4)

    def test_close_stale(self):
        db = FakePooledDatabase('testing', counter=3)

        now = time.time()
        # Closing stale uses the last checkout time rather than the creation
        # time for the connection.
        db._in_use[1] = PoolConnection(now - 400, 1, now - 300)
        db._in_use[2] = PoolConnection(now - 200, 2, now - 200)
        db._in_use[3] = PoolConnection(now - 300, 3, now - 100)
        db._in_use[4] = PoolConnection(now, 4, now)
        self.assertEqual(db.close_stale(age=200), 2)
        self.assertEqual(len(db._in_use), 2)
        self.assertEqual(sorted(db._in_use), [3, 4])

    def test_close_all(self):
        db = FakePooledDatabase('testing', counter=3)

        now = time.time()
        push_conn(db, now - 10, 3)
        push_conn(db, now - 5, 2)
        push_conn(db, now - 1, 1)
        self.assertEqual(db.connection(), 3)
        self.assertTrue(3 in db._in_use)

        db.close_all()
        self.assertEqual(len(db._connections), 0)
        self.assertEqual(len(db._in_use), 0)

        self.assertEqual(db.connection(), 4)

    def test_stale_timeout_cascade(self):
        now = time.time()
        db = FakePooledDatabase('testing', stale_timeout=10)
        conns = [
            (now - 20, 1),
            (now - 15, 2),
            (now - 5, 3),
            (now, 4),
        ]
        for ts, conn in conns:
            push_conn(db, ts, conn)

        self.assertEqual(db.connection(), 3)
        self.assertEqual(len(db._in_use), 1)
        self.assertTrue(3 in db._in_use)
        self.assertEqual(len(db._connections), 1)
        self.assertEqual(db._connections[0][2], 4)

    def test_connect_cascade(self):
        now = time.time()
        class ClosedPooledDatabase(FakePooledDatabase):
            def _is_closed(self, conn):
                return conn in (2, 4)

        db = ClosedPooledDatabase('testing', stale_timeout=10)

        conns = [
            (now - 15, 1),  # Skipped due to being stale.
            (now - 5, 2),  # Will appear closed.
            (now - 3, 3),
            (now, 4),  # Will appear closed.
        ]
        db.counter = 4  # The next connection we create will have id=5.
        for ts, conn in conns:
            push_conn(db, ts, conn)

        # Conn 3 is not stale or closed, so we will get it.
        self.assertEqual(db.connection(), 3)
        self.assertEqual(len(db._in_use), 1)
        self.assertTrue(3 in db._in_use)
        pool_conn = db._in_use[3]
        self.assertEqual(pool_conn.timestamp, now - 3)
        self.assertEqual(pool_conn.connection, 3)

        # Only conn 4 remains in the idle pool.
        self.assertEqual(len(db._connections), 1)
        self.assertEqual(db._connections[0][2], 4)

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

    def test_heap_counter_deterministic_ordering(self):
        # Verify that connections pushed with the same timestamp are returned
        # in order.
        now = time.time()
        push_conn(self.db, now, 'a')
        push_conn(self.db, now, 'b')
        push_conn(self.db, now, 'c')

        results = []
        while self.db._connections:
            ts, counter, conn = heapq.heappop(self.db._connections)
            results.append(conn)
        self.assertEqual(results, ['a', 'b', 'c'])

    def test_close_conn_removes_from_in_use(self):
        # _close(conn, close_conn=True) should pop the key from _in_use AND
        # close the underlying driver conn.
        self.assertEqual(self.db.connection(), 1)
        self.assertTrue(1 in self.db._in_use)

        closed_before = self.db.closed_counter
        self.db._close(1, close_conn=True)

        self.assertNotIn(1, self.db._in_use)
        self.assertEqual(self.db.closed_counter, closed_before + 1)

    def test_double_close_is_noop(self):
        # Calling _close on a connection not in _in_use (and close_conn=False)
        # should be a safe no-op rather than raising or leaking.
        self.assertEqual(self.db.connection(), 1)
        self.db.close()  # Returns conn 1 to the pool.

        self.assertNotIn(1, self.db._in_use)
        closed_before = self.db.closed_counter
        # Second close should do nothing.
        self.db._close(1)
        self.assertEqual(self.db.closed_counter, closed_before)
        # Pool state unchanged.
        self.assertEqual(len(self.db._connections), 1)

    def test_can_reuse_false_closes_connection(self):
        # When _can_reuse returns False on check-in, the connection should be
        # closed at the driver level and not returned to the pool.
        class NotReusablePooledDatabase(FakePooledDatabase):
            def _can_reuse(self, conn):
                return False

        db = NotReusablePooledDatabase('testing')
        self.assertEqual(db.connection(), 1)
        closed_before = db.closed_counter

        db.close()

        # Connection should have been driver-closed, not pooled.
        self.assertEqual(db.closed_counter, closed_before + 1)
        self.assertEqual(len(db._connections), 0)
        self.assertEqual(db._in_use, {})

        # Next connect creates a brand new connection.
        self.assertEqual(db.connection(), 2)

    def test_close_raw_swallows_exception(self):
        called = []
        # _close_raw should not propagate exceptions from the driver.
        class BrokenDriverClose(FakeDatabase):
            def _close(self, conn):
                called.append(conn)
                raise RuntimeError('failed')

        class BrokenPool(FakePooledDatabase, BrokenDriverClose):
            pass

        db = BrokenPool('testing')
        db._close_raw(1337)
        self.assertEqual(called, [1337])

    def test_close_stale_removes_from_in_use(self):
        # Verify that close_stale both driver-closes the connection AND
        # removes it from _in_use (no dangling keys).
        db = FakePooledDatabase('testing', counter=2)

        now = time.time()
        db._in_use[1] = PoolConnection(now - 1000, 1, now - 1000)
        db._in_use[2] = PoolConnection(now, 2, now)

        closed_before = db.closed_counter
        self.assertEqual(db.close_stale(age=500), 1)
        self.assertNotIn(1, db._in_use)
        self.assertIn(2, db._in_use)
        self.assertEqual(db.closed_counter, closed_before + 1)

    def test_close_all_clears_both_pools(self):
        # close_all should leave both _connections and _in_use completely
        # empty, and driver-close every connection.
        db = FakePooledDatabase('testing', counter=3)

        now = time.time()
        push_conn(db, now - 5, 1)
        push_conn(db, now - 1, 2)

        # Simulate two in-use connections.
        db._in_use[3] = PoolConnection(now, 3, now)
        db._in_use[4] = PoolConnection(now, 4, now)

        # One more for the "current thread" via normal connect path so
        # self.close() inside close_all has something to reset.
        db._state.closed = True
        db.connect()
        conn = db.connection()
        self.assertIn(db.conn_key(conn), db._in_use)

        closed_before = db.closed_counter
        db.close_all()

        self.assertEqual(db._connections, [])
        self.assertEqual(db._in_use, {})
        # 2 idle + 2 manually-added in_use + the current thread's conn = 5.
        # (close_all calls self.close() which triggers _close for the current
        # thread's conn, but that goes through the return-to-pool path, not
        # _close_raw.  The subsequent loop over the snapshot handles it.)
        self.assertGreaterEqual(db.closed_counter, closed_before + 4)

    def test_connect_timeout_with_condition_variable(self):
        # Verify that connect() with a timeout raises after the timeout
        # expires when the pool is exhausted.
        db = FakePooledDatabase('testing', max_connections=1, timeout=0.15)
        self.assertEqual(db.connection(), 1)

        errors = []
        def try_connect():
            db._state.closed = True  # Appear as a new thread.
            try:
                db.connect()
            except MaxConnectionsExceeded:
                errors.append(True)

        t = threading.Thread(target=try_connect)
        start = time.monotonic()
        t.start()
        t.join(timeout=2)
        elapsed = time.monotonic() - start

        # Should have waited roughly the timeout duration.
        self.assertEqual(len(errors), 1)
        self.assertGreaterEqual(elapsed, 0.1)

    def test_connect_timeout_wakes_on_return(self):
        # Verify that a waiting thread unblocks promptly when a connection
        # is returned to the pool (via the Condition variable notify).
        db = FakePooledDatabase('testing', max_connections=1, timeout=5)
        self.assertEqual(db.connection(), 1)

        results = []
        def try_connect():
            db._state.closed = True
            try:
                db.connect()
                results.append(db.connection())
            except MaxConnectionsExceeded:
                results.append('timeout')

        t = threading.Thread(target=try_connect)
        t.start()

        # Give the thread a moment to start waiting.
        time.sleep(0.05)

        # Return conn 1 to the pool — should wake the waiting thread.
        db.close()

        t.join(timeout=2)
        self.assertFalse(t.is_alive(), 'Thread did not wake up.')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], 1)  # Got the recycled connection.

    def test_connect_timeout_zero_becomes_infinite(self):
        # A timeout of 0 should be treated as infinite (no immediate failure).
        db = FakePooledDatabase('testing', max_connections=1, timeout=0)
        self.assertEqual(db._wait_timeout, float('inf'))

    def test_close_all_wakes_waiters(self):
        # Threads blocked in connect() should be woken by close_all() so they
        # can create fresh connections.
        db = FakePooledDatabase('testing', max_connections=1, timeout=5)
        self.assertEqual(db.connection(), 1)

        results = []
        def try_connect():
            db._state.closed = True
            try:
                db.connect()
                results.append(db.connection())
            except MaxConnectionsExceeded:
                results.append('timeout')

        t = threading.Thread(target=try_connect)
        t.start()
        time.sleep(0.05)

        # close_all frees the slot and calls notify_all.
        db.close_all()

        t.join(timeout=2)
        self.assertFalse(t.is_alive(), 'Thread was not woken by close_all.')
        self.assertEqual(len(results), 1)
        # After close_all, the thread should have gotten a fresh connection.
        self.assertEqual(results[0], 2)

    def test_close_stale_iteration(self):
        db = FakePooledDatabase('testing', counter=10)
        now = time.time()
        for i in range(1, 11):
            db._in_use[i] = PoolConnection(now - 1000, i, now - 1000)

        # All 10 should be closed.
        self.assertEqual(db.close_stale(age=500), 10)
        self.assertEqual(db._in_use, {})

    def test_concurrent_close_stale_and_return(self):
        # Exercise close_stale running while other threads are actively
        # returning connections (calling close()).  The snapshot-before-mutate
        # pattern and the RLock should keep everything consistent.
        db = FakePooledDatabase('testing', max_connections=20)
        barrier = threading.Barrier(11)  # 10 workers + main thread.
        errors = []

        def worker(n):
            """Check out a connection, wait for all workers to be ready,
            then return it."""
            try:
                db._state.closed = True
                db.connect()
                barrier.wait(timeout=2)
                # Small stagger so close_stale and close() overlap.
                time.sleep(0.001 * (n % 3))
                db.close()
            except Exception as exc:
                errors.append(exc)

        # Spin up 10 threads that each grab and return a connection.
        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(10)]
        for t in threads: t.start()

        # Wait until all threads hold a connection.
        while len(db._in_use) < 10:
            time.sleep(.005)

        # Artificially back-date half the checked_out times so that
        # close_stale will try to close them while threads are returning.
        now = time.time()
        for i, key in enumerate(list(db._in_use)):
            if i % 2 == 0:
                pc = db._in_use[key]
                db._in_use[key] = PoolConnection(pc.timestamp, pc.connection,
                                                 now - 10000)

        # Release the barrier so threads start returning connections, and
        # simultaneously run close_stale from the main thread.
        barrier.wait(timeout=2)
        closed = db.close_stale(age=5000)
        for t in threads: t.join(timeout=2)

        self.assertEqual(errors, [])
        for key in db._in_use:
            for _, _, conn in db._connections:
                self.assertNotEqual(db.conn_key(conn), key)

    def test_manual_close_when_already_closed(self):
        # manual_close on an already-closed database should return False.
        self.assertFalse(self.db.manual_close())  # Never opened.

        self.db.connect()
        self.db.close()
        self.assertFalse(self.db.manual_close())  # Already closed.

    def test_close_idle_driver_closes_all(self):
        # Every idle connection should be driver-closed.
        db = FakePooledDatabase('testing', counter=5)
        now = time.time()
        for i in range(1, 6):
            push_conn(db, now - i, i)

        closed_before = db.closed_counter
        db.close_idle()
        self.assertEqual(db._connections, [])
        self.assertEqual(db.closed_counter, closed_before + 5)

    def test_max_connections_zero_means_unlimited(self):
        # max_connections=0 (falsy) should mean no limit.
        db = FakePooledDatabase('testing', max_connections=0)
        for i in range(50):
            db._state.closed = True
            db.connect()
        self.assertEqual(len(db._in_use), 50)

    def test_stale_and_closed_all_skipped(self):
        # If every connection in the pool is either stale or closed, a new one
        # should be created.
        class AllClosedDatabase(FakePooledDatabase):
            def _is_closed(self, conn):
                return True

        db = AllClosedDatabase('testing', stale_timeout=10)
        now = time.time()
        push_conn(db, now - 20, 1)  # Stale.
        push_conn(db, now, 2)       # Closed (per _is_closed override).
        db.counter = 2

        self.assertEqual(db.connection(), 3)
        self.assertEqual(db._connections, [])
        self.assertEqual(list(db._in_use.keys()), [3])

    def test_init_updates_pool_parameters(self):
        # The init() method should allow updating pool parameters after
        # initial construction.
        db = FakePooledDatabase('testing', max_connections=5, stale_timeout=10,
                                timeout=2)
        self.assertEqual(db._max_connections, 5)
        self.assertEqual(db._stale_timeout, 10)
        self.assertEqual(db._wait_timeout, 2)

        db.init('testing', max_connections=50, stale_timeout=100, timeout=20)
        self.assertEqual(db._max_connections, 50)
        self.assertEqual(db._stale_timeout, 100)
        self.assertEqual(db._wait_timeout, 20)

    def test_init_timeout_zero_becomes_infinite(self):
        db = FakePooledDatabase('testing', timeout=5)
        self.assertEqual(db._wait_timeout, 5)

        db.init('testing', timeout=0)
        self.assertEqual(db._wait_timeout, float('inf'))


class TestLivePooledDatabase(ModelTestCase):
    database = PooledTestDatabase('test_pooled.db')
    requires = [Register]

    def tearDown(self):
        super(TestLivePooledDatabase, self).tearDown()
        self.database.close_idle()
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


class TestPooledDatabaseIntegration(ModelTestCase):
    requires = [Register]

    def setUp(self):
        params = {}
        if IS_MYSQL:
            db_class = PooledMySQLDatabase
        elif IS_POSTGRESQL:
            db_class = PooledPostgresqlDatabase
        elif IS_CRDB:
            db_class = PooledCockroachDatabase
        else:
            db_class = PooledSqliteDatabase
            params['check_same_thread'] = False
        self.database = db_loader(BACKEND, db_class=db_class, **params)
        super(TestPooledDatabaseIntegration, self).setUp()

    def assertConnections(self, expected):
        available = len(self.database._connections)
        in_use = len(self.database._in_use)
        self.assertEqual(available + in_use, expected,
                         'expected %s, got: %s available, %s in use'
                         % (expected, available, in_use))

    def test_pooled_database_integration(self):
        # Connection should be open from the setup method.
        self.assertFalse(self.database.is_closed())
        self.assertConnections(1)
        self.assertTrue(self.database.close())
        self.assertTrue(self.database.is_closed())
        self.assertConnections(1)

        signal = threading.Event()
        def connect():
            self.assertTrue(self.database.is_closed())
            self.assertTrue(self.database.connect())
            self.assertFalse(self.database.is_closed())
            signal.wait()
            self.assertTrue(self.database.close())
            self.assertTrue(self.database.is_closed())

        # Open connections in 4 separate threads.
        threads = [threading.Thread(target=connect) for _ in range(4)]
        for t in threads: t.start()

        while len(self.database._in_use) < 4:
            time.sleep(.005)

        # Close connections in all 4 threads.
        signal.set()
        for t in threads: t.join()

        # Verify that there are 4 connections available in the pool.
        self.assertConnections(4)
        self.assertEqual(len(self.database._connections), 4)  # Available.
        self.assertEqual(len(self.database._in_use), 0)

        # Verify state of the main thread, just a sanity check.
        self.assertTrue(self.database.is_closed())

        # Opening a connection will pull from the pool.
        self.assertTrue(self.database.connect())
        self.assertFalse(self.database.connect(reuse_if_open=True))
        self.assertConnections(4)
        self.assertEqual(len(self.database._in_use), 1)

        # Calling close_all() closes everything, including calling thread.
        self.database.close_all()
        self.assertConnections(0)
        self.assertTrue(self.database.is_closed())

    def test_pool_with_models(self):
        self.database.close()
        signal = threading.Event()

        def create_obj(i):
            with self.database.connection_context():
                with self.database.atomic():
                    Register.create(value=i)
                signal.wait()

        # Create 4 objects, one in each thread. The INSERT will be wrapped in a
        # transaction, and after COMMIT (but while the conn is still open), we
        # will wait for the signal that all objects were created. This ensures
        # that all our connections are open concurrently.
        threads = [threading.Thread(target=create_obj, args=(i,))
                   for i in range(4)]
        for t in threads: t.start()

        # Explicitly connect, as the connection is required to verify that all
        # the objects are present (and that its safe to set the signal).
        self.assertTrue(self.database.connect())
        while Register.select().count() != 4:
            time.sleep(0.005)

        # Signal threads that they can exit now and ensure all exited.
        signal.set()
        for t in threads: t.join()

        # Close connection from main thread as well.
        self.database.close()

        self.assertConnections(5)
        self.assertEqual(len(self.database._in_use), 0)

        # Cycle through the available connections, running a query on each, and
        # then manually closing it.
        for i in range(5):
            self.assertTrue(self.database.is_closed())
            self.assertTrue(self.database.connect())

            # Sanity check to verify objects are created.
            query = Register.select().order_by(Register.value)
            self.assertEqual([r.value for r in query], [0, 1, 2, 3])
            self.database.manual_close()
            self.assertConnections(4 - i)

        self.assertConnections(0)
        self.assertEqual(len(self.database._in_use), 0)
