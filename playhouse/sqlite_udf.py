import collections
import datetime
import heapq
import json
import math
import os
import random
import re
import struct
import sys
import threading
import zlib
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse


SQLITE_DATETIME_FORMATS = (
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d %H:%M:%S.%f%z',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M:%S%z',
    '%Y-%m-%d',
    '%H:%M:%S',
    '%H:%M:%S.%f',
    '%H:%M')

from peewee import format_date_time

def format_date_time_sqlite(date_value):
    return format_date_time(date_value, SQLITE_DATETIME_FORMATS)

try:
    from playhouse import _sqlite_udf as cython_udf
except ImportError:
    cython_udf = None


# Group udf by function.
CONTROL_FLOW = 'control_flow'
DATE = 'date'
FILE = 'file'
HELPER = 'helpers'
JSON = 'json'
MATH = 'math'
RANK = 'rank'
STRING = 'string'

AGGREGATE_COLLECTION = {}
UDF_COLLECTION = {}


class synchronized_dict(dict):
    def __init__(self, *args, **kwargs):
        super(synchronized_dict, self).__init__(*args, **kwargs)
        self._lock = threading.Lock()

    def __getitem__(self, key):
        with self._lock:
            return super(synchronized_dict, self).__getitem__(key)

    def __setitem__(self, key, value):
        with self._lock:
            return super(synchronized_dict, self).__setitem__(key, value)

    def __delitem__(self, key):
        with self._lock:
            return super(synchronized_dict, self).__delitem__(key)


STATE = synchronized_dict()
SETTINGS = synchronized_dict()

# Class and function decorators.
def aggregate(*groups):
    def decorator(klass):
        for group in groups:
            AGGREGATE_COLLECTION.setdefault(group, [])
            AGGREGATE_COLLECTION[group].append(klass)
        return klass
    return decorator

def udf(group, name=None):
    def decorator(fn):
        UDF_COLLECTION.setdefault(group, [])
        UDF_COLLECTION[group].append((fn, name or fn.__name__))
        return fn
    return decorator

# Register aggregates / functions with connection.
def register_aggregate_groups(db, *groups):
    seen = set()
    for group in groups:
        klasses = AGGREGATE_COLLECTION.get(group, ())
        for klass in klasses:
            name = getattr(klass, 'name', klass.__name__)
            if name not in seen:
                seen.add(name)
                db.register_aggregate(klass, name)

def register_udf_groups(db, *groups):
    seen = set()
    for group in groups:
        functions = UDF_COLLECTION.get(group, ())
        for function, name in functions:
            if name not in seen:
                seen.add(name)
                db.register_function(function, name)

def register_groups(db, *groups):
    register_aggregate_groups(db, *groups)
    register_udf_groups(db, *groups)

def register_all(db):
    register_aggregate_groups(db, *AGGREGATE_COLLECTION)
    register_udf_groups(db, *UDF_COLLECTION)


# Begin actual user-defined functions and aggregates.

# Scalar functions.
@udf(CONTROL_FLOW)
def if_then_else(cond, truthy, falsey=None):
    if cond:
        return truthy
    return falsey

@udf(DATE)
def strip_tz(date_str):
    date_str = date_str.replace('T', ' ')
    tz_idx1 = date_str.find('+')
    if tz_idx1 != -1:
        return date_str[:tz_idx1]
    tz_idx2 = date_str.find('-')
    if tz_idx2 > 13:
        return date_str[:tz_idx2]
    return date_str

@udf(DATE)
def human_delta(nseconds, glue=', '):
    parts = (
        (86400 * 365, 'year'),
        (86400 * 30, 'month'),
        (86400 * 7, 'week'),
        (86400, 'day'),
        (3600, 'hour'),
        (60, 'minute'),
        (1, 'second'),
    )
    accum = []
    for offset, name in parts:
        val, nseconds = divmod(nseconds, offset)
        if val:
            suffix = val != 1 and 's' or ''
            accum.append('%s %s%s' % (val, name, suffix))
    if not accum:
        return '0 seconds'
    return glue.join(accum)

@udf(FILE)
def file_ext(filename):
    try:
        res = os.path.splitext(filename)
    except ValueError:
        return None
    return res[1]

@udf(FILE)
def file_read(filename):
    try:
        with open(filename) as fh:
            return fh.read()
    except:
        pass

if sys.version_info[0] == 2:
    @udf(HELPER)
    def gzip(data, compression=9):
        return buffer(zlib.compress(data, compression))

    @udf(HELPER)
    def gunzip(data):
        return zlib.decompress(data)
else:
    @udf(HELPER)
    def gzip(data, compression=9):
        if isinstance(data, str):
            data = bytes(data.encode('raw_unicode_escape'))
        return zlib.compress(data, compression)

    @udf(HELPER)
    def gunzip(data):
        return zlib.decompress(data)

@udf(HELPER)
def hostname(url):
    parse_result = urlparse(url)
    if parse_result:
        return parse_result.netloc

@udf(HELPER)
def toggle(key):
    key = key.lower()
    STATE[key] = ret = not STATE.get(key)
    return ret

@udf(HELPER)
def setting(key, value=None):
    if value is None:
        return SETTINGS.get(key)
    else:
        SETTINGS[key] = value
        return value

@udf(HELPER)
def clear_settings():
    SETTINGS.clear()

@udf(HELPER)
def clear_toggles():
    STATE.clear()

@udf(MATH)
def randomrange(start, end=None, step=None):
    if end is None:
        start, end = 0, start
    elif step is None:
        step = 1
    return random.randrange(start, end, step)

@udf(MATH)
def gauss_distribution(mean, sigma):
    try:
        return random.gauss(mean, sigma)
    except ValueError:
        return None

@udf(MATH)
def sqrt(n):
    try:
        return math.sqrt(n)
    except ValueError:
        return None

@udf(MATH)
def tonumber(s):
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except:
            return None

@udf(STRING)
def substr_count(haystack, needle):
    if not haystack or not needle:
        return 0
    return haystack.count(needle)

@udf(STRING)
def strip_chars(haystack, chars):
    return haystack.strip(chars)

@udf(JSON)
def json_contains(src_json, obj_json):
    stack = []
    try:
        stack.append((json.loads(obj_json), json.loads(src_json)))
    except:
        # Invalid JSON!
        return False

    while stack:
        obj, src = stack.pop()
        if isinstance(src, dict):
            if isinstance(obj, dict):
                for key in obj:
                    if key not in src:
                        return False
                    stack.append((obj[key], src[key]))
            elif isinstance(obj, list):
                for item in obj:
                    if item not in src:
                        return False
            elif obj not in src:
                return False
        elif isinstance(src, list):
            if isinstance(obj, dict):
                return False
            elif isinstance(obj, list):
                try:
                    for i in range(len(obj)):
                        stack.append((obj[i], src[i]))
                except IndexError:
                    return False
            elif obj not in src:
                return False
        elif obj != src:
            return False
    return True


# Aggregates.
class _heap_agg(object):
    def __init__(self):
        self.heap = []
        self.ct = 0

    def process(self, value):
        return value

    def step(self, value):
        self.ct += 1
        heapq.heappush(self.heap, self.process(value))

class _datetime_heap_agg(_heap_agg):
    def process(self, value):
        return format_date_time_sqlite(value)

if sys.version_info[:2] == (2, 6):
    def total_seconds(td):
        return (td.seconds +
                (td.days * 86400) +
                (td.microseconds / (10.**6)))
else:
    total_seconds = lambda td: td.total_seconds()

@aggregate(DATE)
class mintdiff(_datetime_heap_agg):
    def finalize(self):
        dtp = min_diff = None
        while self.heap:
            if min_diff is None:
                if dtp is None:
                    dtp = heapq.heappop(self.heap)
                    continue
            dt = heapq.heappop(self.heap)
            diff = dt - dtp
            if min_diff is None or min_diff > diff:
                min_diff = diff
            dtp = dt
        if min_diff is not None:
            return total_seconds(min_diff)

@aggregate(DATE)
class avgtdiff(_datetime_heap_agg):
    def finalize(self):
        if self.ct < 1:
            return
        elif self.ct == 1:
            return 0

        total = ct = 0
        dtp = None
        while self.heap:
            if total == 0:
                if dtp is None:
                    dtp = heapq.heappop(self.heap)
                    continue

            dt = heapq.heappop(self.heap)
            diff = dt - dtp
            ct += 1
            total += total_seconds(diff)
            dtp = dt

        return float(total) / ct

@aggregate(DATE)
class duration(object):
    def __init__(self):
        self._min = self._max = None

    def step(self, value):
        dt = format_date_time_sqlite(value)
        if self._min is None or dt < self._min:
            self._min = dt
        if self._max is None or dt > self._max:
            self._max = dt

    def finalize(self):
        if self._min and self._max:
            td = (self._max - self._min)
            return total_seconds(td)
        return None

@aggregate(MATH)
class mode(object):
    def __init__(self):
        self.items = collections.Counter()

    def step(self, *args):
        self.items.update(args)

    def finalize(self):
        if self.items:
            return self.items.most_common(1)[0][0]

@aggregate(MATH)
class minrange(_heap_agg):
    def finalize(self):
        if self.ct == 0:
            return
        elif self.ct == 1:
            return 0

        prev = min_diff = None

        while self.heap:
            if min_diff is None:
                if prev is None:
                    prev = heapq.heappop(self.heap)
                    continue
            curr = heapq.heappop(self.heap)
            diff = curr - prev
            if min_diff is None or min_diff > diff:
                min_diff = diff
            prev = curr
        return min_diff

@aggregate(MATH)
class avgrange(_heap_agg):
    def finalize(self):
        if self.ct == 0:
            return
        elif self.ct == 1:
            return 0

        total = ct = 0
        prev = None
        while self.heap:
            if total == 0:
                if prev is None:
                    prev = heapq.heappop(self.heap)
                    continue

            curr = heapq.heappop(self.heap)
            diff = curr - prev
            ct += 1
            total += diff
            prev = curr

        return float(total) / ct

@aggregate(MATH)
class _range(object):
    name = 'range'

    def __init__(self):
        self._min = self._max = None

    def step(self, value):
        if self._min is None or value < self._min:
            self._min = value
        if self._max is None or value > self._max:
            self._max = value

    def finalize(self):
        if self._min is not None and self._max is not None:
            return self._max - self._min
        return None

@aggregate(MATH)
class stddev(object):
    def __init__(self):
        self.n = 0
        self.values = []
    def step(self, v):
        self.n += 1
        self.values.append(v)
    def finalize(self):
        if self.n <= 1:
            return 0
        mean = sum(self.values) / self.n
        return math.sqrt(sum((i - mean) ** 2 for i in self.values) / (self.n - 1))


def _parse_match_info(buf):
    # See http://sqlite.org/fts3.html#matchinfo
    bufsize = len(buf)  # Length in bytes.
    return [struct.unpack('@I', buf[i:i+4])[0] for i in range(0, bufsize, 4)]

def get_weights(ncol, raw_weights):
    if not raw_weights:
        return [1] * ncol
    else:
        weights = [0] * ncol
        for i, weight in enumerate(raw_weights):
            weights[i] = weight
    return weights

# Ranking implementation, which parse matchinfo.
def rank(raw_match_info, *raw_weights):
    # Handle match_info called w/default args 'pcx' - based on the example rank
    # function http://sqlite.org/fts3.html#appendix_a
    match_info = _parse_match_info(raw_match_info)
    score = 0.0

    p, c = match_info[:2]
    weights = get_weights(c, raw_weights)

    # matchinfo X value corresponds to, for each phrase in the search query, a
    # list of 3 values for each column in the search table.
    # So if we have a two-phrase search query and three columns of data, the
    # following would be the layout:
    # p0 : c0=[0, 1, 2],   c1=[3, 4, 5],    c2=[6, 7, 8]
    # p1 : c0=[9, 10, 11], c1=[12, 13, 14], c2=[15, 16, 17]
    for phrase_num in range(p):
        phrase_info_idx = 2 + (phrase_num * c * 3)
        for col_num in range(c):
            weight = weights[col_num]
            if not weight:
                continue

            col_idx = phrase_info_idx + (col_num * 3)

            # The idea is that we count the number of times the phrase appears
            # in this column of the current row, compared to how many times it
            # appears in this column across all rows. The ratio of these values
            # provides a rough way to score based on "high value" terms.
            row_hits = match_info[col_idx]
            all_rows_hits = match_info[col_idx + 1]
            if row_hits > 0:
                score += weight * (float(row_hits) / all_rows_hits)

    return -score

# Okapi BM25 ranking implementation (FTS4 only).
def bm25(raw_match_info, *args):
    """
    Usage:

        # Format string *must* be pcnalx
        # Second parameter to bm25 specifies the index of the column, on
        # the table being queries.
        bm25(matchinfo(document_tbl, 'pcnalx'), 1) AS rank
    """
    match_info = _parse_match_info(raw_match_info)
    K = 1.2
    B = 0.75
    score = 0.0

    P_O, C_O, N_O, A_O = range(4)  # Offsets into the matchinfo buffer.
    term_count = match_info[P_O]  # n
    col_count = match_info[C_O]
    total_docs = match_info[N_O]  # N
    L_O = A_O + col_count
    X_O = L_O + col_count

    # Worked example of pcnalx for two columns and two phrases, 100 docs total.
    # {
    #   p  = 2
    #   c  = 2
    #   n  = 100
    #   a0 = 4   -- avg number of tokens for col0, e.g. title
    #   a1 = 40  -- avg number of tokens for col1, e.g. body
    #   l0 = 5   -- curr doc has 5 tokens in col0
    #   l1 = 30  -- curr doc has 30 tokens in col1
    #
    #   x000     -- hits this row for phrase0, col0
    #   x001     -- hits all rows for phrase0, col0
    #   x002     -- rows with phrase0 in col0 at least once
    #
    #   x010     -- hits this row for phrase0, col1
    #   x011     -- hits all rows for phrase0, col1
    #   x012     -- rows with phrase0 in col1 at least once
    #
    #   x100     -- hits this row for phrase1, col0
    #   x101     -- hits all rows for phrase1, col0
    #   x102     -- rows with phrase1 in col0 at least once
    #
    #   x110     -- hits this row for phrase1, col1
    #   x111     -- hits all rows for phrase1, col1
    #   x112     -- rows with phrase1 in col1 at least once
    # }

    weights = get_weights(col_count, args)

    for i in range(term_count):
        for j in range(col_count):
            weight = weights[j]
            if weight == 0:
                continue

            x = X_O + (3 * (j + i * col_count))
            term_frequency = float(match_info[x])  # f(qi, D)
            docs_with_term = float(match_info[x + 2])  # n(qi)

            # log( (N - n(qi) + 0.5) / (n(qi) + 0.5) )
            idf = math.log(
                    (total_docs - docs_with_term + 0.5) /
                    (docs_with_term + 0.5))
            if idf <= 0.0:
                idf = 1e-6

            doc_length = float(match_info[L_O + j])  # |D|
            avg_length = float(match_info[A_O + j]) or 1.  # avgdl
            ratio = doc_length / avg_length

            num = term_frequency * (K + 1.0)
            b_part = 1.0 - B + (B * ratio)
            denom = term_frequency + (K * b_part)

            pc_score = idf * (num / denom)
            score += (pc_score * weight)

    return -score


if cython_udf is not None:
    rank = udf(RANK, 'fts_rank')(cython_udf.peewee_rank)
    lucene = udf(RANK, 'fts_lucene')(cython_udf.peewee_lucene)
    bm25 = udf(RANK, 'fts_bm25')(cython_udf.peewee_bm25)
    bm25f = udf(RANK, 'fts_bm25f')(cython_udf.peewee_bm25f)

    damerau_levenshtein_dist = udf(STRING)(cython_udf.damerau_levenshtein_dist)
    levenshtein_dist = udf(STRING)(cython_udf.levenshtein_dist)
    str_dist = udf(STRING)(cython_udf.str_dist)
    median = aggregate(MATH)(cython_udf.median)
else:
    rank = udf(RANK, 'fts_rank')(rank)
    bm25 = udf(RANK, 'fts_bm25')(bm25)
