import functools
import heapq
import logging
import threading
import time
from collections import namedtuple

from peewee import MySQLDatabase
from peewee import PostgresqlDatabase
from peewee import SqliteDatabase

logger = logging.getLogger('peewee.pool')


def make_int(val):
    if val is not None and not isinstance(val, (int, float)):
        return int(val)
    return val


class MaxConnectionsExceeded(ValueError): pass


PoolConnection = namedtuple('PoolConnection', ('timestamp', 'connection',
                                               'checked_out'))

class _sentinel(object):
    def __lt__(self, other):
        return True


def locked(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        with self._pool_lock:
            return fn(self, *args, **kwargs)
    return inner


class PooledDatabase(object):
    def __init__(self, database, max_connections=20, stale_timeout=None,
                 timeout=None, **kwargs):
        self._max_connections = make_int(max_connections)
        self._stale_timeout = make_int(stale_timeout)
        self._wait_timeout = make_int(timeout)
        if self._wait_timeout == 0:
            self._wait_timeout = float('inf')

        # Lock for pool operations and condition for notifying when connection
        # is released back to pool.
        self._pool_lock = threading.RLock()
        self._pool_available = threading.Condition(self._pool_lock)

        # Available / idle connections stored in a heap, sorted oldest first.
        self._connections = []

        # Counter used for tie-breaker in heap (so we don't try comparing
        # connection against connection).
        self._heap_counter = 0

        # Mapping of connection id to PoolConnection. Ordinarily we would want
        # to use something like a WeakKeyDictionary, but Python typically won't
        # allow us to create weak references to connection objects.
        self._in_use = {}

        # Use the memory address of the connection as the key in the event the
        # connection object is not hashable. Connections will not get
        # garbage-collected, however, because a reference to them will persist
        # in "_in_use" as long as the conn has not been closed.
        self.conn_key = id

        super(PooledDatabase, self).__init__(database, **kwargs)

    def init(self, database, max_connections=None, stale_timeout=None,
             timeout=None, **connect_kwargs):
        super(PooledDatabase, self).init(database, **connect_kwargs)
        if max_connections is not None:
            self._max_connections = make_int(max_connections)
        if stale_timeout is not None:
            self._stale_timeout = make_int(stale_timeout)
        if timeout is not None:
            self._wait_timeout = make_int(timeout)
            if self._wait_timeout == 0:
                self._wait_timeout = float('inf')

    def connect(self, reuse_if_open=False):
        if not self._wait_timeout:
            return super(PooledDatabase, self).connect(reuse_if_open)

        deadline = time.monotonic() + self._wait_timeout
        while True:
            try:
                return super(PooledDatabase, self).connect(reuse_if_open)
            except MaxConnectionsExceeded:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MaxConnectionsExceeded(
                        'Max connections exceeded, timed out attempting to '
                        'connect.')
                with self._pool_available:
                    self._pool_available.wait(timeout=min(remaining, 1.0))

    @locked
    def _connect(self):
        while self._connections:
            try:
                # Remove the oldest connection from the heap.
                ts, _counter, conn = heapq.heappop(self._connections)
            except IndexError:
                break

            key = self.conn_key(conn)
            if self._is_closed(conn):
                # Connection closed either by user or by driver - discard.
                logger.debug('Connection %s was closed, discarding.', key)
                continue

            if self._stale_timeout and self._is_stale(ts):
                logger.debug('Connection %s was stale, closing.', key)
                self._close_raw(conn)
                continue

            # Connection OK to use.
            self._in_use[key] = PoolConnection(ts, conn, time.time())
            return conn

        if self._max_connections and (
                len(self._in_use) >= self._max_connections):
            raise MaxConnectionsExceeded('Exceeded maximum connections.')

        conn = super(PooledDatabase, self)._connect()
        ts = time.time()
        key = self.conn_key(conn)
        logger.debug('Created new connection %s.', key)
        self._in_use[key] = PoolConnection(ts, conn, time.time())
        return conn

    def _is_stale(self, timestamp):
        # Called on check-out and check-in to ensure the connection has
        # not outlived the stale timeout.
        return (time.time() - timestamp) > self._stale_timeout

    def _is_closed(self, conn):
        return False

    def _can_reuse(self, conn):
        # Called on check-in to make sure the connection can be re-used.
        return True

    def _close_raw(self, conn):
        try:
            super(PooledDatabase, self)._close(conn)
        except Exception:
            logger.debug('Error closing connection %s.', self.conn_key(conn),
                         exc_info=True)

    @locked
    def _close(self, conn, close_conn=False):
        # if close_conn == True, close underlying driver connection and remove
        # from _in_use tracking. Do not return to available conns.
        key = self.conn_key(conn)

        if close_conn:
            self._in_use.pop(key, None)
            self._close_raw(conn)
            return

        if key not in self._in_use:
            logger.debug('Connection %s not in use, ignoring close.', key)
            return

        pool_conn = self._in_use.pop(key)
        if self._stale_timeout and self._is_stale(pool_conn.timestamp):
            logger.debug('Closing stale connection %s on check-in.', key)
            self._close_raw(conn)
        elif not self._can_reuse(conn):
            logger.debug('Connection %s not reusable, closing.', key)
            self._close_raw(conn)
        else:
            logger.debug('Returning %s to pool.', key)
            self._heap_counter += 1
            heapq.heappush(self._connections,
                           (pool_conn.timestamp, self._heap_counter, conn))

        # Wake up thread that may be waiting on connection.
        self._pool_available.notify()

    @locked
    def manual_close(self):
        """
        Close the underlying connection without returning it to the pool.
        """
        if self.is_closed():
            return False

        # Obtain reference to the connection in-use by the calling thread.
        conn = self.connection()
        key = self.conn_key(conn)

        # Remove from _in_use so that subsequent self.close() won't try to
        # restore it to the pool.
        self._in_use.pop(key, None)
        self.close()
        self._close_raw(conn)

    @locked
    def close_idle(self):
        # Close any open connections that are not currently in-use.
        idle = self._connections
        self._connections = []
        for _, _, conn in idle:
            self._close_raw(conn)

    @locked
    def close_stale(self, age=600):
        # Close any connections that are in-use but were checked out quite some
        # time ago and can be considered stale. May close connections in use by
        # running threads.
        cutoff = time.time() - age
        n = 0
        for key, pool_conn in list(self._in_use.items()):
            if pool_conn.checked_out < cutoff:
                self._close_raw(pool_conn.connection)
                del self._in_use[key]
                n += 1

        self._pool_available.notify_all()
        return n

    @locked
    def close_all(self):
        # Close all connections -- available and in-use. Warning: may break any
        # active connections used by other threads.
        self.close()
        self.close_idle()
        in_use, self._in_use = self._in_use, {}
        for pool_conn in in_use.values():
            self._close_raw(pool_conn.connection)

        self._pool_available.notify_all()


class _PooledMySQLDatabase(PooledDatabase):
    def _is_closed(self, conn):
        if self.server_version[0] == 8:
            args = ()
        else:
            args = (False,)
        try:
            conn.ping(*args)
        except:
            return True
        return False

class PooledMySQLDatabase(_PooledMySQLDatabase, MySQLDatabase):
    pass


class _PooledPostgresqlDatabase(PooledDatabase):
    def _is_closed(self, conn):
        if conn.closed:
            return True
        return self._adapter.is_connection_closed(conn)

    def _can_reuse(self, conn):
        return self._adapter.is_connection_reusable(conn)

class PooledPostgresqlDatabase(_PooledPostgresqlDatabase, PostgresqlDatabase):
    pass


class _PooledSqliteDatabase(PooledDatabase):
    def _is_closed(self, conn):
        try:
            conn.total_changes
        except:
            return True
        return False

class PooledSqliteDatabase(_PooledSqliteDatabase, SqliteDatabase):
    pass
