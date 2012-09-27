import re
from collections import namedtuple
from copy import deepcopy


class Database(object):
    def __init__(self, name):
        self.name = name

    def connect(self):
        pass

    def close(self):
        pass


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


class FieldDescriptor(object):
    def __init__(self, field):
        self.field = field
        self.att_name = self.field.name

    def __get__(self, instance, instance_type=None):
        if instance:
            return instance._data.get(self.att_name)
        return self.field

    def __set__(self, instance, value):
        instance._data[self.att_name] = value


class Field(Expr):
    _field_counter = 0
    _order = 0

    def __init__(self, null=False, index=False, unique=False, verbose_name=None,
                 help_text=None, db_column=None, default=None, choices=None, *args, **kwargs):
        self.null = null
        self.index = index
        self.unique = unique
        self.verbose_name = verbose_name
        self.help_text = help_text
        self.db_column = db_column
        self.default = default
        self.choices = choices
        self.attributes = kwargs

        Field._field_counter += 1
        self._order = Field._field_counter

        super(Field, self).__init__()

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        setattr(model_class, name, FieldDescriptor(self))

    def db_value(self, value):
        return value

    def python_value(self, value):
        return value


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


class RelationDescriptor(FieldDescriptor):
    def get_object_or_id(self, instance):
        rel_id = instance._data.get(self.att_name)
        if rel_id:
            if self.att_name not in instance._obj_cache:
                # TODO: fk lookup code
                #rel_obj = self.field.rel_model.get(...)
                instance._obj_cache[self.att_name] = rel_obj
            return instance._obj_cache[self.att_name]
        return rel_id

    def __get__(self, instance, instance_type=None):
        if instance:
            return self.get_object_or_id(instance)
        return self.field

    def __set__(self, instance, value):
        if isinstance(value, Model):
            instance._data[self.att_name] = value.get_id()
            instance._obj_cache[self.att_name] = value
        else:
            instance._data[self.att_name] = value


class ReverseRelationDescriptor(object):
    def __init__(self, field):
        self.field = field
        self.related_model = field.model_class

    def __get__(self, instance, instance_type=None):
        # TODO: lookup code
        # this is blog.entry_set, so entry.select().where(blog=self)
        #query = self.field.model_class.select().where(blog=instance.id)
        return query


class ForeignKeyField(Field):
    def __init__(self, rel_model, null=False, related_name=None, cascade=False, extra=None, *args, **kwargs):
        self.rel_model = rel_model
        self.related_name = related_name
        self.cascade = cascade
        self.extra = extra

        super(ForeignKeyField, self).__init__(null=null, *args, **kwargs)

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        self.related_name = self.related_name or '%s_set' % (model_class._meta.name)

        if self.rel_model == 'self':
            self.rel_model = self.model_class

        setattr(model_class, name, RelationDescriptor(self))
        setattr(self.rel_model, self.related_name, ReverseRelationDescriptor(self))

        model_class._meta.rel[self.name] = self
        self.rel_model._meta.reverse_rel[self.name] = self

    def db_value(self, value):
        if isinstance(value, self.rel_model):
            value = value.get_id()
        return super(ForeignKeyField, self).db_value(value)


class PrimaryKeyField(Field):
    pass


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
        if q._where is not None:
            return self.parse_node(q._where, alias_map)
        return '', []

    def parse_joins(self, joins, model_class, alias_map):
        parsed = []

        def _traverse(curr):
            if curr not in joins:
                return
            for join in joins[curr]:
                from_model = curr
                to_model = join.model_class

                field = from_model._meta.rel_for_model(to_model, join.column)
                if field:
                    left_field = field.name
                    right_field = to_model._meta.id_field
                else:
                    field = to_model._meta.rel_for_model(from_model, join.column)
                    left_field = to_model._meta.id_field
                    right_field = field.name

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

    def parse_expr_list(self, s, alias_map):
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
        model = query.model_class
        alias_map = self.calculate_alias_map(query)

        parts = ['SELECT']
        params = []

        if query._distinct:
            parts.append('DISTINCT')

        selection = query._select or model._meta.get_fields()
        select, s_params = self.parse_expr_list(selection, alias_map)

        parts.append(select)
        params.extend(s_params)

        parts.append('FROM %s AS %s' % (self.quote(model._meta.db_table), alias_map[model]))

        joins = self.parse_joins(query._joins, query.model_class, alias_map)
        if joins:
            parts.append(' '.join(joins))

        where, w_params = self.parse_where(query, alias_map)
        if where:
            parts.append('WHERE %s' % where)
            params.extend(w_params)

        if query._group_by:
            group_by, g_params = self.parse_expr_list(query._group_by, alias_map)
            parts.append('GROUP BY %s' % group_by)
            params.extend(w_params)

        if query._having:
            having, h_params = self.parse_where(query, alias_map)
            parts.append('HAVING %s' % having)
            params.extend(h_params)

        if query._limit:
            parts.append('LIMIT %s' % query._limit)
        if query._offset:
            parts.append('OFFSET %s' % query._offset)

        return ' '.join(parts), params


def returns_clone(func):
    def inner(self, *args, **kwargs):
        clone = self.clone()
        func(clone, *args, **kwargs)
        return clone
    return inner


Join = namedtuple('Join', ('model_class', 'join_type', 'column'))

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
        query._query_ctx = self._query_ctx
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
        if not self._query_ctx._meta.rel_exists(model_class):
            raise ValueError('No foreign key between %s and %s' % (
                self._query_ctx, model_class,
            ))
        self._joins.setdefault(self._query_ctx, [])
        self._joins[self._query_ctx].append(Join(model_class, join_type, on))
        self._query_ctx = model_class

    @returns_clone
    def switch(self, model_class):
        self._query_ctx = model_class

    def sql(self):
        raise NotImplementedError()

    def execute(self):
        pass


class SelectQuery(Query):
    def __init__(self, model_class, *selection):
        self._select = selection
        self._group_by = None
        self._having = None
        self._limit = None
        self._offset = None
        self._distinct = False
        super(SelectQuery, self).__init__(model_class)

    def clone(self):
        query = super(SelectQuery, self).clone()
        query._select = list(self._select)
        query._limit = self._limit
        query._offset = self._offset
        if self._group_by:
            query._group_by = list(self._group_by)
        if self._having:
            query._having = self._having.clone()
        return query

    @returns_clone
    def group_by(self, *args):
        grouping = []
        for arg in args:
            if isinstance(arg, Model):
                grouping.extend(arg._meta.get_fields())
            else:
                grouping.append(arg)
        self._group_by = grouping

    @returns_clone
    def having(self, q_or_node):
        if self._having is None:
            self._having = Node(OP_AND)
        self._having &= q_or_node

    @returns_clone
    def limit(self, lim):
        self._limit = lim

    @returns_clone
    def offset(self, off):
        self._offset = off

    @returns_clone
    def distinct(self, is_distinct=True):
        self._distinct = is_distinct

    def sql(self):
        compiler = QueryCompiler()
        return compiler.parse_select_query(self)


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

class ModelOptions(object):
    def __init__(self, cls):
        self.model_class = cls
        self.name = cls.__name__.lower()
        self.fields = {}
        self.indexes = []
        self.id_field = None

        self.rel = {}
        self.reverse_rel = {}

        self.db_table = None

    def get_sorted_fields(self):
        return sorted(self.fields.items(), key=lambda (k,v): (v == self.id_field and 1 or 2, v._order))

    def get_field_names(self):
        return [f[0] for f in self.get_sorted_fields()]

    def get_fields(self):
        return [f[1] for f in self.get_sorted_fields()]

    def rel_for_model(self, model, name=None):
        for field in self.get_fields():
            if isinstance(field, ForeignKeyField) and field.rel_model == model:
                if name is None or name == field.name:
                    return field

    def reverse_rel_for_model(self, model):
        return model._meta.rel_for_model(self.model_class)

    def rel_exists(self, model):
        return self.rel_for_model(model) or self.reverse_rel_for_model(model)


class BaseModel(type):
    def __new__(cls, name, bases, attrs):
        if not bases:
            return super(BaseModel, cls).__new__(cls, name, bases, attrs)

        # inherit any field descriptors by deep copying the underlying field obj
        # into the attrs of the new model
        for b in bases:
            for (k, v) in b.__dict__.items():
                if isinstance(v, FieldDescriptor) and k not in attrs:
                    attrs[k] = deepcopy(v.field)

        # initialize the new class and set the magic attributes
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        cls._meta = ModelOptions(cls)
        cls._data = None

        id_field = None

        # replace the fields with field descriptors
        for name, attr in cls.__dict__.items():
            if isinstance(attr, Field):
                attr.add_to_class(cls, name)
                cls._meta.fields[attr.name] = attr
                if attr.index:
                    cls._meta.indexes.append(attr.name)
            if isinstance(attr, PrimaryKeyField):
                id_field = attr

        if not id_field:
            id_field = PrimaryKeyField()
            id_field.add_to_class(cls, 'id')

        cls._meta.id_field = id_field.name
        cls._meta.db_table = re.sub('[^\w]+', '_', cls.__name__.lower())

        return cls


class Model(object):
    __metaclass__ = BaseModel

    def __init__(self, *args, **kwargs):
        self._data = {} # attributes
        self._obj_cache = {} # cache of related objects
        for key, value in kwargs.iteritems():
            setattr(self, key, value)


if __name__ == '__main__':
    class Blog(Model):
        title = Field()
        pub_date= Field()
        votes = Field()

    class Entry(Model):
        blog = ForeignKeyField(Blog)
        headline = Field()
        content = Field()

    q = SelectQuery(Blog)
    qc = QueryCompiler()
    q = q.where((Blog.title == 'alpha') | (Blog.title == 'bravo'))
    q = q.where(Blog.votes - 10 == Blog.pub_date)
    print qc.parse_node(q._where)
    print q.sql()

    q = SelectQuery(Entry)
    q = q.join(Blog)
    q = q.where((Entry.headline=='headline') | (Blog.title == 'titttle'))
    print q.sql()

    class A(Model):
        a_field = Field()
    class B(Model):
        a = ForeignKeyField(A)
        b_field = Field()
    class B2(Model):
        a = ForeignKeyField(A)
        b2_field = Field()
    class C(Model):
        b = ForeignKeyField(B)
        c_field = Field()

    q = SelectQuery(C).join(B).join(A).join(B2).where(
        (A.a_field == 'a') | (B.b_field == 'b')
    )
    print q.sql()

    q = SelectQuery(A).join(B).switch(A)
    q = q.join(B2)
    q = q.switch(B)
    q = q.join(C).where(
        (A.a_field=='a') | (B2.b2_field=='bbb222')
    )
    print q.sql()
    #q = SelectQuery(None)
    #q = q.where(fn.SUBSTR(fn.LOWER(f1), 0, 1) == 'b')
    #print qc.parse_node(q._where)
    #q = SelectQuery(None, f1, f2, (f1+1).set_alias('baz'))
    #print qc.parse_select(q._select, None)
    #sq = SelectQuery('a', f1, f2, (f1 + 10).set_alias('f1plusten'))
    #sq = sq.join('b').join('c').switch('a').join('b2')
    #sq = sq.where((f1 == 'b') | (f2 == 'c'))
    #sq.sql()
