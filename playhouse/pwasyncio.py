import asyncio
import collections
import contextvars
import itertools
import json
import logging
import re

from greenlet import greenlet, getcurrent
from peewee import *
from peewee import _atomic, _savepoint, _transaction
from peewee import _callable_context_manager
from peewee import __exception_wrapper__
from peewee import Node
from peewee import Psycopg3Adapter
from playhouse.postgres_ext import Json

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
        if asyncio.iscoroutine(awaitable):
            awaitable.close()  # Avoid a "never awaited" RuntimeWarning.
        raise MissingGreenletBridge('await_() called outside greenlet_spawn()')
    return parent.switch(awaitable)


class _State(object):
    __slots__ = ('conn', 'closed', 'transactions', 'ctx', '_task_id')

    def __init__(self):
        self._task_id = None
        self.reset()

    def reset(self):
        self.conn = None
        self.closed = True
        self.transactions = []
        self.ctx = []


class _ConnectionState(object):
    def __init__(self):
        self._cv = contextvars.ContextVar('pwasyncio_state')
        # Central registry: task-id -> _State.  Allows close_pool() to
        # enumerate *all* live states and release their connections.
        self._states = {}
        self._orphaned_conns = []

    def _current(self):
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError('Cannot determine current task')
        tid = id(task)

        try:
            state = self._cv.get()
            if state._task_id == tid:
                # Re-register if evicted (e.g. by close_pool clearing _states).
                if tid not in self._states:
                    self._states[tid] = state
                    # Unnecessary to register the callback; task is still
                    # running so the original callback should be present.
                    # task.add_done_callback(self._on_task_done)
                return state
        except LookupError:
            pass

        if tid in self._states:
            state = self._states[tid]
        else:
            state = _State()
            state._task_id = tid
            self._states[tid] = state
            task.add_done_callback(self._on_task_done)

        # Cache in the contextvar for subsequent calls for task.
        self._cv.set(state)
        return state

    def _on_task_done(self, task):
        tid = id(task)
        state = self._states.pop(tid, None)
        if state is not None and state.conn is not None and not state.closed:
            self._orphaned_conns.append(state.conn)
            state.reset()

    @property
    def conn(self):
        return self._current().conn

    @property
    def closed(self):
        return self._current().closed

    @property
    def transactions(self):
        return self._current().transactions

    @property
    def ctx(self):
        return self._current().ctx

    def reset(self):
        try:
            state = self._current()
        except RuntimeError:
            return
        state.reset()

    def set_connection(self, conn):
        state = self._current()
        state.conn = conn
        state.closed = False


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

        self._state = _ConnectionState()
        self._pool = None
        self._pool_lock = asyncio.Lock()
        self._closing = False  # Guard against use during shutdown.

    def execute_sql(self, sql, params=None):
        try:
            return await_(self.aexecute_sql(sql, params or ()))
        except MissingGreenletBridge as exc:
            raise MissingGreenletBridge(
                f'Attempted query outside greenlet runner: {sql}') from exc

    async def aexecute_sql(self, sql, params=None):
        conn = await self.aconnect()
        with __exception_wrapper__:
            return await conn.execute(sql, params)

    def connect(self):
        return await_(self.aconnect())

    async def aconnect(self):
        if self._closing:
            raise InterfaceError('Database pool is shutting down.')

        # Drain any connections orphaned by dead tasks.
        while self._state._orphaned_conns:
            orphan = self._state._orphaned_conns.pop()
            await self._pool_release(orphan)

        conn = self._state.conn
        if conn is None or conn.conn is None:
            if conn is not None:
                # Previous connection was invalidated, release it.
                await self._pool_release(conn)
            conn = await self._acquire_conn_async()
            self._state.set_connection(conn)
        return conn

    def close(self):
        return await_(self.aclose())

    async def aclose(self):
        if self.in_transaction():
            raise OperationalError('Attempting to close database while '
                                   'transaction is open.')
        conn = self._state.conn
        if conn:
            self._state.reset()
            logger.debug('Releasing connection %s to pool.', id(conn))
            await self._pool_release(conn)

    async def _acquire_conn_async(self):
        async with self._pool_lock:
            if self._pool is None:
                self._pool = await self._create_pool_async()

        try:
            conn = await self._pool_acquire()
        except asyncio.TimeoutError:
            raise OperationalError(
                'Timed out acquiring connection from pool '
                '(acquire_timeout=%s).' % self._acquire_timeout) from None
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
                # Release connections held by any task still in the registry.
                # We must clear each state BEFORE releasing the connection,
                # because the await in _pool_release can let the event loop
                # run pending task-done callbacks.  If the callback sees
                # state.conn still set it will orphan the same connection,
                # leading to a double-release that overfills the pool queue.
                for state in list(self._state._states.values()):
                    if state.conn and not state.closed:
                        conn = state.conn
                        state.reset()
                        try:
                            await self._pool_release(conn)
                        except Exception:
                            logger.warning(
                                'Error releasing connection during pool close',
                                exc_info=True)
                self._state._states.clear()

                # Drain any connections orphaned by completed tasks.
                while self._state._orphaned_conns:
                    orphan = self._state._orphaned_conns.pop()
                    try:
                        await self._pool_release(orphan)
                    except Exception:
                        logger.warning('Error releasing orphaned connection',
                                       exc_info=True)

                await self._pool_close()
                self._pool = None
        finally:
            self._closing = False

    async def _pool_close(self):
        raise NotImplementedError('Subclasses must implement.')

    async def __aenter__(self):
        await self.run(self.connect)
        return self

    async def __aexit__(self, exc_typ, exc, tb):
        await self.run(self.close)

    def atomic(self, *args, **kwargs):
        return async_atomic(self, *args, **kwargs)

    def transaction(self, *args, **kwargs):
        return async_transaction(self, *args, **kwargs)

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

    async def iterate(self, query, buffer_size=None):
        # Use similar approach to postgres_ext server-side query impl.
        query.bind(self)
        sql, params = query.sql()
        conn = await self.aconnect()
        with __exception_wrapper__:
            cursor = await conn.execute_iter(sql, params or ())
        if buffer_size is not None:
            cursor._buffer_size = buffer_size

        try:
            wrapper = query._get_cursor_wrapper(cursor)
            row_iter = wrapper.iterator()
            _sentinel = object()

            # Cursor wrapper `iterator()` calls fetchone() to grab rows from
            # the internal buffer. `fetchone()` may dispatch do the event loop
            # to refill buffer (async).
            while True:
                row = await greenlet_spawn(next, row_iter, _sentinel)
                if row is _sentinel:
                    break
                yield row
        finally:
            await cursor.aclose()

    async def run(self, fn, *args, **kwargs):
        return await greenlet_spawn(fn, *args, **kwargs)

    def is_closed(self):
        try:
            return self._state.closed
        except RuntimeError:
            return True


class CursorAdapter(object):
    DEFAULT_BUFFER_SIZE = 100

    def __init__(self, rows=None, lastrowid=None, rowcount=None,
                 description=None, fetch_many=None, cleanup=None,
                 buffer_size=None):
        self._rows = rows or []
        self._idx = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount if rowcount is not None else len(self._rows)
        self.description = description or []

        # Async server-side cursor support.
        self._fetch_many = fetch_many
        self._cleanup = cleanup
        self._buffer_size = buffer_size or self.DEFAULT_BUFFER_SIZE
        self._buffer = collections.deque()
        self._exhausted = False

    def fetchone(self):
        if self._fetch_many is not None:
            return self._lazy_fetchone()
        if self._idx >= len(self._rows):
            return
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def _lazy_fetchone(self):
        if not self._buffer:
            if self._exhausted:
                return None
            with __exception_wrapper__:
                rows = await_(self._fetch_many(self._buffer_size))
            if not rows:
                self._exhausted = True
                return None
            self._buffer.extend(rows)
        return self._buffer.popleft()

    def fetchall(self):
        if self._fetch_many is not None:
            return list(self)
        return self._rows

    def __iter__(self):
        if self._fetch_many is not None:
            return _lazy_cursor_iter(self)
        return iter(self._rows)

    def close(self):
        pass

    async def aclose(self):
        if self._cleanup is not None:
            try:
                await self._cleanup()
            finally:
                self._cleanup = None
                self._fetch_many = None


def _lazy_cursor_iter(cursor):
    while True:
        row = cursor.fetchone()
        if row is None:
            return
        yield row


class DummyCursor(object):
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        return await_(self._async_execute(sql, params))

    async def _async_execute(self, sql, params):
        return await self.conn.execute(sql, params)


class AsyncConnectionWrapper(object):
    # Grace period for an abandoned iterate() generator to finalize (e.g.
    # the caller broke out of the async-for) before a competing query on
    # this connection gives up instead of deadlocking.
    streaming_timeout = 5.0

    def __init__(self, conn):
        self.conn = conn
        self._lock = asyncio.Lock()
        self._streaming = False  # Lock is held by an open iterate() cursor.

    async def _acquire_lock(self):
        # When an iterate() cursor holds the lock, wait briefly for it to
        # finalize rather than deadlocking - this covers plain queries AND
        # a second iterate() on the same connection.
        if self._streaming:
            try:
                await asyncio.wait_for(self._lock.acquire(),
                                       self.streaming_timeout)
            except asyncio.TimeoutError:
                raise InterfaceError(
                    'Connection is busy streaming results from iterate(). '
                    'Run the query from another task, or exhaust or '
                    'aclose() the iterator.') from None
        else:
            await self._lock.acquire()

    async def execute(self, sql, params=None):
        await self._acquire_lock()
        try:
            return await self._execute(sql, params)
        finally:
            self._lock.release()

    async def _execute(self, sql, params):
        raise NotImplementedError('Subclasses must implement.')

    def cursor(self):
        return DummyCursor(self)

    async def execute_iter(self, sql, params=None):
        raise NotImplementedError('Subclasses must implement.')

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None


class AsyncSqlitePool(object):
    def __init__(self, database, pool_size=5, on_connect=None,
                 **connect_params):
        self._database = database
        self._pool_size = pool_size
        self._on_connect = on_connect
        self._connect_params = connect_params
        self._queue = asyncio.Queue(maxsize=pool_size)
        self._all_connections = []
        self._closed = False

    async def initialize(self):
        for _ in range(self._pool_size):
            conn = await self._create_connection()
            self._queue.put_nowait(conn)
        return self

    async def _create_connection(self):
        conn = await aiosqlite.connect(
            self._database,
            isolation_level=None,
            **self._connect_params)
        if self._on_connect is not None:
            await self._on_connect(conn)
        wrapped = AsyncSqliteConnection(conn)
        self._all_connections.append(wrapped)
        return wrapped

    async def acquire(self, timeout=None):
        if self._closed:
            raise InterfaceError('Pool is closed.')
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    def _conn_is_valid(self, conn):
        driver_conn = conn.conn
        if driver_conn is None:
            return False
        # aiosqlite private attrs - tolerate their absence in new versions.
        if not getattr(driver_conn, '_running', True):
            return False
        if not getattr(driver_conn, '_connection', True):
            return False
        return True

    async def release(self, conn):
        if self._closed:
            return
        valid = self._conn_is_valid(conn)
        if valid and conn.conn.in_transaction:
            # Roll back any transaction left open, e.g. by a dead task, so
            # the next acquirer gets a clean connection.
            try:
                await conn.conn.rollback()
            except Exception:
                logger.warning('Error rolling back connection', exc_info=True)
                valid = False
        if valid:
            await self._queue.put(conn)
        else:
            try:
                self._all_connections.remove(conn)
            except ValueError:
                pass
            await self._queue.put(await self._create_connection())

    async def close(self):
        self._closed = True
        conns, self._all_connections = list(self._all_connections), []
        for conn in conns:
            try:
                await conn.close()
            except Exception:
                logger.warning('Error closing pooled connection',
                               exc_info=True)


class AsyncSqliteConnection(AsyncConnectionWrapper):
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

    async def execute_iter(self, sql, params=None):
        await self._acquire_lock()
        self._streaming = True
        try:
            cursor = await self.conn.execute(sql, params or ())
        except BaseException:
            self._streaming = False
            self._lock.release()
            raise

        lock = self._lock

        async def fetch_many(count):
            return await cursor.fetchmany(count)

        async def cleanup():
            try:
                await cursor.close()
            finally:
                self._streaming = False
                lock.release()

        return CursorAdapter(
            description=cursor.description,
            fetch_many=fetch_many,
            cleanup=cleanup)


class AsyncSqliteDatabase(AsyncDatabaseMixin, SqliteDatabase):
    async def _create_pool_async(self):
        if aiosqlite is None:
            raise ImproperlyConfigured('aiosqlite is not installed')
        if self.database == ':memory:':
            # Pooled in-memory connections would each be a separate, empty
            # database - use a single shared connection instead.
            pool_size = 1
        else:
            pool_size = self._pool_size
        pool = AsyncSqlitePool(self.database, pool_size=pool_size,
                               on_connect=self._add_conn_hooks,
                               timeout=self._timeout,
                               **self.connect_params)
        return await pool.initialize()

    async def _add_conn_hooks(self, conn):
        if self._attached:
            await self._attach_databases(conn)
        if self._pragmas:
            await self._set_pragmas(conn)
        if self._aggregates:
            await self._load_aggregates(conn)
        if self._collations:
            await self._load_collations(conn)
        if self._functions:
            await self._load_functions(conn)
        if self._window_functions and \
           aiosqlite.sqlite_version_info >= (3, 25, 0):
            await self._load_window_functions(conn)
        if self._extensions:
            await self._load_extensions(conn)

    async def _attach_databases(self, conn):
        for name, db in self._attached.items():
            await conn.execute('ATTACH DATABASE "%s" AS "%s"' % (db, name))

    async def _set_pragmas(self, conn):
        for pragma, value in self._pragmas:
            await conn.execute('PRAGMA %s = %s;' % (pragma, value))

    async def _load_aggregates(self, conn):
        # aiosqlite exposes no create_aggregate - run it on the worker
        # thread against the raw sqlite3 connection.
        for name, (klass, num_params) in self._aggregates.items():
            await conn._execute(
                conn._conn.create_aggregate, name, num_params, klass)

    async def _load_collations(self, conn):
        for name, fn in self._collations.items():
            await conn._execute(conn._conn.create_collation, name, fn)

    async def _load_functions(self, conn):
        for name, (fn, n_params, deterministic) in self._functions.items():
            kwargs = {'deterministic': deterministic} if deterministic else {}
            await conn.create_function(name, n_params, fn, **kwargs)

    async def _load_window_functions(self, conn):
        for name, (klass, num_params) in self._window_functions.items():
            await conn._execute(
                conn._conn.create_window_function, name, num_params, klass)

    async def _load_extensions(self, conn):
        await conn.enable_load_extension(True)
        for extension in self._extensions:
            await conn.load_extension(extension)

    async def _pool_acquire(self):
        return await self._pool.acquire(timeout=self._acquire_timeout)

    async def _pool_release(self, conn):
        if conn is not None:
            await self._pool.release(conn)

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

    async def execute_iter(self, sql, params=None):
        await self._acquire_lock()
        self._streaming = True
        try:
            # Server-side cursor for unbuffered streaming.
            cursor = await self.conn.cursor(aiomysql.SSCursor)
            await cursor.execute(sql, params or ())
        except BaseException:
            self._streaming = False
            self._lock.release()
            raise

        lock = self._lock

        async def fetch_many(count):
            return await cursor.fetchmany(count)

        async def cleanup():
            try:
                await cursor.close()
            finally:
                self._streaming = False
                lock.release()

        return CursorAdapter(
            description=cursor.description,
            fetch_many=fetch_many,
            cleanup=cleanup)


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
        if self.server_version is None:
            # Distinguishes MySQL from MariaDB, e.g. for JSONField SQL.
            self.server_version = self._extract_server_version(
                conn.get_server_info())
        return AsyncMySQLConnection(conn)

    async def _pool_release(self, conn):
        if conn and conn.conn:
            if conn.conn.get_transaction_status():
                # Roll back any transaction left open, e.g. by a dead task,
                # so the next acquirer gets a clean connection (aiomysql
                # destroys connections released mid-transaction).
                try:
                    await conn.conn.rollback()
                except Exception:
                    logger.warning('Error rolling back connection',
                                   exc_info=True)
            self._pool.release(conn.conn)

    async def _pool_close(self):
        self._pool.close()
        await self._pool.wait_closed()


class AsyncPostgresqlConnection(AsyncConnectionWrapper):
    async def _execute(self, sql, params=None):
        # asyncpg uses $1, $2 positional params instead of %s.
        if params:
            sql = self._translate_placeholders(sql)

        stmt = await self.conn.prepare(sql)
        records = await stmt.fetch(*(params or ()))
        if records:
            description = [(k,) for k in records[0].keys()]
        else:
            description = []

        # asyncpg exposes no rowcount; parse the command-status tail, e.g.
        # "UPDATE 3" / "DELETE 2" / "INSERT 0 3".
        status = (stmt.get_statusmsg() or '').rsplit(' ', 1)
        if len(status) == 2 and status[1].isdigit():
            rowcount = int(status[1])
        else:
            rowcount = len(records)

        return CursorAdapter(records, rowcount=rowcount,
                             description=description)

    async def execute_iter(self, sql, params=None):
        if params:
            sql = self._translate_placeholders(sql)
        await self._acquire_lock()
        self._streaming = True
        tr = None
        try:
            # NB: asyncpg cursors require an active transaction.
            # Right now we cannot use peewee-managed transactions because
            # asyncpg's Cursor._check_ready() requires an asyncpg-managed
            # transaction be active.
            # See: https://github.com/MagicStack/asyncpg/issues/1311
            tr = self.conn.transaction()
            await tr.start()
            stmt = await self.conn.prepare(sql)
            cursor = await stmt.cursor(*(params or ()))
        except BaseException:
            if tr is not None:
                # Don't leave the connection inside an open transaction.
                try:
                    await tr.rollback()
                except Exception:
                    pass
            self._streaming = False
            self._lock.release()
            raise

        lock = self._lock

        async def fetch_many(count):
            return await cursor.fetch(count)

        async def cleanup():
            try:
                await tr.rollback()
            except Exception:
                pass
            finally:
                self._streaming = False
                lock.release()

        return CursorAdapter(
            fetch_many=fetch_many,
            cleanup=cleanup,
            description=[(a.name,) for a in stmt.get_attributes()])

    @staticmethod
    def _translate_placeholders(sql):
        # %s is treated as a placeholder wherever it appears, including
        # inside quoted strings, and %% as an escaped literal percent -
        # mirroring psycopg. Pass literal values as parameters.
        if '%' not in sql:
            return sql
        counter = itertools.count(1)
        def replace(match):
            if match.group(0) == '%%':
                return '%'
            return '$%d' % next(counter)
        return re.sub('%%|%s', replace, sql)


class AsyncPgAdapter(Psycopg3Adapter):
    def __init__(self):
        super(AsyncPgAdapter, self).__init__()
        self.json_type = Json
        self.jsonb_type = Json


class AsyncPgAtomic(_callable_context_manager):
    def __init__(self, db, *args, **kwargs):
        self.db = db
        self._begin_args = (args, kwargs)

    def __enter__(self):
        await_(self._abegin())
        self.db._state.transactions.append(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db._state.transactions.pop()
        if exc_type:
            self.rollback(False)
        else:
            try:
                self.commit(False)
            except Exception:
                # asyncpg marks the transaction FAILED when commit errors,
                # making rollback raise too - don't mask the original.
                try:
                    self.rollback(False)
                except Exception:
                    pass
                raise

    def commit(self, begin=True):
        await_(self.acommit(begin))

    def rollback(self, begin=True):
        await_(self.arollback(begin))

    async def _abegin(self):
        a, k = self._begin_args
        conn = await self.db.aconnect()
        with __exception_wrapper__:
            self._tx = conn.conn.transaction(*a, **k)
            await self._tx.start()
        return self._tx

    async def acommit(self, begin=True):
        with __exception_wrapper__:
            await self._tx.commit()
        if begin:
            await self._abegin()

    async def arollback(self, begin=True):
        with __exception_wrapper__:
            await self._tx.rollback()
        if begin:
            await self._abegin()

    async def __aenter__(self):
        await self._abegin()
        self.db._state.transactions.append(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.db._state.transactions.pop()
        if exc_type:
            await self.arollback(False)
        else:
            try:
                await self.acommit(False)
            except Exception:
                # asyncpg marks the transaction FAILED when commit errors,
                # making rollback raise too - don't mask the original.
                try:
                    await self.arollback(False)
                except Exception:
                    pass
                raise


class AsyncPostgresqlDatabase(AsyncDatabaseMixin, PostgresqlDatabase):
    psycopg2_adapter = psycopg3_adapter = AsyncPgAdapter

    def init(self, database, **kwargs):
        # asyncpg has no psycopg-style isolation-level constants; keep the
        # raw value and apply it per-connection in register_adapters().
        self._async_isolation_level = kwargs.pop('isolation_level', None)
        super(AsyncPostgresqlDatabase, self).init(database, **kwargs)

    async def register_adapters(self, conn):
        def encode_json(val):
            return val if isinstance(val, bytes) else val.encode('utf8')

        def decode_json(bval):
            return json.loads(bval.decode())

        await conn.set_type_codec(
            'json', encoder=encode_json, decoder=decode_json,
            schema='pg_catalog', format='binary')

        def encode_jsonb(val):
            if isinstance(val, bytes):
                return b'\x01' + val
            return b'\x01' + val.encode('utf8')

        def decode_jsonb(bval):
            return json.loads(bval[1:].decode())

        await conn.set_type_codec(
            'jsonb', encoder=encode_jsonb, decoder=decode_jsonb,
            schema='pg_catalog', format='binary')

        if self._async_isolation_level:
            await conn.execute(
                'SET SESSION CHARACTERISTICS AS TRANSACTION '
                'ISOLATION LEVEL %s' % self._async_isolation_level)

    async def _create_pool_async(self):
        if asyncpg is None:
            raise ImproperlyConfigured('asyncpg is not installed')
        if self.database and self.database.startswith(
                ('postgresql://', 'postgres://')):
            db_params = {'dsn': self.database}
        else:
            db_params = {'database': self.database}
        return await asyncpg.create_pool(
            min_size=self._pool_min_size,
            max_size=self._pool_size,
            init=self.register_adapters,
            **db_params,
            **self.connect_params)

    async def _pool_acquire(self):
        conn = await asyncio.wait_for(
            self._pool.acquire(),
            timeout=self._acquire_timeout)
        return AsyncPostgresqlConnection(conn)

    async def _pool_release(self, conn):
        if conn and conn.conn:
            if conn.conn.is_in_transaction():
                # Roll back any transaction left open, e.g. by a dead task -
                # otherwise asyncpg's pool reset logs a noisy warning.
                try:
                    await conn.conn.execute('ROLLBACK')
                except Exception:
                    logger.warning('Error rolling back connection',
                                   exc_info=True)
            await self._pool.release(conn.conn)

    async def _pool_close(self):
        await self._pool.close()

    def atomic(self, *args, **kwargs):
        return AsyncPgAtomic(self, *args, **kwargs)
    def transaction(self, *args, **kwargs):
        return AsyncPgAtomic(self, *args, **kwargs)
    def savepoint(self, *args, **kwargs):
        return AsyncPgAtomic(self, *args, **kwargs)
