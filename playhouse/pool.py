"""
EXPERIMENTAL
============

Lightweight connection pooling for peewee.

In a single-threaded application, only one connection will be created. It will
be continually recycled until either it exceeds the stale timeout or is closed
explicitly (using `.manual_close()`).

In a multi-threaded application, up to `max_connections` will be opened.
"""
import heapq
import logging
import threading
import time

from peewee import MySQLDatabase
from peewee import PostgresqlDatabase

logger = logging.getLogger('peewee.pool')

class PooledDatabase(object):
    def __init__(self, database, max_connections=20, stale_timeout=None,
                 **kwargs):
        self.max_connections = max_connections
        self.stale_timeout = stale_timeout
        self._connections = []
        self._in_use = {}
        self._closed = set()
        self.conn_key = id

        super(PooledDatabase, self).__init__(database, **kwargs)

    def _connect(self, *args, **kwargs):
        while True:
            try:
                ts, conn = heapq.heappop(self._connections)
                key = self.conn_key(conn)
            except IndexError:
                ts = conn = None
                logger.debug('No connection available in pool.')
                break
            else:
                if self.stale_timeout and self._is_stale(ts):
                    logger.debug('Connection %s was stale, closing.', key)
                    self._close(conn, True)
                    ts = conn = None
                elif self._is_closed(key, conn):
                    logger.debug('Connection %s was closed.', key)
                    ts = conn = None
                    self._closed.discard(key)
                else:
                    break

        if conn is None:
            if self.max_connections and (
                    len(self._in_use) >= self.max_connections):
                raise ValueError('Exceeded maximum connections.')
            conn = super(PooledDatabase, self)._connect(*args, **kwargs)
            ts = time.time()
            key = self.conn_key(conn)
            logger.debug('Created new connection %s.', key)

        self._in_use[key] = ts
        return conn

    def _is_stale(self, timestamp):
        return (time.time() - timestamp) > self.stale_timeout

    def _is_closed(self, key, conn):
        return key in self._closed

    def _close(self, conn, close_conn=False):
        key = self.conn_key(conn)
        if close_conn:
            self._closed.add(key)
            super(PooledDatabase, self)._close(conn)
        elif key in self._in_use:
            logger.debug('Returning %s to pool.', key)
            ts = self._in_use[key]
            del self._in_use[key]
            heapq.heappush(self._connections, (ts, conn))

    def manual_close(self):
        """
        Close the underlying connection without returning it to the pool.
        """
        conn = self.get_conn()
        self.close()
        self._close(conn, close_conn=True)

    def close_all(self):
        """
        Close all connections managed by the pool.
        """
        for _, conn in self._connections:
            self._close(conn, close_conn=True)
        for conn in self._in_use:
            self._close(conn, close_conn=True)

class PooledMySQLDatabase(PooledDatabase, MySQLDatabase):
    def _is_closed(self, key, conn):
        is_closed = super(PooledMySQLDatabase, self)._is_closed(key, conn)
        if not is_closed:
            if hasattr(conn, 'open'):
                # MySQLdb `ping()` seems to always return `None` in my testing.
                # So the `open` attribute will be used instead.
                is_closed = not bool(conn.open)
            else:
                # pymysql `ping([reconnect=True])` will indicate if the conn
                # is closed or not.
                try:
                    is_closed = not conn.ping(False)
                except:
                    is_closed = True
        return is_closed

class _PooledPostgresqlDatabase(PooledDatabase):
    def _is_closed(self, key, conn):
        is_closed = super(_PooledPostgresqlDatabase, self)._is_closed(key, conn)
        if not is_closed:
            is_closed = bool(conn.closed)
        return is_closed

class PooledPostgresqlDatabase(_PooledPostgresqlDatabase, PostgresqlDatabase):
    pass

try:
    from playhouse.postgres_ext import PostgresqlExtDatabase

    class PooledPostgresqlExtDatabase(_PooledPostgresqlDatabase, PostgresqlExtDatabase):
        pass
except ImportError:
    pass
