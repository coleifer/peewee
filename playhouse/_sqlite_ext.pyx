import hashlib
import zlib

cimport cython
from cpython cimport datetime
from cpython.bytes cimport PyBytes_AsStringAndSize
from cpython.bytes cimport PyBytes_Check
from cpython.bytes cimport PyBytes_FromStringAndSize
from cpython.bytes cimport PyBytes_AS_STRING
from cpython.object cimport PyObject
from cpython.ref cimport Py_INCREF, Py_DECREF
from cpython.unicode cimport PyUnicode_AsUTF8String
from cpython.unicode cimport PyUnicode_Check
from cpython.unicode cimport PyUnicode_DecodeUTF8
from cpython.version cimport PY_MAJOR_VERSION
from libc.float cimport DBL_MAX
from libc.math cimport ceil, log, sqrt
from libc.math cimport pow as cpow
#from libc.stdint cimport ssize_t
from libc.stdint cimport uint8_t
from libc.stdint cimport uint32_t
from libc.stdlib cimport calloc, free, malloc, rand
from libc.string cimport memcpy, memset, strlen

from peewee import InterfaceError
from peewee import Node
from peewee import OperationalError
from peewee import sqlite3 as pysqlite

import traceback


cdef struct sqlite3_index_constraint:
    int iColumn  # Column constrained, -1 for rowid.
    unsigned char op  # Constraint operator.
    unsigned char usable  # True if this constraint is usable.
    int iTermOffset  # Used internally - xBestIndex should ignore.


cdef struct sqlite3_index_orderby:
    int iColumn
    unsigned char desc


cdef struct sqlite3_index_constraint_usage:
    int argvIndex  # if > 0, constraint is part of argv to xFilter.
    unsigned char omit


cdef extern from "sqlite3.h" nogil:
    ctypedef struct sqlite3:
        int busyTimeout
    ctypedef struct sqlite3_backup
    ctypedef struct sqlite3_blob
    ctypedef struct sqlite3_context
    ctypedef struct sqlite3_value
    ctypedef long long sqlite3_int64
    ctypedef unsigned long long sqlite_uint64

    # Virtual tables.
    ctypedef struct sqlite3_module  # Forward reference.
    ctypedef struct sqlite3_vtab:
        const sqlite3_module *pModule
        int nRef
        char *zErrMsg
    ctypedef struct sqlite3_vtab_cursor:
        sqlite3_vtab *pVtab

    ctypedef struct sqlite3_index_info:
        int nConstraint
        sqlite3_index_constraint *aConstraint
        int nOrderBy
        sqlite3_index_orderby *aOrderBy
        sqlite3_index_constraint_usage *aConstraintUsage
        int idxNum
        char *idxStr
        int needToFreeIdxStr
        int orderByConsumed
        double estimatedCost
        sqlite3_int64 estimatedRows
        int idxFlags

    ctypedef struct sqlite3_module:
        int iVersion
        int (*xCreate)(sqlite3*, void *pAux, int argc, const char *const*argv,
                       sqlite3_vtab **ppVTab, char**)
        int (*xConnect)(sqlite3*, void *pAux, int argc, const char *const*argv,
                        sqlite3_vtab **ppVTab, char**)
        int (*xBestIndex)(sqlite3_vtab *pVTab, sqlite3_index_info*)
        int (*xDisconnect)(sqlite3_vtab *pVTab)
        int (*xDestroy)(sqlite3_vtab *pVTab)
        int (*xOpen)(sqlite3_vtab *pVTab, sqlite3_vtab_cursor **ppCursor)
        int (*xClose)(sqlite3_vtab_cursor*)
        int (*xFilter)(sqlite3_vtab_cursor*, int idxNum, const char *idxStr,
                       int argc, sqlite3_value **argv)
        int (*xNext)(sqlite3_vtab_cursor*)
        int (*xEof)(sqlite3_vtab_cursor*)
        int (*xColumn)(sqlite3_vtab_cursor*, sqlite3_context *, int)
        int (*xRowid)(sqlite3_vtab_cursor*, sqlite3_int64 *pRowid)
        int (*xUpdate)(sqlite3_vtab *pVTab, int, sqlite3_value **,
                       sqlite3_int64 **)
        int (*xBegin)(sqlite3_vtab *pVTab)
        int (*xSync)(sqlite3_vtab *pVTab)
        int (*xCommit)(sqlite3_vtab *pVTab)
        int (*xRollback)(sqlite3_vtab *pVTab)
        int (*xFindFunction)(sqlite3_vtab *pVTab, int nArg, const char *zName,
                             void (**pxFunc)(sqlite3_context *, int,
                                             sqlite3_value **),
                             void **ppArg)
        int (*xRename)(sqlite3_vtab *pVTab, const char *zNew)
        int (*xSavepoint)(sqlite3_vtab *pVTab, int)
        int (*xRelease)(sqlite3_vtab *pVTab, int)
        int (*xRollbackTo)(sqlite3_vtab *pVTab, int)

    cdef int sqlite3_declare_vtab(sqlite3 *db, const char *zSQL)
    cdef int sqlite3_create_module(sqlite3 *db, const char *zName,
                                   const sqlite3_module *p, void *pClientData)

    cdef const char sqlite3_version[]

    # Encoding.
    cdef int SQLITE_UTF8 = 1

    # Return values.
    cdef int SQLITE_OK = 0
    cdef int SQLITE_ERROR = 1
    cdef int SQLITE_INTERNAL = 2
    cdef int SQLITE_PERM = 3
    cdef int SQLITE_ABORT = 4
    cdef int SQLITE_BUSY = 5
    cdef int SQLITE_LOCKED = 6
    cdef int SQLITE_NOMEM = 7
    cdef int SQLITE_READONLY = 8
    cdef int SQLITE_INTERRUPT = 9
    cdef int SQLITE_DONE = 101

    # Function type.
    cdef int SQLITE_DETERMINISTIC = 0x800

    # Types of filtering operations.
    cdef int SQLITE_INDEX_CONSTRAINT_EQ = 2
    cdef int SQLITE_INDEX_CONSTRAINT_GT = 4
    cdef int SQLITE_INDEX_CONSTRAINT_LE = 8
    cdef int SQLITE_INDEX_CONSTRAINT_LT = 16
    cdef int SQLITE_INDEX_CONSTRAINT_GE = 32
    cdef int SQLITE_INDEX_CONSTRAINT_MATCH = 64

    # sqlite_value_type.
    cdef int SQLITE_INTEGER = 1
    cdef int SQLITE_FLOAT   = 2
    cdef int SQLITE3_TEXT   = 3
    cdef int SQLITE_TEXT    = 3
    cdef int SQLITE_BLOB    = 4
    cdef int SQLITE_NULL    = 5

    ctypedef void (*sqlite3_destructor_type)(void*)

    # Converting from Sqlite -> Python.
    cdef const void *sqlite3_value_blob(sqlite3_value*)
    cdef int sqlite3_value_bytes(sqlite3_value*)
    cdef double sqlite3_value_double(sqlite3_value*)
    cdef int sqlite3_value_int(sqlite3_value*)
    cdef sqlite3_int64 sqlite3_value_int64(sqlite3_value*)
    cdef const unsigned char *sqlite3_value_text(sqlite3_value*)
    cdef int sqlite3_value_type(sqlite3_value*)
    cdef int sqlite3_value_numeric_type(sqlite3_value*)

    # Converting from Python -> Sqlite.
    cdef void sqlite3_result_blob(sqlite3_context*, const void *, int,
                                  void(*)(void*))
    cdef void sqlite3_result_double(sqlite3_context*, double)
    cdef void sqlite3_result_error(sqlite3_context*, const char*, int)
    cdef void sqlite3_result_error_toobig(sqlite3_context*)
    cdef void sqlite3_result_error_nomem(sqlite3_context*)
    cdef void sqlite3_result_error_code(sqlite3_context*, int)
    cdef void sqlite3_result_int(sqlite3_context*, int)
    cdef void sqlite3_result_int64(sqlite3_context*, sqlite3_int64)
    cdef void sqlite3_result_null(sqlite3_context*)
    cdef void sqlite3_result_text(sqlite3_context*, const char*, int,
                                  void(*)(void*))
    cdef void sqlite3_result_value(sqlite3_context*, sqlite3_value*)

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

    cdef int SQLITE_CONFIG_SINGLETHREAD = 1  # None
    cdef int SQLITE_CONFIG_MULTITHREAD = 2  # None
    cdef int SQLITE_CONFIG_SERIALIZED = 3  # None
    cdef int SQLITE_CONFIG_SCRATCH = 6  # void *, int sz, int N
    cdef int SQLITE_CONFIG_PAGECACHE = 7  # void *, int sz, int N
    cdef int SQLITE_CONFIG_HEAP = 8  # void *, int nByte, int min
    cdef int SQLITE_CONFIG_MEMSTATUS = 9  # boolean
    cdef int SQLITE_CONFIG_LOOKASIDE = 13  # int, int
    cdef int SQLITE_CONFIG_URI = 17  # int
    cdef int SQLITE_CONFIG_MMAP_SIZE = 22  # sqlite3_int64, sqlite3_int64
    cdef int SQLITE_CONFIG_STMTJRNL_SPILL = 26  # int nByte
    cdef int SQLITE_DBCONFIG_MAINDBNAME = 1000  # const char*
    cdef int SQLITE_DBCONFIG_LOOKASIDE = 1001  # void* int int
    cdef int SQLITE_DBCONFIG_ENABLE_FKEY = 1002  # int int*
    cdef int SQLITE_DBCONFIG_ENABLE_TRIGGER = 1003  # int int*
    cdef int SQLITE_DBCONFIG_ENABLE_FTS3_TOKENIZER = 1004  # int int*
    cdef int SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION = 1005  # int int*
    cdef int SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE = 1006  # int int*
    cdef int SQLITE_DBCONFIG_ENABLE_QPSG = 1007  # int int*

    cdef int sqlite3_config(int, ...)
    cdef int sqlite3_db_config(sqlite3*, int op, ...)

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
    cdef char *sqlite3_mprintf(const char *, ...)

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


cdef sqlite_to_python(int argc, sqlite3_value **params):
    cdef:
        int i
        int vtype
        list pyargs = []

    for i in range(argc):
        vtype = sqlite3_value_type(params[i])
        if vtype == SQLITE_INTEGER:
            pyval = sqlite3_value_int(params[i])
        elif vtype == SQLITE_FLOAT:
            pyval = sqlite3_value_double(params[i])
        elif vtype == SQLITE_TEXT:
            pyval = PyUnicode_DecodeUTF8(
                <const char *>sqlite3_value_text(params[i]),
                <Py_ssize_t>sqlite3_value_bytes(params[i]), NULL)
        elif vtype == SQLITE_BLOB:
            pyval = PyBytes_FromStringAndSize(
                <const char *>sqlite3_value_blob(params[i]),
                <Py_ssize_t>sqlite3_value_bytes(params[i]))
        elif vtype == SQLITE_NULL:
            pyval = None
        else:
            pyval = None

        pyargs.append(pyval)

    return pyargs


cdef python_to_sqlite(sqlite3_context *context, value):
    if value is None:
        sqlite3_result_null(context)
    elif isinstance(value, (int, long)):
        sqlite3_result_int64(context, <sqlite3_int64>value)
    elif isinstance(value, float):
        sqlite3_result_double(context, <double>value)
    elif isinstance(value, unicode):
        bval = PyUnicode_AsUTF8String(value)
        sqlite3_result_text(
            context,
            <const char *>bval,
            len(bval),
            <sqlite3_destructor_type>-1)
    elif isinstance(value, bytes):
        if PY_MAJOR_VERSION > 2:
            sqlite3_result_blob(
                context,
                <void *>(<char *>value),
                len(value),
                <sqlite3_destructor_type>-1)
        else:
            sqlite3_result_text(
                context,
                <const char *>value,
                len(value),
                <sqlite3_destructor_type>-1)
    else:
        sqlite3_result_error(
            context,
            encode('Unsupported type %s' % type(value)),
            -1)
        return SQLITE_ERROR

    return SQLITE_OK


cdef int SQLITE_CONSTRAINT = 19  # Abort due to constraint violation.

USE_SQLITE_CONSTRAINT = sqlite3_version[:4] >= b'3.26'

# The peewee_vtab struct embeds the base sqlite3_vtab struct, and adds a field
# to store a reference to the Python implementation.
ctypedef struct peewee_vtab:
    sqlite3_vtab base
    void *table_func_cls


# Like peewee_vtab, the peewee_cursor embeds the base sqlite3_vtab_cursor and
# adds fields to store references to the current index, the Python
# implementation, the current rows' data, and a flag for whether the cursor has
# been exhausted.
ctypedef struct peewee_cursor:
    sqlite3_vtab_cursor base
    long long idx
    void *table_func
    void *row_data
    bint stopped


# We define an xConnect function, but leave xCreate NULL so that the
# table-function can be called eponymously.
cdef int pwConnect(sqlite3 *db, void *pAux, int argc, const char *const*argv,
                   sqlite3_vtab **ppVtab, char **pzErr) with gil:
    cdef:
        int rc
        object table_func_cls = <object>pAux
        peewee_vtab *pNew = <peewee_vtab *>0

    rc = sqlite3_declare_vtab(
        db,
        encode('CREATE TABLE x(%s);' %
               table_func_cls.get_table_columns_declaration()))
    if rc == SQLITE_OK:
        pNew = <peewee_vtab *>sqlite3_malloc(sizeof(pNew[0]))
        memset(<char *>pNew, 0, sizeof(pNew[0]))
        ppVtab[0] = &(pNew.base)

        pNew.table_func_cls = <void *>table_func_cls
        Py_INCREF(table_func_cls)

    return rc


cdef int pwDisconnect(sqlite3_vtab *pBase) with gil:
    cdef:
        peewee_vtab *pVtab = <peewee_vtab *>pBase
        object table_func_cls = <object>(pVtab.table_func_cls)

    Py_DECREF(table_func_cls)
    sqlite3_free(pVtab)
    return SQLITE_OK


# The xOpen method is used to initialize a cursor. In this method we
# instantiate the TableFunction class and zero out a new cursor for iteration.
cdef int pwOpen(sqlite3_vtab *pBase, sqlite3_vtab_cursor **ppCursor) with gil:
    cdef:
        peewee_vtab *pVtab = <peewee_vtab *>pBase
        peewee_cursor *pCur = <peewee_cursor *>0
        object table_func_cls = <object>pVtab.table_func_cls

    pCur = <peewee_cursor *>sqlite3_malloc(sizeof(pCur[0]))
    memset(<char *>pCur, 0, sizeof(pCur[0]))
    ppCursor[0] = &(pCur.base)
    pCur.idx = 0
    try:
        table_func = table_func_cls()
    except:
        if table_func_cls.print_tracebacks:
            traceback.print_exc()
        sqlite3_free(pCur)
        return SQLITE_ERROR

    Py_INCREF(table_func)
    pCur.table_func = <void *>table_func
    pCur.stopped = False
    return SQLITE_OK


cdef int pwClose(sqlite3_vtab_cursor *pBase) with gil:
    cdef:
        peewee_cursor *pCur = <peewee_cursor *>pBase
        object table_func = <object>pCur.table_func
    Py_DECREF(table_func)
    sqlite3_free(pCur)
    return SQLITE_OK


# Iterate once, advancing the cursor's index and assigning the row data to the
# `row_data` field on the peewee_cursor struct.
cdef int pwNext(sqlite3_vtab_cursor *pBase) with gil:
    cdef:
        peewee_cursor *pCur = <peewee_cursor *>pBase
        object table_func = <object>pCur.table_func
        tuple result

    if pCur.row_data:
        Py_DECREF(<tuple>pCur.row_data)

    pCur.row_data = NULL
    try:
        result = tuple(table_func.iterate(pCur.idx))
    except StopIteration:
        pCur.stopped = True
    except:
        if table_func.print_tracebacks:
            traceback.print_exc()
        return SQLITE_ERROR
    else:
        Py_INCREF(result)
        pCur.row_data = <void *>result
        pCur.idx += 1
        pCur.stopped = False

    return SQLITE_OK


# Return the requested column from the current row.
cdef int pwColumn(sqlite3_vtab_cursor *pBase, sqlite3_context *ctx,
                  int iCol) with gil:
    cdef:
        bytes bval
        peewee_cursor *pCur = <peewee_cursor *>pBase
        sqlite3_int64 x = 0
        tuple row_data

    if iCol == -1:
        sqlite3_result_int64(ctx, <sqlite3_int64>pCur.idx)
        return SQLITE_OK

    if not pCur.row_data:
        sqlite3_result_error(ctx, encode('no row data'), -1)
        return SQLITE_ERROR

    row_data = <tuple>pCur.row_data
    return python_to_sqlite(ctx, row_data[iCol])


cdef int pwRowid(sqlite3_vtab_cursor *pBase, sqlite3_int64 *pRowid):
    cdef:
        peewee_cursor *pCur = <peewee_cursor *>pBase
    pRowid[0] = <sqlite3_int64>pCur.idx
    return SQLITE_OK


# Return a boolean indicating whether the cursor has been consumed.
cdef int pwEof(sqlite3_vtab_cursor *pBase):
    cdef:
        peewee_cursor *pCur = <peewee_cursor *>pBase
    return 1 if pCur.stopped else 0


# The filter method is called on the first iteration. This method is where we
# get access to the parameters that the function was called with, and call the
# TableFunction's `initialize()` function.
cdef int pwFilter(sqlite3_vtab_cursor *pBase, int idxNum,
                  const char *idxStr, int argc, sqlite3_value **argv) with gil:
    cdef:
        peewee_cursor *pCur = <peewee_cursor *>pBase
        object table_func = <object>pCur.table_func
        dict query = {}
        int idx
        int value_type
        tuple row_data
        void *row_data_raw

    if not idxStr or argc == 0 and len(table_func.params):
        return SQLITE_ERROR
    elif len(idxStr):
        params = decode(idxStr).split(',')
    else:
        params = []

    py_values = sqlite_to_python(argc, argv)

    for idx, param in enumerate(params):
        value = argv[idx]
        if not value:
            query[param] = None
        else:
            query[param] = py_values[idx]

    try:
        table_func.initialize(**query)
    except:
        if table_func.print_tracebacks:
            traceback.print_exc()
        return SQLITE_ERROR

    pCur.stopped = False
    try:
        row_data = tuple(table_func.iterate(0))
    except StopIteration:
        pCur.stopped = True
    except:
        if table_func.print_tracebacks:
            traceback.print_exc()
        return SQLITE_ERROR
    else:
        Py_INCREF(row_data)
        pCur.row_data = <void *>row_data
        pCur.idx += 1
    return SQLITE_OK


# SQLite will (in some cases, repeatedly) call the xBestIndex method to try and
# find the best query plan.
cdef int pwBestIndex(sqlite3_vtab *pBase, sqlite3_index_info *pIdxInfo) \
        with gil:
    cdef:
        int i
        int col_idx
        int idxNum = 0, nArg = 0
        peewee_vtab *pVtab = <peewee_vtab *>pBase
        object table_func_cls = <object>pVtab.table_func_cls
        sqlite3_index_constraint *pConstraint = <sqlite3_index_constraint *>0
        list columns = []
        char *idxStr
        int nParams = len(table_func_cls.params)

    for i in range(pIdxInfo.nConstraint):
        pConstraint = <sqlite3_index_constraint *>pIdxInfo.aConstraint + i
        if not pConstraint.usable:
            continue
        if pConstraint.op != SQLITE_INDEX_CONSTRAINT_EQ:
            continue

        col_idx = pConstraint.iColumn - table_func_cls._ncols
        if col_idx >= 0:
            columns.append(table_func_cls.params[col_idx])
            nArg += 1
            pIdxInfo.aConstraintUsage[i].argvIndex = nArg
            pIdxInfo.aConstraintUsage[i].omit = 1

    if nArg > 0 or nParams == 0:
        if nArg == nParams:
            # All parameters are present, this is ideal.
            pIdxInfo.estimatedCost = <double>1
            pIdxInfo.estimatedRows = 10
        else:
            # Penalize score based on number of missing params.
            pIdxInfo.estimatedCost = <double>10000000000000 * <double>(nParams - nArg)
            pIdxInfo.estimatedRows = 10 ** (nParams - nArg)

        # Store a reference to the columns in the index info structure.
        joinedCols = encode(','.join(columns))
        pIdxInfo.idxStr = sqlite3_mprintf("%s", <char *>joinedCols)
        pIdxInfo.needToFreeIdxStr = 1
    elif USE_SQLITE_CONSTRAINT:
        return SQLITE_CONSTRAINT
    else:
        pIdxInfo.estimatedCost = DBL_MAX
        pIdxInfo.estimatedRows = 100000
    return SQLITE_OK


cdef class _TableFunctionImpl(object):
    cdef:
        sqlite3_module module
        object table_function

    def __cinit__(self, table_function):
        self.table_function = table_function

    cdef create_module(self, pysqlite_Connection* sqlite_conn):
        cdef:
            bytes name = encode(self.table_function.name)
            sqlite3 *db = sqlite_conn.db
            int rc

        # Populate the SQLite module struct members.
        self.module.iVersion = 0
        self.module.xCreate = NULL
        self.module.xConnect = pwConnect
        self.module.xBestIndex = pwBestIndex
        self.module.xDisconnect = pwDisconnect
        self.module.xDestroy = NULL
        self.module.xOpen = pwOpen
        self.module.xClose = pwClose
        self.module.xFilter = pwFilter
        self.module.xNext = pwNext
        self.module.xEof = pwEof
        self.module.xColumn = pwColumn
        self.module.xRowid = pwRowid
        self.module.xUpdate = NULL
        self.module.xBegin = NULL
        self.module.xSync = NULL
        self.module.xCommit = NULL
        self.module.xRollback = NULL
        self.module.xFindFunction = NULL
        self.module.xRename = NULL

        # Create the SQLite virtual table.
        rc = sqlite3_create_module(
            db,
            <const char *>name,
            &self.module,
            <void *>(self.table_function))

        Py_INCREF(self)

        return rc == SQLITE_OK


class TableFunction(object):
    columns = None
    params = None
    name = None
    print_tracebacks = True
    _ncols = None

    @classmethod
    def register(cls, conn):
        cdef _TableFunctionImpl impl = _TableFunctionImpl(cls)
        impl.create_module(<pysqlite_Connection *>conn)
        cls._ncols = len(cls.columns)

    def initialize(self, **filters):
        raise NotImplementedError

    def iterate(self, idx):
        raise NotImplementedError

    @classmethod
    def get_table_columns_declaration(cls):
        cdef list accum = []

        for column in cls.columns:
            if isinstance(column, tuple):
                if len(column) != 2:
                    raise ValueError('Column must be either a string or a '
                                     '2-tuple of name, type')
                accum.append('%s %s' % column)
            else:
                accum.append(column)

        for param in cls.params:
            accum.append('%s HIDDEN' % param)

        return ', '.join(accum)


cdef inline bytes encode(key):
    cdef bytes bkey
    if PyUnicode_Check(key):
        bkey = PyUnicode_AsUTF8String(key)
    elif PyBytes_Check(key):
        bkey = <bytes>key
    elif key is None:
        return None
    else:
        bkey = PyUnicode_AsUTF8String(str(key))
    return bkey


cdef inline unicode decode(key):
    cdef unicode ukey
    if PyBytes_Check(key):
        ukey = key.decode('utf-8')
    elif PyUnicode_Check(key):
        ukey = <unicode>key
    elif key is None:
        return None
    else:
        ukey = unicode(key)
    return ukey


cdef double *get_weights(int ncol, tuple raw_weights):
    cdef:
        int argc = len(raw_weights)
        int icol
        double *weights = <double *>malloc(sizeof(double) * ncol)

    for icol in range(ncol):
        if argc == 0:
            weights[icol] = 1.0
        elif icol < argc:
            weights[icol] = <double>raw_weights[icol]
        else:
            weights[icol] = 0.0
    return weights


def peewee_rank(py_match_info, *raw_weights):
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int nphrase, ncol, icol, iphrase, hits, global_hits
        int P_O = 0, C_O = 1, X_O = 2
        double score = 0.0, weight
        double *weights

    match_info = <unsigned int *>match_info_buf
    nphrase = match_info[P_O]
    ncol = match_info[C_O]
    weights = get_weights(ncol, raw_weights)

    # matchinfo X value corresponds to, for each phrase in the search query, a
    # list of 3 values for each column in the search table.
    # So if we have a two-phrase search query and three columns of data, the
    # following would be the layout:
    # p0 : c0=[0, 1, 2],   c1=[3, 4, 5],    c2=[6, 7, 8]
    # p1 : c0=[9, 10, 11], c1=[12, 13, 14], c2=[15, 16, 17]
    for iphrase in range(nphrase):
        phrase_info = &match_info[X_O + iphrase * ncol * 3]
        for icol in range(ncol):
            weight = weights[icol]
            if weight == 0:
                continue

            # The idea is that we count the number of times the phrase appears
            # in this column of the current row, compared to how many times it
            # appears in this column across all rows. The ratio of these values
            # provides a rough way to score based on "high value" terms.
            hits = phrase_info[3 * icol]
            global_hits = phrase_info[3 * icol + 1]
            if hits > 0:
                score += weight * (<double>hits / <double>global_hits)

    free(weights)
    return -1 * score


def peewee_lucene(py_match_info, *raw_weights):
    # Usage: peewee_lucene(matchinfo(table, 'pcnalx'), 1)
    cdef:
        unsigned int *match_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int nphrase, ncol
        double total_docs, term_frequency
        double doc_length, docs_with_term, avg_length
        double idf, weight, rhs, denom
        double *weights
        int P_O = 0, C_O = 1, N_O = 2, L_O, X_O
        int iphrase, icol, x
        double score = 0.0

    match_info = <unsigned int *>match_info_buf
    nphrase = match_info[P_O]
    ncol = match_info[C_O]
    total_docs = match_info[N_O]

    L_O = 3 + ncol
    X_O = L_O + ncol
    weights = get_weights(ncol, raw_weights)

    for iphrase in range(nphrase):
        for icol in range(ncol):
            weight = weights[icol]
            if weight == 0:
                continue
            doc_length = match_info[L_O + icol]
            x = X_O + (3 * (icol + iphrase * ncol))
            term_frequency = match_info[x]  # f(qi)
            docs_with_term = match_info[x + 2] or 1. # n(qi)
            idf = log(total_docs / (docs_with_term + 1.))
            tf = sqrt(term_frequency)
            fieldNorms = 1.0 / sqrt(doc_length)
            score += (idf * tf * fieldNorms)

    free(weights)
    return -1 * score


def peewee_bm25(py_match_info, *raw_weights):
    # Usage: peewee_bm25(matchinfo(table, 'pcnalx'), 1)
    # where the second parameter is the index of the column and
    # the 3rd and 4th specify k and b.
    cdef:
        unsigned int *match_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int nphrase, ncol
        double B = 0.75, K = 1.2
        double total_docs, term_frequency
        double doc_length, docs_with_term, avg_length
        double idf, weight, ratio, num, b_part, denom, pc_score
        double *weights
        int P_O = 0, C_O = 1, N_O = 2, A_O = 3, L_O, X_O
        int iphrase, icol, x
        double score = 0.0

    match_info = <unsigned int *>match_info_buf
    # PCNALX = matchinfo format.
    # P = 1 = phrase count within query.
    # C = 1 = searchable columns in table.
    # N = 1 = total rows in table.
    # A = c = for each column, avg number of tokens
    # L = c = for each column, length of current row (in tokens)
    # X = 3 * c * p = for each phrase and table column,
    # * phrase count within column for current row.
    # * phrase count within column for all rows.
    # * total rows for which column contains phrase.
    nphrase = match_info[P_O]  # n
    ncol = match_info[C_O]
    total_docs = match_info[N_O]  # N

    L_O = A_O + ncol
    X_O = L_O + ncol
    weights = get_weights(ncol, raw_weights)

    for iphrase in range(nphrase):
        for icol in range(ncol):
            weight = weights[icol]
            if weight == 0:
                continue

            x = X_O + (3 * (icol + iphrase * ncol))
            term_frequency = match_info[x]  # f(qi, D)
            docs_with_term = match_info[x + 2]  # n(qi)

            # log( (N - n(qi) + 0.5) / (n(qi) + 0.5) )
            idf = log(
                    (total_docs - docs_with_term + 0.5) /
                    (docs_with_term + 0.5))
            if idf <= 0.0:
                idf = 1e-6

            doc_length = match_info[L_O + icol]  # |D|
            avg_length = match_info[A_O + icol]  # avgdl
            if avg_length == 0:
                avg_length = 1
            ratio = doc_length / avg_length

            num = term_frequency * (K + 1)
            b_part = 1 - B + (B * ratio)
            denom = term_frequency + (K * b_part)

            pc_score = idf * (num / denom)
            score += (pc_score * weight)

    free(weights)
    return -1 * score


def peewee_bm25f(py_match_info, *raw_weights):
    # Usage: peewee_bm25f(matchinfo(table, 'pcnalx'), 1)
    # where the second parameter is the index of the column and
    # the 3rd and 4th specify k and b.
    cdef:
        unsigned int *match_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int nphrase, ncol
        double B = 0.75, K = 1.2, epsilon
        double total_docs, term_frequency, docs_with_term
        double doc_length = 0.0, avg_length = 0.0
        double idf, weight, ratio, num, b_part, denom, pc_score
        double *weights
        int P_O = 0, C_O = 1, N_O = 2, A_O = 3, L_O, X_O
        int iphrase, icol, x
        double score = 0.0

    match_info = <unsigned int *>match_info_buf
    nphrase = match_info[P_O]  # n
    ncol = match_info[C_O]
    total_docs = match_info[N_O]  # N

    L_O = A_O + ncol
    X_O = L_O + ncol

    for icol in range(ncol):
        avg_length += match_info[A_O + icol]
        doc_length += match_info[L_O + icol]

    epsilon = 1.0 / (total_docs * avg_length)
    if avg_length == 0:
        avg_length = 1
    ratio = doc_length / avg_length
    weights = get_weights(ncol, raw_weights)

    for iphrase in range(nphrase):
        for icol in range(ncol):
            weight = weights[icol]
            if weight == 0:
                continue

            x = X_O + (3 * (icol + iphrase * ncol))
            term_frequency = match_info[x]  # f(qi, D)
            docs_with_term = match_info[x + 2]  # n(qi)

            # log( (N - n(qi) + 0.5) / (n(qi) + 0.5) )
            idf = log(
                (total_docs - docs_with_term + 0.5) /
                (docs_with_term + 0.5))
            idf = epsilon if idf <= 0 else idf

            num = term_frequency * (K + 1)
            b_part = 1 - B + (B * ratio)
            denom = term_frequency + (K * b_part)

            pc_score = idf * ((num / denom) + 1.)
            score += (pc_score * weight)

    free(weights)
    return -1 * score


cdef uint32_t murmurhash2(const unsigned char *key, ssize_t nlen,
                          uint32_t seed):
    cdef:
        uint32_t m = 0x5bd1e995
        int r = 24
        const unsigned char *data = key
        uint32_t h = seed ^ nlen
        uint32_t k

    while nlen >= 4:
        k = <uint32_t>((<uint32_t *>data)[0])

        k *= m
        k = k ^ (k >> r)
        k *= m

        h *= m
        h = h ^ k

        data += 4
        nlen -= 4

    if nlen == 3:
        h = h ^ (data[2] << 16)
    if nlen >= 2:
        h = h ^ (data[1] << 8)
    if nlen >= 1:
        h = h ^ (data[0])
        h *= m

    h = h ^ (h >> 13)
    h *= m
    h = h ^ (h >> 15)
    return h


def peewee_murmurhash(key, seed=None):
    if key is None:
        return

    cdef:
        bytes bkey = encode(key)
        int nseed = seed or 0

    if key:
        return murmurhash2(<unsigned char *>bkey, len(bkey), nseed)
    return 0


def make_hash(hash_impl):
    def inner(*items):
        state = hash_impl()
        for item in items:
            state.update(encode(item))
        return state.hexdigest()
    return inner


peewee_md5 = make_hash(hashlib.md5)
peewee_sha1 = make_hash(hashlib.sha1)
peewee_sha256 = make_hash(hashlib.sha256)


def _register_functions(database, pairs):
    for func, name in pairs:
        database.register_function(func, name)


def register_hash_functions(database):
    _register_functions(database, (
        (peewee_murmurhash, 'murmurhash'),
        (peewee_md5, 'md5'),
        (peewee_sha1, 'sha1'),
        (peewee_sha256, 'sha256'),
        (zlib.adler32, 'adler32'),
        (zlib.crc32, 'crc32')))


def register_rank_functions(database):
    _register_functions(database, (
        (peewee_bm25, 'fts_bm25'),
        (peewee_bm25f, 'fts_bm25f'),
        (peewee_lucene, 'fts_lucene'),
        (peewee_rank, 'fts_rank')))


ctypedef struct bf_t:
    void *bits
    size_t size

cdef int seeds[10]
seeds[:] = [0, 1337, 37, 0xabcd, 0xdead, 0xface, 97, 0xed11, 0xcad9, 0x827b]


cdef bf_t *bf_create(size_t size):
    cdef bf_t *bf = <bf_t *>calloc(1, sizeof(bf_t))
    bf.size = size
    bf.bits = calloc(1, size)
    return bf

@cython.cdivision(True)
cdef uint32_t bf_bitindex(bf_t *bf, unsigned char *key, size_t klen, int seed):
    cdef:
        uint32_t h = murmurhash2(key, klen, seed)
    return h % (bf.size * 8)

@cython.cdivision(True)
cdef bf_add(bf_t *bf, unsigned char *key):
    cdef:
        uint8_t *bits = <uint8_t *>(bf.bits)
        uint32_t h
        int pos, seed
        size_t keylen = strlen(<const char *>key)

    for seed in seeds:
        h = bf_bitindex(bf, key, keylen, seed)
        pos = h / 8
        bits[pos] = bits[pos] | (1 << (h % 8))

@cython.cdivision(True)
cdef int bf_contains(bf_t *bf, unsigned char *key):
    cdef:
        uint8_t *bits = <uint8_t *>(bf.bits)
        uint32_t h
        int pos, seed
        size_t keylen = strlen(<const char *>key)

    for seed in seeds:
        h = bf_bitindex(bf, key, keylen, seed)
        pos = h / 8
        if not (bits[pos] & (1 << (h % 8))):
            return 0
    return 1

cdef bf_free(bf_t *bf):
    free(bf.bits)
    free(bf)


cdef class BloomFilter(object):
    cdef:
        bf_t *bf

    def __init__(self, size=1024 * 32):
        self.bf = bf_create(<size_t>size)

    def __dealloc__(self):
        if self.bf:
            bf_free(self.bf)

    def __len__(self):
        return self.bf.size

    def add(self, *keys):
        cdef bytes bkey

        for key in keys:
            bkey = encode(key)
            bf_add(self.bf, <unsigned char *>bkey)

    def __contains__(self, key):
        cdef bytes bkey = encode(key)
        return bf_contains(self.bf, <unsigned char *>bkey)

    def to_buffer(self):
        # We have to do this so that embedded NULL bytes are preserved.
        cdef bytes buf = PyBytes_FromStringAndSize(<char *>(self.bf.bits),
                                                   self.bf.size)
        # Similarly we wrap in a buffer object so pysqlite preserves the
        # embedded NULL bytes.
        return buf

    @classmethod
    def from_buffer(cls, data):
        cdef:
            char *buf
            Py_ssize_t buflen
            BloomFilter bloom

        PyBytes_AsStringAndSize(data, &buf, &buflen)

        bloom = BloomFilter(buflen)
        memcpy(bloom.bf.bits, <void *>buf, buflen)
        return bloom

    @classmethod
    def calculate_size(cls, double n, double p):
        cdef double m = ceil((n * log(p)) / log(1.0 / (pow(2.0, log(2.0)))))
        return m


cdef class BloomFilterAggregate(object):
    cdef:
        BloomFilter bf

    def __init__(self):
        self.bf = None

    def step(self, value, size=None):
        if not self.bf:
            size = size or 1024
            self.bf = BloomFilter(size)

        self.bf.add(value)

    def finalize(self):
        if not self.bf:
            return None

        return pysqlite.Binary(self.bf.to_buffer())


def peewee_bloomfilter_contains(key, data):
    cdef:
        bf_t bf
        bytes bkey
        bytes bdata = bytes(data)
        unsigned char *cdata = <unsigned char *>bdata

    bf.size = len(data)
    bf.bits = <void *>cdata
    bkey = encode(key)

    return bf_contains(&bf, <unsigned char *>bkey)


def peewee_bloomfilter_calculate_size(n_items, error_p):
    return BloomFilter.calculate_size(n_items, error_p)


def register_bloomfilter(database):
    database.register_aggregate(BloomFilterAggregate, 'bloomfilter')
    database.register_function(peewee_bloomfilter_contains,
                               'bloomfilter_contains')
    database.register_function(peewee_bloomfilter_calculate_size,
                               'bloomfilter_calculate_size')


cdef inline int _check_connection(pysqlite_Connection *conn) except -1:
    """
    Check that the underlying SQLite database connection is usable. Raises an
    InterfaceError if the connection is either uninitialized or closed.
    """
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
            bytes btable = encode(table)
            bytes bcolumn = encode(column)
            int flags = 0 if read_only else 1
            int rc
            sqlite3_blob *blob

        self.conn = <pysqlite_Connection *>(database._state.conn)
        _check_connection(self.conn)

        rc = sqlite3_blob_open(
            self.conn.db,
            'main',
            <char *>btable,
            <char *>bcolumn,
            <long long>rowid,
            flags,
            &blob)
        if rc != SQLITE_OK:
            raise OperationalError('Unable to open blob.')
        if not blob:
            raise MemoryError('Unable to allocate blob.')

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
            return b''

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

    def write(self, bytes data):
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


def sqlite_get_status(flag):
    cdef:
        int current, highwater, rc

    rc = sqlite3_status(flag, &current, &highwater, 0)
    if rc == SQLITE_OK:
        return (current, highwater)
    raise Exception('Error requesting status: %s' % rc)


def sqlite_get_db_status(conn, flag):
    cdef:
        int current, highwater, rc
        pysqlite_Connection *c_conn = <pysqlite_Connection *>conn

    if not c_conn.db:
        return (None, None)

    rc = sqlite3_db_status(c_conn.db, flag, &current, &highwater, 0)
    if rc == SQLITE_OK:
        return (current, highwater)
    raise Exception('Error requesting db status: %s' % rc)


cdef class ConnectionHelper(object):
    cdef:
        object _commit_hook, _rollback_hook, _update_hook
        pysqlite_Connection *conn

    def __init__(self, connection):
        self.conn = <pysqlite_Connection *>connection
        self._commit_hook = self._rollback_hook = self._update_hook = None

    def __dealloc__(self):
        # When deallocating a Database object, we need to ensure that we clear
        # any commit, rollback or update hooks that may have been applied.
        if not self.conn.initialized or not self.conn.db:
            return

        if self._commit_hook is not None:
            sqlite3_commit_hook(self.conn.db, NULL, NULL)
        if self._rollback_hook is not None:
            sqlite3_rollback_hook(self.conn.db, NULL, NULL)
        if self._update_hook is not None:
            sqlite3_update_hook(self.conn.db, NULL, NULL)

    def set_commit_hook(self, fn):
        if not self.conn.initialized or not self.conn.db:
            return

        self._commit_hook = fn
        if fn is None:
            sqlite3_commit_hook(self.conn.db, NULL, NULL)
        else:
            sqlite3_commit_hook(self.conn.db, _commit_callback, <void *>fn)

    def set_rollback_hook(self, fn):
        if not self.conn.initialized or not self.conn.db:
            return

        self._rollback_hook = fn
        if fn is None:
            sqlite3_rollback_hook(self.conn.db, NULL, NULL)
        else:
            sqlite3_rollback_hook(self.conn.db, _rollback_callback, <void *>fn)

    def set_update_hook(self, fn):
        if not self.conn.initialized or not self.conn.db:
            return

        self._update_hook = fn
        if fn is None:
            sqlite3_update_hook(self.conn.db, NULL, NULL)
        else:
            sqlite3_update_hook(self.conn.db, _update_callback, <void *>fn)

    def set_busy_handler(self, timeout=5):
        """
        Replace the default busy handler with one that introduces some "jitter"
        into the amount of time delayed between checks.
        """
        if not self.conn.initialized or not self.conn.db:
            return False

        cdef sqlite3_int64 n = timeout * 1000
        sqlite3_busy_handler(self.conn.db, _aggressive_busy_handler, <void *>n)
        return True

    def changes(self):
        if self.conn.initialized and self.conn.db:
            return sqlite3_changes(self.conn.db)

    def last_insert_rowid(self):
        if self.conn.initialized and self.conn.db:
            return <int>sqlite3_last_insert_rowid(self.conn.db)

    def autocommit(self):
        if self.conn.initialized and self.conn.db:
            return sqlite3_get_autocommit(self.conn.db) != 0


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


cdef void _update_callback(void *userData, int queryType, const char *database,
                           const char *table, sqlite3_int64 rowid) with gil:
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
    fn(query, decode(database), decode(table), <int>rowid)


def backup(src_conn, dest_conn, pages=None, name=None, progress=None):
    cdef:
        bytes bname = encode(name or 'main')
        int page_step = pages or -1
        int rc
        pysqlite_Connection *src = <pysqlite_Connection *>src_conn
        pysqlite_Connection *dest = <pysqlite_Connection *>dest_conn
        sqlite3 *src_db = src.db
        sqlite3 *dest_db = dest.db
        sqlite3_backup *backup

    if not src_db or not dest_db:
        raise OperationalError('cannot backup to or from a closed database')

    # We always backup to the "main" database in the dest db.
    backup = sqlite3_backup_init(dest_db, b'main', src_db, bname)
    if backup == NULL:
        raise OperationalError('Unable to initialize backup.')

    while True:
        with nogil:
            rc = sqlite3_backup_step(backup, page_step)
        if progress is not None:
            # Progress-handler is called with (remaining, page count, is done?)
            remaining = sqlite3_backup_remaining(backup)
            page_count = sqlite3_backup_pagecount(backup)
            try:
                progress(remaining, page_count, rc == SQLITE_DONE)
            except:
                sqlite3_backup_finish(backup)
                raise
        if rc == SQLITE_BUSY or rc == SQLITE_LOCKED:
            with nogil:
                sqlite3_sleep(250)
        elif rc == SQLITE_DONE:
            break

    with nogil:
        sqlite3_backup_finish(backup)
    if sqlite3_errcode(dest_db):
        raise OperationalError('Error backuping up database: %s' %
                               sqlite3_errmsg(dest_db))
    return True


def backup_to_file(src_conn, filename, pages=None, name=None, progress=None):
    dest_conn = pysqlite.connect(filename)
    backup(src_conn, dest_conn, pages=pages, name=name, progress=progress)
    dest_conn.close()
    return True


cdef int _aggressive_busy_handler(void *ptr, int n) nogil:
    # In concurrent environments, it often seems that if multiple queries are
    # kicked off at around the same time, they proceed in lock-step to check
    # for the availability of the lock. By introducing some "jitter" we can
    # ensure that this doesn't happen. Furthermore, this function makes more
    # attempts in the same time period than the default handler.
    cdef:
        sqlite3_int64 busyTimeout = <sqlite3_int64>ptr
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
