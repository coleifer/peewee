cdef extern from "_pysqlite/connection.h":
    ctypedef struct pysqlite_Connection:
        sqlite3 *db
        double timeout


cdef extern from "sqlite3.h":
    ctypedef struct sqlite3
    ctypedef struct sqlite3_context
    ctypedef struct sqlite3_value
    ctypedef long long sqlite3_int64

    cdef int SQLITE_UTF8 = 1
    cdef int SQLITE_OK = 0
    cdef int SQLITE_ERROR = 1

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


cdef class ConnWrapper(object):
    cdef:
        pysqlite_Connection *conn

    def __init__(self, conn):
        self.conn = <pysqlite_Connection *>conn

    def changes(self):
        return sqlite3_changes(self.conn.db)
