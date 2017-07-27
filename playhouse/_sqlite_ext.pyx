import hashlib
import zlib
from random import randint

from cpython cimport datetime
from cpython.mem cimport PyMem_Free
from cpython.object cimport PyObject
from cpython.ref cimport Py_INCREF, Py_DECREF
from libc.float cimport DBL_MAX
from libc.math cimport log, sqrt
from libc.stdlib cimport free, malloc
from libc.string cimport memcpy, memset

from peewee import InterfaceError


cdef struct sqlite3_index_constraint:
    int iColumn
    unsigned char op
    unsigned char usable
    int iTermOffset


cdef struct sqlite3_index_orderby:
    int iColumn
    unsigned char desc


cdef struct sqlite3_index_constraint_usage:
    int argvIndex
    unsigned char omit


cdef extern from "sqlite3.h":
    ctypedef struct sqlite3:
        int busyTimeout
    ctypedef struct sqlite3_context
    ctypedef struct sqlite3_value
    ctypedef long long sqlite3_int64

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
        int (*xCreate)(sqlite3*, void *pAux, int argc, char **argv,
                       sqlite3_vtab **ppVTab, char**)
        int (*xConnect)(sqlite3*, void *pAux, int argc, char **argv,
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

    # Encoding.
    cdef int SQLITE_UTF8 = 1

    # Return values.
    cdef int SQLITE_OK = 0
    cdef int SQLITE_ERROR = 1
    cdef int SQLITE_NOMEM = 7

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


cdef extern from "_pysqlite/connection.h":
    ctypedef struct pysqlite_Connection:
        sqlite3* db
        double timeout
        int initialized
        PyObject* isolation_level
        char* begin_statement


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
cdef int pwConnect(sqlite3 *db, void *pAux, int argc, char **argv,
                   sqlite3_vtab **ppVtab, char **pzErr) with gil:
    cdef:
        int rc
        object table_func_cls = <object>pAux
        peewee_vtab *pNew

    rc = sqlite3_declare_vtab(
        db,
        'CREATE TABLE x(%s);' % table_func_cls.get_table_columns_declaration())
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
        peewee_cursor *pCur
        object table_func_cls = <object>pVtab.table_func_cls

    pCur = <peewee_cursor *>sqlite3_malloc(sizeof(pCur[0]))
    memset(<char *>pCur, 0, sizeof(pCur[0]))
    ppCursor[0] = &(pCur.base)
    pCur.idx = 0
    table_func = table_func_cls()
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

    try:
        result = table_func.iterate(pCur.idx)
    except StopIteration:
        pCur.stopped = True
    except:
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
        peewee_cursor *pCur = <peewee_cursor *>pBase
        sqlite3_int64 x = 0
        tuple row_data

    if iCol == -1:
        sqlite3_result_int64(ctx, <sqlite3_int64>pCur.idx)
        return SQLITE_OK

    row_data = <tuple>pCur.row_data
    value = row_data[iCol]
    if value is None:
        sqlite3_result_null(ctx)
    elif isinstance(value, (int, long)):
        sqlite3_result_int64(ctx, <sqlite3_int64>value)
    elif isinstance(value, float):
        sqlite3_result_double(ctx, <double>value)
    elif isinstance(value, basestring):
        sqlite3_result_text(
            ctx,
            <const char *>value,
            -1,
            <sqlite3_destructor_type>-1)
    elif isinstance(value, bool):
        sqlite3_result_int(ctx, int(value))
    else:
        sqlite3_result_error(ctx, 'Unsupported type %s' % type(value), -1)
        return SQLITE_ERROR

    return SQLITE_OK


cdef int pwRowid(sqlite3_vtab_cursor *pBase, sqlite3_int64 *pRowid):
    cdef:
        peewee_cursor *pCur = <peewee_cursor *>pBase
    pRowid[0] = <sqlite3_int64>pCur.idx
    return SQLITE_OK


# Return a boolean indicating whether the cursor has been consumed.
cdef int pwEof(sqlite3_vtab_cursor *pBase):
    cdef:
        peewee_cursor *pCur = <peewee_cursor *>pBase
    if pCur.stopped:
        return 1
    return 0


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
    elif idxStr:
        params = str(idxStr).split(',')
    else:
        params = []

    for idx, param in enumerate(params):
        value = argv[idx]
        if not value:
            query[param] = None
            continue

        value_type = sqlite3_value_type(value)
        if value_type == SQLITE_INTEGER:
            query[param] = sqlite3_value_int(value)
        elif value_type == SQLITE_FLOAT:
            query[param] = sqlite3_value_double(value)
        elif value_type == SQLITE_TEXT:
            query[param] = str(sqlite3_value_text(value))
        elif value_type == SQLITE_BLOB:
            query[param] = <bytes>sqlite3_value_blob(value)
        elif value_type == SQLITE_NULL:
            query[param] = None
        else:
            query[param] = None

    table_func.initialize(**query)
    pCur.stopped = False
    try:
        row_data = table_func.iterate(0)
    except StopIteration:
        pCur.stopped = True
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
        int idxNum = 0, nArg = 0
        peewee_vtab *pVtab = <peewee_vtab *>pBase
        object table_func_cls = <object>pVtab.table_func_cls
        sqlite3_index_constraint *pConstraint
        list columns = []
        char *idxStr
        int nParams = len(table_func_cls.params)

    pConstraint = <sqlite3_index_constraint*>0
    for i in range(pIdxInfo.nConstraint):
        pConstraint = &pIdxInfo.aConstraint[i]
        if not pConstraint.usable:
            continue
        if pConstraint.op != SQLITE_INDEX_CONSTRAINT_EQ:
            continue

        columns.append(table_func_cls.params[pConstraint.iColumn -
                                             table_func_cls._ncols])
        nArg += 1
        pIdxInfo.aConstraintUsage[i].argvIndex = nArg
        pIdxInfo.aConstraintUsage[i].omit = 1

    if nArg > 0:
        if nArg == nParams:
            # All parameters are present, this is ideal.
            pIdxInfo.estimatedCost = <double>1
            pIdxInfo.estimatedRows = 10
        else:
            # Penalize score based on number of missing params.
            pIdxInfo.estimatedCost = <double>10000000000000 * <double>(nParams - nArg)
            pIdxInfo.estimatedRows = 10 ** (nParams - nArg)

        # Store a reference to the columns in the index info structure.
        joinedCols = ','.join(columns)
        idxStr = <char *>sqlite3_malloc((len(joinedCols) + 1) * sizeof(char))
        memcpy(idxStr, <char *>joinedCols, len(joinedCols))
        idxStr[len(joinedCols)] = '\x00'
        pIdxInfo.idxStr = idxStr
        pIdxInfo.needToFreeIdxStr = 0
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

    def __dealloc__(self):
        Py_DECREF(self)

    cdef create_module(self, pysqlite_Connection* sqlite_conn):
        cdef:
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
            <const char *>self.table_function.name,
            &self.module,
            <void *>(self.table_function))

        Py_INCREF(self)

        return rc == SQLITE_OK


class TableFunction(object):
    columns = None
    params = None
    name = None
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


cdef tuple SQLITE_DATETIME_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d',
    '%H:%M:%S',
    '%H:%M:%S.%f',
    '%H:%M')

cdef dict SQLITE_DATE_TRUNC_MAPPING = {
    'year': '%Y',
    'month': '%Y-%m',
    'day': '%Y-%m-%d',
    'hour': '%Y-%m-%d %H',
    'minute': '%Y-%m-%d %H:%M',
    'second': '%Y-%m-%d %H:%M:%S'}


cdef tuple validate_and_format_datetime(lookup, date_str):
    if not date_str or not lookup:
        return

    lookup = lookup.lower()
    if lookup not in SQLITE_DATE_TRUNC_MAPPING:
        return

    cdef datetime.datetime date_obj
    cdef bint success = False

    for date_format in SQLITE_DATETIME_FORMATS:
        try:
            date_obj = datetime.datetime.strptime(date_str, date_format)
        except ValueError:
            pass
        else:
            return (date_obj, lookup)


def peewee_rank(py_match_info, *raw_weights):
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int argc = len(raw_weights)
        int ncol, nphrase, icol, iphrase, hits, global_hits
        int P_O = 0, C_O = 1, X_O = 2
        double score = 0.0, weight
        double *weights

    match_info = <unsigned int *>match_info_buf
    nphrase = match_info[P_O]
    ncol = match_info[C_O]

    weights = <double *>malloc(sizeof(double) * ncol)
    for icol in range(ncol):
        if icol < argc:
            weights[icol] = <double>raw_weights[icol]
        else:
            weights[icol] = 1.0

    for iphrase in range(nphrase):
        phrase_info = &match_info[X_O + iphrase * ncol * 3]
        for icol in range(ncol):
            weight = weights[icol]
            if weight == 0:
                continue
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
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int argc = len(raw_weights)
        int term_count, col_count
        double total_docs, term_frequency,
        double doc_length, docs_with_term, avg_length
        double idf, weight, rhs, denom
        double *weights
        int P_O = 0, C_O = 1, N_O = 2, L_O, X_O
        int i, j, x

        double score = 0.0

    match_info = <unsigned int *>match_info_buf
    term_count = match_info[P_O]
    col_count = match_info[C_O]
    total_docs = match_info[N_O]

    L_O = 3 + col_count
    X_O = L_O + col_count

    weights = <double *>malloc(sizeof(double) * col_count)
    for i in range(col_count):
        if argc == 0:
            weights[i] = 1.
        elif i < argc:
            weights[i] = <double>raw_weights[i]
        else:
            weights[i] = 0

    for i in range(term_count):
        for j in range(col_count):
            weight = weights[j]
            if weight == 0:
                continue
            doc_length = match_info[L_O + j]
            x = X_O + (3 * j * (i + 1))
            term_frequency = match_info[x]
            docs_with_term = match_info[x + 2]
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
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int argc = len(raw_weights)
        int term_count, col_count
        double B = 0.75, K = 1.2, D
        double total_docs, term_frequency,
        double doc_length, docs_with_term, avg_length
        double idf, weight, rhs, denom
        double *weights
        int P_O = 0, C_O = 1, N_O = 2, A_O = 3, L_O, X_O
        int i, j, x

        double score = 0.0

    match_info = <unsigned int *>match_info_buf
    term_count = match_info[P_O]
    col_count = match_info[C_O]
    total_docs = match_info[N_O]

    L_O = A_O + col_count
    X_O = L_O + col_count

    weights = <double *>malloc(sizeof(double) * col_count)
    for i in range(col_count):
        if argc == 0:
            weights[i] = 1.
        elif i < argc:
            weights[i] = <double>raw_weights[i]
        else:
            weights[i] = 0

    for i in range(term_count):
        for j in range(col_count):
            weight = weights[j]
            if weight == 0:
                continue
            avg_length = match_info[A_O + j]
            doc_length = match_info[L_O + j]
            if avg_length == 0:
                D = 0
            else:
                D = 1 - B + (B * (doc_length / avg_length))

            x = X_O + (3 * j * (i + 1))
            term_frequency = match_info[x]
            docs_with_term = match_info[x + 2]
            idf = max(
                log(
                    (total_docs - docs_with_term + 0.5) /
                    (docs_with_term + 0.5)),
                0)
            denom = term_frequency + (K * D)
            if denom == 0:
                rhs = 0
            else:
                rhs = (term_frequency * (K + 1)) / denom

            score += (idf * rhs) * weight

    free(weights)
    return -1 * score


def peewee_bm25f(py_match_info, *raw_weights):
    # Usage: peewee_bm25f(matchinfo(table, 'pcnalx'), 1)
    # where the second parameter is the index of the column and
    # the 3rd and 4th specify k and b.
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int argc = len(raw_weights)
        int term_count, col_count
        double B = 0.75, K1 = 1.2, D, epsilon
        double total_docs, term_frequency, docs_with_term
        double doc_length = 0.0, avg_length = 0.0
        double idf, weight, rhs, denom
        double *weights
        int P_O = 0, C_O = 1, N_O = 2, A_O = 3, L_O, X_O
        int i, j, current_x

        double score = 0.0

    match_info = <unsigned int *>match_info_buf
    term_count = match_info[P_O]
    col_count = match_info[C_O]
    total_docs = match_info[N_O]

    L_O = A_O + col_count
    X_O = L_O + col_count

    for j in range(col_count):
        avg_length += match_info[A_O + j]
        doc_length += match_info[L_O + j]

    epsilon = 1.0 / (total_docs * avg_length)

    weights = <double *>malloc(sizeof(double) * col_count)
    for i in range(col_count):
        if argc == 0:
            weights[i] = 1.
        elif i < argc:
            weights[i] = <double>raw_weights[i]
        else:
            weights[i] = 0

    for i in range(term_count):
        for j in range(col_count):
            weight = weights[j]
            if weight == 0:
                continue
            current_x = X_O + (3 * j * (i + 1))
            term_frequency = match_info[current_x]
            docs_with_term = match_info[current_x + 2]
            idf = log(
                (total_docs - docs_with_term + 0.5) /
                (docs_with_term + 0.5))
            idf = epsilon if idf < 0 else idf

            D = (term_frequency +
                 (K1 * (1 - B + (B * (doc_length / avg_length)))))
            rhs = (term_frequency * (K1 + 1)) / D
            rhs += 1.

            score += (idf * rhs) * weight

    free(weights)
    return -1 * score


cdef unsigned int murmurhash2(const char *key, int nlen, unsigned int seed):
    cdef:
        unsigned int m = 0x5bd1e995
        int r = 24
        unsigned int l = nlen
        unsigned char *data = <unsigned char *>key
        unsigned int h = seed
        unsigned int k
        unsigned int t = 0

    while nlen >= 4:
        k = <unsigned int>(<unsigned int *>data)[0]

        # mmix(h, k).
        k *= m
        k = k ^ (k >> r)
        k *= m
        h *= m
        h = h ^ k

        data += 4
        nlen -= 4

    if nlen == 3:
        t = t ^ (data[2] << 16)
    if nlen >= 2:
        t = t ^ (data[1] << 8)
    if nlen >= 1:
        t = t ^ (data[0])

    # mmix(h, t).
    t *= m
    t = t ^ (t >> r)
    t *= m
    h *= m
    h = h ^ t

    # mmix(h, l).
    l *= m
    l = l ^ (l >> r)
    l *= m
    h *= m
    h = h ^ l

    h = h ^ (h >> 13)
    h *= m
    h = h ^ (h >> 15)

    return h


def peewee_murmurhash(key, seed=None):
    if key is None:
        return

    cdef:
        bytes bkey
        int nseed = seed or 0

    if isinstance(key, unicode):
        bkey = <bytes>key.encode('utf-8')
    else:
        bkey = <bytes>key

    if key:
        return murmurhash2(<char *>bkey, len(bkey), nseed)
    return 0


def make_hash(hash_impl):
    def inner(*items):
        state = hash_impl()
        for item in items:
            state.update(item)
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


cdef class median(object):
    cdef:
        int ct
        list items

    def __init__(self):
        self.ct = 0
        self.items = []

    cdef selectKth(self, int k, int s=0, int e=-1):
        cdef:
            int idx
        if e < 0:
            e = len(self.items)
        idx = randint(s, e-1)
        idx = self.partition_k(idx, s, e)
        if idx > k:
            return self.selectKth(k, s, idx)
        elif idx < k:
            return self.selectKth(k, idx + 1, e)
        else:
            return self.items[idx]

    cdef int partition_k(self, int pi, int s, int e):
        cdef:
            int i, x

        val = self.items[pi]
        # Swap pivot w/last item.
        self.items[e - 1], self.items[pi] = self.items[pi], self.items[e - 1]
        x = s
        for i in range(s, e):
            if self.items[i] < val:
                self.items[i], self.items[x] = self.items[x], self.items[i]
                x += 1
        self.items[x], self.items[e-1] = self.items[e-1], self.items[x]
        return x

    def step(self, item):
        self.items.append(item)
        self.ct += 1

    def finalize(self):
        if self.ct == 0:
            return None
        elif self.ct < 3:
            return self.items[0]
        else:
            return self.selectKth(self.ct / 2)
