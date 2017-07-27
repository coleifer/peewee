from cpython.bytes cimport PyBytes_AsStringAndSize
from cpython.bytes cimport PyBytes_FromStringAndSize
from cpython.bytes cimport PyBytes_AS_STRING
from cpython.object cimport PyObject
from libc.stdlib cimport rand

import weakref

from peewee import InterfaceError
from peewee import Node
from peewee import OperationalError
from peewee import sqlite3 as pysqlite
from playhouse.sqlite_ext import SqliteExtDatabase


cdef extern from "sqlite3.h":
    ctypedef struct sqlite3:
        int busyTimeout
    ctypedef struct sqlite3_backup
    ctypedef struct sqlite3_blob
    ctypedef long long sqlite3_int64
    ctypedef unsigned long long sqlite_uint64

    # Return values.
    cdef int SQLITE_OK = 0
    cdef int SQLITE_ERROR = 1
    cdef int SQLITE_NOMEM = 7

    ctypedef void (*sqlite3_destructor_type)(void*)

    # Memory management.
    cdef void* sqlite3_malloc(int)
    cdef void sqlite3_free(void *)

    cdef int sqlite3_changes(sqlite3 *db)
    cdef int sqlite3_get_autocommit(sqlite3 *db)
    cdef sqlite3_int64 sqlite3_last_insert_rowid(sqlite3 *db)

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
    #cdef int SQLITE_DBSTATUS_CACHE_USED_SHARED = 11
    cdef int sqlite3_db_status(sqlite3 *, int op, int *pCur, int *pHigh, int reset)

    cdef int SQLITE_DELETE = 9
    cdef int SQLITE_INSERT = 18
    cdef int SQLITE_UPDATE = 23

    # Misc.
    cdef int sqlite3_busy_handler(sqlite3 *db, int(*)(void *, int), void *)
    cdef int sqlite3_sleep(int ms)
    cdef sqlite3_backup *sqlite3_backup_init(
        sqlite3 *pDest,
        const char *zDestName,
        sqlite3 *pSource,
        const char *zSourceName)

    # Backup.
    cdef int sqlite3_backup_step(sqlite3_backup *p, int nPage)
    cdef int sqlite3_backup_finish(sqlite3_backup *p)
    cdef int sqlite3_backup_remaining(sqlite3_backup *p)
    cdef int sqlite3_backup_pagecount(sqlite3_backup *p)

    # Error handling.
    cdef int sqlite3_errcode(sqlite3 *db)
    cdef int sqlite3_errstr(int)
    cdef const char *sqlite3_errmsg(sqlite3 *db)

    cdef int sqlite3_blob_open(
          sqlite3*,
          const char *zDb,
          const char *zTable,
          const char *zColumn,
          sqlite3_int64 iRow,
          int flags,
          sqlite3_blob **ppBlob)
    cdef int sqlite3_blob_reopen(sqlite3_blob *, sqlite3_int64)
    cdef int sqlite3_blob_close(sqlite3_blob *)
    cdef int sqlite3_blob_bytes(sqlite3_blob *)
    cdef int sqlite3_blob_read(sqlite3_blob *, void *Z, int N, int iOffset)
    cdef int sqlite3_blob_write(sqlite3_blob *, const void *z, int n,
                                int iOffset)


cdef extern from "_pysqlite/connection.h":
    ctypedef struct pysqlite_Connection:
        sqlite3* db
        double timeout
        int initialized
        PyObject* isolation_level
        char* begin_statement


cdef inline int _check_connection(db) except -1:
    """
    Check that the underlying SQLite database connection is usable. Raises an
    InterfaceError if the connection is either uninitialized or closed.
    """
    cdef:
        pysqlite_Connection *conn = <pysqlite_Connection *>(db._state.conn)
    if not conn.initialized:
        raise InterfaceError('Connection not initialized.')
    if not conn.db:
        raise InterfaceError('Cannot operate on closed database.')
    return 1


class ZeroBlob(Node):
    def __init__(self, length):
        if not isinstance(length, int) or length < 0:
            raise ValueError('Length must be a positive integer.')
        self.length = length

    def __sql__(self, ctx):
        return ctx.literal('zeroblob(%s)' % self.length)


cdef class Blob(object)  # Forward declaration.


cdef inline int _check_blob_closed(Blob blob) except -1:
    if not blob.pBlob:
        raise InterfaceError('Cannot operate on closed blob.')
    return 1


cdef class Blob(object):
    cdef:
        int offset
        pysqlite_Connection *conn
        sqlite3_blob *pBlob

    def __init__(self, database, table, column, rowid,
                 read_only=False):
        cdef:
            int flags = 0 if read_only else 1
            int rc
            sqlite3_blob *blob

        _check_connection(database)

        self.conn = <pysqlite_Connection *>(database._state.conn)
        rc = sqlite3_blob_open(
            self.conn.db,
            'main',
            <char *>table,
            <char *>column,
            <long long>rowid,
            flags,
            &blob)
        if rc != SQLITE_OK:
            raise OperationalError('Unable to open blob.')

        self.pBlob = blob
        self.offset = 0

    cdef _close(self):
        if self.pBlob:
            sqlite3_blob_close(self.pBlob)
        self.pBlob = <sqlite3_blob *>0

    def __dealloc__(self):
        self._close()

    def __len__(self):
        _check_blob_closed(self)
        return sqlite3_blob_bytes(self.pBlob)

    def read(self, n=None):
        cdef:
            bytes pybuf
            int length = -1
            int size
            char *buf

        if n is not None:
            length = n

        _check_blob_closed(self)
        size = sqlite3_blob_bytes(self.pBlob)
        if self.offset == size or length == 0:
            return ''

        if length < 0:
            length = size - self.offset

        if self.offset + length > size:
            length = size - self.offset

        pybuf = PyBytes_FromStringAndSize(NULL, length)
        buf = PyBytes_AS_STRING(pybuf)
        if sqlite3_blob_read(self.pBlob, buf, length, self.offset):
            self._close()
            raise OperationalError('Error reading from blob.')

        self.offset += length
        return bytes(pybuf)

    def seek(self, offset, frame_of_reference=0):
        cdef int size
        _check_blob_closed(self)
        size = sqlite3_blob_bytes(self.pBlob)
        if frame_of_reference == 0:
            if offset < 0 or offset > size:
                raise ValueError('seek() offset outside of valid range.')
            self.offset = offset
        elif frame_of_reference == 1:
            if self.offset + offset < 0 or self.offset + offset > size:
                raise ValueError('seek() offset outside of valid range.')
            self.offset += offset
        elif frame_of_reference == 2:
            if size + offset < 0 or size + offset > size:
                raise ValueError('seek() offset outside of valid range.')
            self.offset = size + offset
        else:
            raise ValueError('seek() frame of reference must be 0, 1 or 2.')

    def tell(self):
        _check_blob_closed(self)
        return self.offset

    def write(self, data):
        cdef:
            char *buf
            int size
            Py_ssize_t buflen

        _check_blob_closed(self)
        size = sqlite3_blob_bytes(self.pBlob)
        PyBytes_AsStringAndSize(data, &buf, &buflen)
        if (<int>(buflen + self.offset)) < self.offset:
            raise ValueError('Data is too large (integer wrap)')
        if (<int>(buflen + self.offset)) > size:
            raise ValueError('Data would go beyond end of blob')
        if sqlite3_blob_write(self.pBlob, buf, buflen, self.offset):
            raise OperationalError('Error writing to blob.')
        self.offset += <int>buflen

    def close(self):
        self._close()

    def reopen(self, rowid):
        _check_blob_closed(self)
        self.offset = 0
        if sqlite3_blob_reopen(self.pBlob, <long long>rowid):
            self._close()
            raise OperationalError('Unable to re-open blob.')


def __status__(flag, return_highwater=False):
    """
    Expose a sqlite3_status() call for a particular flag as a property of the
    Database object.
    """
    def getter(self):
        cdef int current, highwater
        cdef int rc = sqlite3_status(flag, &current, &highwater, 0)
        if rc == SQLITE_OK:
            if return_highwater:
                return highwater
            else:
                return (current, highwater)
        else:
            raise Exception('Error requesting status: %s' % rc)
    return property(getter)


def __dbstatus__(flag, return_highwater=False, return_current=False):
    """
    Expose a sqlite3_dbstatus() call for a particular flag as a property of the
    Database instance. Unlike sqlite3_status(), the dbstatus properties pertain
    to the current connection.
    """
    def getter(self):
        cdef:
            int current, hi
            pysqlite_Connection *c = <pysqlite_Connection *>(self._state.conn)
            int rc = sqlite3_db_status(c.db, flag, &current, &hi, 0)

        if rc != SQLITE_OK:
            raise Exception('Error requesting db status: %s' % rc)

        if return_highwater:
            return hi
        elif return_current:
            return current
        else:
            return (current, hi)
    return property(getter)


class CySqliteExtDatabase(SqliteExtDatabase):
    def __init__(self, database, pragmas=None, *args, **kwargs):
        super(CySqliteExtDatabase, self).__init__(database, pragmas=pragmas,
                                                  *args, **kwargs)
        self._commit_hook = None
        self._rollback_hook = None
        self._update_hook = None

    def _add_conn_hooks(self, conn):
        super(CySqliteExtDatabase, self)._add_conn_hooks(conn)

        if self._commit_hook is not None:
            self._set_commit_hook(conn, self._commit_hook)
        if self._rollback_hook is not None:
            self._set_rollback_hook(conn, self._rollback_hook)
        if self._update_hook is not None:
            self._set_update_hook(conn, self._update_hook)

    def on_commit(self, fn):
        self._commit_hook = fn
        if not self.is_closed():
            self._set_commit_hook(self.connection(), fn)
        return fn

    def _set_commit_hook(self, connection, fn):
        cdef pysqlite_Connection *conn = <pysqlite_Connection *>connection
        if fn is None:
            sqlite3_commit_hook(conn.db, NULL, NULL)
        else:
            sqlite3_commit_hook(conn.db, _commit_callback, <void *>fn)

    def on_rollback(self, fn):
        self._rollback_hook = fn
        if not self.is_closed():
            self._set_rollback_hook(self.connection(), fn)
        return fn

    def _set_rollback_hook(self, connection, fn):
        cdef pysqlite_Connection *conn = <pysqlite_Connection *>connection
        if fn is None:
            sqlite3_rollback_hook(conn.db, NULL, NULL)
        else:
            sqlite3_rollback_hook(conn.db, _rollback_callback, <void *>fn)

    def on_update(self, fn):
        self._update_hook = fn
        if not self.is_closed():
            self._set_update_hook(self.connection(), fn)
        return fn

    def _set_update_hook(self, connection, fn):
        cdef pysqlite_Connection *conn = <pysqlite_Connection *>connection
        if fn is None:
            sqlite3_update_hook(conn.db, NULL, NULL)
        else:
            sqlite3_update_hook(conn.db, _update_callback, <void *>fn)

    def blob_open(self, table, column, rowid, read_only=False):
        return Blob(self, table, column, rowid, read_only)

    def backup(self, destination):
        return backup(self.connection(), destination.connection())

    def backup_to_file(self, filename):
        return backup_to_file(self.connection(), filename)

    def set_busy_handler(self, timeout=5000):
        """
        Replace the default busy handler with one that introduces some "jitter"
        into the amount of time delayed between checks.
        """
        cdef:
            int n = timeout
            pysqlite_Connection *c = <pysqlite_Connection *>(self._state.conn)

        sqlite3_busy_handler(c.db, _aggressive_busy_handler, <void *>n)
        return True

    def changes(self):
        cdef:
            pysqlite_Connection *c = <pysqlite_Connection *>(self._state.conn)
        return sqlite3_changes(c.db)

    @property
    def last_insert_rowid(self):
        cdef:
            pysqlite_Connection *c = <pysqlite_Connection *>(self._state.conn)
        return <int>sqlite3_last_insert_rowid(c.db)

    @property
    def autocommit(self):
        cdef:
            pysqlite_Connection *c = <pysqlite_Connection *>(self._state.conn)
        return sqlite3_get_autocommit(c.db) != 0

    # Status properties.
    memory_used = __status__(SQLITE_STATUS_MEMORY_USED)
    malloc_size = __status__(SQLITE_STATUS_MALLOC_SIZE, True)
    malloc_count = __status__(SQLITE_STATUS_MALLOC_COUNT)
    pagecache_used = __status__(SQLITE_STATUS_PAGECACHE_USED)
    pagecache_overflow = __status__(SQLITE_STATUS_PAGECACHE_OVERFLOW)
    pagecache_size = __status__(SQLITE_STATUS_PAGECACHE_SIZE, True)
    scratch_used = __status__(SQLITE_STATUS_SCRATCH_USED)
    scratch_overflow = __status__(SQLITE_STATUS_SCRATCH_OVERFLOW)
    scratch_size = __status__(SQLITE_STATUS_SCRATCH_SIZE, True)

    # Connection status properties.
    lookaside_used = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_USED)
    lookaside_hit = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_HIT, True)
    lookaside_miss = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_MISS_SIZE, True)
    lookaside_miss_full = __dbstatus__(SQLITE_DBSTATUS_LOOKASIDE_MISS_FULL,
                                       True)
    cache_used = __dbstatus__(SQLITE_DBSTATUS_CACHE_USED, False, True)
    #cache_used_shared = __dbstatus__(SQLITE_DBSTATUS_CACHE_USED_SHARED,
    #                                 False, True)
    schema_used = __dbstatus__(SQLITE_DBSTATUS_SCHEMA_USED, False, True)
    statement_used = __dbstatus__(SQLITE_DBSTATUS_STMT_USED, False, True)
    cache_hit = __dbstatus__(SQLITE_DBSTATUS_CACHE_HIT, False, True)
    cache_miss = __dbstatus__(SQLITE_DBSTATUS_CACHE_MISS, False, True)
    cache_write = __dbstatus__(SQLITE_DBSTATUS_CACHE_WRITE, False, True)


cdef int _commit_callback(void *userData) with gil:
    # C-callback that delegates to the Python commit handler. If the Python
    # function raises a ValueError, then the commit is aborted and the
    # transaction rolled back. Otherwise, regardless of the function return
    # value, the transaction will commit.
    cdef object fn = <object>userData
    try:
        fn()
    except ValueError:
        return 1
    else:
        return SQLITE_OK


cdef void _rollback_callback(void *userData) with gil:
    # C-callback that delegates to the Python rollback handler.
    cdef object fn = <object>userData
    fn()


cdef void _update_callback(void *userData, int queryType, char *database,
                            char *table, sqlite3_int64 rowid) with gil:
    # C-callback that delegates to a Python function that is executed whenever
    # the database is updated (insert/update/delete queries). The Python
    # callback receives a string indicating the query type, the name of the
    # database, the name of the table being updated, and the rowid of the row
    # being updatd.
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


def backup(src_conn, dest_conn):
    cdef:
        pysqlite_Connection *src = <pysqlite_Connection *>src_conn
        pysqlite_Connection *dest = <pysqlite_Connection *>dest_conn
        sqlite3 *src_db = src.db
        sqlite3 *dest_db = dest.db
        sqlite3_backup *backup

    backup = sqlite3_backup_init(dest_db, 'main', src_db, 'main')
    if (backup == NULL):
        raise OperationalError('Unable to initialize backup.')

    sqlite3_backup_step(backup, -1)
    sqlite3_backup_finish(backup)
    if sqlite3_errcode(dest_db):
        raise OperationalError('Error finishing backup: %s' %
                               sqlite3_errmsg(dest_db))
    return True


def backup_to_file(src_conn, filename):
    dest_conn = pysqlite.connect(filename)
    backup(src_conn, dest_conn)
    dest_conn.close()
    return True


cdef int _aggressive_busy_handler(void *ptr, int n):
    # In concurrent environments, it often seems that if multiple queries are
    # kicked off at around the same time, they proceed in lock-step to check
    # for the availability of the lock. By introducing some "jitter" we can
    # ensure that this doesn't happen. Furthermore, this function makes more
    # attempts in the same time period than the default handler.
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
        total = 1200 + ((n - 40) * 100)  # Estimate the amount of time slept.

    if total + current > busyTimeout:
        current = busyTimeout - total
    if current > 0:
        sqlite3_sleep(current)
        return 1
    return 0
