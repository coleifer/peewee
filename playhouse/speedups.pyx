from cpython cimport datetime
from cpython.tuple cimport PyTuple_New, PyTuple_SetItem


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
        public _QueryResultWrapper qrw

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
        bint _populated, _initialized
        dict join_meta
        int _ct, _idx
        list column_meta
        readonly list _result_cache
        object cursor, model

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
        pass

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

    cpdef fill_cache(self, int n=-1):
        if n > 0:
            n = n - self.ct

        self._idx = self._ct
        while not self._populated and n:
            try:
                next(self)
            except StopIteration:
                break
            else:
                n -= 1


cdef class _ModelResultWrapper(_QueryResultWrapper):
    cdef:
        int row_size
        list column_names, converters

    cdef initialize(self, cursor_description):
        cdef:
            int i
            int n = len(cursor_description)

        self.row_size = n
        self.column_names = []
        self.converters = []

        for i in range(n):
            attr_name = cursor_description[i][0]
            self.column_names.append(attr_name)
            found = None
            if self.column_meta is not None:
                try:
                    column = self.column_meta[i]
                except IndexError:
                    pass
                else:
                    try:
                        found = column.python_value
                    except AttributeError:
                        pass

            if found is None:
                if attr_name in self.model._meta.columns:
                    found = self.model._meta.columns[attr_name].python_value

            self.converters.append(found)


cdef class _TuplesQueryResultWrapper(_ModelResultWrapper):
    cdef process_row(self, tuple row):
        cdef:
            int i = 0
            list ret = []

        for i in range(self.row_size):
            if self.converters[i] is None:
                ret.append(row[i])
            else:
                ret.append(self.converters[i](row[i]))

        return tuple(ret)


cdef class _DictQueryResultWrapper(_ModelResultWrapper):
    cdef process_row(self, tuple row):
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
