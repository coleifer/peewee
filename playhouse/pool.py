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
                elif key in self._closed:
                    logger.debug('Connection %s was closed.', key)
                    ts = conn = None
                    self._closed.remove(key)
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
    pass

class PooledPostgresqlDatabase(PooledDatabase, PostgresqlDatabase):
    pass

try:
    from playhouse.postgres_ext import PostgresqlExtDatabase

    class PooledPostgresqlExtDatabase(PooledDatabase, PostgresqlExtDatabase):
        pass
except ImportError:
    pass
