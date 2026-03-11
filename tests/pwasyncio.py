import asyncio
import collections
import contextvars
import gc
import glob
import itertools
import tempfile
import os
import unittest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from peewee import *
from playhouse.pwasyncio import *
from playhouse.pwasyncio import _State, _lazy_cursor_iter
from .base import MYSQL_PARAMS
from .base import PSQL_PARAMS
from .base import IS_MYSQL
from .base import IS_POSTGRESQL

try:
    import asyncpg
except ImportError:
    asyncpg = None

try:
    import aiomysql
except ImportError:
    aiomysql = None

import aiosqlite

SQLITE_RETURNING = aiosqlite.sqlite_version_info >= (3, 35, 0)


class TestModel(Model):
    name = CharField()
    value = IntegerField(default=0)

class User(Model):
    username = CharField()

class Tweet(Model):
    user = ForeignKeyField(User, backref='tweets')
    message = TextField()


class TestGreenletSpawn(unittest.IsolatedAsyncioTestCase):
    async def test_simple_function(self):
        result = await greenlet_spawn(lambda x, y: x + y, 5, 3)
        self.assertEqual(result, 8)

    async def test_function_with_await(self):
        async def async_helper():
            await asyncio.sleep(0.01)
            return 2
        def func():
            return await_(async_helper()) * 2
        self.assertEqual(await greenlet_spawn(func), 4)

    async def test_multiple_awaits(self):
        async def fetch_value(val):
            await asyncio.sleep(0.01)
            return val
        def multi():
            return sum([await_(fetch_value(i)) for i in [10, 20, 30]])
        self.assertEqual(await greenlet_spawn(multi), 60)

    async def test_exception_propagation(self):
        with self.assertRaises(ValueError):
            await greenlet_spawn(lambda: (_ for _ in ()).throw(ValueError('x')))

    async def test_exception_in_awaitable(self):
        async def fail():
            raise RuntimeError('async error')
        with self.assertRaises(RuntimeError):
            await greenlet_spawn(lambda: await_(fail()))

    def test_await_outside_greenlet(self):
        with self.assertRaises(MissingGreenletBridge):
            await_(Mock())

    async def test_contextvars(self):
        var = contextvars.ContextVar('data', default='x')
        state = []
        def get_var():
            state.append(var.get())
        async def aget_var():
            await greenlet_spawn(get_var)

        var.set('y')
        await aget_var()
        await greenlet_spawn(lambda: await_(aget_var()))
        await aget_var()
        self.assertEqual(state, ['y', 'y', 'y'])


class TestTaskLocal(unittest.IsolatedAsyncioTestCase):
    async def test_task_isolation(self):
        tl = TaskLocal()
        async def worker(tid):
            tl._current().conn = tid
            await asyncio.sleep(0.01)
            return tl._current().conn
        results = await asyncio.gather(*[worker(i) for i in range(5)])
        self.assertEqual(results, [0, 1, 2, 3, 4])

    async def test_state_attributes(self):
        tl = TaskLocal()
        tl.conn = 'c'
        tl.closed = False
        tl.transactions = [1]
        self.assertEqual(tl.conn, 'c')
        self.assertFalse(tl.closed)
        self.assertEqual(tl.transactions, [1])

    async def test_get_returns_fresh_state(self):
        s = TaskLocal().get()
        self.assertIsNone(s.conn)
        self.assertTrue(s.closed)
        self.assertEqual(s.transactions, [])

    async def test_clear(self):
        tl = TaskLocal()
        tl.conn = 'x'
        key = tl._get_storage_key()
        tl.clear()
        self.assertNotIn(key, tl._state_storage)

    async def test_reset(self):
        tl = TaskLocal()
        tl.conn = 'x'
        tl.closed = False
        tl.transactions = [1, 2]
        tl.reset()
        self.assertIsNone(tl.conn)
        self.assertTrue(tl.closed)
        self.assertEqual(tl.transactions, [])

    async def test_set_connection(self):
        tl = TaskLocal()
        m = Mock()
        tl.set_connection(m)
        self.assertIs(tl.conn, m)
        self.assertFalse(tl.closed)

    async def test_cleanup_dead_tasks(self):
        tl = TaskLocal()
        tl._current().conn = 1
        tl._state_storage[999999] = Mock()
        cleaned = tl.cleanup_dead_tasks()
        self.assertGreaterEqual(cleaned, 1)
        self.assertNotIn(999999, tl._state_storage)

    async def test_periodic_cleanup(self):
        tl = TaskLocal()
        super(TaskLocal, tl).__setattr__('_CLEANUP_INTERVAL', 5)
        tl._state_storage[888888] = _State()
        for _ in range(5):
            self.assertIn(888888, tl._state_storage)
            tl._current()
        self.assertNotIn(888888, tl._state_storage)


def _make_lazy_cursor(rows, batch_size=2):
    it = iter(rows)
    fetch_counts = []
    cleanup_called = []

    async def fetch_many(count):
        fetch_counts.append(count)
        return list(itertools.islice(it, count))

    async def cleanup():
        cleanup_called.append(True)

    cursor = CursorAdapter(
        description=[('id',), ('name',)],
        fetch_many=fetch_many,
        cleanup=cleanup,
        buffer_size=batch_size)
    return cursor, fetch_counts, cleanup_called


class TestCursorAdapter(unittest.IsolatedAsyncioTestCase):
    def test_eager_fetchone(self):
        c = CursorAdapter([(1, 'a'), (2, 'b'), (3, 'c')])
        self.assertEqual(c.fetchone(), (1, 'a'))
        self.assertEqual(c.fetchone(), (2, 'b'))
        self.assertEqual(c.fetchone(), (3, 'c'))
        self.assertIsNone(c.fetchone())

    def test_eager_fetchall(self):
        rows = [(1,), (2,)]
        c = CursorAdapter(rows)
        self.assertIs(c.fetchall(), rows)

    def test_eager_iter(self):
        rows = [(1,), (2,), (3,)]
        self.assertEqual(list(CursorAdapter(rows)), rows)
        self.assertEqual(CursorAdapter(rows).rowcount, 3)

    def test_eager_metadata(self):
        c = CursorAdapter()
        self.assertEqual(c._rows, [])
        self.assertEqual(c.rowcount, 0)
        self.assertEqual(c.description, [])
        self.assertIsNone(c.fetchone())
        self.assertEqual(list(c), [])

        c = CursorAdapter([(1,)], lastrowid=5, rowcount=1,
                          description=[('id',)])
        self.assertEqual(c.lastrowid, 5)
        self.assertEqual(c.rowcount, 1)
        self.assertEqual(c.description, [('id',)])

    async def test_lazy_fetchone_batches(self):
        rows = [(i,) for i in range(5)]
        cursor, counts, _ = _make_lazy_cursor(rows, batch_size=2)

        collected = []
        def drain():
            while True:
                r = cursor.fetchone()
                if r is None:
                    break
                collected.append(r)
        await greenlet_spawn(drain)

        self.assertEqual(collected, rows)
        # 2 + 2 + 1 + 0(empty) = 4 calls, each requesting 2
        self.assertEqual(len(counts), 4)
        self.assertTrue(all(c == 2 for c in counts))

    async def test_lazy_fetchone_empty(self):
        cursor, _, _ = _make_lazy_cursor([], batch_size=2)
        self.assertIsNone(await greenlet_spawn(cursor.fetchone))
        # Already exhausted, still returns None.
        self.assertIsNone(await greenlet_spawn(cursor.fetchone))

    async def test_lazy_iter(self):
        rows = [(i,) for i in range(7)]
        cursor, counts, _ = _make_lazy_cursor(rows, batch_size=3)
        self.assertEqual(await greenlet_spawn(list, cursor), rows)
        # 3 + 3 + 1 + 0 = 4 calls
        self.assertEqual(len(counts), 4)

    async def test_lazy_fetchall(self):
        rows = [(1,), (2,), (3,)]
        cursor, _, _ = _make_lazy_cursor(rows, batch_size=10)
        self.assertEqual(await greenlet_spawn(cursor.fetchall), rows)

    async def test_lazy_buffer_reuse(self):
        rows = [(i,) for i in range(3)]
        cursor, counts, _ = _make_lazy_cursor(rows, batch_size=10)
        await greenlet_spawn(cursor.fetchone)
        self.assertEqual(len(counts), 1)
        await greenlet_spawn(cursor.fetchone)
        await greenlet_spawn(cursor.fetchone)
        self.assertEqual(len(counts), 1)  # still 1
        await greenlet_spawn(cursor.fetchone)  # second fetch (empty).
        self.assertEqual(len(counts), 2)

    async def test_lazy_description(self):
        cursor, _, _ = _make_lazy_cursor([], batch_size=2)
        self.assertEqual(cursor.description, [('id',), ('name',)])

    async def test_lazy_buffer_size_override(self):
        rows = [(i,) for i in range(10)]
        cursor, counts, _ = _make_lazy_cursor(rows, batch_size=5)
        cursor._buffer_size = 3
        await greenlet_spawn(list, cursor)
        self.assertTrue(all(c == 3 for c in counts))

    async def test_aclose_cleanup(self):
        cursor, _, cleanup = _make_lazy_cursor([], batch_size=2)
        await cursor.aclose()
        self.assertEqual(cleanup, [True])
        self.assertIsNone(cursor._fetch_many)
        self.assertIsNone(cursor._cleanup)

    async def test_aclose_idempotent(self):
        call_count = []
        async def cleanup():
            call_count.append(1)
        cursor, _, _ = _make_lazy_cursor([], batch_size=2)
        cursor._cleanup = cleanup
        await cursor.aclose()
        await cursor.aclose()
        self.assertEqual(len(call_count), 1)

    async def test_aclose_noop_for_eager(self):
        await CursorAdapter([(1,)]).aclose()  # must not raise

    async def test_lazy_cursor_iter(self):
        rows = [(1,), (2,), (3,)]
        cursor, _, _ = _make_lazy_cursor(rows, batch_size=10)
        result = await greenlet_spawn(list, _lazy_cursor_iter(cursor))
        self.assertEqual(result, rows)

    async def test_lazy_cursor_iter_empty(self):
        cursor, _, _ = _make_lazy_cursor([], batch_size=2)
        result = await greenlet_spawn(list, _lazy_cursor_iter(cursor))
        self.assertEqual(result, [])


class TestConnectionWrappers(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_execute(self):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [(1, 'test')]
        mock_cursor.lastrowid = 1
        mock_cursor.rowcount = 1
        mock_cursor.description = [('id',), ('name',)]
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = mock_cursor

        result = await AsyncSqliteConnection(mock_conn).execute(
            'SELECT * FROM test')
        self.assertIsInstance(result, CursorAdapter)
        self.assertEqual(result.fetchall(), [(1, 'test')])
        self.assertEqual(result.lastrowid, 1)
        mock_cursor.close.assert_awaited_once()

    async def test_sqlite_execute_iter_returns_lazy(self):
        mock_cursor = AsyncMock()
        mock_cursor.description = [('a',), ('b',)]
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = mock_cursor

        conn = AsyncSqliteConnection(mock_conn)
        cursor = await conn.execute_iter('SELECT a, b FROM t')
        self.assertIsInstance(cursor, CursorAdapter)
        self.assertIsNotNone(cursor._fetch_many)
        self.assertEqual(cursor.description, [('a',), ('b',)])
        await cursor.aclose()

    async def test_sqlite_execute_iter_lock_lifecycle(self):
        mock_cursor = AsyncMock()
        mock_cursor.description = []
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = mock_cursor

        conn = AsyncSqliteConnection(mock_conn)
        cursor = await conn.execute_iter('SELECT 1')
        self.assertTrue(conn._lock.locked())
        await cursor.aclose()
        self.assertFalse(conn._lock.locked())
        mock_cursor.close.assert_awaited_once()

    async def test_sqlite_execute_iter_lock_on_failure(self):
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = RuntimeError('fail')
        conn = AsyncSqliteConnection(mock_conn)
        with self.assertRaises(RuntimeError):
            await conn.execute_iter('invalid')
        self.assertFalse(conn._lock.locked())

    async def test_mysql_execute(self):
        mock_cursor = AsyncMock()
        mock_cursor.fetchall.return_value = [(1, 'test')]
        mock_cursor.lastrowid = 1
        mock_cursor.rowcount = 1
        mock_cursor.description = [('id',), ('name',)]
        mock_conn = AsyncMock()
        mock_conn.cursor.return_value = mock_cursor

        result = await AsyncMySQLConnection(mock_conn).execute(
            'SELECT * FROM test')
        self.assertIsInstance(result, CursorAdapter)
        self.assertEqual(result.fetchall(), [(1, 'test')])
        mock_cursor.close.assert_awaited_once()

    async def test_mysql_cursor_closed_on_error(self):
        mock_cursor = AsyncMock()
        mock_cursor.execute.side_effect = RuntimeError('fail')
        mock_conn = AsyncMock()
        mock_conn.cursor.return_value = mock_cursor

        with self.assertRaises(RuntimeError):
            await AsyncMySQLConnection(mock_conn).execute('invalid')
        mock_cursor.close.assert_awaited_once()

    async def test_mysql_concurrent_serialized(self):
        order = []
        async def tracked(sql, params):
            order.append(f'start-{sql}')
            await asyncio.sleep(0.05)
            order.append(f'end-{sql}')
            return []
        mock_cursor = AsyncMock()
        mock_cursor.execute = tracked
        mock_conn = AsyncMock()
        mock_conn.cursor.return_value = mock_cursor

        conn = AsyncMySQLConnection(mock_conn)
        await asyncio.gather(conn.execute('Q1', None),
                             conn.execute('Q2', None))
        idx = {e: i for i, e in enumerate(order)}
        self.assertTrue(idx['end-Q1'] < idx['start-Q2']
                        or idx['end-Q2'] < idx['start-Q1'])

    async def test_mysql_execute_iter_uses_ss_cursor(self):
        import playhouse.pwasyncio as mod
        mock_cursor = AsyncMock()
        mock_cursor.description = [('x',)]
        mock_cursor.execute = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.cursor.return_value = mock_cursor

        sentinel = object()
        with patch.object(mod, 'aiomysql') as m:
            m.SSCursor = sentinel
            cursor = await AsyncMySQLConnection(mock_conn).execute_iter(
                'SELECT 1')
        mock_conn.cursor.assert_awaited_once_with(sentinel)
        self.assertIsNotNone(cursor._fetch_many)
        await cursor.aclose()

    async def test_mysql_execute_iter_lock_lifecycle(self):
        import playhouse.pwasyncio as mod
        mock_cursor = AsyncMock()
        mock_cursor.description = [('x',)]
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.cursor.return_value = mock_cursor

        conn = AsyncMySQLConnection(mock_conn)
        with patch.object(mod, 'aiomysql', create=True) as m:
            m.SSCursor = object()
            cursor = await conn.execute_iter('SELECT 1')
        self.assertTrue(conn._lock.locked())
        await cursor.aclose()
        self.assertFalse(conn._lock.locked())
        mock_cursor.close.assert_awaited_once()

    async def test_pg_parameter_conversion(self):
        mock_record = Mock()
        mock_record.keys.return_value = ['id', 'name']
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [mock_record]

        await AsyncPostgresqlConnection(mock_conn).execute(
            'SELECT * FROM t WHERE id = %s AND name = %s', (1, 'x'))
        sql = mock_conn.fetch.call_args[0][0]
        self.assertEqual(sql, 'SELECT * FROM t WHERE id = $1 AND name = $2')

    async def test_pg_concurrent_serialized(self):
        order = []
        async def tracked(sql, params=None):
            order.append(f'start-{sql}')
            await asyncio.sleep(0.05)
            order.append(f'end-{sql}')
            return []
        mock_conn = AsyncMock()
        mock_conn.fetch = tracked

        conn = AsyncPostgresqlConnection(mock_conn)
        await asyncio.gather(conn.execute('Q1', None),
                             conn.execute('Q2', None))
        idx = {e: i for i, e in enumerate(order)}
        self.assertTrue(idx['end-Q1'] < idx['start-Q2']
                        or idx['end-Q2'] < idx['start-Q1'])

    async def test_pg_no_params(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        await AsyncPostgresqlConnection(mock_conn).execute(
            'SELECT * FROM t', None)
        mock_conn.fetch.assert_called_once_with('SELECT * FROM t')

    async def test_pg_empty_results(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        r = await AsyncPostgresqlConnection(mock_conn).execute(
            'SELECT * FROM empty')
        self.assertEqual(r.fetchall(), [])
        self.assertEqual(r.description, [])

    def test_translate_placeholders(self):
        f = AsyncPostgresqlConnection._translate_placeholders
        self.assertEqual(f('SELECT 1'), 'SELECT 1')
        self.assertEqual(
            f('SELECT * FROM t WHERE a = %s AND b = %s'),
            'SELECT * FROM t WHERE a = $1 AND b = $2')
        self.assertEqual(
            f('INSERT INTO t VALUES (%s, %s, %s)'),
            'INSERT INTO t VALUES ($1, $2, $3)')

    def _pg_mocks(self, rows=None):
        rows = rows or []
        attr = MagicMock(); attr.name = 'col1'
        it = iter(rows)
        mock_cursor = AsyncMock()
        async def _fetch(count):
            return list(itertools.islice(it, count))
        mock_cursor.fetch = _fetch

        mock_stmt = AsyncMock()
        mock_stmt.cursor.return_value = mock_cursor
        mock_stmt.get_attributes = MagicMock(return_value=[attr])

        mock_tr = AsyncMock()
        mock_conn = MagicMock()
        mock_conn.transaction.return_value = mock_tr
        mock_conn.prepare = AsyncMock(return_value=mock_stmt)
        return mock_conn, mock_tr, mock_stmt, mock_cursor

    async def test_pg_execute_iter_description(self):
        mock_conn, _, mock_stmt, _ = self._pg_mocks()
        a1, a2 = MagicMock(), MagicMock()
        a1.name = 'id'; a2.name = 'username'
        mock_stmt.get_attributes.return_value = [a1, a2]

        conn = AsyncPostgresqlConnection(mock_conn)
        cursor = await conn.execute_iter('SELECT id, username FROM users')
        self.assertEqual(cursor.description, [('id',), ('username',)])
        await cursor.aclose()

    async def test_pg_execute_iter_starts_transaction(self):
        mock_conn, mock_tr, _, _ = self._pg_mocks()
        conn = AsyncPostgresqlConnection(mock_conn)
        cursor = await conn.execute_iter('SELECT 1')
        mock_conn.transaction.assert_called_once()
        mock_tr.start.assert_awaited_once()
        await cursor.aclose()

    async def test_pg_execute_iter_cleanup_rolls_back(self):
        mock_conn, mock_tr, _, _ = self._pg_mocks()
        conn = AsyncPostgresqlConnection(mock_conn)
        cursor = await conn.execute_iter('SELECT 1')
        self.assertTrue(conn._lock.locked())
        await cursor.aclose()
        mock_tr.rollback.assert_awaited_once()
        self.assertFalse(conn._lock.locked())

    async def test_pg_execute_iter_translates_placeholders(self):
        mock_conn, _, _, _ = self._pg_mocks()
        conn = AsyncPostgresqlConnection(mock_conn)
        cursor = await conn.execute_iter(
            'SELECT * FROM t WHERE a = %s AND b = %s', params=(1, 2))
        sql = mock_conn.prepare.call_args[0][0]
        self.assertIn('$1', sql)
        self.assertNotIn('%s', sql)
        await cursor.aclose()

    async def test_pg_execute_iter_lock_on_failure(self):
        mock_conn, _, _, _ = self._pg_mocks()
        mock_conn.prepare = AsyncMock(side_effect=RuntimeError('fail'))
        conn = AsyncPostgresqlConnection(mock_conn)
        with self.assertRaises(RuntimeError):
            await conn.execute_iter('invalid')
        self.assertFalse(conn._lock.locked())


class TestTaskLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            self.db_path = f.name

        self.db = AsyncSqliteDatabase(self.db_path)
        TestModel._meta.set_database(self.db)

        await self.db.aconnect()
        await self.db.acreate_tables([TestModel])

    async def asyncTearDown(self):
        await self.db.aclose()
        await self.db.close_pool()

        if self.db_path and os.path.exists(self.db_path):
            for fname in glob.glob(self.db_path + '*'):
                os.unlink(fname)

    async def test_task_state_cleanup_after_completion(self):
        async def task_with_state():
            async with self.db:
                await self.db.run(TestModel.create, name='test', value=1)
            return self.db._state._get_storage_key()

        task_key = await asyncio.create_task(task_with_state())
        await asyncio.sleep(0)
        gc.collect()

        self.db._state.cleanup_dead_tasks()
        self.assertFalse(task_key in self.db._state._state_storage)

    async def test_concurrent_task_state_isolation(self):
        async def capture(tid):
            async with self.db:
                before = id(self.db._state.get())
                await self.db.run(TestModel.create, name=f't{tid}', value=tid)
                after = id(self.db._state.get())
                self.assertEqual(before, after)
                return before

        results = await asyncio.gather(*[capture(i) for i in range(5)])
        self.assertTrue(all(results))
        self.assertTrue(len(set(results)), 5)


class IntegrationTests(object):
    db_path = None
    models = [TestModel, User, Tweet]

    def get_database(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            self.db_path = f.name
        return AsyncSqliteDatabase(self.db_path)

    def tearDown(self):
        if self.db_path and os.path.exists(self.db_path):
            os.unlink(self.db_path)

    async def asyncSetUp(self):
        try:
            self.db = self.get_database()
            await self.db.aconnect()
            await self.db.aclose()
        except Exception as exc:
            self.skipTest(f'Cannot connect: {exc}')

        if isinstance(self.db, AsyncSqliteDatabase):
            self.driver = 'sqlite'
            self.support_returning = SQLITE_RETURNING
        elif isinstance(self.db, AsyncMySQLDatabase):
            self.driver = 'mysql'
            self.support_returning = False
        elif isinstance(self.db, AsyncPostgresqlDatabase):
            self.driver = 'postgresql'
            self.support_returning = True
        else:
            raise ValueError('Unrecognized driver')

        for m in self.models:
            m._meta.set_database(self.db)
        async with self.db:
            await self.db.adrop_tables(self.models)
            await self.db.acreate_tables(self.models)

    async def asyncTearDown(self):
        async with self.db:
            await self.db.adrop_tables(self.models)
        await self.db.close_pool()

    async def create_record(self, name='test', value=1):
        return await self.db.run(TestModel.create, name=name, value=value)

    async def assertCount(self, expected):
        count = await self.db.run(TestModel.select().count)
        self.assertEqual(count, expected)

    async def assertNames(self, expected):
        curs = await self.db.list(TestModel.select().order_by(TestModel.name))
        self.assertEqual([tm.name for tm in curs], expected)

    async def seed(self, n=20):
        def _seed():
            with self.db.atomic():
                for i in range(n):
                    TestModel.create(name=f'item{i:02d}', value=i * 10)
        await self.db.run(_seed)

    async def test_pool_created_on_connect(self):
        await self.db.aclose()
        await self.db.close_pool()
        self.assertIsNone(self.db._pool)
        await self.db.aconnect()
        self.assertIsNotNone(self.db._pool)
        self.assertIsNotNone(self.db._state.conn)
        self.assertFalse(self.db.is_closed())
        await self.db.aclose()
        self.assertIsNone(self.db._state.conn)
        self.assertTrue(self.db.is_closed())

    async def test_is_closed(self):
        for i in range(2):
            await self.db.aconnect()
            self.assertFalse(self.db.is_closed())
            await self.db.aclose()
            self.assertTrue(self.db.is_closed())

    async def test_multiple_close_safe(self):
        await self.db.aclose()
        self.assertTrue(self.db.is_closed())
        await self.db.aclose()
        await self.db.aconnect()
        self.assertFalse(self.db.is_closed())

    async def test_reconnect_after_pool_close(self):
        await self.create_record('first', 1)
        await self.db.aclose()
        await self.db.close_pool()
        self.assertIsNone(self.db._pool)
        async with self.db:
            await self.assertCount(1)
        self.assertIsNotNone(self.db._pool)
        self.assertTrue(self.db.is_closed())

    async def test_connection_reuse_within_task(self):
        await self.db.aconnect()
        c1 = self.db._state.conn
        await self.create_record('a', 1)
        c2 = self.db._state.conn
        await self.create_record('b', 2)
        self.assertIs(c1, c2)
        self.assertIs(c2, self.db._state.conn)

    async def test_closing_flag_prevents_connect(self):
        self.db._closing = True
        try:
            with self.assertRaises(InterfaceError):
                await self.db.aconnect()
        finally:
            self.db._closing = False

    async def test_double_close_pool(self):
        await self.db.aclose()
        await self.db.close_pool()
        await self.db.close_pool()

    async def test_dead_connection_replaced(self):
        if self.driver == 'mysql':
            self.skipTest('closing underlying conn incompatible with aiomysql')
            return

        await self.db.aconnect()
        conn = self.db._state.conn
        await conn.close()
        await self.create_record('test', 1)
        self.assertIsNot(self.db._state.conn, conn)
        await self.assertCount(1)

    async def test_context_manager(self):
        async with self.db:
            self.assertIsNotNone(self.db._state.conn)
            self.assertFalse(self.db._state.closed)
            self.assertFalse(self.db.is_closed())
        self.assertIsNone(self.db._state.conn)
        self.assertTrue(self.db._state.closed)
        self.assertTrue(self.db.is_closed())

    async def test_exception_in_context_manager(self):
        try:
            async with self.db:
                raise RuntimeError('fail')
        except RuntimeError:
            pass
        self.assertTrue(self.db._state.closed)
        self.assertTrue(self.db.is_closed())
        async with self.db:
            await self.create_record('after_error', 1)
            self.assertFalse(self.db.is_closed())
            await self.assertCount(1)

        self.assertTrue(self.db.is_closed())

    async def test_execute_sql(self):
        iq, iparams = User.insert(username='x').sql()
        sq, _= User.select().sql()
        await self.db.aexecute_sql(iq, iparams)
        r = await self.db.aexecute_sql(sq)
        self.assertEqual(r.fetchall()[0][1], 'x')

    async def test_multiple_tasks_raw_sql(self):
        iq, _ = User.insert(username='x').sql()
        sq, _ = User.select(User.username).where(User.username == 'x').sql()

        async def worker(tid):
            username = f'u{tid}'
            await self.db.aconnect()
            await self.db.aexecute_sql(iq, (username,))
            r = await self.db.aexecute_sql(sq, (username,))
            row = r.fetchone()
            self.assertEqual(row[0], username)
            await self.db.aclose()
            return row

        results = await asyncio.gather(*[worker(i) for i in range(3)])
        self.assertEqual(sorted(results), [('u0',), ('u1',), ('u2',)])

    async def test_list(self):
        await self.seed(5)
        query = TestModel.select().order_by(TestModel.value)
        results = await self.db.list(query)
        self.assertEqual(len(results), 5)
        self.assertIsInstance(results[0], TestModel)
        self.assertEqual([r.value for r in results], [0, 10, 20, 30, 40])

    async def test_list_empty(self):
        self.assertEqual(await self.db.list(TestModel.select()), [])

    async def test_get(self):
        rec = await self.create_record('unique', 999)
        q = TestModel.select().where(TestModel.name == 'unique')
        fetched = await self.db.get(q)
        self.assertEqual(fetched.id, rec.id)
        self.assertEqual(fetched.name, 'unique')
        self.assertEqual(fetched.value, 999)

    async def test_get_not_found(self):
        with self.assertRaises(TestModel.DoesNotExist):
            q = TestModel.select().where(TestModel.id == 0)
            await self.db.get(q)

    async def test_scalar(self):
        await self.seed(10)
        query = TestModel.select(fn.MAX(TestModel.value))
        self.assertEqual(await self.db.scalar(query), 90)

    async def test_scalar_no_results(self):
        query = TestModel.select(fn.COUNT(TestModel.id))
        self.assertEqual(await self.db.scalar(query), 0)

        await self.seed(5)
        self.assertEqual(await self.db.scalar(query), 5)

    async def test_count(self):
        self.assertEqual(await self.db.count(TestModel.select()), 0)
        await self.seed(5)
        self.assertEqual(await self.db.count(TestModel.select()), 5)

    async def test_exists(self):
        self.assertFalse(await self.db.exists(TestModel.select()))
        await self.create_record('x', 1)
        self.assertTrue(await self.db.exists(TestModel.select()))

    async def test_aexecute(self):
        q = TestModel.insert_many([(f'item{i}', i) for i in range(10)])
        if self.support_returning:
            q = q.returning(TestModel.name)
            res = await self.db.aexecute(q)
            self.assertEqual([t.name for t in res],
                             [f'item{i}' for i in range(10)])
        else:
            await self.db.aexecute(q)
        await self.assertCount(10)

        q = (TestModel
             .update(value=TestModel.value * 10)
             .where(TestModel.value < 3))

        if self.support_returning:
            q = q.returning(TestModel.name, TestModel.value)
            res = await self.db.aexecute(q)
            self.assertEqual(sorted([(t.name, t.value) for t in res]),
                             [('item0', 0), ('item1', 10), ('item2', 20)])
        else:
            res = await self.db.aexecute(q)
            self.assertEqual(res, 2)

        q = TestModel.select().where(TestModel.value >= 10)
        self.assertEqual(await self.db.run(q.count), 2)

        rows = await self.db.aexecute(q.order_by(TestModel.value))
        self.assertEqual([r.name for r in rows], ['item1', 'item2'])

        q = TestModel.delete().where(TestModel.value >= 10)
        if self.support_returning:
            q = q.returning(TestModel.name, TestModel.value)
            res = await self.db.aexecute(q)
            self.assertEqual(sorted([(t.name, t.value) for t in res]),
                             [('item1', 10), ('item2', 20)])
        else:
            res = await self.db.aexecute(q)
            self.assertEqual(res, 2)

    async def test_run_contextvars(self):
        var = contextvars.ContextVar('v', default='x')
        state = []
        def do_run():
            state.append(var.get())
        var.set('y')
        state.append(var.get())
        await self.db.run(do_run)
        state.append(var.get())
        self.assertEqual(state, ['y', 'y', 'y'])

    async def test_create(self):
        tm = await self.create_record('test1', 100)
        self.assertEqual(tm.name, 'test1')
        self.assertEqual(tm.value, 100)

        tm = await self.db.run(TestModel.create, name='test2', value=101)
        self.assertEqual(tm.name, 'test2')
        self.assertEqual(tm.value, 101)

        await self.assertCount(2)
        await self.assertNames(['test1', 'test2'])

    async def test_select(self):
        tm = await self.create_record('test1', 100)
        res = await self.db.list(TestModel.select())
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].name, 'test1')
        self.assertEqual(res[0], tm)

    async def test_filter(self):
        await self.seed(20)
        query = TestModel.select().where(TestModel.value > 100)
        results = await self.db.list(query)
        self.assertEqual(len(results), 9)

    async def test_ordering(self):
        await self.seed(20)
        query = TestModel.select().order_by(TestModel.value.desc()).limit(5)
        results = await self.db.list(query)
        self.assertEqual(results[0].value, 190)
        self.assertEqual(results[4].value, 150)

    async def test_create_save_update(self):
        await self.create_record('test1', 100)

        def do_update():
            r = TestModel.get(TestModel.name == 'test1')
            r.value = 999; r.save()
            return TestModel.get(TestModel.name == 'test1').value

        self.assertEqual(await self.db.run(do_update), 999)

        uq = TestModel.update(name='test1x').where(TestModel.name == 'test1')
        res = await self.db.aexecute(uq)
        #self.assertEqual(res, 1)

        q = TestModel.select().where(TestModel.name == 'test1x')
        tm = await self.db.get(q)
        self.assertEqual(tm.value, 999)

    async def test_update(self):
        await self.seed(50)
        await self.db.aexecute(TestModel
                               .update(value=TestModel.value + 1000)
                               .where(TestModel.value < 250))
        query = TestModel.select().where(TestModel.value >= 1000)
        self.assertEqual(await self.db.count(query), 25)

        query = TestModel.select(fn.SUM(TestModel.value))
        self.assertEqual(await self.db.scalar(query), 37250)

    async def test_delete(self):
        await self.seed(20)
        await self.db.aexecute(TestModel.delete().where(TestModel.value < 50))
        await self.assertCount(15)

        tm = await self.db.get(TestModel.select())
        await self.db.run(tm.delete_instance)
        await self.assertCount(14)

    async def test_bulk_create(self):
        recs = [TestModel(name=f'b{i}', value=i) for i in range(100)]
        await self.db.run(TestModel.bulk_create, recs, batch_size=25)
        await self.assertCount(100)

    async def test_bulk_update(self):
        if self.driver == 'postgresql':
            self.skipTest('bulk_update incompatible with asyncpg')
            return

        accum = [await self.db.run(TestModel.create, name=f'b{i}', value=i)
                 for i in range(5)]
        for tm in accum:
            tm.name += '-x'
            tm.value += 100

        await self.db.run(TestModel.bulk_update, accum,
                          fields=[TestModel.name, TestModel.value])

        q = await self.db.list(TestModel.select().order_by(TestModel.value))
        self.assertEqual([(tm.name, tm.value) for tm in q],
                         [('b0-x', 100), ('b1-x', 101), ('b2-x', 102),
                          ('b3-x', 103), ('b4-x', 104)])

    async def test_insert_many(self):
        def insert():
            data = [{'name': f'i{i}', 'value': i} for i in range(100)]
            TestModel.insert_many(data).execute()
        await self.db.run(insert)
        await self.assertCount(100)

        data = [{'name': f'i{i}', 'value': i} for i in range(100, 200)]
        await self.db.aexecute(TestModel.insert_many(data))
        await self.assertCount(200)

        data = [(f'i{i}', i) for i in range(200, 300)]
        iq = (TestModel
              .insert_many(data, fields=[TestModel.name, TestModel.value]))
        await self.db.aexecute(iq)
        await self.assertCount(300)

    async def test_atomic(self):
        async with self.db.atomic():
            await self.create_record('a', 1)
        await self.assertCount(1)

        async with self.db.atomic() as txn:
            await self.create_record('b', 2)
            await self.assertCount(2)
            await self.assertNames(['a', 'b'])
            await txn.arollback()
            await self.assertCount(1)
            await self.create_record('c', 3)
            await self.create_record('d', 4)

        await self.assertCount(3)
        await self.assertNames(['a', 'c', 'd'])

    async def test_transaction_commit(self):
        def create_in_tx():
            with self.db.atomic():
                TestModel.create(name='tx1')
                TestModel.create(name='tx2')
        await self.db.run(create_in_tx)
        await self.assertCount(2)

        async with self.db.atomic():
            await self.db.run(TestModel.create, name='tx1')
            await self.db.run(TestModel.create, name='tx2')
        await self.assertCount(4)

    async def test_transaction_rollback(self):
        def failing():
            with self.db.atomic():
                TestModel.create(name='tx1')
                raise ValueError('fail')
        with self.assertRaises(ValueError):
            await self.db.run(failing)
        await self.assertCount(0)

        async with self.db.atomic() as txn:
            await self.create_record('tx2')
            await self.assertCount(1)
            await txn.arollback()
        await self.assertCount(0)

    async def test_nested_transactions(self):
        def nested():
            with self.db.atomic():
                TestModel.create(name='o1', value=1)
                with self.db.atomic():
                    TestModel.create(name='i1', value=2)
                    TestModel.create(name='i2', value=3)
                TestModel.create(name='o2', value=4)
        await self.db.run(nested)
        await self.assertCount(4)
        await self.assertNames(['i1', 'i2', 'o1', 'o2'])

        async with self.db.atomic():
            await self.db.run(TestModel.create, name='o3', value=1)
            async with self.db.atomic():
                await self.db.run(TestModel.create, name='i3', value=2)
                await self.db.run(TestModel.create, name='i4', value=3)
            await self.db.run(TestModel.create, name='o4', value=4)

        await self.assertCount(8)
        await self.assertNames(['i1', 'i2', 'i3', 'i4',
                                'o1', 'o2', 'o3', 'o4'])

    async def test_nested_implicit_rollback(self):
        def nested():
            with self.db.atomic():
                TestModel.create(name='o1', value=1)
                try:
                    with self.db.atomic():
                        TestModel.create(name='i1', value=2)
                        raise ValueError('fail')
                except ValueError:
                    pass
                TestModel.create(name='o2', value=3)
        await self.db.run(nested)
        await self.assertCount(2)
        await self.assertNames(['o1', 'o2'])

        async with self.db.atomic():
            await self.db.run(TestModel.create, name='o3', value=1)
            try:
                async with self.db.atomic():
                    await self.db.run(TestModel.create, name='i3', value=2)
                    raise ValueError('fail')
            except ValueError:
                pass
            await self.assertCount(3)
            await self.db.run(TestModel.create, name='o4', value=3)

        await self.assertCount(4)
        await self.assertNames(['o1', 'o2', 'o3', 'o4'])

    async def test_nested_explicit_rollback(self):
        def nested():
            with self.db.atomic():
                TestModel.create(name='o1')
                with self.db.atomic() as sp:
                    TestModel.create(name='i1')
                    self.assertEqual(TestModel.select().count(), 2)
                    sp.rollback()
                self.assertEqual(TestModel.select().count(), 1)
                TestModel.create(name='o2')

        await self.db.run(nested)
        await self.assertCount(2)
        await self.assertNames(['o1', 'o2'])

        async with self.db.atomic():
            await self.db.run(TestModel.create, name='o3')
            async with self.db.atomic() as sp:
                await self.db.run(TestModel.create, name='i2')
                await self.assertCount(4)
                await sp.arollback()
            await self.assertCount(3)
            await self.db.run(TestModel.create, name='o4')

        await self.assertCount(4)
        await self.assertNames(['o1', 'o2', 'o3', 'o4'])

    async def test_nested_mix(self):
        async with self.db.atomic():
            await self.create_record('t1')
            async with self.db.atomic():
                await self.create_record('t2')
                async with self.db.atomic():
                    await self.create_record('t3')
                try:
                    async with self.db.atomic():
                        await self.create_record('t4')
                        await self.assertCount(4)
                        raise ValueError('fail')
                except ValueError:
                    pass
                async with self.db.atomic() as sp:
                    await self.create_record('t4')
                    await self.assertCount(4)
                    await sp.arollback()
                await self.assertCount(3)
            try:
                async with self.db.atomic():
                    await self.create_record('t5')
                    await self.assertCount(4)
                    raise ValueError('fail')
            except ValueError:
                await self.assertCount(3)

        await self.assertCount(3)
        await self.assertNames(['t1', 't2', 't3'])

        try:
            async with self.db.atomic():
                await self.create_record('t6')
                async with self.db.atomic():
                    await self.create_record('t7')
                    async with self.db.atomic():
                        await self.create_record('t8')
                        await self.assertCount(6)
                raise ValueError('fail')
        except ValueError:
            pass

        await self.assertCount(3)
        await self.assertNames(['t1', 't2', 't3'])

    async def test_acommit_arollback(self):
        async with self.db.atomic() as txn:
            await self.create_record('committed', 1)
            await txn.acommit()
            await self.create_record('not-committed', 2)
            await txn.arollback()

        await self.assertCount(1)
        await self.assertNames(['committed'])

    async def test_concurrent_reads_writes(self):
        await self.seed(10)

        async def writer(sid):
            def _write():
                for i in range(5):
                    TestModel.create(name=f'w{sid}-{i}', value=sid * 100 + i)

            async with self.db:
                await self.db.run(_write)

        async def reader():
            async with self.db:
                query = TestModel.select()
                return await self.db.run(lambda: len(list(query)))

        await asyncio.gather(*[writer(i) for i in range(3)])
        reads = await asyncio.gather(*[reader() for _ in range(3)])
        self.assertTrue(all(r >= 10 for r in reads))
        await self.assertCount(25)

    async def test_isolated_connections_per_task(self):
        async def worker(tid):
            async with self.db:
                c1 = self.db._state.conn
                await self.create_record(f't{tid}', tid)
                return c1 is self.db._state.conn

        results = await asyncio.gather(*[worker(i) for i in range(5)])
        self.assertTrue(all(results))
        await self.assertCount(5)

    async def test_many_concurrent_tasks(self):
        ntasks = 50 if self.driver == 'sqlite' else 10
        async def task(tid):
            async with self.db:
                await self.create_record(f't{tid}', tid)
        await asyncio.gather(*[task(i) for i in range(ntasks)])
        await self.assertCount(ntasks)

    async def test_syntax_error_recovery(self):
        with self.assertRaises(Exception):
            await self.db.aexecute_sql('INVALID SQL')
        await self.create_record('after_error', 1)
        await self.assertCount(1)

    async def test_concurrent_errors(self):
        errors, successes = [], []

        async def worker(tid):
            async with self.db:
                try:
                    def work():
                        TestModel.create(name=f't{tid}', value=tid)
                        if tid % 2 == 0:
                            raise ValueError(f'Task {tid} fails')
                    await self.db.run(work)
                    successes.append(tid)
                except ValueError:
                    errors.append(tid)

        await asyncio.gather(*[worker(i) for i in range(10)])
        self.assertEqual(sorted(errors), [0, 2, 4, 6, 8])
        self.assertEqual(sorted(successes), [1, 3, 5, 7, 9])
        await self.assertCount(10)

    async def test_iterate_yields_model_instances(self):
        await self.seed(20)
        results = []
        query = TestModel.select().order_by(TestModel.value)
        async for obj in self.db.iterate(query):
            results.append(obj)

        self.assertEqual(len(results), 20)
        self.assertTrue(all(isinstance(r, TestModel) for r in results))
        self.assertEqual(results[0].name, 'item00')
        self.assertEqual(results[0].value, 0)
        self.assertEqual(results[-1].name, 'item19')
        self.assertEqual(results[-1].value, 190)

    async def test_iterate_matches_list(self):
        await self.seed(20)
        query = TestModel.select().order_by(TestModel.name)

        eager = await self.db.list(query)
        lazy = [obj async for obj in self.db.iterate(query)]
        self.assertEqual(len(eager), len(lazy))

        for e, l in zip(eager, lazy):
            self.assertEqual(e.name, l.name)
            self.assertEqual(e.value, l.value)

    async def test_iterate_dicts(self):
        await self.seed(5)
        query = TestModel.select().order_by(TestModel.name)
        results = [row async for row in self.db.iterate(query.dicts())]

        self.assertEqual(len(results), 5)
        self.assertIsInstance(results[0], dict)
        self.assertEqual(results[0]['name'], 'item00')
        self.assertEqual(results[-1]['name'], 'item04')

    async def test_iterate_tuples(self):
        await self.seed(5)
        query = TestModel.select(TestModel.name).order_by(TestModel.name)
        results = [row async for row in self.db.iterate(query.tuples())]

        self.assertEqual(len(results), 5)
        self.assertIsInstance(results[0], tuple)
        self.assertEqual(results[0][0], 'item00')
        self.assertEqual(results[-1][0], 'item04')

    async def test_iterate_namedtuples(self):
        await self.seed(5)
        query = TestModel.select(TestModel.name).order_by(TestModel.name)
        results = [row async for row in self.db.iterate(query.namedtuples())]

        self.assertEqual(len(results), 5)
        self.assertEqual(results[0].name, 'item00')
        self.assertEqual(results[0][0], 'item00')
        self.assertEqual(results[-1].name, 'item04')
        self.assertEqual(results[-1][0], 'item04')

    async def test_iterate_with_where(self):
        await self.seed(20)
        query = (TestModel.select()
                 .where(TestModel.value >= 150)
                 .order_by(TestModel.value))
        results = [row async for row in self.db.iterate(query)]

        self.assertEqual(len(results), 5)
        self.assertEqual(results[0].value, 150)
        self.assertEqual(results[-1].value, 190)

    async def test_iterate_empty(self):
        query = TestModel.select().where(TestModel.id == 0)
        results = [row async for row in self.db.iterate(query)]
        self.assertEqual(results, [])

    async def test_iterate_buffer_size(self):
        await self.seed(20)
        query = TestModel.select().order_by(TestModel.value)
        results = [obj async for obj in self.db.iterate(query, buffer_size=3)]

        self.assertEqual(len(results), 20)
        self.assertEqual(results[0].value, 0)
        self.assertEqual(results[-1].value, 190)

    async def test_iterate_early_break(self):
        await self.seed(20)
        count = 0
        query = TestModel.select().order_by(TestModel.value)
        async for obj in self.db.iterate(query):
            count += 1
            if count == 5:
                break
        self.assertEqual(count, 5)
        # Database still usable (lock released).
        self.assertEqual(await self.db.count(TestModel.select()), 20)

    async def test_iterate_aggregation(self):
        await self.seed(20)
        query = (TestModel
                 .select(fn.AVG(TestModel.value).alias('avg_val'))
                 .dicts())
        results = [row async for row in self.db.iterate(query)]

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['avg_val'], 95.0)

    async def test_iterate_sequential(self):
        await self.seed(20)
        query = (TestModel.select()
                 .where(TestModel.value < 50)
                 .order_by(TestModel.value))
        r1 = [obj.value async for obj in self.db.iterate(query)]

        query = (TestModel.select()
                 .where(TestModel.value >= 150)
                 .order_by(TestModel.value))
        r2 = [obj.value async for obj in self.db.iterate(query)]

        self.assertEqual(r1, [0, 10, 20, 30, 40])
        self.assertEqual(r2, [150, 160, 170, 180, 190])

    async def test_iterate_break_then_iterate_again(self):
        await self.seed(20)
        query = TestModel.select().order_by(TestModel.value)
        async for obj in self.db.iterate(query):
            break
        results = []
        async for obj in self.db.iterate(query):
            results.append(obj.value)
        self.assertEqual(len(results), 20)

    async def test_basic_crud(self):
        rec = await self.create_record('testx', value=2)
        self.assertEqual(rec.name, 'testx')
        fetched = await self.db.run(TestModel.get, TestModel.name == 'testx')
        self.assertEqual(fetched.value, 2)

        def update():
            r = TestModel.get(TestModel.id == rec.id)
            r.value = 100; r.save()
            return TestModel.get(TestModel.id == rec.id)
        self.assertEqual((await self.db.run(update)).value, 100)

        await self.db.run(rec.delete_instance)
        await self.assertCount(0)

    async def test_foreign_keys(self):
        users = [User(username=f'u{i}') for i in range(3)]
        await self.db.run(User.bulk_create, users)
        self.assertEqual(await self.db.run(User.select().count), 3)
        users = await self.db.list(User.select())

        async with self.db.atomic():
            for u in users:
                for i in range(2):
                    await self.db.run(
                        Tweet.create, user=u, message=f'{u.username}-{i}')

        self.assertEqual(await self.db.run(Tweet.select().count), 6)

        q = Tweet.select().where(Tweet.message == 'u0-0')
        tweet = await self.db.get(q)
        self.assertEqual(await self.db.run(lambda: tweet.user.username), 'u0')

        q = (Tweet.select(Tweet, User)
             .join(User)
             .where(Tweet.message == 'u0-0'))
        tweet = await self.db.get(q)
        self.assertEqual(tweet.user.username, 'u0')

        q = User.select().where(User.username == 'u2')
        user = await self.db.get(q)
        tweets = await self.db.list(user.tweets.order_by(Tweet.id))
        self.assertEqual([t.message for t in tweets], ['u2-0', 'u2-1'])

        users_q = User.select().order_by(User.username)
        tweets_q = Tweet.select().order_by(Tweet.message)
        await self.db.aprefetch(users_q, tweets_q)
        self.assertEqual(
            [(u.username, [t.message for t in u.tweets]) for u in users_q],
            [('u0', ['u0-0', 'u0-1']),
             ('u1', ['u1-0', 'u1-1']),
             ('u2', ['u2-0', 'u2-1'])])

    async def test_transactions(self):
        def ok_tx():
            with self.db.atomic():
                TestModel.create(name='t1', value=1)
                TestModel.create(name='t2', value=2)
        await self.db.run(ok_tx)
        await self.assertCount(2)

        def bad_tx():
            with self.db.atomic():
                TestModel.create(name='t3', value=3)
                raise ValueError('fail')
        with self.assertRaises(ValueError):
            await self.db.run(bad_tx)

        async with self.db.atomic():
            await self.create_record('t4')
            try:
                async with self.db.atomic():
                    await self.create_record('t5')
                    await self.assertCount(4)
                    raise ValueError('fail')
            except ValueError:
                pass
            await self.assertCount(3)

        await self.assertCount(3)
        await self.assertNames(['t1', 't2', 't4'])


class TestSqliteIntegration(IntegrationTests, unittest.IsolatedAsyncioTestCase):
    def get_database(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            self.db_path = f.name
        return AsyncSqliteDatabase(self.db_path)

    async def test_pragmas(self):
        db = AsyncSqliteDatabase(':memory:', pragmas={'user_version': '99'})
        conn = await db.aconnect()
        r = await conn.execute('PRAGMA user_version')
        self.assertEqual(r.fetchone(), (99,))
        await db.close_pool()

    async def test_custom_functions(self):
        db = AsyncSqliteDatabase(':memory:')

        @db.func()
        def title_case(s):
            return s.title()

        async with db:
            r = await db.aexecute_sql('SELECT title_case(?)', ('test foo',))
            self.assertEqual(r.fetchone(), ('Test Foo',))
        await db.close_pool()

    async def test_constraint_violation_recovery(self):
        await self.db.aexecute_sql(
            'CREATE TABLE ut (id INTEGER PRIMARY KEY, v TEXT UNIQUE)')
        await self.db.aexecute_sql(
            'INSERT INTO ut (v) VALUES (?)', ('x',))
        with self.assertRaises(IntegrityError):
            await self.db.aexecute_sql(
                'INSERT INTO ut (v) VALUES (?)', ('x',))
        await self.db.aexecute_sql(
            'INSERT INTO ut (v) VALUES (?)', ('y',))


@unittest.skipIf(not IS_POSTGRESQL, 'skipping postgres test')
@unittest.skipUnless(asyncpg, 'asyncpg not installed')
class TestPostgresqlIntegration(IntegrationTests, unittest.IsolatedAsyncioTestCase):
    def get_database(self):
        return AsyncPostgresqlDatabase('peewee_test', **PSQL_PARAMS)

    async def test_placeholder_conversion(self):
        def insert():
            return self.db.execute_sql(
                'INSERT INTO testmodel (name, value) VALUES (%s, %s)',
                ('placeholder_test', 999))
        await self.db.run(insert)

        def query():
            r = self.db.execute_sql(
                'SELECT * FROM testmodel WHERE name = %s',
                ('placeholder_test',))
            return r.fetchone()
        row = await self.db.run(query)
        self.assertIsNotNone(row)
        self.assertEqual(row['name'], 'placeholder_test')
        self.assertEqual(row['value'], 999)

        curs = await self.db.aexecute_sql('select %s', ('test',))
        self.assertEqual(curs.fetchone()[0], 'test')

    async def test_iterator_with_transaction(self):
        async with self.db.atomic() as tx:
            await self.seed(2)
            q = TestModel.select().order_by(TestModel.value)
            results = [obj.value async for obj in self.db.iterate(q)]
            self.assertEqual(results, [0, 10])

        await self.assertCount(2)


@unittest.skipIf(not IS_MYSQL, 'skipping mysql test')
@unittest.skipUnless(aiomysql, 'aiomysql not installed')
class TestMySQLIntegration(IntegrationTests, unittest.IsolatedAsyncioTestCase):
    def get_database(self):
        return AsyncMySQLDatabase('peewee_test', **MYSQL_PARAMS)


if __name__ == '__main__':
    unittest.main()
