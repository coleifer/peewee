"""
Translate web-search query syntax into a SQLite FTS5 query.

Search-box grammar:

    query    := or
    or       := and (OR and)*
    and      := unary+                    # juxtaposition means AND
    unary    := ['-'] atom                # '-' excludes matching documents
    atom     := [colspec ':'] phrase
              | [colspec ':'] '(' query ')'
    colspec  := colname | '{' colname ... '}'
    phrase   := '"' text '"' ['*'] | word ['*']

Translation to FTS5:

    phrase        -> "escaped text"[*]
    colspec: x    -> colspec: x       (x parenthesized when compound)
    and(a, b)     -> a AND b          (fts5 implicit AND is phrase-only)
    or(a, b)      -> a OR b
    -x            -> hoisted to the enclosing AND: (rest) NOT x
    ( query )     -> preserved

Anything that does not fit the grammar is treated as literal text, so the
translation always produces a valid query. Unbalanced parentheses and quotes
are repaired, operators with nothing to operate on are dropped, and nesting
deeper than MAX_DEPTH is flattened.

An exclusion only applies to the terms it is AND-ed with, as fts5 has no way
to express it otherwise. In "a OR -b" the exclusion has nothing to apply to
and is dropped, leaving "a".

Note fts5 reads "-colname:" as "every column except colname" and rejects a
bare "-phrase". Web-search "-" excludes the document, so it is always
translated to NOT.
"""
import re


__all__ = ['parse']

COLSPEC_RE = re.compile(r'(?:(\w+)|\{([^}]*)\})\s*:')
TERM_RE = re.compile(r'(?:"(?P<phrase>[^"]*)"?|(?P<word>[^\s"()]+?))'
                     r'(?P<star>\*)?'
                     r'(?=[\s"()]|$)')
WORD_RE = re.compile(r'\w')
OPERATORS = ('AND', 'OR', 'NOT')
MAX_DEPTH = 32  # Parser recurses 4 frames per level of nesting.


class _Parser:
    def __init__(self, query, columns):
        self.columns = set(columns)
        self.tokens = self._scan(query)
        self.pos = 0

    def _scan(self, query):
        tokens = []
        pos = 0
        while pos < len(query):
            char = query[pos]
            if char.isspace():
                pos += 1
                continue
            if char in '()':
                tokens.append((char, None))
                pos += 1
                continue
            if char == '-' and query[pos + 1:pos + 2].strip():
                tokens.append(('neg', None))
                pos += 1
                continue
            match = COLSPEC_RE.match(query, pos)
            if match is not None:
                name, group = match.group(1, 2)
                names = [name] if name else group.split()
                if names and all(n in self.columns for n in names):
                    # Column names are quoted: they may not be valid barewords.
                    quoted = ['"%s"' % n.replace('"', '""') for n in names]
                    tokens.append(('col', quoted[0] if name else
                                   '{%s}' % ' '.join(quoted)))
                    pos = match.end()
                    continue
            match = TERM_RE.match(query, pos)
            if match is None:
                pos += 1
                continue
            pos = match.end()
            phrase, word, star = match.group('phrase', 'word', 'star')
            if phrase is None and not star and word in OPERATORS:
                if word == 'NOT' and tokens and tokens[-1] == ('op', 'AND'):
                    tokens.pop()  # "AND NOT" means NOT.
                tokens.append(('op', word))
                continue
            text = word if phrase is None else phrase
            if WORD_RE.search(text):
                tokens.append(('term', '"%s"%s' % (text, star or '')))
        return self._balance(tokens)

    def _balance(self, tokens):
        # Drop unmatched ")" and close unmatched "(" so parsing cannot fail,
        # and drop nesting past MAX_DEPTH so it cannot exhaust the stack.
        depth = dropped = 0
        accum = []
        for token in tokens:
            if token[0] == '(':
                if depth == MAX_DEPTH:
                    dropped += 1
                    continue
                depth += 1
            elif token[0] == ')':
                if dropped:
                    dropped -= 1  # Closes the most recent dropped "(".
                    continue
                if not depth:
                    continue
                depth -= 1
            accum.append(token)
        return accum + [(')', None)] * depth

    def _peek(self):
        return self.tokens[self.pos][0] if self.pos < len(self.tokens) else None

    def _is_op(self, op):
        return (self._peek() == 'op' and self.tokens[self.pos][1] == op)

    def _parse_or(self):
        nodes = [self._parse_and()]
        while self._is_op('OR'):
            self.pos += 1
            nodes.append(self._parse_and())
        nodes = [node for node in nodes if node]
        if not nodes:
            return None
        return nodes[0] if len(nodes) == 1 else ('or', nodes)

    def _parse_and(self):
        positive, negative = [], []
        while True:
            token = self._peek()
            if token == 'op':
                if self._is_op('OR'):
                    break
                self.pos += 1  # Juxtaposition already ANDs, so AND is a no-op.
                continue
            if token in (')', None):
                break
            node, negate = self._parse_not()
            if node:
                (negative if negate else positive).append(node)
        if not positive:
            return None
        node = positive[0] if len(positive) == 1 else ('and', positive)
        return ('not', node, negative) if negative else node

    def _parse_not(self):
        node, negate = self._parse_atom()
        while self._is_op('NOT'):
            self.pos += 1
            right, _ = self._parse_atom()
            if node and right:
                node = ('not', node, [right])
        return node, negate

    def _parse_atom(self):
        negate = self._peek() == 'neg'
        if negate:
            self.pos += 1
        colspec = None
        if self._peek() == 'col':
            colspec = self.tokens[self.pos][1]
            self.pos += 1
        token = self._peek()
        if token == 'term':
            node = ('t', self.tokens[self.pos][1])
            self.pos += 1
        elif token == '(':
            self.pos += 1
            node = self._parse_or()
            if self._peek() == ')':
                self.pos += 1
        else:
            # A neg/col was consumed, so the caller still makes progress.
            return None, False
        return (('col', colspec, node) if node and colspec else node), negate

    def _render(self, node, nested=False):
        kind = node[0]
        if kind == 't':
            return node[1]
        if kind == 'col':
            sql = '%s: %s' % (node[1], self._render(node[2], True))
            return '(%s)' % sql if nested else sql
        if kind == 'and':
            sql = ' AND '.join(self._render(n, True) for n in node[1])
        elif kind == 'or':
            sql = ' OR '.join(self._render(n, True) for n in node[1])
        else:
            sql = '%s NOT %s' % (
                self._render(node[1], True),
                ' NOT '.join(self._render(n, True) for n in node[2]))
        return '(%s)' % sql if nested else sql

    def translate(self):
        nodes = []
        while self.pos < len(self.tokens):
            pos = self.pos
            node = self._parse_or()
            if node:
                nodes.append(node)
            if self.pos == pos:
                self.pos += 1
        if not nodes:
            return '""'
        node = nodes[0] if len(nodes) == 1 else ('and', nodes)
        return self._render(node)


def parse(query, columns=None):
    """
    Translate a search-box query into an FTS5 query. Column filters are only
    honored for the given column names, so unknown ones become search terms.

    A query with no searchable terms in it, including an empty string,
    translates to '""', which is valid and matches no rows.
    """
    return _Parser(query, columns or ()).translate()
