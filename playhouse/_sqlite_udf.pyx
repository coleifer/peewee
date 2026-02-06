# cython: language_level=3
from libc.stdlib cimport free, malloc
from libc.math cimport log, sqrt

import sys
from difflib import SequenceMatcher
from random import randint


IS_PY3K = sys.version_info[0] == 3

# FTS ranking functions.

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


# String UDF.
def damerau_levenshtein_dist(s1, s2):
    cdef:
        int i, j, del_cost, add_cost, sub_cost
        int s1_len = len(s1), s2_len = len(s2)
        list one_ago, two_ago, current_row
        list zeroes = [0] * (s2_len + 1)

    if IS_PY3K:
        current_row = list(range(1, s2_len + 2))
    else:
        current_row = range(1, s2_len + 2)

    current_row[-1] = 0
    one_ago = None

    for i in range(s1_len):
        two_ago = one_ago
        one_ago = current_row
        current_row = list(zeroes)
        current_row[-1] = i + 1
        for j in range(s2_len):
            del_cost = one_ago[j] + 1
            add_cost = current_row[j - 1] + 1
            sub_cost = one_ago[j - 1] + (s1[i] != s2[j])
            current_row[j] = min(del_cost, add_cost, sub_cost)

            # Handle transpositions.
            if (i > 0 and j > 0 and s1[i] == s2[j - 1]
                and s1[i-1] == s2[j] and s1[i] != s2[j]):
                current_row[j] = min(current_row[j], two_ago[j - 2] + 1)

    return current_row[s2_len - 1]

# String UDF.
def levenshtein_dist(a, b):
    cdef:
        int add, delete, change
        int i, j
        int n = len(a), m = len(b)
        list current, previous
        list zeroes

    if n > m:
        a, b = b, a
        n, m = m, n

    zeroes = [0] * (m + 1)

    if IS_PY3K:
        current = list(range(n + 1))
    else:
        current = range(n + 1)

    for i in range(1, m + 1):
        previous = current
        current = list(zeroes)
        current[0] = i

        for j in range(1, n + 1):
            add = previous[j] + 1
            delete = current[j - 1] + 1
            change = previous[j - 1]
            if a[j - 1] != b[i - 1]:
                change +=1
            current[j] = min(add, delete, change)

    return current[n]

# String UDF.
def str_dist(a, b):
    cdef:
        int t = 0

    for i in SequenceMatcher(None, a, b).get_opcodes():
        if i[0] == 'equal':
            continue
        t = t + max(i[4] - i[3], i[2] - i[1])
    return t

# Math Aggregate.
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
            return self.selectKth(self.ct // 2)
