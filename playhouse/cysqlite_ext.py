import logging
from peewee import ImproperlyConfigured
from peewee import SqliteDatabase
from peewee import __exception_wrapper__

try:
    import cysqlite
except ImportError:
    Connection = None

logger = logging.getLogger('peewee')

class CySqliteDatabase(SqliteDatabase):
    def _connect(self):
        if cysqlite is None:
            raise ImproperlyConfigured('cysqlite is not installed.')
        conn = cysqlite.Connection(self.database, timeout=self._timeout,
                                   extensions=True, **self.connect_params)
        try:
            self._add_conn_hooks(conn)
        except Exception:
            conn.close()
            raise
        return conn

    def _set_pragmas(self, conn):
        for pragma, value in self._pragmas:
            conn.pragma(pragma, value)

    def _attach_databases(self, conn):
        for name, db in self._attached.items():
            conn.attach(db, name)

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

    def begin(self, lock_type='deferred'):
        with __exception_wrapper__:
            self.connection().begin(lock_type)

    def commit(self):
        with __exception_wrapper__:
            self.connection().commit()

    def rollback(self):
        with __exception_wrapper__:
            self.connection().rollback()
