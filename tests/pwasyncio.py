import asyncio
import collections
import contextlib
import contextvars
import glob
import inspect
import itertools
import tempfile
import os
import unittest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from peewee import *
from playhouse import signals
from playhouse.pwasyncio import *
from playhouse.pwasyncio import _State, _ConnectionState, _lazy_cursor_iter
from .base import MYSQL_PARAMS
from .base import PSQL_PARAMS
from .base import IS_MARIADB
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

class UniqueModel(Model):
    name = CharField(unique=True)


# Models using the async model-method mixin.

class AUser(AsyncModelMixin, Model):
    username = CharField()

class ATweet(AsyncModelMixin, Model):
    user = ForeignKeyField(AUser, backref='tweets')
    editor = ForeignKeyField(AUser, backref='edited', null=True)
    message = TextField()

class ANoLazy(AsyncModelMixin, Model):
    user = ForeignKeyField(AUser, backref='nolazy', lazy_load=False)
    message = TextField()

class AUnique(AsyncModelMixin, Model):
    name = CharField(unique=True)

class AComposite(AsyncModelMixin, Model):
    first = CharField()
    last = CharField()
    data = TextField(default='')
    class Meta:
        primary_key = CompositeKey('first', 'last')

class ADirty(AsyncModelMixin, Model):
    name = CharField()
    class Meta:
        only_save_dirty = True

class ASignal(AsyncModelMixin, signals.Model):
    name = CharField()

# Core (cross-backend) JSONField. Bound per-test via IntegrationTests helper.
class JSONM(Model):
    data = JSONField(null=True)


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

    def test_await_outside_greenlet_hint(self):
        with self.assertRaises(MissingGreenletBridge) as ctx:
            await_(Mock())
        msg = str(ctx.exception)
        self.assertIn('db.run', msg)
        self.assertIn('afetch', msg)
        self.assertIn('aexecute', msg)

    def test_await_outside_greenlet_closes_coroutine(self):
        async def coro():
            pass
        c = coro()
        with self.assertRaises(MissingGreenletBridge):
            await_(c)
        self.assertIsNone(c.cr_frame)  # Closed - no warning at GC.

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


class TestConnectionState(unittest.IsolatedAsyncioTestCase):
    async def test_task_isolation(self):
        cs = _ConnectionState()
        async def worker(tid):
            cs._current().conn = tid
            await asyncio.sleep(0.01)
            return cs._current().conn
        results = await asyncio.gather(*[worker(i) for i in range(5)])
        self.assertEqual(results, [0, 1, 2, 3, 4])

    async def test_state_attributes(self):
        cs = _ConnectionState()
        cs.set_connection('c')
        cs.transactions.append(1)
        self.assertEqual(cs.conn, 'c')
        self.assertFalse(cs.closed)
        self.assertEqual(cs.transactions, [1])

    async def test_get_returns_fresh_state(self):
        s = _ConnectionState()._current()
        self.assertIsNone(s.conn)
        self.assertTrue(s.closed)
        self.assertEqual(s.transactions, [])

    async def test_reset(self):
        cs = _ConnectionState()
        cs.set_connection('x')
        cs.transactions.append(1)
        cs.reset()
        self.assertIsNone(cs.conn)
        self.assertTrue(cs.closed)
        self.assertEqual(cs.transactions, [])

    async def test_set_connection(self):
        cs = _ConnectionState()
        m = Mock()
        cs.set_connection(m)
        self.assertIs(cs.conn, m)
        self.assertFalse(cs.closed)

    async def test_done_callback_orphans_connection(self):
        cs = _ConnectionState()
        conn_mock = Mock()

        async def acquire_and_abandon():
            cs.set_connection(conn_mock)
            return id(asyncio.current_task())

        task_id = await asyncio.create_task(acquire_and_abandon())
        # After the task completes, the done-callback should have fired.
        await asyncio.sleep(0)
        self.assertNotIn(task_id, cs._states)
        self.assertIn(conn_mock, cs._orphaned_conns)

    async def test_done_callback_noop_when_closed(self):
        cs = _ConnectionState()

        async def open_and_close():
            cs.set_connection(Mock())
            cs.reset()  # Simulate proper close.

        await asyncio.create_task(open_and_close())
        await asyncio.sleep(0)
        self.assertEqual(cs._orphaned_conns, [])


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

    def _pg_stmt(self, rows=None, status='SELECT 0'):
        mock_stmt = AsyncMock()
        mock_stmt.fetch.return_value = rows or []
        mock_stmt.get_statusmsg = Mock(return_value=status)
        mock_conn = AsyncMock()
        mock_conn.prepare.return_value = mock_stmt
        return mock_conn, mock_stmt

    async def test_pg_parameter_conversion(self):
        mock_record = Mock()
        mock_record.keys.return_value = ['id', 'name']
        mock_conn, mock_stmt = self._pg_stmt([mock_record], 'SELECT 1')

        await AsyncPostgresqlConnection(mock_conn).execute(
            'SELECT * FROM t WHERE id = %s AND name = %s', (1, 'x'))
        sql = mock_conn.prepare.call_args[0][0]
        self.assertEqual(sql, 'SELECT * FROM t WHERE id = $1 AND name = $2')
        mock_stmt.fetch.assert_awaited_once_with(1, 'x')

    async def test_pg_concurrent_serialized(self):
        order = []
        async def prepare(sql):
            order.append(f'start-{sql}')
            await asyncio.sleep(0.05)
            order.append(f'end-{sql}')
            stmt = AsyncMock()
            stmt.fetch.return_value = []
            stmt.get_statusmsg = Mock(return_value=None)
            return stmt
        mock_conn = AsyncMock()
        mock_conn.prepare = prepare

        conn = AsyncPostgresqlConnection(mock_conn)
        await asyncio.gather(conn.execute('Q1', None),
                             conn.execute('Q2', None))
        idx = {e: i for i, e in enumerate(order)}
        self.assertTrue(idx['end-Q1'] < idx['start-Q2']
                        or idx['end-Q2'] < idx['start-Q1'])

    async def test_pg_no_params(self):
        mock_conn, mock_stmt = self._pg_stmt()
        await AsyncPostgresqlConnection(mock_conn).execute(
            'SELECT * FROM t', None)
        mock_conn.prepare.assert_awaited_once_with('SELECT * FROM t')
        mock_stmt.fetch.assert_awaited_once_with()

    async def test_pg_empty_results(self):
        mock_conn, _ = self._pg_stmt()
        r = await AsyncPostgresqlConnection(mock_conn).execute(
            'SELECT * FROM empty')
        self.assertEqual(r.fetchall(), [])
        self.assertEqual(r.description, [])

    async def test_pg_rowcount_from_status(self):
        for status, expected in (('UPDATE 3', 3), ('DELETE 2', 2),
                                 ('INSERT 0 4', 4), ('SELECT 0', 0),
                                 (None, 0), ('CREATE TABLE', 0)):
            mock_conn, _ = self._pg_stmt(status=status)
            r = await AsyncPostgresqlConnection(mock_conn).execute('Q')
            self.assertEqual(r.rowcount, expected)

    def test_translate_placeholders(self):
        f = AsyncPostgresqlConnection._translate_placeholders
        self.assertEqual(f('SELECT 1'), 'SELECT 1')
        self.assertEqual(
            f('SELECT * FROM t WHERE a = %s AND b = %s'),
            'SELECT * FROM t WHERE a = $1 AND b = $2')
        self.assertEqual(
            f('INSERT INTO t VALUES (%s, %s, %s)'),
            'INSERT INTO t VALUES ($1, $2, $3)')
        # Like psycopg, %s is a placeholder even inside quoted strings -
        # literal values must be passed as parameters.
        self.assertEqual(
            f("SELECT * FROM t WHERE x LIKE '%s' AND y = %s"),
            "SELECT * FROM t WHERE x LIKE '$1' AND y = $2")
        # %% is an escaped literal percent, also mirroring psycopg.
        self.assertEqual(
            f("SELECT * FROM t WHERE x LIKE 'a%%b' AND y = %s"),
            "SELECT * FROM t WHERE x LIKE 'a%b' AND y = $1")
        self.assertEqual(f('100%% of %s'), '100% of $1')

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

        async with self.db:
            await self.db.acreate_tables([TestModel])

    async def asyncTearDown(self):
        await self.db.close_pool()

        if self.db_path and os.path.exists(self.db_path):
            for fname in glob.glob(self.db_path + '*'):
                os.unlink(fname)

    async def test_task_id_behavior(self):
        async def a1(db):
            accum = []
            async with db:
                accum.append(db._state._current())
                accum.append(await a2(db))
            return accum

        async def a2(db):
            async with db:
                return db._state._current()

        def s1(db):
            accum = []
            with db.connection_context():
                accum.append(db._state._current())
                accum.append(s2(db))
            return accum

        def s2(db):
            with db.connection_context():
                return db._state._current()

        async with self.db:
            ids = await(a1(self.db))
            ids.extend(await self.db.run(s1, self.db))

        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 1)

        async with self.db:
            ids = await asyncio.create_task(a1(self.db))
            ids.extend(await asyncio.create_task(self.db.run(s1, self.db)))

        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 2)

    async def test_task_state_cleanup_after_completion(self):
        async def task_with_state():
            async with self.db:
                await self.db.run(TestModel.create, name='test', value=1)
            return id(asyncio.current_task())

        await asyncio.create_task(task_with_state())

        # Child task properly closed connection (async with db), so close pool
        # should exit cleanly.
        await asyncio.wait_for(self.db.close_pool(), timeout=2.0)

        # Verify the write persisted.
        async with self.db:
            self.assertEqual(await self.db.count(TestModel.select()), 1)

    async def test_concurrent_task_state_isolation(self):
        async def capture(tid):
            async with self.db:
                before = id(self.db._state._current())
                await self.db.run(TestModel.create, name=f't{tid}', value=tid)
                after = id(self.db._state._current())
                self.assertEqual(before, after)
                return before

        results = await asyncio.gather(*[capture(i) for i in range(5)])
        self.assertTrue(all(results))
        self.assertEqual(len(set(results)), 5)

    async def test_connection_returned_when_task_dies(self):
        async def acquire_and_abandon():
            await self.db.aconnect()
            return  # Connection is not closed, callback must handle cleanup.

        await asyncio.create_task(acquire_and_abandon())

        # The done-callback should have moved the connection to orphaned
        # connections, which are handled either via done callback or during
        # pool shutdown.
        await asyncio.wait_for(self.db.close_pool(), timeout=2.0)


class TestQueryAexecuteErrors(unittest.IsolatedAsyncioTestCase):
    async def test_unbound_query(self):
        class M(Model):
            name = CharField()
        with self.assertRaises(InterfaceError) as ctx:
            await M.select().aexecute()
        self.assertIn('aexecute', str(ctx.exception))

    async def test_sync_database(self):
        class M(Model):
            name = CharField()
            class Meta:
                database = SqliteDatabase(':memory:')
        with self.assertRaises(AttributeError) as ctx:
            await M.select().aexecute()
        self.assertIn('SqliteDatabase', str(ctx.exception))

    def test_is_coroutine_function(self):
        self.assertTrue(inspect.iscoroutinefunction(Select.aexecute))

    async def test_explicit_database_no_rebind(self):
        a1 = AsyncSqliteDatabase(':memory:', pool_size=1)
        a2 = AsyncSqliteDatabase(':memory:', pool_size=1)
        class M(Model):
            name = CharField()
            class Meta:
                database = a1
        await a1.aconnect()
        await a1.acreate_tables([M])
        await a2.aconnect()
        def create_in_a2():
            with M.bind_ctx(a2):
                M.create_table()
        await a2.run(create_in_a2)
        await M.insert(name='in-a2').aexecute(a2)

        q = M.select()
        self.assertEqual([r.name for r in await q.aexecute(a2)], ['in-a2'])
        self.assertIs(q._database, a1)  # Explicit database did not rebind.
        self.assertEqual(await a1.count(M.select()), 0)
        await a1.close_pool()
        await a2.close_pool()

    async def test_proxy_not_unwrapped(self):
        proxy = DatabaseProxy()
        class M(Model):
            name = CharField()
            class Meta:
                database = proxy
        adb = AsyncSqliteDatabase(':memory:', pool_size=1)
        proxy.initialize(adb)
        await adb.aconnect()
        await adb.acreate_tables([M])
        await M.insert(name='x').aexecute()

        q = M.select()
        self.assertEqual([r.name for r in await q.aexecute()], ['x'])
        self.assertIs(q._database, proxy)  # Binding is still the proxy.
        await adb.close_pool()


class IntegrationTests(object):
    db_path = None
    models = [TestModel, User, Tweet, UniqueModel, AUser, ATweet, ANoLazy,
              AUnique, AComposite, ADirty, ASignal]

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
        await self.db.aclose()
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

    async def test_amodel_create_get(self):
        u = await AUser.acreate(username='u1')
        self.assertIsNotNone(u.id)

        ug = await AUser.aget(AUser.username == 'u1')
        self.assertEqual(ug.id, u.id)
        ug = await AUser.aget(username='u1')
        self.assertEqual(ug.id, u.id)
        ug = await AUser.aget_by_id(u.id)
        self.assertEqual(ug.username, 'u1')

        self.assertIsNone(await AUser.aget_or_none(AUser.username == 'ux'))
        with self.assertRaises(AUser.DoesNotExist):
            await AUser.aget(AUser.username == 'ux')

    async def test_amodel_save_update_delete(self):
        u = await AUser.acreate(username='u1')
        u.username = 'u2'
        self.assertEqual(await u.asave(), 1)
        self.assertEqual((await AUser.aget_by_id(u.id)).username, 'u2')

        await AUser.aset_by_id(u.id, {'username': 'u3'})
        self.assertEqual((await AUser.aget_by_id(u.id)).username, 'u3')

        self.assertEqual(await u.adelete_instance(), 1)
        self.assertIsNone(await AUser.aget_or_none(AUser.id == u.id))

        u2 = await AUser.acreate(username='u4')
        await AUser.adelete_by_id(u2.id)
        self.assertIsNone(await AUser.aget_or_none(AUser.id == u2.id))

    async def test_amodel_get_or_create(self):
        o1, created = await AUnique.aget_or_create(name='k')
        self.assertTrue(created)
        o2, created = await AUnique.aget_or_create(name='k')
        self.assertFalse(created)
        self.assertEqual(o1.id, o2.id)

    async def test_aget_or_create_race(self):
        # Core's IntegrityError race-recovery, exercised from two tasks on
        # two pool connections.
        async def attempt():
            return await AUnique.aget_or_create(name='race')
        (o1, c1), (o2, c2) = await asyncio.gather(attempt(), attempt())
        self.assertEqual(sorted([c1, c2]), [False, True])
        self.assertEqual(o1.id, o2.id)

    async def test_abulk_create_update(self):
        users = [AUser(username='b%s' % i) for i in range(5)]
        await AUser.abulk_create(users, 2)
        q = AUser.select().where(AUser.username.startswith('b'))
        self.assertEqual(await self.db.count(q), 5)

        if self.driver == 'postgresql':
            return  # bulk_update incompatible with asyncpg (documented).

        objs = await self.db.list(q.order_by(AUser.username))
        for o in objs:
            o.username += 'x'
        await AUser.abulk_update(objs, [AUser.username], 2)
        names = [u.username for u in
                 await self.db.list(q.order_by(AUser.username))]
        self.assertEqual(names, ['b0x', 'b1x', 'b2x', 'b3x', 'b4x'])

    async def test_asave_composite_key(self):
        c = AComposite(first='a', last='b', data='x')
        self.assertEqual(await c.asave(force_insert=True), 1)
        c.data = 'y'
        self.assertEqual(await c.asave(), 1)
        cg = await AComposite.aget(AComposite.first == 'a',
                                   AComposite.last == 'b')
        self.assertEqual(cg.data, 'y')

    async def test_asave_only_save_dirty(self):
        d = await ADirty.acreate(name='d1')
        self.assertFalse(await d.asave())  # No dirty fields -> False.
        d.name = 'd2'
        self.assertEqual(await d.asave(), 1)
        self.assertEqual((await ADirty.aget_by_id(d.id)).name, 'd2')

    async def test_signals_inside_bridge(self):
        accum = []
        def pre_save(sender, instance, created):
            accum.append(('pre_save', created))
        def post_save(sender, instance, created):
            accum.append(('post_save', created))
        def pre_delete(sender, instance):
            accum.append(('pre_delete',))
        def post_delete(sender, instance):
            accum.append(('post_delete',))

        signals.pre_save.connect(pre_save, sender=ASignal)
        signals.post_save.connect(post_save, sender=ASignal)
        signals.pre_delete.connect(pre_delete, sender=ASignal)
        signals.post_delete.connect(post_delete, sender=ASignal)
        try:
            s = ASignal(name='s1')
            await s.asave()
            await s.adelete_instance()
        finally:
            signals.pre_save.disconnect(pre_save, sender=ASignal)
            signals.post_save.disconnect(post_save, sender=ASignal)
            signals.pre_delete.disconnect(pre_delete, sender=ASignal)
            signals.post_delete.disconnect(post_delete, sender=ASignal)

        self.assertEqual(accum, [
            ('pre_save', True), ('post_save', True),
            ('pre_delete',), ('post_delete',)])

    async def test_afetch(self):
        u = await AUser.acreate(username='af')
        t_id = (await ATweet.acreate(user=u, message='m')).id

        t = await ATweet.aget_by_id(t_id)
        self.assertNotIn('user', t.__rel__)
        rel = await t.afetch(ATweet.user)
        self.assertEqual(rel.id, u.id)
        self.assertIn('user', t.__rel__)
        self.assertIs(t.user, rel)  # Plain access is now cache-hit.

        # String forms resolve via _meta.combined: name and column name.
        t2 = await ATweet.aget_by_id(t_id)
        self.assertEqual((await t2.afetch('user')).id, u.id)
        t3 = await ATweet.aget_by_id(t_id)
        self.assertEqual((await t3.afetch('user_id')).id, u.id)

        with self.assertRaises(ValueError):
            await t.afetch(ATweet.message)  # Non-FK field.
        with self.assertRaises(KeyError):
            await t.afetch('nope')  # Unknown name, core parity.

        # Nullable FK, not set -> None.
        self.assertIsNone(await t.afetch(ATweet.editor))

    async def test_afetch_cache_hit_no_bridge(self):
        u = await AUser.acreate(username='af2')
        await ATweet.acreate(user=u, message='m2')

        t = await self.db.get(
            ATweet.select(ATweet, AUser).join(AUser, on=ATweet.user))
        self.assertIn('user', t.__rel__)

        # Swap in a database lacking `run` to prove no bridge is used.
        real_db = ATweet._meta.database
        ATweet._meta.database = Mock(spec=[])
        try:
            rel = await t.afetch(ATweet.user)
        finally:
            ATweet._meta.database = real_db
        self.assertEqual(rel.username, 'af2')

    async def test_afetch_after_aprefetch(self):
        u = await AUser.acreate(username='af3')
        await ATweet.acreate(user=u, message='m3')

        users = await self.db.aprefetch(
            AUser.select().where(AUser.username == 'af3'), ATweet.select())
        tweet = users[0].tweets[0]
        self.assertIn('user', tweet.__rel__)

        real_db = ATweet._meta.database
        ATweet._meta.database = Mock(spec=[])
        try:
            rel = await tweet.afetch(ATweet.user)
        finally:
            ATweet._meta.database = real_db
        self.assertEqual(rel.id, u.id)

    async def test_afetch_lazy_load_false(self):
        u = await AUser.acreate(username='nl')
        n = await ANoLazy.acreate(user=u, message='x')

        ng = await ANoLazy.aget_by_id(n.id)
        with self.assertRaises(ValueError) as ctx:
            await ng.afetch(ANoLazy.user)
        self.assertIn('lazy_load', str(ctx.exception))
        self.assertEqual((await AUser.aget_by_id(ng.user)).id, u.id)

    async def test_afetch_missing_rel(self):
        if self.driver != 'sqlite':
            self.skipTest('FK constraints enforced on this backend')
        # Same task -> same connection, so the pragma applies to the insert.
        await self.db.aexecute_sql('PRAGMA foreign_keys=0')
        try:
            await self.db.aexecute(ATweet.insert(user=99999,
                                                 message='orphan'))
        finally:
            await self.db.aexecute_sql('PRAGMA foreign_keys=1')
        t = await ATweet.aget(ATweet.message == 'orphan')
        with self.assertRaises(AUser.DoesNotExist):
            await t.afetch(ATweet.user)

    async def test_db_model_property(self):
        base = self.db.Model
        self.assertTrue(issubclass(base, AsyncModel))
        self.assertIs(base, self.db.Model)  # Cached.

        DynModel = type('DynModel', (base,), {'name': CharField()})
        await self.db.acreate_tables([DynModel])
        try:
            obj = await DynModel.acreate(name='dyn')
            got = await DynModel.aget(DynModel.name == 'dyn')
            self.assertEqual(got.id, obj.id)
        finally:
            await self.db.adrop_tables([DynModel])

    async def test_amodel_sync_db_raises(self):
        sync_db = SqliteDatabase(':memory:')
        class SyncBound(AsyncModelMixin, Model):
            name = CharField()
            class Meta:
                database = sync_db
        with self.assertRaises(InterfaceError) as ctx:
            await SyncBound.acreate(name='x')
        self.assertIn('Async database', str(ctx.exception))

    async def test_amodel_unbound_raises(self):
        class Unbound(AsyncModelMixin, Model):
            name = CharField()
            class Meta:
                database = None
        with self.assertRaises(InterfaceError) as ctx:
            await Unbound.acreate(name='x')
        self.assertIn('not bound', str(ctx.exception))

    async def test_amodel_proxy(self):
        proxy = DatabaseProxy()
        class PModel(AsyncModelMixin, Model):
            name = CharField()
            class Meta:
                database = proxy

        with self.assertRaises(InterfaceError):
            await PModel.acreate(name='x')  # Uninitialized proxy.

        proxy.initialize(self.db)
        await self.db.acreate_tables([PModel])
        try:
            p = await PModel.acreate(name='x')
            self.assertEqual((await PModel.aget_by_id(p.id)).name, 'x')
        finally:
            await self.db.adrop_tables([PModel])

    async def test_gather_inside_atomic(self):
        # Tasks spawned inside a transaction get their own connections and run
        # OUTSIDE the transaction.
        conn_ids = []
        async def child(i):
            conn_ids.append(id(self.db._state._current()))
            await AUser.acreate(username='child%s' % i)

        class Abort(Exception):
            pass

        parent_state = []
        try:
            async with self.db.atomic():
                parent_state.append(id(self.db._state._current()))
                await asyncio.gather(child(1), child(2))
                raise Abort()
        except Abort:
            pass

        # Children used distinct connections, not the parent's...
        self.assertEqual(len(set(conn_ids)), 2)
        self.assertNotIn(parent_state[0], conn_ids)
        # ...so their writes survived the parent's rollback.
        q = AUser.select().where(AUser.username.startswith('child'))
        self.assertEqual(await self.db.count(q), 2)

    async def test_query_outside_bridge_hint(self):
        with self.assertRaises(MissingGreenletBridge) as ctx:
            list(TestModel.select())
        msg = str(ctx.exception)
        self.assertTrue(msg.startswith(
            'Attempted query outside greenlet runner: SELECT'))
        self.assertIn('db.run', msg)
        self.assertIn('afetch', msg)

    async def test_db_first(self):
        self.assertIsNone(await self.db.first(TestModel.select()))
        await self.seed(3)
        first = await self.db.first(
            TestModel.select().order_by(TestModel.value))
        self.assertEqual(first.name, 'item00')

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
            self.assertEqual(sorted([t.name for t in res]),
                             [f'item{i}' for i in range(10)])
        else:
            await self.db.aexecute(q)
        await self.assertCount(10)

        q = (TestModel
             .update(value=TestModel.value * 10)
             .where((TestModel.value > 0) & (TestModel.value < 3)))

        if self.support_returning:
            q = q.returning(TestModel.name, TestModel.value)
            res = await self.db.aexecute(q)
            self.assertEqual(sorted([(t.name, t.value) for t in res]),
                             [('item1', 10), ('item2', 20)])
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

    async def test_query_aexecute(self):
        # BaseQuery.aexecute() - postfix twin of db.aexecute(query).
        q = TestModel.insert_many([(f'item{i}', i) for i in range(10)])
        if self.support_returning:
            q = q.returning(TestModel.name)
            res = await q.aexecute()
            self.assertEqual(sorted([t.name for t in res]),
                             [f'item{i}' for i in range(10)])
        else:
            await q.aexecute()
        await self.assertCount(10)

        q = (TestModel
             .update(value=TestModel.value * 10)
             .where((TestModel.value > 0) & (TestModel.value < 3)))
        if self.support_returning:
            q = q.returning(TestModel.name, TestModel.value)
            res = await q.aexecute()
            self.assertEqual(sorted([(t.name, t.value) for t in res]),
                             [('item1', 10), ('item2', 20)])
        else:
            res = await q.aexecute()
            self.assertEqual(res, 2)

        q = (TestModel
             .select()
             .where(TestModel.value >= 10)
             .order_by(TestModel.value))
        rows = await q.aexecute()
        self.assertEqual([r.name for r in rows], ['item1', 'item2'])

        # Interchangeable with db.aexecute() and, for iteration, db.list().
        # Clones ensure these execute fresh instead of reading q's cache.
        self.assertEqual([r.name for r in await self.db.aexecute(q.clone())],
                         ['item1', 'item2'])
        self.assertEqual([r.name for r in await self.db.list(q.clone())],
                         ['item1', 'item2'])

        q = TestModel.delete().where(TestModel.value >= 10)
        if self.support_returning:
            q = q.returning(TestModel.name)
            res = await q.aexecute()
            self.assertEqual(sorted([t.name for t in res]),
                             ['item1', 'item2'])
        else:
            res = await q.aexecute()
            self.assertEqual(res, 2)
        await self.assertCount(8)

        pk = await TestModel.insert(name='solo', value=99).aexecute()
        obj = await self.db.run(TestModel.get_by_id, pk)
        self.assertEqual(obj.name, 'solo')

    async def test_query_aexecute_semantics(self):
        await self.seed(3)
        q = TestModel.select().order_by(TestModel.name)
        r1 = await q.aexecute()
        r2 = await q.aexecute()
        self.assertIs(r1, r2)  # Sync execute() parity: select result cached.

        u = TestModel.update(value=TestModel.value + 1)
        self.assertEqual(await u.aexecute(), 3)
        self.assertEqual(await u.aexecute(), 3)  # Writes re-execute.

    async def test_query_aexecute_backref(self):
        u = await AUser.acreate(username='u1')
        for i in range(3):
            await ATweet.acreate(user=u, message=f't{i}')

        tweets = await u.tweets.aexecute()
        self.assertEqual(sorted(t.message for t in tweets),
                         ['t0', 't1', 't2'])

    async def test_query_aexecute_compound(self):
        await self.seed(4)
        lhs = TestModel.select().where(TestModel.value == 0)
        rhs = TestModel.select().where(TestModel.value == 30)
        res = await (lhs | rhs).aexecute()
        self.assertEqual(sorted([r.name for r in res]),
                         ['item00', 'item03'])

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

    async def test_iterate_multi(self):
        await self.seed(10)
        async def iterate_multi():
            async with self.db:
                query = TestModel.select().order_by(TestModel.value)
                return [obj.id async for obj in self.db.iterate(query)]

        results = await asyncio.gather(*[iterate_multi() for i in range(5)])
        self.assertEqual(len(results), 5)
        self.assertTrue(all(len(r) == 10 for r in results))

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

    async def test_update_delete_rowcount(self):
        for name in ('a', 'b', 'c'):
            await self.create_record(name)
        # NB: use a new value - MySQL reports affected (changed) rows.
        n = await self.db.aexecute(
            TestModel.update(value=99).where(TestModel.name != 'a'))
        self.assertEqual(n, 2)
        n = await self.db.aexecute(TestModel.delete())
        self.assertEqual(n, 3)

    async def test_nested_iterate(self):
        await self.seed(3)
        with patch.object(AsyncConnectionWrapper, 'streaming_timeout', 0.25):
            it = self.db.iterate(TestModel.select())
            with self.assertRaises(InterfaceError):
                async for row in it:
                    async for row2 in self.db.iterate(TestModel.select()):
                        pass
            await it.aclose()
        # The connection is usable again afterwards.
        await self.assertCount(3)

    async def test_integrity_error_translation(self):
        await self.db.run(UniqueModel.create, name='u1')
        with self.assertRaises(IntegrityError):
            await self.db.run(UniqueModel.create, name='u1')
        # The connection remains usable afterwards.
        await self.db.run(UniqueModel.create, name='u2')

    async def test_query_during_iterate(self):
        await self.seed(3)
        it = self.db.iterate(TestModel.select())
        with patch.object(AsyncConnectionWrapper, 'streaming_timeout', 0.25):
            with self.assertRaises(InterfaceError):
                async for row in it:
                    await self.db.scalar(
                        TestModel.select(fn.MAX(TestModel.value)))
        await it.aclose()
        # The connection is usable again afterwards.
        await self.assertCount(3)

    async def test_task_death_rolls_back_transaction(self):
        await self.create_record('keep')

        async def dirty():
            txn = self.db.atomic()
            await txn.__aenter__()
            await self.create_record('dirty')
            # Task ends without commit/rollback or close().

        await asyncio.ensure_future(dirty())
        for _ in range(10):  # Allow the done-callback to orphan the conn.
            await asyncio.sleep(0.01)
            if self.db._state._orphaned_conns:
                break
        await self.db.aconnect()  # Drains the orphan: rolls back, releases.
        await self.assertCount(1)
        await self.create_record('after')
        await self.assertCount(2)

    @contextlib.asynccontextmanager
    async def _json_model(self):
        # Bind the core JSONField model to the active async db and manage its
        # table. Skips where JSON is unsupported (e.g. ancient SQLite).
        try:
            JSONM._meta.set_database(self.db)
        except NotSupportedError:
            self.skipTest('JSONField not supported on this backend')
        await self.db.adrop_tables([JSONM])
        await self.db.acreate_tables([JSONM])
        try:
            yield JSONM
        finally:
            await self.db.adrop_tables([JSONM])

    async def test_json_field(self):
        # Round-trips on every async backend: nested objects, arrays, unicode,
        # quotes, and a top-level array document.
        async with self._json_model() as M:
            payload = {'k': 'v', 'n': 5, 'nested': {'a': [1, 2, 3]},
                       'q': "O'Brien", 'u': 'café 日本語'}
            o = await self.db.run(M.create, data=payload)
            row = await self.db.get(M.select().where(M.id == o.id))
            self.assertEqual(row.data, payload)

            o2 = await self.db.run(M.create, data=[1, 'two', {'three': 3}])
            row2 = await self.db.get(M.select().where(M.id == o2.id))
            self.assertEqual(row2.data, [1, 'two', {'three': 3}])

    async def test_json_extract(self):
        # Path extraction, casts, and path comparisons in WHERE.
        async with self._json_model() as M:
            o = await self.db.run(M.create, data={
                'a': {'b': {'c': 42}}, 'arr': [10, 20, 30], 's': 'hi'})

            async def val(expr):
                return await self.db.scalar(M.select(expr).where(M.id == o.id))

            self.assertEqual(await val(M.data['a']['b']['c']), 42)
            self.assertEqual(await val(M.data.path('a', 'b', 'c')), 42)
            self.assertEqual(await val(M.data['arr'][1]), 20)
            self.assertEqual(await val(M.data['s'].as_text()), 'hi')
            as_int = await val(M.data['a']['b']['c'].as_int())
            self.assertEqual(as_int, 42)
            self.assertIsInstance(as_int, int)

            async def count(expr):
                return await self.db.count(M.select().where(expr))

            self.assertEqual(await count(M.data['s'] == 'hi'), 1)
            self.assertEqual(await count(M.data['a']['b']['c'] == 42), 1)
            self.assertEqual(await count(M.data['s'] != 'nope'), 1)
            # == None catches SQL NULL, a missing key, and stored JSON null.
            self.assertEqual(await count(M.data['missing'] == None), 1)

    async def test_json_mutations(self):
        # set/append/remove/length/update all read back the mutated document.
        async with self._json_model() as M:
            async def data_of(oid):
                row = await self.db.get(M.select().where(M.id == oid))
                return row.data

            o = await self.db.run(M.create, data={'a': {'b': 1}})
            await self.db.aexecute(M.update(data=M.data['a']['b'].set(99))
                                   .where(M.id == o.id))
            self.assertEqual((await data_of(o.id))['a']['b'], 99)

            o = await self.db.run(M.create, data={'arr': [1, 2]})
            await self.db.aexecute(M.update(data=M.data['arr'].append(3))
                                   .where(M.id == o.id))
            self.assertEqual(await self.db.scalar(
                M.select(M.data['arr'].length()).where(M.id == o.id)), 3)
            self.assertEqual((await data_of(o.id))['arr'], [1, 2, 3])

            o = await self.db.run(M.create, data={'keep': 1, 'drop': 2})
            await self.db.aexecute(M.update(data=M.data['drop'].remove())
                                   .where(M.id == o.id))
            self.assertEqual(await data_of(o.id), {'keep': 1})

            # A disjoint-key merge agrees across PG's `||` and MySQL/SQLite's
            # RFC-7396 patch.
            o = await self.db.run(M.create, data={'a': 1})
            await self.db.aexecute(M.update(data=M.data.update({'b': 2}))
                                   .where(M.id == o.id))
            self.assertEqual(await data_of(o.id), {'a': 1, 'b': 2})

    async def test_json_has_key(self):
        # Key-existence predicates run on every async backend (SQLite via
        # json_type, MySQL via JSON_CONTAINS_PATH, PG via ?/?&/?|).
        async with self._json_model() as M:
            await self.db.run(M.create,
                              data={'k': 'v', 'tags': ['a', 'b'], 'n': 5})
            await self.db.run(M.create, data={'meta': {'x': 1}})

            async def count(expr):
                return await self.db.count(M.select().where(expr))

            self.assertEqual(await count(M.data.has_key('k')), 1)
            self.assertEqual(await count(M.data.has_key('absent')), 0)
            self.assertEqual(await count(M.data.has_keys(['k', 'n'])), 1)
            self.assertEqual(await count(M.data.has_keys(['k', 'absent'])), 0)
            self.assertEqual(await count(M.data.has_any_keys(['zzz', 'n'])), 1)
            self.assertEqual(await count(M.data.has_any_keys(['y', 'z'])), 0)
            # Key existence under a nested path prefix.
            self.assertEqual(await count(M.data['meta'].has_key('x')), 1)

    async def test_json_containment(self):
        # @> / <@ on every async backend: PostgreSQL, MySQL, and SQLite (via
        # the _pw_json_contains UDF loaded onto each connection).
        async with self._json_model() as M:
            await self.db.run(M.create,
                              data={'k': 'v', 'tags': ['a', 'b'], 'n': 5})

            async def count(expr):
                return await self.db.count(M.select().where(expr))

            self.assertEqual(await count(M.data.contains({'k': 'v'})), 1)
            self.assertEqual(await count(M.data.contains({'tags': ['a']})), 1)
            self.assertEqual(await count(M.data.contained_by(
                {'k': 'v', 'tags': ['a', 'b'], 'n': 5, 'x': 0})), 1)

    async def test_sync_query_outside_bridge(self):
        with self.assertRaises(MissingGreenletBridge):
            list(TestModel.select())


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

    async def test_iterate_error_rolls_back(self):
        await self.seed(2)
        with self.assertRaises(ProgrammingError):
            async for row in self.db.iterate(
                    TestModel.select(SQL('no_such_column'))):
                pass

        # The connection is not stuck inside an aborted transaction.
        self.assertFalse(self.db._state.conn.conn.is_in_transaction())
        await self.assertCount(2)

    async def test_json_field_jsonb(self):
        # Core JSONField maps to a real jsonb column on Postgres; values with
        # %s/%% survive asyncpg placeholder translation (they ride as bound
        # params); and jsonb decodes through the server-side cursor.
        async with self._json_model() as M:
            r = await self.db.aexecute_sql(
                'SELECT data_type FROM information_schema.columns '
                'WHERE table_name = %s AND column_name = %s',
                (M._meta.table_name, 'data'))
            self.assertEqual(r.fetchone()[0], 'jsonb')

            payload = {'fmt': 'up 5%s vs 3%% last %s', 'q': 'a"b\\c'}
            o = await self.db.run(M.create, data=payload)
            row = await self.db.get(M.select().where(M.id == o.id))
            self.assertEqual(row.data, payload)

            async with self.db.atomic():
                await self.db.run(M.create, data={'seed': 'A'})
                await self.db.run(M.create, data={'seed': 'B'})
                seeds = sorted([obj.data['seed'] async for obj in
                                self.db.iterate(M.select()
                                .where(M.data.has_key('seed'))
                                .order_by(M.id))])
            self.assertEqual(seeds, ['A', 'B'])


@unittest.skipIf(not IS_MYSQL, 'skipping mysql test')
@unittest.skipUnless(aiomysql, 'aiomysql not installed')
class TestMySQLIntegration(IntegrationTests, unittest.IsolatedAsyncioTestCase):
    def get_database(self):
        return AsyncMySQLDatabase('peewee_test', mariadb=IS_MARIADB,
                                  **MYSQL_PARAMS)


if __name__ == '__main__':
    unittest.main()


class TestConnectErrorTranslation(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_connect_error_translated(self):
        db = AsyncSqliteDatabase('/peewee-nonexistent/foo.db')
        try:
            with self.assertRaises(OperationalError):
                await db.aconnect()
        finally:
            await db.close_pool()
