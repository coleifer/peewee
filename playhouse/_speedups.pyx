from bisect import bisect_left
from bisect import bisect_right
from collections import deque
from cpython cimport datetime


cdef basestring _strip_parens(basestring s):
    if not s or s[0] != '(':
        return s

    cdef int ct = 0, i = 0, unbalanced_ct = 0, required = 0
    cdef int l = len(s)

    while i < l:
        if s[i] == '(' and s[l - 1] == ')':
            ct += 1
            i += 1
            l -= 1
        else:
            break

    if ct:
        for i in range(ct, l - ct):
            if s[i] == '(':
                unbalanced_ct += 1
            elif s[i] == ')':
                unbalanced_ct -= 1
            if unbalanced_ct < 0:
                required += 1
                unbalanced_ct = 0
            if required == ct:
                break

        ct -= required
    if ct > 0:
        return s[ct:-ct]
    return s

def strip_parens(basestring s):
    return _strip_parens(s)


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


cpdef format_date_time(date_value, formats, post_fn=None):
    cdef:
        datetime.datetime date_obj
        tuple formats_t = tuple(formats)

    for date_format in formats_t:
        try:
            date_obj = datetime.datetime.strptime(date_value, date_format)
        except ValueError:
            pass
        else:
            if post_fn:
                return post_fn(date_obj)
            return date_obj
    return date_value

cpdef datetime.datetime format_date_time_sqlite(date_value):
    return format_date_time(date_value, SQLITE_DATETIME_FORMATS)


cdef class _QueryResultWrapper(object)  # Forward decl.


cdef class _ResultIterator(object):
    cdef:
        int _idx
        _QueryResultWrapper qrw

    def __init__(self, _QueryResultWrapper qrw):
        self.qrw = qrw
        self._idx = 0

    def __next__(self):
        if self._idx < self.qrw._ct:
            obj = self.qrw._result_cache[self._idx]
        elif not self.qrw._populated:
            obj = self.qrw.iterate()
            self.qrw._result_cache.append(obj)
            self.qrw._ct += 1
        else:
            raise StopIteration
        self._idx += 1
        return obj


cdef class _QueryResultWrapper(object):
    cdef:
        bint _initialized
        dict join_meta
        int _idx
        int row_size
        list column_names, converters
        readonly bint _populated
        readonly int _ct
        readonly list _result_cache
        object column_meta, cursor, model

    def __init__(self, model, cursor, meta=None):
        self.model = model
        self.cursor = cursor

        self._ct = self._idx = 0
        self._populated = self._initialized = False
        self._result_cache = []
        if meta is not None:
            self.column_meta, self.join_meta = meta
        else:
            self.column_meta = self.join_meta = None

    def __iter__(self):
        if self._populated:
            return iter(self._result_cache)
        return _ResultIterator(self)

    @property
    def count(self):
        self.fill_cache()
        return self._ct

    def __len__(self):
        return self.count

    cdef initialize(self, cursor_description):
        cdef:
            bint found
            int i = 0
            int n = len(cursor_description)
            int n_cm

        self.row_size = n
        self.column_names = []
        self.converters = []

        if self.column_meta is not None:
            n_cm = len(self.column_meta)
            for i, node in enumerate(self.column_meta):
                if not self._initialize_node(node, i):
                    self._initialize_by_name(cursor_description[i][0], i)
            if n_cm == n:
                return

        for i in range(i, n):
            self._initialize_by_name(cursor_description[i][0], i)

    def _initialize_by_name(self, name, int i):
        if name in self.model._meta.columns:
            field = self.model._meta.columns[name]
            self.converters.append(field.python_value)
        else:
            self.converters.append(None)
        self.column_names.append(name)

    cdef bint _initialize_node(self, node, int i):
        try:
            node_type = node._node_type
        except AttributeError:
            return False
        if (node_type == 'field') is True:
            self.column_names.append(node._alias or node.name)
            self.converters.append(node.python_value)
            return True

        if node_type != 'func' or not len(node.arguments):
            return False

        arg = node.arguments[0]
        try:
            node_type = arg._node_type
        except AttributeError:
            return False

        if (node_type == 'field') is True:
            self.column_names.append(node._alias or arg._alias or arg.name)
            self.converters.append(arg.python_value if node._coerce else None)
            return True

        return False

    cdef process_row(self, tuple row):
        return row

    cdef iterate(self):
        cdef:
            tuple row = self.cursor.fetchone()
        if not row:
            self._populated = True
            if not getattr(self.cursor, 'name', None):
                self.cursor.close()
            raise StopIteration
        elif not self._initialized:
            self.initialize(self.cursor.description)
            self._initialized = True
        return self.process_row(row)

    def iterator(self):
        while True:
            yield self.iterate()

    def __next__(self):
        cdef object inst

        if self._idx < self._ct:
            inst = self._result_cache[self._idx]
            self._idx += 1
            return inst
        elif self._populated:
            raise StopIteration

        inst = self.iterate()
        self._result_cache.append(inst)
        self._ct += 1
        self._idx += 1
        return inst

    cpdef fill_cache(self, n=None):
        cdef:
            int counter = -1 if n is None else <int>n
        if counter > 0:
            counter = counter - self._ct

        self._idx = self._ct
        while not self._populated and counter:
            try:
                next(self)
            except StopIteration:
                break
            else:
                counter -= 1


cdef class _TuplesQueryResultWrapper(_QueryResultWrapper):
    cdef process_row(self, tuple row):
        cdef:
            int i = 0
            list ret = []

        for i in range(self.row_size):
            func = self.converters[i]
            if func is None:
                ret.append(row[i])
            else:
                ret.append(func(row[i]))

        return tuple(ret)


cdef class _DictQueryResultWrapper(_QueryResultWrapper):
    cdef dict _make_dict(self, tuple row):
        cdef:
            dict result = {}
            int i = 0

        for i in range(self.row_size):
            func = self.converters[i]
            if func is not None:
                result[self.column_names[i]] = func(row[i])
            else:
                result[self.column_names[i]] = row[i]

        return result

    cdef process_row(self, tuple row):
        return self._make_dict(row)


cdef class _ModelQueryResultWrapper(_DictQueryResultWrapper):
    cdef process_row(self, tuple row):
        inst = self.model(**self._make_dict(row))
        inst._prepare_instance()
        return inst


cdef class _SortedFieldList(object):
    cdef:
        list _items, _keys

    def __init__(self):
        self._items = []
        self._keys = []

    def __getitem__(self, i):
        return self._items[i]

    def __iter__(self):
        return iter(self._items)

    def __contains__(self, item):
        k = item._sort_key
        i = bisect_left(self.keys, k)
        j = bisect_right(self.keys, k)
        return item in self._items[i:j]

    def index(self, field):
        return self._keys.index(field._sort_key)

    def insert(self, item):
        k = item._sort_key
        i = bisect_left(self._keys, k)
        self._keys.insert(i, k)
        self._items.insert(i, item)

    def remove(self, item):
        idx = self.index(item)
        del self._items[idx]
        del self._keys[idx]

cdef tuple _sort_key(model):
    return (model._meta.name, model._meta.db_table)

cdef _sort_models(model, set model_set, set seen, list accum):
    if model in model_set and model not in seen:
        seen.add(model)
        for foreign_key in model._meta.reverse_rel.values():
            _sort_models(foreign_key.model_class, model_set, seen, accum)
        accum.append(model)
        if model._meta.depends_on is not None:
            for dependency in model._meta.depends_on:
                _sort_models(dependency, model_set, seen, accum)

def sort_models_topologically(models):
    cdef:
        set model_set = set(models)
        set seen = set()
        list accum = []

    for model in sorted(model_set, key=_sort_key, reverse=True):
        _sort_models(model, model_set, seen, accum)

    return list(reversed(accum))
