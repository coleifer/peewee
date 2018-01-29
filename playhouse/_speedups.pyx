def quote(list path, str quote_char):
    cdef:
        int n = len(path)
        str part
        tuple quotes = (quote_char, quote_char)

    if n == 1:
        return path[0].join(quotes)
    elif n > 1:
        return '.'.join([part.join(quotes) for part in path])
    return ''
