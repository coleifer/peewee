import logging
from pathlib import Path

from peewee import DecimalField
from peewee import ImproperlyConfigured
from peewee import OP
from peewee import SqliteDatabase
from peewee import __exception_wrapper__
from playhouse.sqlite_ext import (
    RowIDField,
    DocIDField,
    AutoIncrementField,
    ISODateTimeField,
    JSONPath,
    JSONBPath,
    JSONField,
    JSONBField,
    SearchField,
    VirtualModel,
    FTSModel,
    FTS5Model)
from playhouse.sqlite_udf import rank

try:
    import cysqlite
except ImportError as exc:
    raise ImportError('cysqlite is not installed') from exc


logger = logging.getLogger('peewee')


def __status__(flag, return_highwater=False):
    def getter(self):
        result = cysqlite.status(flag)
        return result[1] if return_highwater else result
    return property(getter)

def __dbstatus__(flag, return_highwater=False, return_current=False):
    """
    Expose a sqlite3_dbstatus() call for a particular flag as a property of
    the Database instance. Unlike sqlite3_status(), the dbstatus properties
    pertain to the current connection.
    """
    def getter(self):
        if self._state.conn is None:
            raise ImproperlyConfigured('database connection not opened.')
        result = self._state.conn.status(flag)
        if return_current:
            return result[0]
        return result[1] if return_highwater else result
    return property(getter)


class TDecimalField(DecimalField):
    field_type = 'TEXT'

    def get_modifiers(self): pass

    def db_value(self, value):
        if value is not None:
            return str(super(DecimalField, self).db_value(value))


class CySqliteDatabase(SqliteDatabase):
    def __init__(self, database, rank_functions=True, *args, **kwargs):
        super(CySqliteDatabase, self).__init__(database, *args, **kwargs)

        self._table_functions = []
        self._commit_hook = None
        self._rollback_hook = None
        self._update_hook = None
        self._authorizer = None
        self._trace = None
        self._progress = None

        if rank_functions:
            self.register_function(cysqlite.rank_bm25, 'fts_bm25')
            self.register_function(cysqlite.rank_lucene, 'fts_lucene')
            self.register_function(rank, 'fts_rank')

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

    def _add_conn_hooks(self, conn):
        if self._commit_hook is not None:
            conn.commit_hook(self._commit_hook)
        if self._rollback_hook is not None:
            conn.rollback_hook(self._rollback_hook)
        if self._update_hook is not None:
            conn.update_hook(self._update_hook)
        if self._authorizer is not None:
            conn.authorizer(self._authorizer)
        if self._trace is not None:
            conn.trace(*self._trace)
        if self._progress is not None:
            conn.progress(*self._progress)
        super(CySqliteDatabase, self)._add_conn_hooks(conn)
        if self._table_functions:
            for table_function in self._table_functions:
                table_function.register(conn)

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

    def register_table_function(self, klass, name=None):
        if name is not None:
            klass.name = name
        self._table_functions.append(klass)
        if not self.is_closed():
            klass.register(self.connection())

    def unregister_table_function(self, name):
        for idx, klass in enumerate(self._table_functions):
            if klass.name == name:
                break
        else:
            return False
        self._table_functions.pop(idx)
        return True

    def table_function(self, name=None):
        def decorator(klass):
            self.register_table_function(klass, name)
            return klass
        return decorator

    def on_commit(self, fn):
        self._commit_hook = fn
        if not self.is_closed():
            self.connection().commit_hook(fn)
        return fn

    def on_rollback(self, fn):
        self._rollback_hook = fn
        if not self.is_closed():
            self.connection().rollback_hook(fn)
        return fn

    def on_update(self, fn):
        self._update_hook = fn
        if not self.is_closed():
            self.connection().update_hook(fn)
        return fn

    def authorizer(self, fn):
        self._authorizer = fn
        if not self.is_closed():
            self.connection().authorizer(fn)
        return fn

    def trace(self, fn, mask=2):
        if fn is None:
            self._trace = None
        else:
            self._trace = (fn, mask)
        if not self.is_closed():
            args = (None,) if fn is None else self._trace
            self.connection().trace(*args)
        return fn

    def progress(self, fn, n=1):
        if fn is None:
            self._progress = None
        else:
            self._progress = (fn, mask)
        if not self.is_closed():
            args = (None,) if fn is None else self._progress
            self.connection().progress(*args)
        return fn

    def begin(self, lock_type='deferred'):
        with __exception_wrapper__:
            self.connection().begin(lock_type)

    def commit(self):
        with __exception_wrapper__:
            self.connection().commit()

    def rollback(self):
        with __exception_wrapper__:
            self.connection().rollback()

    @property
    def autocommit(self):
        return self.connection().autocommit()

    def blob_open(self, table, column, rowid, read_only=False, dbname=None):
        return self.connection().blob_open(table, column, rowid, read_only,
                                           db_name)

    def backup(self, destination, pages=None, name=None, progress=None,
               src_name=None):

        if isinstance(destination, CySqliteDatabase):
            conn = destination.connection()
        elif isinstance(destination, cysqlite.Connection):
            conn = destination
        elif isinstance(destination, (str, Path)):
            return self.backup_to_file(str(destination), pages, name,
                                       progress, src_name)

        return self.connection().backup(conn, pages, name, progress, src_name)

    def backup_to_file(self, filename, pages=None, name=None, progress=None,
                       src_name=None):
        return self.connection().backup_to_file(filename, pages, name,
                                                progress, src_name)

    # Status properties.
    memory_used = __status__(cysqlite.SQLITE_STATUS_MEMORY_USED)
    malloc_size = __status__(cysqlite.SQLITE_STATUS_MALLOC_SIZE, True)
    malloc_count = __status__(cysqlite.SQLITE_STATUS_MALLOC_COUNT)
    pagecache_used = __status__(cysqlite.SQLITE_STATUS_PAGECACHE_USED)
    pagecache_overflow = __status__(
        cysqlite.SQLITE_STATUS_PAGECACHE_OVERFLOW)
    pagecache_size = __status__(cysqlite.SQLITE_STATUS_PAGECACHE_SIZE, True)
    scratch_used = __status__(cysqlite.SQLITE_STATUS_SCRATCH_USED)
    scratch_overflow = __status__(cysqlite.SQLITE_STATUS_SCRATCH_OVERFLOW)
    scratch_size = __status__(cysqlite.SQLITE_STATUS_SCRATCH_SIZE, True)

    # Connection status properties.
    lookaside_used = __dbstatus__(cysqlite.SQLITE_DBSTATUS_LOOKASIDE_USED)
    lookaside_hit = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_LOOKASIDE_HIT, True)
    lookaside_miss = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_LOOKASIDE_MISS_SIZE, True)
    lookaside_miss_full = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_LOOKASIDE_MISS_FULL, True)
    cache_used = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_CACHE_USED, False, True)
    schema_used = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_SCHEMA_USED, False, True)
    statement_used = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_STMT_USED, False, True)
    cache_hit = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_CACHE_HIT, False, True)
    cache_miss = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_CACHE_MISS, False, True)
    cache_write = __dbstatus__(
        cysqlite.SQLITE_DBSTATUS_CACHE_WRITE, False, True)


OP.MATCH = 'MATCH'

def _sqlite_regexp(regex, value):
    return re.search(regex, value) is not None
