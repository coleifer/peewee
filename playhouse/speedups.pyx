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
