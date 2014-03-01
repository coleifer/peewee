"""
Lightweight connection pooling for peewee.
"""
import heapq
import logging
import threading
import time

from peewee import MySQLDatabase
from peewee import PostgresqlDatabase

logger = logging.getLogger('peewee.pool')

class PooledDatabase(object):
    def __init__(self, database, max_connections=32, stale_timeout=None,
                 **kwargs):
        self.max_connections = max_connections
        self.stale_timeout = stale_timeout
        self.connections = []
        self.in_use = {}

        super(PooledDatabase, self).__init__(database, **kwargs)

    def _connect(self, *args, **kwargs):
        try:
            ts, conn = heapq.heappop(self.connections)
        except IndexError:
            ts = conn = None
            logger.debug('No connection available in pool.')
        else:
            if self.stale_timeout and self.is_stale(ts):
                logger.debug('Connection %s was stale, closing.' % id(conn))
                self._close(conn, True)
                ts = conn = None

        if conn is None:
            if self.max_connections and (
                    len(self.in_use) >= self.max_connections):
                raise ValueError('Exceeded maximum connections.')
            conn = super(PooledDatabase, self)._connect(*args, **kwargs)
            ts = time.time()
            logger.debug('Created new connection %s.' % id(conn))

        self.in_use[conn] = ts
        return conn

    def is_stale(self, timestamp):
        return (time.time() - timestamp) > self.stale_timeout

    def _close(self, conn, close_conn=False):
        if close_conn:
            super(PooledDatabase, self)._close(conn)
        elif conn in self.in_use:
            logger.debug('Returning %s to pool.' % id(conn))
            ts = self.in_use[conn]
            del self.in_use[conn]
            heapq.heappush(self.connections, (ts, conn))

    def close_all(self):
        for _, conn in self.connections:
            self._close(conn, True)
        for conn in self.in_use:
            self._close(conn, True)

class PooledMySQLDatabase(PooledDatabase, MySQLDatabase):
    pass

class PooledPostgresqlDatabase(PooledDatabase, PostgresqlDatabase):
    pass
