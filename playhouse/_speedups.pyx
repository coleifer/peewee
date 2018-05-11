def quote(list path, str quote_char):
    cdef:
        int n = len(path)
        str part

    if n == 1:
        return path[0].join(quote_char)
    elif n > 1:
        return '.'.join([part.join(quote_char) for part in path])
    return ''
