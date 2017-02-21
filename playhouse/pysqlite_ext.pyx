from peewee import DatabaseError, OperationalError, ProgrammingError
from playhouse.sqlite_ext import SqliteExtDatabase
from cpython.mem cimport PyMem_Free
from cpython.object cimport PyObject
from cpython.ref cimport Py_INCREF
from libc.stdlib cimport rand


cdef extern from "_pysqlite/connection.h":
    ctypedef struct pysqlite_Connection:
        sqlite3* db
        double timeout
        int initialized
        PyObject* isolation_level
        char* begin_statement


cdef extern from "sqlite3.h":
    ctypedef struct sqlite3
    ctypedef struct sqlite3_context
    ctypedef struct sqlite3_value
    ctypedef long long sqlite3_int64

    cdef int SQLITE_UTF8 = 1
    cdef int SQLITE_OK = 0
    cdef int SQLITE_ERROR = 1
    cdef int SQLITE_DETERMINISTIC = 0x800

    # sqlite_value_type.
    cdef int SQLITE_INTEGER = 1
    cdef int SQLITE_FLOAT   = 2
    cdef int SQLITE3_TEXT   = 3
    cdef int SQLITE_TEXT    = 3
    cdef int SQLITE_BLOB    = 4
    cdef int SQLITE_NULL    = 5

    ctypedef void (*sqlite3_destructor_type)(void*)

    cdef int sqlite3_create_function(
        sqlite3 *db,
        const char *zFunctionName,
        int nArg,
        int eTextRep,  # SQLITE_UTF8
        void *pApp,  # App-specific data.
        void (*xFunc)(sqlite3_context *, int, sqlite3_value **),
        void (*xStep)(sqlite3_context*, int, sqlite3_value **),
        void (*xFinal)(sqlite3_context*))

    cdef const void *sqlite3_value_blob(sqlite3_value*);
    cdef int sqlite3_value_bytes(sqlite3_value*);
    cdef double sqlite3_value_double(sqlite3_value*);
    cdef int sqlite3_value_int(sqlite3_value*);
    cdef sqlite3_int64 sqlite3_value_int64(sqlite3_value*);
    cdef const unsigned char *sqlite3_value_text(sqlite3_value*);
    cdef int sqlite3_value_type(sqlite3_value*);
    cdef int sqlite3_value_numeric_type(sqlite3_value*);

    cdef void sqlite3_result_double(sqlite3_context*, double)
    cdef void sqlite3_result_error(sqlite3_context*, const char*, int)
    cdef void sqlite3_result_error_toobig(sqlite3_context*)
    cdef void sqlite3_result_error_nomem(sqlite3_context*)
    cdef void sqlite3_result_error_code(sqlite3_context*, int)
    cdef void sqlite3_result_int(sqlite3_context*, int)
    cdef void sqlite3_result_int64(sqlite3_context*, sqlite3_int64)
    cdef void sqlite3_result_null(sqlite3_context*)
    cdef void sqlite3_result_text(sqlite3_context*, const char*, int, void(*)(void*))
    cdef void sqlite3_result_value(sqlite3_context*, sqlite3_value*)

    cdef void* sqlite3_malloc(int)
    cdef void sqlite3_free(void *)

    cdef int sqlite3_changes(sqlite3 *db)
    cdef int sqlite3_get_autocommit(sqlite3 *db)

    cdef int sqlite3_create_function(
        sqlite3 *db,
        const char *zFunctionName,
        int nArg,
        int eEncoding,
        void *pApp,
        void (*xFunc)(sqlite3_context *, int, sqlite3_value **),
        void (*xStep)(sqlite3_context *, int, sqlite3_value **),
        void (*xFinal)(sqlite3_context *))
    cdef void *sqlite3_user_data(sqlite3_context *)

    cdef void *sqlite3_get_auxdata(sqlite3_context *, int N)
    cdef void sqlite3_set_auxdata(sqlite3_context *, int N, void *, void(*)(void *))

    cdef void *sqlite3_commit_hook(sqlite3 *, int(*)(void *), void *)
    cdef void *sqlite3_rollback_hook(sqlite3 *, void(*)(void *), void *)
    cdef void *sqlite3_update_hook(
        sqlite3 *,
        void(*)(void *, int, char *, char *, sqlite3_int64),
        void *)

    cdef int SQLITE_STATUS_MEMORY_USED = 0
    cdef int SQLITE_STATUS_PAGECACHE_USED = 1
    cdef int SQLITE_STATUS_PAGECACHE_OVERFLOW = 2
    cdef int SQLITE_STATUS_SCRATCH_USED = 3
    cdef int SQLITE_STATUS_SCRATCH_OVERFLOW = 4
    cdef int SQLITE_STATUS_MALLOC_SIZE = 5
    cdef int SQLITE_STATUS_PARSER_STACK = 6
    cdef int SQLITE_STATUS_PAGECACHE_SIZE = 7
    cdef int SQLITE_STATUS_SCRATCH_SIZE = 8
    cdef int SQLITE_STATUS_MALLOC_COUNT = 9
    cdef int sqlite3_status(int op, int *pCurrent, int *pHighwater, int resetFlag)

    cdef int SQLITE_DBSTATUS_LOOKASIDE_USED = 0
    cdef int SQLITE_DBSTATUS_CACHE_USED = 1
    cdef int SQLITE_DBSTATUS_SCHEMA_USED = 2
    cdef int SQLITE_DBSTATUS_STMT_USED = 3
    cdef int SQLITE_DBSTATUS_LOOKASIDE_HIT = 4
    cdef int SQLITE_DBSTATUS_LOOKASIDE_MISS_SIZE = 5
    cdef int SQLITE_DBSTATUS_LOOKASIDE_MISS_FULL = 6
    cdef int SQLITE_DBSTATUS_CACHE_HIT = 7
    cdef int SQLITE_DBSTATUS_CACHE_MISS = 8
    cdef int SQLITE_DBSTATUS_CACHE_WRITE = 9
    cdef int SQLITE_DBSTATUS_DEFERRED_FKS = 10
    cdef int SQLITE_DBSTATUS_CACHE_USED_SHARED = 11
    cdef int sqlite3_db_status(sqlite3 *, int op, int *pCur, int *pHigh, int reset)

    cdef int SQLITE_DELETE = 9
    cdef int SQLITE_INSERT = 18
    cdef int SQLITE_UPDATE = 23

    # Misc.
    cdef int sqlite3_busy_handler(sqlite3 *db, int(*)(void *, int), void *)
    cdef int sqlite3_sleep(int ms)



def status_property(flag, return_highwater=False):
    def getter(self):
        cdef int current, highwater
        cdef int rc = sqlite3_status(flag, &current, &highwater, 0)
        if rc == SQLITE_OK:
            if return_highwater:
                return highwater
            else:
                return (current, highwater)
        else:
            raise DatabaseError('Error requesting status: %s' % rc)
    return property(getter)


class Database(SqliteExtDatabase):
    memory_used = status_property(SQLITE_STATUS_MEMORY_USED)
    malloc_size = status_property(SQLITE_STATUS_MALLOC_SIZE, True)
    malloc_count = status_property(SQLITE_STATUS_MALLOC_COUNT)
    pagecache_used = status_property(SQLITE_STATUS_PAGECACHE_USED)
    pagecache_overflow = status_property(SQLITE_STATUS_PAGECACHE_OVERFLOW)
    pagecache_size = status_property(SQLITE_STATUS_PAGECACHE_SIZE, True)
    scratch_used = status_property(SQLITE_STATUS_SCRATCH_USED)
    scratch_overflow = status_property(SQLITE_STATUS_SCRATCH_OVERFLOW)
    scratch_size = status_property(SQLITE_STATUS_SCRATCH_SIZE, True)

    def __init__(self, *args, **kwargs):
        super(Database, self).__init__(*args, **kwargs)
        self._update_callback = None
        self._commit_callback = None
        self._rollback_callback = None

    @property
    def connection(self):
        return Connection(self.get_conn())

    def _add_conn_hooks(self, conn):
        super(Database, self)._add_conn_hooks(conn)
        cxn = Connection(conn)
        cxn.set_busy_handler(5000)
        if self._update_callback is not None:
            cxn.on_update(self._update_callback)
        if self._commit_callback is not None:
            cxn.on_commit(self._commit_callback)
        if self._rollback_callback is not None:
            cxn.on_rollback(self._rollback_callback)

    def on_update(self, fn):
        self._update_callback = fn
        if not self.is_closed():
            self.connection.on_update(fn)
        return self

    def on_commit(self, fn):
        self._commit_callback = fn
        if not self.is_closed():
            self.connection.on_commit(fn)
        return self

    def on_rollback(self, fn):
        self._rollback_callback = fn
        if not self.is_closed():
            self.connection.on_rollback(fn)
        return self

    def func(self, name=None, num_params=-1, non_deterministic=False):
        def decorator(fn):
            self.register_function(fn, name, num_params, non_deterministic)
            return fn
        return decorator

    def register_function(self, fn, name=None, num_params=-1,
                          non_deterministic=False):
        name = name or fn.__name__
        self._functions[name] = (fn, num_params, non_deterministic)
        if not self.is_closed():
            self._load_functions(self.get_conn())

    def _load_functions(self, conn):
        wrapper = Connection(conn)
        for name, (fn, num_params, non_dtm) in self._functions.items():
            wrapper.create_function(fn, name, num_params, non_dtm)


cdef _sqlite_to_python(sqlite3_context *context, int n, sqlite3_value **args):
    cdef:
        int i
        int value_type
        list accum = []
        sqlite3_value *value

    for i in range(n):
        value = args[i]
        value_type = sqlite3_value_type(value)

        if value_type == SQLITE_INTEGER:
            obj = sqlite3_value_int(value)
        elif value_type == SQLITE_FLOAT:
            obj = sqlite3_value_double(value)
        elif value_type == SQLITE_TEXT:
            obj = str(sqlite3_value_text(value))
        elif value_type == SQLITE_BLOB:
            obj = <bytes>sqlite3_value_blob(value)
        else:
            obj = None
        accum.append(obj)

    return accum


cdef _python_to_sqlite(sqlite3_context *context, value):
    if value is None:
        sqlite3_result_null(context)
    elif isinstance(value, (int, long)):
        sqlite3_result_int64(context, <sqlite3_int64>value)
    elif isinstance(value, float):
        sqlite3_result_double(context, <double>value)
    elif isinstance(value, basestring):
        sqlite3_result_text(context, <const char *>value, -1,
                            <sqlite3_destructor_type>-1)
    elif isinstance(value, bool):
        sqlite3_result_int(context, int(value))
    else:
        sqlite3_result_error(context, 'Unsupported type %s' % type(value), -1)
        return SQLITE_ERROR

    return SQLITE_OK


cdef void _function_callback(sqlite3_context *context, int nparams,
                             sqlite3_value **values) with gil:
    cdef:
        list params = _sqlite_to_python(context, nparams, values)

    fn = <object>sqlite3_user_data(context)
    _python_to_sqlite(context, fn(*params))

cdef int _commit_callback(void *userData) with gil:
    cdef object fn = <object>userData
    try:
        fn()
    except ValueError:
        return 1
    else:
        return SQLITE_OK

cdef void _rollback_callback(void *userData) with gil:
    cdef object fn = <object>userData
    fn()

cdef void _update_callback(void *userData, int queryType, char *database,
                            char *table, sqlite3_int64 rowid) with gil:
    cdef object fn = <object>userData
    if queryType == SQLITE_INSERT:
        query = 'INSERT'
    elif queryType == SQLITE_UPDATE:
        query = 'UPDATE'
    elif queryType == SQLITE_DELETE:
        query = 'DELETE'
    else:
        query = ''
    fn(query, str(database), str(table), <int>rowid)


cdef inline int _check_connection(pysqlite_Connection *conn) except -1:
    if not conn.initialized:
        raise DatabaseError('Connection not initialized.')
    if not conn.db:
        raise ProgrammingError('Cannot operate on closed database.')
    return 1


def dbstatus_property(flag, return_highwater=False, return_current=False):
    def getter(self):
        cdef int current, hi
        cdef Connection connection = <Connection>self
        cdef int rc = sqlite3_db_status((<pysqlite_Connection *>connection.conn).db, flag, &current, &hi, 0)
        if rc == SQLITE_OK:
            if return_highwater:
                return hi
            elif return_current:
                return current
            else:
                return (current, hi)
        else:
            raise DatabaseError('Error requesting db status: %s' % rc)
    return property(getter)


cdef class Connection(object):
    cdef:
        dict _function_map
        pysqlite_Connection *conn

    lookaside_used = dbstatus_property(SQLITE_DBSTATUS_LOOKASIDE_USED)
    lookaside_hit = dbstatus_property(SQLITE_DBSTATUS_LOOKASIDE_HIT, True)
    lookaside_miss = dbstatus_property(SQLITE_DBSTATUS_LOOKASIDE_MISS_SIZE,
                                       True)
    lookaside_miss_full = dbstatus_property(
        SQLITE_DBSTATUS_LOOKASIDE_MISS_FULL,
        True)
    cache_used = dbstatus_property(SQLITE_DBSTATUS_CACHE_USED, False, True)
    cache_used_shared = dbstatus_property(SQLITE_DBSTATUS_CACHE_USED_SHARED,
                                          False, True)
    schema_used = dbstatus_property(SQLITE_DBSTATUS_SCHEMA_USED, False, True)
    statement_used = dbstatus_property(SQLITE_DBSTATUS_STMT_USED, False, True)
    cache_hit = dbstatus_property(SQLITE_DBSTATUS_CACHE_HIT, False, True)
    cache_miss = dbstatus_property(SQLITE_DBSTATUS_CACHE_MISS, False, True)
    cache_write = dbstatus_property(SQLITE_DBSTATUS_CACHE_WRITE, False, True)

    def __init__(self, conn):
        self._function_map = {}
        self.conn = <pysqlite_Connection *>conn
        if self.conn.db:
            self.initialize_connection()

    cdef initialize_connection(self):
        if <object>(self.conn.isolation_level) is None:
            return

        if self.conn.begin_statement:
            PyMem_Free(self.conn.begin_statement)
            self.conn.begin_statement = NULL

        # Set the isolation level to `None` to enable autocommit.
        Py_INCREF(None)
        self.conn.isolation_level = <PyObject *>None

    def create_function(self, fn, name=None, n=-1, non_deterministic=False):
        cdef:
            int flags = SQLITE_UTF8
            int rc

        _check_connection(self.conn)
        name = name or fn.__name__
        if not non_deterministic:
            flags |= SQLITE_DETERMINISTIC

        rc = sqlite3_create_function(self.conn.db, <const char *>name, n,
                                     flags, <void *>fn, _function_callback,
                                     NULL, NULL)

        if rc != SQLITE_OK:
            raise OperationalError('Error calling sqlite3_create_function.')
        else:
            self._function_map[fn] = name

    def func(self, *args, **kwargs):
        def decorator(fn):
            self.create_function(fn, *args, **kwargs)
            return fn
        return decorator

    def on_commit(self, fn):
        if fn is None:
            sqlite3_commit_hook(self.conn.db, NULL, NULL)
        else:
            sqlite3_commit_hook(self.conn.db, _commit_callback, <void *>fn)
        return fn

    def on_rollback(self, fn):
        if fn is None:
            sqlite3_rollback_hook(self.conn.db, NULL, NULL)
        else:
            sqlite3_rollback_hook(self.conn.db, _rollback_callback, <void *>fn)
        return fn

    def on_update(self, fn):
        if fn is None:
            sqlite3_update_hook(self.conn.db, NULL, NULL)
        else:
            sqlite3_update_hook(self.conn.db, _update_callback, <void *>fn)
        return fn

    @property
    def autocommit(self):
        _check_connection(self.conn)
        return bool(sqlite3_get_autocommit(self.conn.db))

    @property
    def changes(self):
        return sqlite3_changes(self.conn.db)

    def set_busy_handler(self, timeout=5000):
        cdef:
            int n = timeout
            sqlite3 *db = (<pysqlite_Connection *>self.conn).db

        sqlite3_busy_handler(db, _aggressive_busy_handler, <void *>n)
        return True


cdef int _aggressive_busy_handler(void *ptr, int n):
    cdef:
        int busyTimeout = <int>ptr
        int current, total

    if n < 20:
        current = 25 - (rand() % 10)  # ~20ms
        total = n * 20
    elif n < 40:
        current = 50 - (rand() % 20)  # ~40ms
        total = 400 + ((n - 20) * 40)
    else:
        current = 120 - (rand() % 40)  # ~100ms
        total = 1200 + ((n - 40) * 100)

    if total + current > busyTimeout:
        current = busyTimeout - total
    if current > 0:
        sqlite3_sleep(current)
        return 1
    return 0
