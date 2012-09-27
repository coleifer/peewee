from collections import namedtuple

OP_AND = 0
OP_OR = 1

OP_ADD = 0
OP_SUB = 1
OP_MUL = 2
OP_DIV = 3
OP_AND = 4
OP_OR = 5
OP_XOR = 6
OP_USER = 9

OP_EQ = 0
OP_LT = 1
OP_LTE = 2
OP_GT = 3
OP_GTE = 4
OP_NE = 5
OP_IN = 6
OP_ISNULL = 7
OP_IEQ = 8
OP_CONTAINS = 9
OP_ICONTAINS = 10
OP_STARTSWITH = 11
OP_ISTARTSWITH = 12

SCALAR = 99

JOIN_INNER = 1
JOIN_LEFT_OUTER = 2
JOIN_FULL = 3


Join = namedtuple('Join', ('model_class', 'join_type', 'column'))


class Node(object):
    def __init__(self, connector, children=None, negated=False):
        self.connector = connector
        self.children = children or []
        self.negated = negated

    def connect(self, rhs, connector):
        if isinstance(rhs, Leaf):
            if connector == self.connector:
                self.children.append(rhs)
                return self
        p = Node(connector)
        p.children = [self, rhs]
        return p

    def __and__(self, rhs):
        return self.connect(rhs, OP_AND)

    def __or__(self, rhs):
        return self.connect(rhs, OP_OR)

    def __invert__(self):
        self.negated = not self.negated
        return self

    def __nonzero__(self):
        return bool(self.children)

    def clone(self):
        return Node(self.connector, [c.clone() for c in self.children], self.negated)


class Leaf(object):
    def __init__(self):
        self.parent = None
        self.negated = False

    def connect(self, connector):
        if self.parent is None:
            self.parent = Node(connector)
            self.parent.children.append(self)

    def __and__(self, rhs):
        self.connect(OP_AND)
        return self.parent & rhs

    def __or__(self, rhs):
        self.connect(OP_OR)
        return self.parent | rhs

    def __invert__(self):
        self.negated = not self.negated
        return self


class Q(Leaf):
    # binary expression
    def __init__(self, lhs, op, rhs, negated=False):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        self.negated = negated
        super(Q, self).__init__()

    def clone(self):
        return Q(self.lhs, self.op, self.rhs, self.negated)


class Expr(object):
    def __init__(self):
        self.alias = None

    def set_alias(self, a=None):
        self.alias = a
        return self

    def _expr(op, n=False):
        def inner(self, value):
            return BinaryExpr(self, op, value)
        return inner
    __add__ = _expr(OP_ADD)
    __sub__ = _expr(OP_SUB)
    __mul__ = _expr(OP_MUL)
    __div__ = _expr(OP_DIV)
    __and__ = _expr(OP_AND)
    __or__ = _expr(OP_OR)
    __xor__ = _expr(OP_XOR)

    def _q(op):
        def inner(self, value):
            return Q(self, op, value)
        return inner

    __eq__ = _q(OP_EQ)
    __lt__ = _q(OP_LT)
    __lte__ = _q(OP_LTE)
    __gt__ = _q(OP_GT)
    __gte__ = _q(OP_GTE)
    __ne__ = _q(OP_NE)
    __lshift__ = _q(OP_IN)
    __rshift__ = _q(OP_ISNULL)
    __mod__ = _q(OP_CONTAINS)


class BinaryExpr(Expr):
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        super(BinaryExpr, self).__init__()


class Field(Expr):
    def __init__(self, name):
        self.name = name
        self.model_class = None
        super(Field, self).__init__()

    def add_to_class(self, model_class, name):
        self.model_class = model_class
        self.name = name


class Func(Expr):
    def __init__(self, fn_name, *params):
        self.fn_name = fn_name
        self.params = params
        super(Func, self).__init__()


class _FN(object):
    def __getattr__(self, attr):
        def dec(*args, **kwargs):
            return Func(attr, *args, **kwargs)
        return dec
fn = _FN()


class QueryCompiler(object):
    q_op_map = {
        OP_EQ: '=',
        OP_LT: '<',
        OP_LTE: '<=',
        OP_GT: '>',
        OP_GTE: '>=',
        OP_NE: '!=',
        OP_IN: ' IN ',
        OP_ISNULL: ' IS NULL',
        OP_IEQ: '=',
        OP_CONTAINS: '',
        OP_ICONTAINS: '',
        OP_STARTSWITH: '',
        OP_ISTARTSWITH: '',
    }

    expr_op_map = {
        OP_ADD: '+',
        OP_SUB: '-',
        OP_MUL: '*',
        OP_DIV: '/',
        OP_AND: '&',
        OP_OR: '|',
        OP_XOR: '^',
    }

    join_map = {
        JOIN_INNER: 'INNER',
        JOIN_LEFT_OUTER: 'LEFT OUTER',
        JOIN_FULL: 'FULL',
    }

    def __init__(self, quote_char='"', interpolation='?'):
        self.quote_char = quote_char
        self.interpolation = interpolation

    def quote(self, s):
        return ''.join((self.quote_char, s, self.quote_char))

    def _add_alias(self, expr_str, expr):
        if expr.alias:
            expr_str = ' '.join((expr_str, 'as', expr.alias))
        return expr_str

    def parse_expr(self, expr, alias_map=None):
        if isinstance(expr, BinaryExpr):
            lhs, lparams = self.parse_expr(expr.lhs, alias_map)
            rhs, rparams = self.parse_expr(expr.rhs, alias_map)
            expr_str = '(%s %s %s)' % (lhs, self.expr_op_map[expr.op], rhs)
            return self._add_alias(expr_str, expr), lparams + rparams
        if isinstance(expr, Field):
            expr_str = self.quote(expr.name)
            if alias_map and expr.model_class in alias_map:
                expr_str = '.'.join((alias_map[expr.model_class], expr_str))
            return self._add_alias(expr_str, expr), []
        elif isinstance(expr, Func):
            scalars = []
            exprs = []
            for p in expr.params:
                parsed, params = self.parse_expr(p, alias_map)
                exprs.append(parsed)
                scalars.extend(params)
            expr_str = '%s(%s)' % (expr.fn_name, ', '.join(exprs))
            return self._add_alias(expr_str, expr), scalars
        return self.interpolation, [expr]

    def parse_q(self, q, alias_map=None):
        lhs_expr, lparams = self.parse_expr(q.lhs, alias_map)
        rhs_expr, rparams = self.parse_expr(q.rhs, alias_map)
        not_expr = q.negated and 'NOT ' or ''
        return '%s%s %s %s' % (not_expr, lhs_expr, self.q_op_map[q.op], rhs_expr), lparams + rparams

    def parse_node(self, n, alias_map=None):
        query = []
        data = []
        for child in n.children:
            if isinstance(child, Node):
                parsed, child_data = self.parse_node(child, alias_map)
                if parsed:
                    query.append('(%s)' % parsed)
            elif isinstance(child, Q):
                parsed, child_data = self.parse_q(child, alias_map)
                query.append(parsed)
            data.extend(child_data)
        if n.connector == OP_AND:
            connector = ' AND '
        else:
            connector = ' OR '
        query = connector.join(query)
        if n.negated:
            query = 'NOT (%s)' % query
        return query, data

    def parse_where(self, q, alias_map):
        pass

    def parse_joins(self, joins, model_class, alias_map):
        parsed = []

        def _traverse(curr):
            if curr not in joins:
                return
            for i, join in enumerate(joins[curr]):
                from_model = curr
                to_model = join.model_class

                # figure out relationship
                #field = from_model._meta.get_related_field_for_model(model, on)
                #if field:
                #    left_field = field.db_column
                #    right_field = model._meta.pk_col
                #else:
                #    field = from_model._meta.get_reverse_related_field_for_model(model, on)
                #    left_field = from_model._meta.pk_col
                #    right_field = field.db_column

                join_type = join.join_type or JOIN_INNER
                lhs = '%s.%s' % (alias_map[from_model], self.quote(left_field))
                rhs = '%s.%s' % (alias_map[to_model], self.quote(right_field))

                parsed.append('%s JOIN %s AS %s ON %s = %s' % (
                    self.join_map[join_type],
                    self.quote(to_model._meta.db_table),
                    alias_map[to_model],
                    lhs,
                    rhs,
                ))

                _traverse(to_model)
        _traverse(model_class)
        return parsed

    def parse_select(self, s, alias_map):
        parsed = []
        data = []
        for expr in s:
            expr_str, vars = self.parse_expr(expr, alias_map)
            parsed.append(expr_str)
            data.extend(vars)
        return ', '.join(parsed), data

    def parse_update(self, u, alias_map):
        pass

    def calculate_alias_map(self, query, start=1):
        alias_map = {query.model_class: 't%s' % start}
        for model, joins in query._joins.items():
            if model not in alias_map:
                start += 1
                alias_map[model] = 't%s' % start
            for join in joins:
                if join.model_class not in alias_map:
                    start += 1
                    alias_map[join.model_class] = 't%s' % start
        return alias_map

    def parse_select_query(self, query):
        """
        - calculate alias map
        - select/update
        - joins
        - where
        - group by / having
        """
        alias_map = self.calculate_alias_map(query)
        select = self.parse_select(query._select, alias_map)
        joins = self.parse_joins(query._joins, query.model_class, alias_map)
        print select


def returns_clone(func):
    def inner(self, *args, **kwargs):
        clone = self.clone()
        func(clone, *args, **kwargs)
        return clone
    return inner


class Query(object):
    def __init__(self, model_class):
        self.model_class = model_class
        self._query_ctx = model_class
        self._joins = {self.model_class: []} # adjacency graph
        self._where = None

    def clone(self):
        query = type(self)(self.model_class)
        if self._where is not None:
            query._where = self._where.clone()
        query._joins = self.clone_joins()
        return query

    def clone_joins(self):
        return dict(
            (mc, list(j)) for mc, j in self._joins.items()
        )

    @returns_clone
    def where(self, q_or_node):
        if self._where is None:
            self._where = Node(OP_AND)
        self._where &= q_or_node

    @returns_clone
    def join(self, model_class, join_type=None, on=None):
        self._joins.setdefault(self._query_ctx, [])
        self._joins[self._query_ctx].append(Join(model_class, join_type, on))
        self._query_ctx = model_class

    @returns_clone
    def switch(self, model_class):
        if model_class in self._joins:
            self._query_ctx = model_class
        else:
            raise AttributeError('You must JOIN on %s' % model_class.__name__)

    def sql(self):
        raise NotImplementedError()

    def execute(self):
        pass


class SelectQuery(Query):
    def __init__(self, model_class, *selection):
        self._select = selection
        super(SelectQuery, self).__init__(model_class)

    def clone(self):
        query = super(SelectQuery, self).clone()
        query._select = list(self._select)
        return query

    def sql(self):
        compiler = QueryCompiler()
        sql = compiler.parse_select_query(self)
        """
        - calculate alias map
        - select/update
        - joins
        - where
        - group by / having
        """
        return ''


"""
WHERE examples:

    (field1 == 'v1') | (field2 == 'v2')
    (field1 < (field2 + 10)) & (field3 << ['a', 'b', 'c'])

SELECT examples:

    *
    field1, field2, field2 + 5, field3.alias('bar'), fn.Count(field4)

UPDATE example:

    field1=v1, field2=v2
    field1=field2 + 10
"""


if __name__ == '__main__':
    f1 = Field('f1')
    f2 = Field('f2')
    q = SelectQuery(None)
    qc = QueryCompiler()
    q = q.where((f1 == 'alpha') | (f2 == 'bravo'))
    q = q.where(f1 - 10 == f2)
    print qc.parse_node(q._where)
    q = SelectQuery(None)
    q = q.where(fn.SUBSTR(fn.LOWER(f1), 0, 1) == 'b')
    print qc.parse_node(q._where)
    q = SelectQuery(None, f1, f2, (f1+1).set_alias('baz'))
    print qc.parse_select(q._select, None)
    sq = SelectQuery('a', f1, f2, (f1 + 10).set_alias('f1plusten'))
    sq = sq.join('b').join('c').switch('a').join('b2')
    print qc.calculate_alias_map(sq)
    print sq.sql()
