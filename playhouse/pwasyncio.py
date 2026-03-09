import asyncio
import logging
import weakref

from greenlet import greenlet, getcurrent
from peewee import *
from peewee import _atomic, _savepoint, _transaction
from peewee import __exception_wrapper__

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

try:
    import asyncpg
except ImportError:
    asyncpg = None

try:
    import aiomysql
except ImportError:
    aiomysql = None


logger = logging.getLogger(__name__)


class MissingGreenletBridge(RuntimeError):
    pass


async def greenlet_spawn(fn, *args, **kwargs):
    parent = getcurrent()
    result = None
    error = None

    def runner():
        nonlocal result, error
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:
            error = exc

    # Run the sync code in a greenlet - the sync code must use await_()
    # whenever blocking would occur. await_() transfers a coroutine and control
    # back up to this runner, which can safely `await` the coroutine before
    # switching back to the sync code.
    g = greenlet(runner, parent=parent)
    g.gr_context = parent.gr_context
    value = g.switch()
    while not g.dead:
        try:
            value = g.switch(await value)
        except BaseException as exc:
            value = g.throw(exc)

    if error:
        raise error
    return result


def await_(awaitable):
    current = getcurrent()
    parent = current.parent
    if parent is None:
        raise MissingGreenletBridge('await_() called outside greenlet_spawn()')
    return parent.switch(awaitable)


class _State(object):
    __slots__ = ('conn', 'closed', 'transactions')
    def __init__(self):
        self.conn = None
        self.closed = True
        self.transactions = []


class TaskLocal(object):
    # Interval (in number of _current() calls) between automatic cleanups of
    # dead-task state. Set to 0 to disable periodic cleanup.
    _CLEANUP_INTERVAL = 100

    def __init__(self):
        self._state_storage = {}  # Keyed by task id.
        self._task_refs = weakref.WeakSet()
        self._access_count = 0

    def _get_storage_key(self):
        try:
            task = asyncio.current_task()
            if task is not None:
                self._task_refs.add(task)
                return id(task)
        except RuntimeError:
            pass

    def _current(self):
        key = self._get_storage_key()
        if key is None:
            raise RuntimeError('Cannot determine current task')

        if key not in self._state_storage:
            self._state_storage[key] = _State()

        # Periodically clean up state for dead tasks to prevent memory leaks.
        if self._CLEANUP_INTERVAL > 0:
            self._access_count += 1
            if self._access_count >= self._CLEANUP_INTERVAL:
                self._access_count = 0
                self.cleanup_dead_tasks()

        return self._state_storage[key]

    def __getattr__(self, name):
        return getattr(self._current(), name)

    def __setattr__(self, name, value):
        if name in ('_state_storage', '_task_refs', '_access_count'):
            super(TaskLocal, self).__setattr__(name, value)
        else:
            setattr(self._current(), name, value)

    def __delattr__(self, name):
        delattr(self._current(), name)

    def get(self):
        return self._current()

    def clear(self):
        key = self._get_storage_key()
        if key and key in self._state_storage:
            del self._state_storage[key]

    def reset(self):
        key = self._get_storage_key()
        if key and key in self._state_storage:
            state = self._state_storage[key]
            state.conn = None
            state.closed = True
            state.transactions = []

    def set_connection(self, conn):
        self.conn = conn
        self.closed = False

    def cleanup_dead_tasks(self):
        live_task_ids = {id(task) for task in self._task_refs}
        dead_keys = [key for key in self._state_storage
                     if key not in live_task_ids]
        for key in dead_keys:
            del self._state_storage[key]
        return len(dead_keys)


class _async_transaction_helper(object):
    async def __aenter__(self):
        return await self.db.run(self.__enter__)

    async def __aexit__(self, exc_typ, exc, tb):
        return await self.db.run(self.__exit__, exc_typ, exc, tb)

    async def acommit(self):
        return await self.db.run(self.commit)

    async def arollback(self):
        return await self.db.run(self.rollback)


class async_atomic(_async_transaction_helper, _atomic): pass
class async_transaction(_async_transaction_helper, _transaction): pass
class async_savepoint(_async_transaction_helper, _savepoint): pass


class AsyncDatabaseMixin(object):
    def __init__(self, database, **kwargs):
        self._pool_size = kwargs.pop('pool_size', 10)
        self._pool_min_size = kwargs.pop('pool_min_size', 1)
        self._acquire_timeout = kwargs.pop('acquire_timeout', 10)
        super(AsyncDatabaseMixin, self).__init__(database, **kwargs)

        self._state = TaskLocal()
        self._pool = None
        self._pool_lock = asyncio.Lock()
        self._closing = False  # Guard against use during shutdown.

    def execute_sql(self, sql, params=None):
        try:
            return await_(self.aexecute_sql(sql, params or ()))
        except MissingGreenletBridge as exc:
            raise MissingGreenletBridge(
                f'Attempted query {sql} ({params}) outside greenlet runner.') \
                    from exc

    async def aexecute_sql(self, sql, params=None):
        conn = await self.aconnect()
        with __exception_wrapper__:
            return await conn.execute(sql, params)

    def connect(self):
        return await_(self.aconnect())

    async def aconnect(self):
        if self._closing:
            raise InterfaceError('Database pool is shutting down.')

        conn = self._state.conn
        if conn is None or conn.conn is None:
            if conn is not None:
                # Previous connection was invalidated; release it.
                await self._pool_release(conn)
            conn = await self._acquire_conn_async()
            self._state.set_connection(conn)
        return conn

    def close(self):
        return await_(self.aclose())

    async def aclose(self):
        conn = self._state.conn
        if conn:
            self._state.reset()
            logger.debug('Releasing connection %s to pool.', id(conn))
            await self._pool_release(conn)

    async def _acquire_conn_async(self):
        async with self._pool_lock:
            if self._pool is None:
                self._pool = await self._create_pool_async()

        conn = await self._pool_acquire()
        logger.debug('Acquired connection %s from pool.', id(conn))
        return conn

    async def _create_pool_async(self):
        raise NotImplementedError('Subclasses must implement.')

    async def _pool_acquire(self):
        raise NotImplementedError('Subclasses must implement.')

    async def _pool_release(self, conn):
        raise NotImplementedError('Subclasses must implement.')

    async def close_pool(self):
        self._closing = True
        try:
            if self._pool:
                # Snapshot active connections and release them.
                active = list(self._state._state_storage.values())
                for state in active:
                    if state.conn and not state.closed:
                        logger.debug('Closing active connection for task %s',
                                     id(state.conn))
                        try:
                            await self._pool_release(state.conn)
                        except Exception:
                            logger.warning(
                                'Error releasing connection during pool close',
                                exc_info=True)
                        state.conn = None
                        state.closed = True
                        state.transactions = []

                await self._pool_close()
                self._pool = None

            cleaned = self._state.cleanup_dead_tasks()
            if cleaned > 0:
                logger.debug('Cleaned up %d dead task states', cleaned)
        finally:
            self._closing = False

    async def _pool_close(self):
        raise NotImplementedError('Subclasses must implement.')

    async def __aenter__(self):
        await self.run(self.connect)
        return self

    async def __aexit__(self, exc_typ, exc, tb):
        await self.run(self.close)

    def atomic(self):
        return async_atomic(self)

    def transaction(self):
        return async_transaction(self)

    def savepoint(self):
        return async_savepoint(self)

    async def acreate_tables(self, *args, **kwargs):
        return await greenlet_spawn(self.create_tables, *args, **kwargs)

    async def adrop_tables(self, *args, **kwargs):
        return await greenlet_spawn(self.drop_tables, *args, **kwargs)

    async def aexecute(self, query):
        query.bind(self)
        return await self.run(query.execute)

    async def get(self, query):
        return await self.run(query.get)

    async def list(self, query):
        return await self.run(list, query)

    async def scalar(self, query):
        return await self.run(query.scalar)

    async def count(self, query):
        return await self.run(query.count)

    async def exists(self, query):
        return await self.run(query.exists)

    async def aprefetch(self, query, *subqueries):
        return await self.run(prefetch, query, *subqueries)

    async def run(self, fn, *args, **kwargs):
        return await greenlet_spawn(fn, *args, **kwargs)

    def is_closed(self):
        """Check if the current task's connection is closed."""
        try:
            return self._state.closed
        except RuntimeError:
            return True


class CursorAdapter(object):
    def __init__(self, rows, lastrowid=None, rowcount=None, description=None):
        self._rows = rows
        self._idx = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount if rowcount is not None else len(rows)
        self.description = description or []

    def fetchone(self):
        if self._idx >= len(self._rows):
            return
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)

    def close(self):
        pass


class DummyCursor(object):
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        return await_(self._async_execute(sql, params))

    async def _async_execute(self, sql, params):
        return await self.conn.execute(sql, params)


class AsyncConnectionWrapper(object):
    def __init__(self, conn):
        self.conn = conn
        self._lock = asyncio.Lock()

    async def execute(self, sql, params=None):
        async with self._lock:
            return await self._execute(sql, params)

    async def _execute(self, sql, params):
        raise NotImplementedError('Subclasses must implement.')

    def cursor(self):
        return DummyCursor(self)

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None


class AsyncSQLiteConnection(AsyncConnectionWrapper):
    async def _execute(self, sql, params=None):
        params = params or ()
        cursor = await self.conn.execute(sql, params)
        rows = await cursor.fetchall()
        lastrowid = cursor.lastrowid
        rowcount = cursor.rowcount
        description = cursor.description
        await cursor.close()
        return CursorAdapter(rows, lastrowid=lastrowid, rowcount=rowcount,
                             description=description)


class AsyncSqliteDatabase(AsyncDatabaseMixin, SqliteDatabase):
    async def _create_pool_async(self):
        if aiosqlite is None:
            raise ImproperlyConfigured('aiosqlite is not installed')
        conn = await aiosqlite.connect(self.database, isolation_level=None)
        conn.row_factory = lambda cursor, row: tuple(row)
        await self._add_conn_hooks(conn)
        return AsyncSQLiteConnection(conn)

    async def _add_conn_hooks(self, conn):
        if self._pragmas:
            await self._set_pragmas(conn)
        if self._functions:
            await self._load_functions(conn)

    async def _set_pragmas(self, conn):
        for pragma, value in self._pragmas:
            await conn.execute('PRAGMA %s = %s;' % (pragma, value))

    async def _load_functions(self, conn):
        for name, (fn, n_params, deterministic) in self._functions.items():
            kwargs = {'deterministic': deterministic} if deterministic else {}
            await conn.create_function(name, n_params, fn, **kwargs)

    async def _pool_acquire(self):
        # SQLite uses a single shared connection. Re-create if lost.
        async with self._pool_lock:
            if self._pool is None or self._pool.conn is None:
                self._pool = await self._create_pool_async()
        return self._pool

    async def _pool_release(self, conn):
        # For SQLite we don't actually release the shared connection — we only
        # disassociate it from the current task's state.  The connection stays
        # open until close_pool().
        pass

    async def _pool_close(self):
        if self._pool:
            await self._pool.close()


class AsyncMySQLConnection(AsyncConnectionWrapper):
    async def _execute(self, sql, params=None):
        params = params or ()
        cursor = await self.conn.cursor()
        try:
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
            lastrowid = cursor.lastrowid
            rowcount = cursor.rowcount
            description = cursor.description
        finally:
            await cursor.close()
        return CursorAdapter(rows, lastrowid=lastrowid, rowcount=rowcount,
                             description=description)


class AsyncMySQLDatabase(AsyncDatabaseMixin, MySQLDatabase):
    async def _create_pool_async(self):
        if aiomysql is None:
            raise ImproperlyConfigured('aiomysql is not installed')
        return await aiomysql.create_pool(
            db=self.database,
            autocommit=True,
            minsize=self._pool_min_size,
            maxsize=self._pool_size,
            **self.connect_params)

    async def _pool_acquire(self):
        conn = await asyncio.wait_for(
            self._pool.acquire(),
            timeout=self._acquire_timeout)
        return AsyncMySQLConnection(conn)

    async def _pool_release(self, conn):
        if conn and conn.conn:
            self._pool.release(conn.conn)

    async def _pool_close(self):
        self._pool.close()
        await self._pool.wait_closed()


class AsyncPostgresqlConnection(AsyncConnectionWrapper):
    async def _execute(self, sql, params=None):
        # asyncpg uses $1, $2 positional params instead of %s.
        if params:
            sql = self._translate_placeholders(sql)

        records = await self.conn.fetch(sql, *(params or ()))
        if records:
            description = [(k,) for k in records[0].keys()]
            rows = records
        else:
            description = []
            rows = []

        return CursorAdapter(rows, description=description)

    @staticmethod
    def _translate_placeholders(sql):
        parts = sql.split('%s')
        if len(parts) == 1:
            return sql
        accum = [parts[0]]
        for i, part in enumerate(parts[1:], 1):
            accum.append('$%d' % i)
            accum.append(part)
        return ''.join(accum)


class AsyncPostgresqlDatabase(AsyncDatabaseMixin, PostgresqlDatabase):
    async def _create_pool_async(self):
        if asyncpg is None:
            raise ImproperlyConfigured('asyncpg is not installed')
        return await asyncpg.create_pool(
            database=self.database,
            min_size=self._pool_min_size,
            max_size=self._pool_size,
            **self.connect_params)

    async def _pool_acquire(self):
        conn = await asyncio.wait_for(
            self._pool.acquire(),
            timeout=self._acquire_timeout)
        return AsyncPostgresqlConnection(conn)

    async def _pool_release(self, conn):
        if conn and conn.conn:
            await self._pool.release(conn.conn)

    async def _pool_close(self):
        await self._pool.close()
