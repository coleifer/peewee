"""
Lightweight connection pooling for peewee.

In a multi-threaded application, up to `max_connections` will be opened. Each
thread (or, if using gevent, greenlet) will have it's own connection.

In a single-threaded application, only one connection will be created. It will
be continually recycled until either it exceeds the stale timeout or is closed
explicitly (using `.manual_close()`).

By default, all your application needs to do is ensure that connections are
closed when you are finished with them, and they will be returned to the pool.
For web applications, this typically means that at the beginning of a request,
you will open a connection, and when you return a response, you will close the
connection.

Simple Postgres pool example code:

    # Use the special postgresql extensions.
    from playhouse.pool import PooledPostgresqlExtDatabase

    db = PooledPostgresqlExtDatabase(
        'my_app',
        max_connections=32,
        stale_timeout=300,  # 5 minutes.
        user='postgres')

    class BaseModel(Model):
        class Meta:
            database = db

That's it!

In some situations you may want to manage your connections more explicitly.
Since peewee stores the active connection in a threadlocal, this typically
would mean that there could only ever be one connection open per thread. For
most applications this is desirable, but if you would like to manually manage
multiple connections you can create an *ExecutionContext*.

Execution contexts allow finer-grained control over managing multiple
connections to the database. When an execution context is initialized (either
as a context manager or as a decorated function), a separate connection will
be used for the duration of the wrapped block. You can also choose whether to
wrap the block in a transaction.

Execution context examples (using above `db` instance):

    with db.execution_context() as ctx:
        # A new connection will be opened or pulled from the pool of available
        # connections. Additionally, a transaction will be started.
        user = User.create(username='charlie')

    # When the block ends, the transaction will be committed and the connection
    # will be returned to the pool.

    @db.execution_context(with_transaction=False)
    def do_something(foo, bar):
        # When this function is called, a separate connection is made and will
        # be closed when the function returns.
"""
import heapq
import logging
import time

from peewee import MySQLDatabase
from peewee import PostgresqlDatabase
from peewee import SqliteDatabase

logger = logging.getLogger('peewee.pool')


class PooledDatabase(object):
    def __init__(self, database, max_connections=20, stale_timeout=None,
                 **kwargs):
        self.max_connections = int(max_connections)
        self.stale_timeout = float(stale_timeout)
        self._connections = []
        self._in_use = {}
        self._closed = set()
        self.conn_key = id

        super(PooledDatabase, self).__init__(database, **kwargs)

    def init(self, database, max_connections=None, stale_timeout=None,
             **connect_kwargs):
        super(PooledDatabase, self).init(database, **connect_kwargs)
        if max_connections:
            self.max_connections = max_connections
        if stale_timeout:
            self.stale_timeout = stale_timeout

    def _connect(self, *args, **kwargs):
        while True:
            try:
                # Remove the oldest connection from the heap.
                ts, conn = heapq.heappop(self._connections)
                key = self.conn_key(conn)
            except IndexError:
                ts = conn = None
                logger.debug('No connection available in pool.')
                break
            else:
                if self._is_closed(key, conn):
                    # This connecton was closed, but since it was not stale
                    # it got added back to the queue of available conns. We
                    # then closed it and marked it as explicitly closed, so
                    # it's safe to throw it away now.
                    # (Because Database.close() calls Database._close()).
                    logger.debug('Connection %s was closed.', key)
                    ts = conn = None
                    self._closed.discard(key)
                elif self.stale_timeout and self._is_stale(ts):
                    # If we are attempting to check out a stale connection,
                    # then close it. We don't need to mark it in the "closed"
                    # set, because it is not in the list of available conns
                    # anymore.
                    logger.debug('Connection %s was stale, closing.', key)
                    self._close(conn, True)
                    self._closed.discard(key)
                    ts = conn = None
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
            ts = self._in_use[key]
            del self._in_use[key]
            if self.stale_timeout and self._is_stale(ts):
                logger.debug('Closing stale connection %s.', key)
                super(PooledDatabase, self)._close(conn)
            else:
                logger.debug('Returning %s to pool.', key)
                heapq.heappush(self._connections, (ts, conn))

    def manual_close(self):
        """
        Close the underlying connection without returning it to the pool.
        """
        conn = self.get_conn()
        self.close()
        if not self._is_closed(self.conn_key(conn), conn):
            self._close(conn, close_conn=True)

    def close_all(self):
        """
        Close all connections managed by the pool.
        """
        for _, conn in self._connections:
            self._close(conn, close_conn=True)


class PooledMySQLDatabase(PooledDatabase, MySQLDatabase):
    def _is_closed(self, key, conn):
        is_closed = super(PooledMySQLDatabase, self)._is_closed(key, conn)
        if not is_closed:
            try:
                conn.ping(False)
            except:
                is_closed = True
        return is_closed


class _PooledPostgresqlDatabase(PooledDatabase):
    def _is_closed(self, key, conn):
        closed = super(_PooledPostgresqlDatabase, self)._is_closed(key, conn)
        if not closed:
            closed = bool(conn.closed)
        return closed

class PooledPostgresqlDatabase(_PooledPostgresqlDatabase, PostgresqlDatabase):
    pass

try:
    from playhouse.postgres_ext import PostgresqlExtDatabase

    class PooledPostgresqlExtDatabase(_PooledPostgresqlDatabase, PostgresqlExtDatabase):
        pass
except ImportError:
    pass


class _PooledSqliteDatabase(PooledDatabase):
    def _is_closed(self, key, conn):
        closed = super(_PooledSqliteDatabase, self)._is_closed(key, conn)
        if not closed:
            try:
                conn.total_changes
            except:
                return True
        return closed

class PooledSqliteDatabase(_PooledSqliteDatabase, SqliteDatabase):
    pass

try:
    from playhouse.sqlite_ext import SqliteExtDatabase

    class PooledSqliteExtDatabase(_PooledSqliteDatabase, SqliteExtDatabase):
        pass
except ImportError:
    pass
