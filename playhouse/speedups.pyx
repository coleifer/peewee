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
