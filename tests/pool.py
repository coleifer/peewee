import heapq
import os
import threading
import time

from peewee import *
from peewee import _savepoint
from peewee import _transaction
from playhouse.pool import *

from .base import BACKEND
from .base import BaseTestCase
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
        heapq.heappush(db._connections, (now - 10, 3))
        heapq.heappush(db._connections, (now - 5, 2))
        heapq.heappush(db._connections, (now - 1, 1))

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
        heapq.heappush(db._connections, (now - 10, 3))
        heapq.heappush(db._connections, (now - 5, 2))
        heapq.heappush(db._connections, (now - 1, 1))
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
        for ts_conn in conns:
            heapq.heappush(db._connections, ts_conn)

        self.assertEqual(db.connection(), 3)
        self.assertEqual(len(db._in_use), 1)
        self.assertTrue(3 in db._in_use)
        self.assertEqual(db._connections, [(now, 4)])

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
        for ts_conn in conns:
            heapq.heappush(db._connections, ts_conn)

        # Conn 3 is not stale or closed, so we will get it.
        self.assertEqual(db.connection(), 3)
        self.assertEqual(len(db._in_use), 1)
        self.assertTrue(3 in db._in_use)
        pool_conn = db._in_use[3]
        self.assertEqual(pool_conn.timestamp, now - 3)
        self.assertEqual(pool_conn.connection, 3)
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
