import re
from cpython cimport datetime
from libc.math cimport log, sqrt
from libc.stdlib cimport free, malloc


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


cpdef peewee_date_part(lookup, date_str):
    cdef:
        tuple result = validate_and_format_datetime(lookup, date_str)

    if result:
        return getattr(result[0], result[1])


cpdef peewee_date_trunc(lookup, date_str):
    cdef:
        tuple result = validate_and_format_datetime(lookup, date_str)

    if result:
        return result[0].strftime(SQLITE_DATE_TRUNC_MAPPING[result[1]])


cpdef peewee_regexp(regex_str, value):
    if value is None or regex_str is None:
        return

    regex = re.compile(regex_str, re.I)
    if value and regex.search(value):
        return True
    return False


def peewee_rank(py_match_info, *raw_weights):
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int argc = len(raw_weights) + 1
        int ncol, nphrase, icol, iphrase, hits, global_hits
        int P_O = 0, C_O = 1, X_O = 2
        double score = 0.0, weight
        double *weights

    if argc < 1:
        raise ValueError('Missing matchinfo().')

    match_info = <unsigned int *>match_info_buf
    nphrase = match_info[P_O]
    ncol = match_info[C_O]

    weights = <double *>malloc(sizeof(double) * ncol)
    for icol in range(ncol):
        if icol < (argc - 1):
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
    # Usage: peewee_lucene(matchinfo(table, 'pcxnal'), 1)
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int argc = len(raw_weights) + 1
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
        if i < (argc - 1):
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
    # Usage: peewee_bm25(matchinfo(table, 'pcxnal'), 1)
    # where the second parameter is the index of the column and
    # the 3rd and 4th specify k and b.
    cdef:
        unsigned int *match_info
        unsigned int *phrase_info
        bytes _match_info_buf = bytes(py_match_info)
        char *match_info_buf = _match_info_buf
        int argc = len(raw_weights) + 1
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
        if i < (argc - 1):
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
