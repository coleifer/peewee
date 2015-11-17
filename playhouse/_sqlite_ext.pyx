import re
from cpython cimport datetime
from libc.math cimport log
from libc.stdlib cimport free, malloc


cdef extern from "Python.h":
    cdef void Py_Initialize()
    cdef int Py_IsInitialized()


cdef extern from "sqlite3.h":
    ctypedef struct sqlite3
    ctypedef struct sqlite3_context
    ctypedef struct sqlite3_value
    ctypedef long long sqlite3_int64
    cdef int SQLITE_UTF8 = 1
    cdef int SQLITE_OK = 0

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
        void (*xFinal)(sqlite3_context*),
    )

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


cdef extern from "sqlite3ext.h":
    ctypedef struct sqlite3_api_routines


cdef const sqlite3_api_routines *sqlite3_api "sqlite3_api"

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


cdef void udf_error(sqlite3_context *ctx, const char *msg):
    sqlite3_result_error(ctx, msg, -1)


cdef tuple validate_and_format_datetime(sqlite3_context *ctx, int argc,
                                        sqlite3_value **argv):
    cdef:
        bint success = False
        int date_type = sqlite3_value_type(argv[1])
        int lookup_type = sqlite3_value_type(argv[0])
        int result

    if lookup_type == SQLITE_NULL or date_type == SQLITE_NULL:
        sqlite3_result_null(ctx)
        return

    date_part = sqlite3_value_text(argv[0])
    date_part = date_part.lower()
    if date_part not in SQLITE_DATE_TRUNC_MAPPING:
        udf_error(ctx, 'Unrecognized date part %s' % date_part)
        return

    date_value = sqlite3_value_text(argv[1])

    for date_format in SQLITE_DATETIME_FORMATS:
        try:
            date_obj = datetime.datetime.strptime(date_value, date_format)
        except ValueError:
            pass
        else:
            success = True
            break

    if not success:
        sqlite3_result_null(ctx)
        return

    return (date_obj, date_part)


cdef void peewee_date_part(sqlite3_context *ctx, int argc,
                           sqlite3_value **argv) with gil:
    cdef:
        tuple result = validate_and_format_datetime(ctx, argc, argv)

    if result:
        sqlite3_result_int(ctx, <int>getattr(result[0], result[1]))


cdef void peewee_date_trunc(sqlite3_context *ctx, int argc,
                            sqlite3_value **argv) with gil:
    cdef:
        tuple result = validate_and_format_datetime(ctx, argc, argv)

    if result:
        truncated = result[0].strftime(SQLITE_DATE_TRUNC_MAPPING[result[1]])
        sqlite3_result_text(
            ctx,
            <const char *>truncated,
            len(truncated),
            <sqlite3_destructor_type>-1)


cdef dict regex_cache = {}
cdef int regex_cache_size = 16

cdef void peewee_regexp(sqlite3_context *ctx, int argc,
                        sqlite3_value **argv) with gil:
    cdef int result = 0
    global regex_cache
    global regex_cache_size
    regex_str = sqlite3_value_text(argv[0])
    if not regex_str:
        sqlite3_result_int(ctx, 0)
        return

    if regex_str in regex_cache:
        regex = regex_cache[regex_str]
    else:
        try:
            regex = re.compile(regex_str, re.I)
        except TypeError as exc:
            sqlite3_result_error(ctx, <const char *>exc.message, -1)
            return
        else:
            if len(regex_cache) == regex_cache_size:
                regex_cache.popitem()
            regex_cache[regex_str] = regex

    value = sqlite3_value_text(argv[1])
    if value and regex.search(value) is not None:
        result = 1
    sqlite3_result_int(ctx, result)
    return


cdef void peewee_rank(sqlite3_context *ctx, int argc,
                      sqlite3_value **argv) with gil:
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        int ncol, nphrase, icol, iphrase, hits, global_hits
        int P_O = 0, C_O = 1, X_O = 2
        double score = 0.0, weight
        double *weights

    if argc < 1:
        sqlite3_result_error(ctx, 'Missing matchinfo().', -1)
        return

    match_info = <unsigned int *>sqlite3_value_blob(argv[0])
    nphrase = match_info[P_O]
    ncol = match_info[C_O]

    weights = <double *>malloc(sizeof(double) * ncol)
    for icol in range(ncol):
        if icol < (argc - 1):
            weights[icol] = sqlite3_value_double(argv[icol + 1])
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

    sqlite3_result_double(ctx, -1 * score)
    free(weights)


cdef void peewee_bm25(sqlite3_context *ctx, int argc,
                      sqlite3_value **argv) with gil:
    # Usage: peewee_bm25(matchinfo(table, 'pcxnal'), 1)
    # where the second parameter is the index of the column and
    # the 3rd and 4th specify k and b.
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        int term_count, col_count
        double B = 0.75, K = 1.2
        double total_docs, term_frequency,
        double doc_length, docs_with_term, avg_length
        double idf, weight, rhs
        double *weights
        int P_O = 0, C_O = 1, N_O = 2, A_O = 3, L_O, X_O
        int i, j, x

        double score = 0.0

    match_info = <unsigned int *>sqlite3_value_blob(argv[0])
    term_count = match_info[P_O]
    col_count = match_info[C_O]
    total_docs = match_info[N_O]

    L_O = A_O + col_count
    X_O = L_O + col_count

    weights = <double *>malloc(sizeof(double) * col_count)
    for i in range(col_count):
        if i < (argc - 1):
            weights[i] = sqlite3_value_double(argv[i + 1])
        else:
            weights[i] = 0

    for i in range(term_count):
        for j in range(col_count):
            weight = weights[j]
            if weight == 0:
                continue
            avg_length = match_info[A_O + j]
            doc_length = match_info[L_O + j]
            x = X_O + (3 * j * (i + 1))
            term_frequency = match_info[x]
            docs_with_term = match_info[x + 2]
            idf = log(
                (total_docs - docs_with_term + 0.5) /
                (docs_with_term + 0.5)
            )
            rhs = (
                (term_frequency * (K + 1)) /
                (term_frequency +
                 (K * (1 - B + (B * (doc_length / avg_length))))
                )
            )
            score += (idf * rhs) * weight

    sqlite3_result_double(ctx, -1 * score)
    free(weights)


cdef extern void init_sqlite_ext() except *

cdef public int sqlite3_sqliteext_init(sqlite3 *conn, char **errMessage, const sqlite3_api_routines *pApi):
    cdef int rc
    global sqlite3_api
    sqlite3_api = pApi

    Py_Initialize()
    init_sqlite_ext()

    rc = sqlite3_create_function(
        conn,
        'date_part',
        2,
        SQLITE_UTF8,
        NULL,
        peewee_date_part,
        NULL,
        NULL)
    rc = sqlite3_create_function(
        conn,
        'date_trunc',
        2,
        SQLITE_UTF8,
        NULL,
        peewee_date_trunc,
        NULL,
        NULL)
    rc = sqlite3_create_function(
        conn,
        'regexp',
        2,
        SQLITE_UTF8,
        NULL,
        peewee_regexp,
        NULL,
        NULL)
    rc = sqlite3_create_function(
        conn,
        'fts_rank',
        -1,
        SQLITE_UTF8,
        NULL,
        peewee_rank,
        NULL,
        NULL)
    rc = sqlite3_create_function(
        conn,
        'fts_bm25',
        -1,
        SQLITE_UTF8,
        NULL,
        peewee_bm25,
        NULL,
        NULL)

    return SQLITE_OK
