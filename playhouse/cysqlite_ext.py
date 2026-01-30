import logging
from peewee import ImproperlyConfigured
from peewee import SqliteDatabase
from peewee import __exception_wrapper__

try:
    from cysqlite import Connection
except ImportError:
    Connection = None

logger = logging.getLogger('peewee')

class CySqliteDatabase(SqliteDatabase):
    def _connect(self):
        if Connection is None:
            raise ImproperlyConfigured('cysqlite is not installed.')
        conn = Connection(self.database, timeout=self._timeout,
                          extensions=True, **self.connect_params)
        conn.connect()
        try:
            self._add_conn_hooks(conn)
        except:
            conn.close()
            raise
        return conn

    def _set_pragmas(self, conn):
        for pragma, value in self._pragmas:
            conn.execute_one('PRAGMA %s = %s;' % (pragma, value))

    def _attach_databases(self, conn):
        for name, db in self._attached.items():
            conn.execute_one('ATTACH DATABASE "%s" AS "%s"' % (db, name))

    def _load_aggregates(self, conn):
        for name, (klass, num_params) in self._aggregates.items():
            conn.create_aggregate(klass, name, num_params)

    def _load_collations(self, conn):
        for name, fn in self._collations.items():
            conn.create_collation(fn, name)

    def _load_functions(self, conn):
        for name, (fn, num_params, deterministic) in self._functions.items():
            conn.create_function(fn, name, num_params, deterministic)

    def _load_window_functions(self, conn):
        for name, (klass, num_params) in self._window_functions.items():
            conn.create_window_function(klass, name, num_params)

    def last_insert_id(self, cursor, query_type=None):
        return self.connection().last_insert_rowid()

    def rows_affected(self, cursor):
        return self.connection().changes()

    def begin(self, lock_type='deferred'):
        with __exception_wrapper__:
            self.connection().begin(lock_type)

    def commit(self):
        with __exception_wrapper__:
            self.connection().commit()

    def rollback(self):
        with __exception_wrapper__:
            self.connection().rollback()

    def cursor(self):
        raise NotImplementedError('cysqlite does not use a cursor interface.')

    def execute_sql(self, sql, params=None):
        logger.debug((sql, params))
        with __exception_wrapper__:
            conn = self.connection()
            stmt = conn.execute(sql, params or ())
        return stmt
