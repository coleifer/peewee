import sys
from difflib import SequenceMatcher
from random import randint


IS_PY3K = sys.version_info[0] == 3

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
            return self.selectKth(self.ct / 2)
