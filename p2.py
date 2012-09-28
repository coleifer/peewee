from __future__ import with_statement
import datetime
import decimal
import logging
import os
import re
import threading
import time
from collections import namedtuple
from copy import deepcopy

try:
    import sqlite3
except ImportError:
    sqlite3 = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import MySQLdb as mysql
except ImportError:
    mysql = None

class ImproperlyConfigured(Exception):
    pass

if sqlite3 is None and psycopg2 is None and mysql is None:
    raise ImproperlyConfigured('Either sqlite3, psycopg2 or MySQLdb must be installed')

if sqlite3:
    sqlite3.register_adapter(decimal.Decimal, str)
    sqlite3.register_adapter(datetime.date, str)
    sqlite3.register_adapter(datetime.time, str)
    sqlite3.register_converter('decimal', lambda v: decimal.Decimal(v))

if psycopg2:
    import psycopg2.extensions
    psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
    psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

logger = logging.getLogger('peewee.logger')

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
OP_LIKE = 8

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
    __mod__ = _q(OP_LIKE)


class BinaryExpr(Expr):
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        super(BinaryExpr, self).__init__()


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
    db_field = 'unknown'
    template = '%(column_type)s'

    def __init__(self, null=False, index=False, unique=False, verbose_name=None,
                 help_text=None, db_column=None, default=None, choices=None,
                 primary_key=False, *args, **kwargs):
        self.null = null
        self.index = index
        self.unique = unique
        self.verbose_name = verbose_name
        self.help_text = help_text
        self.db_column = db_column
        self.default = default
        self.choices = choices
        self.primary_key = primary_key

        self.attributes = self.field_attributes()
        self.attributes.update(kwargs)

        Field._field_counter += 1
        self._order = Field._field_counter

        super(Field, self).__init__()

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        self.db_column = self.db_column or self.name
        setattr(model_class, name, FieldDescriptor(self))

    def field_attributes(self):
        return {}

    def get_db_field(self):
        return self.db_field

    def coerce(self, value):
        return value

    def db_value(self, value):
        return value if value is None else self.coerce(value)

    def python_value(self, value):
        return value if value is None else self.coerce(value)


class IntegerField(Field):
    db_field = 'int'

    def coerce(self, value):
        return int(value)

class BigIntegerField(IntegerField):
    db_field = 'bigint'

class PrimaryKeyField(IntegerField):
    db_field = 'primary_key'

    def __init__(self, *args, **kwargs):
        kwargs['primary_key'] = True
        super(PrimaryKeyField, self).__init__(*args, **kwargs)


class FloatField(Field):
    db_field = 'float'

    def coerce(self, value):
        return float(value)

class DoubleField(FloatField):
    db_field = 'double'

class DecimalField(Field):
    db_field = 'decimal'
    template = '%(column_type)s(%(max_digits)d, %(decimal_places)d)'

    def field_attributes(self):
        return {
            'max_digits': 10,
            'decimal_places': 5,
            'auto_round': False,
            'rounding': decimal.DefaultContext.rounding,
        }

    def db_value(self, value):
        D = decimal.Decimal
        if not value:
            return value if value is None else D(0)
        if self.attributes['auto_round']:
            exp = D(10)**(-self.attributes['decimal_places'])
            return D(str(value)).quantize(exp, rounding=self.attributes['rounding'])
        return value

    def python_value(self, value):
        if value is not None:
            if isinstance(value, decimal.Decimal):
                return value
            return decimal.Decimal(str(value))

class CharField(Field):
    db_field = 'string'
    template = '%(column_type)s(%(max_length)s)'

    def field_attributes(self):
        return {'max_length': 255}

    def coerce(self, value):
        value = unicode(value or '')
        return value[:self.attributes['max_length']]

class TextField(Field):
    db_field = 'text'

    def coerce(self, value):
        return unicode(value or '')

def format_date_time(value, formats, post_process=None):
    post_process = post_process or (lambda x: x)
    for fmt in formats:
        try:
            return post_process(datetime.datetime.strptime(value, fmt))
        except ValueError:
            pass
    return value

class DateTimeField(Field):
    db_field = 'datetime'

    def field_attributes(self):
        return {
            'formats': [
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
            ]
        }

    def python_value(self, value):
        if value and isinstance(value, basestring):
            return format_date_time(value, self.attributes['formats'])
        return value

class DateField(Field):
    db_field = 'date'

    def field_attributes(self):
        return {
            'formats': [
                '%Y-%m-%d',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
            ]
        }

    def python_value(self, value):
        if value and isinstance(value, basestring):
            pp = lambda x: x.date()
            return format_date_time(value, self.attributes['formats'], pp)
        elif value and isinstance(value, datetime.datetime):
            return value.date()
        return value

class TimeField(Field):
    db_field = 'time'

    def field_attributes(self):
        return {
            'formats': [
                '%H:%M:%S.%f',
                '%H:%M:%S',
                '%H:%M',
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S',
            ]
        }

    def python_value(self, value):
        if value and isinstance(value, basestring):
            pp = lambda x: x.time()
            return format_date_time(value, self.attributes['formats'], pp)
        elif value and isinstance(value, datetime.datetime):
            return value.time()
        return value

class BooleanField(Field):
    db_field = 'bool'

    def coerce(self, value):
        return bool(value)


class RelationDescriptor(FieldDescriptor):
    def __init__(self, field, rel_model):
        self.rel_model = rel_model
        super(RelationDescriptor, self).__init__(field)

    def get_object_or_id(self, instance):
        rel_id = instance._data.get(self.att_name)
        if rel_id:
            if self.att_name not in instance._obj_cache:
                obj = self.rel_model.get(self.rel_model._meta.primary_key==rel_id)
                instance._obj_cache[self.att_name] = obj
            return instance._obj_cache[self.att_name]
        elif not self.field.null:
            raise RelModel.DoesNotExist
        return rel_id

    def __get__(self, instance, instance_type=None):
        if instance:
            return self.get_object_or_id(instance)
        return self.field

    def __set__(self, instance, value):
        if isinstance(value, self.rel_model):
            instance._data[self.att_name] = value.get_id()
            instance._obj_cache[self.att_name] = value
        else:
            instance._data[self.att_name] = value


class ReverseRelationDescriptor(object):
    def __init__(self, field):
        self.field = field
        self.related_model = field.model_class

    def __get__(self, instance, instance_type=None):
        return self.related_model.select().where(self.field==instance.get_id())


class ForeignKeyField(Field):
    def __init__(self, rel_model, null=False, related_name=None, cascade=False, extra=None, *args, **kwargs):
        self.rel_model = rel_model
        self.related_name = related_name
        self.cascade = cascade
        self.extra = extra

        kwargs.update(dict(
            cascade='ON DELETE CASCADE' if self.cascade else '',
            extra=extra or '',
        ))

        super(ForeignKeyField, self).__init__(null=null, *args, **kwargs)

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        self.db_column = self.db_column or '%s_id' % self.name

        self.related_name = self.related_name or '%s_set' % (model_class._meta.name)

        if self.rel_model == 'self':
            self.rel_model = self.model_class

        setattr(model_class, name, RelationDescriptor(self, self.rel_model))
        setattr(self.rel_model, self.related_name, ReverseRelationDescriptor(self))

        model_class._meta.rel[self.name] = self
        self.rel_model._meta.reverse_rel[self.name] = self

    def get_db_field(self):
        to_pk = self.rel_model._meta.primary_key
        return to_pk.get_db_field()

    def db_value(self, value):
        if isinstance(value, self.rel_model):
            value = value.get_id()
        return self.rel_model._meta.primary_key.db_value(value)


class QueryCompiler(object):
    field_map = {
        'int': 'INTEGER',
        'bigint': 'INTEGER',
        'float': 'REAL',
        'double': 'REAL',
        'decimal': 'DECIMAL',
        'string': 'VARCHAR',
        'text': 'TEXT',
        'datetime': 'DATETIME',
        'date': 'DATE',
        'time': 'TIME',
        'bool': 'SMALLINT',
        'primary_key': 'INTEGER',
    }

    q_op_map = {
        OP_EQ: '=',
        OP_LT: '<',
        OP_LTE: '<=',
        OP_GT: '>',
        OP_GTE: '>=',
        OP_NE: '!=',
        OP_IN: 'IN',
        OP_ISNULL: 'IS NULL',
        OP_LIKE: 'LIKE',
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

    def __init__(self, quote_char='"', interpolation='?', field_map_overrides=None):
        self.quote_char = quote_char
        self.interpolation = interpolation
        self.field_map_overrides = field_map_overrides or {}

    def quote(self, s):
        return ''.join((self.quote_char, s, self.quote_char))

    def _add_alias(self, expr_str, expr):
        if expr.alias:
            expr_str = ' '.join((expr_str, 'as', expr.alias))
        return expr_str

    def _max_alias(self, am):
        max_alias = 0
        if am:
            for a in am.values():
                i = int(a.lstrip('t'))
                if i > max_alias:
                    max_alias = i
        return max_alias + 1

    def parse_expr(self, expr, alias_map=None):
        if isinstance(expr, BinaryExpr):
            lhs, lparams = self.parse_expr(expr.lhs, alias_map)
            rhs, rparams = self.parse_expr(expr.rhs, alias_map)
            expr_str = '(%s %s %s)' % (lhs, self.expr_op_map[expr.op], rhs)
            return self._add_alias(expr_str, expr), lparams + rparams
        if isinstance(expr, Field):
            expr_str = self.quote(expr.db_column)
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
        elif isinstance(expr, SelectQuery):
            max_alias = self._max_alias(alias_map)
            clone = expr.clone()
            clone._select = (clone.model_class._meta.primary_key,)
            subselect, params = self.parse_select_query(clone, max_alias)
            return '(%s)' % subselect, params
        elif isinstance(expr, (list, tuple)):
            expr_str = '(%s)' % ','.join(self.interpolation for i in range(len(expr)))
            return expr_str, expr
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

    def parse_query_node(self, qnode, alias_map):
        if qnode is not None:
            return self.parse_node(qnode, alias_map)
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
                    left_field = field.db_column
                    right_field = to_model._meta.primary_key.db_column
                else:
                    field = to_model._meta.rel_for_model(from_model, join.column)
                    left_field = to_model._meta.primary_key.db_column
                    right_field = field.db_column

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

    def parse_select_query(self, query, start=1):
        model = query.model_class
        alias_map = self.calculate_alias_map(query, start)

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

        where, w_params = self.parse_query_node(query._where, alias_map)
        if where:
            parts.append('WHERE %s' % where)
            params.extend(w_params)

        if query._group_by:
            group_by, g_params = self.parse_expr_list(query._group_by, alias_map)
            parts.append('GROUP BY %s' % group_by)
            params.extend(g_params)

        if query._having:
            having, h_params = self.parse_query_node(query._having, alias_map)
            parts.append('HAVING %s' % having)
            params.extend(h_params)

        if query._limit:
            parts.append('LIMIT %s' % query._limit)
        if query._offset:
            parts.append('OFFSET %s' % query._offset)

        return ' '.join(parts), params

    def _parse_field_dictionary(self, d):
        sets, params = [], []
        for field, expr in d.items():
            field_str, _ = self.parse_expr(field)
            val_str, val_params = self.parse_expr(expr)
            sets.append((field_str, val_str))
            params.extend(val_params)
        return sets, params

    def parse_update_query(self, query):
        model = query.model_class

        parts = ['UPDATE %s SET' % self.quote(model._meta.db_table)]
        sets, params = self._parse_field_dictionary(query._update)

        parts.append(', '.join('%s=%s' % (f, v) for f, v in sets))

        where, w_params = self.parse_query_node(query._where, None)
        if where:
            parts.append('WHERE %s' % where)
            params.extend(w_params)
        return ' '.join(parts), params

    def parse_insert_query(self, query):
        model = query.model_class

        parts = ['INSERT INTO %s' % self.quote(model._meta.db_table)]
        sets, params = self._parse_field_dictionary(query._insert)

        parts.append('(%s)' % ', '.join(s[0] for s in sets))
        parts.append('VALUES (%s)' % ', '.join(s[1] for s in sets))

        return ' '.join(parts), params

    def parse_delete_query(self, query):
        model = query.model_class

        parts = ['DELETE FROM %s' % self.quote(model._meta.db_table)]
        params = []

        where, w_params = self.parse_query_node(query._where, None)
        if where:
            parts.append('WHERE %s' % where)
            params.extend(w_params)

        return ' '.join(parts), params

    def get_field_type(self, field):
        f_map = dict(self.field_map)
        f_map.update(self.field_map_overrides)
        return f_map[field.get_db_field()]

    def field_sql(self, field):
        attrs = field.attributes
        attrs['column_type'] = self.get_field_type(field)
        parts = [self.quote(field.db_column), field.template]
        if not field.null:
            parts.append('NOT NULL')
        if field.primary_key:
            parts.append('PRIMARY KEY')
        if isinstance(field, ForeignKeyField):
            ref_mc = (
                self.quote(field.rel_model._meta.db_table),
                self.quote(field.rel_model._meta.primary_key.db_column),
            )
            parts.append('REFERENCES %s (%s)' % ref_mc)
            parts.append('%(cascade)s%(extra)s')
        return ' '.join(p % attrs for p in parts)

    def create_table(self, model_class, safe=False):
        parts = ['CREATE TABLE']
        if safe:
            parts.append('IF NOT EXISTS')
        parts.append(self.quote(model_class._meta.db_table))
        columns = ', '.join(self.field_sql(f) for f in model_class._meta.get_fields())
        parts.append('(%s)' % columns)
        return ' '.join(parts)


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
        self.database = model_class._meta.database

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

    def sql(self, compiler):
        raise NotImplementedError()

    def execute(self):
        return self.database.execute(self)


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
            if isinstance(arg, Field):
                grouping.append(arg)
            elif issubclass(arg, Model):
                grouping.extend(arg._meta.get_fields())
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

    def sql(self, compiler):
        return compiler.parse_select_query(self)

def not_allowed(fn):
    def inner(self, *args, **kwargs):
        raise NotImplementedError('%s is not allowed on %s instances' % (
            fn, type(self).__name__,
        ))
    return inner

class UpdateQuery(Query):
    def __init__(self, model_class, update=None):
        self._update = update
        super(UpdateQuery, self).__init__(model_class)

    def clone(self):
        query = super(UpdateQuery, self).clone()
        query._update = dict(self._update)
        return query

    join = not_allowed('joining')

    def sql(self, compiler):
        return compiler.parse_update_query(self)

class InsertQuery(Query):
    def __init__(self, model_class, insert=None):
        self._insert = insert
        super(InsertQuery, self).__init__(model_class)

    def clone(self):
        query = super(InsertQuery, self).clone()
        query._insert = dict(self._insert)
        return query

    join = not_allowed('joining')
    where = not_allowed('where clause')

    def sql(self, compiler):
        return compiler.parse_insert_query(self)

class DeleteQuery(Query):
    join = not_allowed('joining')

    def sql(self, compiler):
        return compiler.parse_delete_query(self)


class Database(object):
    field_overrides = {}
    for_update = False
    interpolation = '?'
    quote_char = '"'
    reserved_tables = []
    sequences = False
    subquery_delete_same_table = True

    def __init__(self, database, threadlocals=False, autocommit=True, **connect_kwargs):
        self.init(database, **connect_kwargs)

        if threadlocals:
            self.__local = threading.local()
        else:
            self.__local = type('DummyLocal', (object,), {})

        self._conn_lock = threading.Lock()
        self.autocommit = autocommit

    def init(self, database, **connect_kwargs):
        self.deferred = database is None
        self.database = database
        self.connect_kwargs = connect_kwargs

    def connect(self):
        with self._conn_lock:
            if self.deferred:
                raise Exception('Error, database not properly initialized before opening connection')
            self.__local.conn = self._connect(self.database, **self.connect_kwargs)
            self.__local.closed = False

    def close(self):
        with self._conn_lock:
            if self.deferred:
                raise Exception('Error, database not properly initialized before closing connection')
            self._close(self.__local.conn)
            self.__local.closed = True

    def get_conn(self):
        if not hasattr(self.__local, 'closed') or self.__local.closed:
            self.connect()
        return self.__local.conn

    def is_closed(self):
        return getattr(self.__local, 'closed', True)

    def get_cursor(self):
        return self.get_conn().cursor()

    def _connect(self, database, **kwargs):
        raise NotImplementedError

    def close(self, conn):
        return conn.close()

    def last_insert_id(self, cursor, model):
        return cursor.lastrowid

    def rows_affected(self, cursor):
        return cursor.rowcount

    def get_compiler(self):
        return QueryCompiler(self.quote_char, self.interpolation, self.field_overrides)

    def execute(self, query):
        sql, params = query.sql(self.get_compiler())
        return sql, params

    def execute_sql(self, sql, params=None, require_commit=True):
        cursor = self.get_cursor()
        res = cursor.execute(sql, params or ())
        if require_commit and self.get_autocommit():
            self.commit()
        logger.debug((sql, params))
        return cursor

    def begin(self):
        pass

    def commit(self):
        self.get_conn().commit()

    def rollback(self):
        self.get_conn().rollback()

    def set_autocommit(self, autocommit):
        self.__local.autocommit = autocommit

    def get_autocommit(self):
        if not hasattr(self.__local, 'autocommit'):
            self.set_autocommit(self.autocommit)
        return self.__local.autocommit


class SqliteDatabase(Database):
    def _connect(self, database, **kwargs):
        if not sqlite3:
            raise ImproperlyConfigured('sqlite3 must be installed on the system')
        return sqlite3.connect(database, **kwargs)


class PostgresqlDatabase(Database):
    field_overrides = {
        'bigint': 'BIGINT',
        'boolean': 'BOOLEAN',
        'datetime': 'TIMESTAMP',
        'decimal': 'NUMERIC',
        'double': 'DOUBLE PRECISION',
        'primary_key': 'SERIAL',
    }
    for_update = True
    reserved_tables = ['user']
    sequences = True

    def _connect(self, database, **kwargs):
        if not psycopg2:
            raise ImproperlyConfigured('psycopg2 must be installed on the system')
        return psycopg2.connect(database=database, **kwargs)

    def last_insert_id(self, cursor, model):
        if model._meta.pk_sequence:
            cursor.execute("SELECT CURRVAL('\"%s\"')" % (
                model._meta.pk_sequence))
        else:
            cursor.execute("SELECT CURRVAL('\"%s_%s_seq\"')" % (
                model._meta.db_table, model._meta.pk_col))
        return cursor.fetchone()[0]


class MySQLDatabase(Database):
    field_overrides = {
        'bigint': 'BIGINT',
        'boolean': 'BOOL',
        'decimal': 'NUMERIC',
        'double': 'DOUBLE PRECISION',
        'float': 'FLOAT',
        'primary_key': 'INTEGER AUTO_INCREMENT',
        'text': 'LONGTEXT',
    }
    for_update_support = True
    quote_char = '`'
    subquery_delete_same_table = False

    def _connect(self, database, **kwargs):
        if not mysql:
            raise ImproperlyConfigured('MySQLdb must be installed on the system')
        conn_kwargs = {
            'charset': 'utf8',
            'use_unicode': True,
        }
        conn_kwargs.update(kwargs)
        return mysql.connect(db=database, **conn_kwargs)


class DoesNotExist(Exception):
    pass


default_database = SqliteDatabase('peewee.db')


class ModelOptions(object):
    def __init__(self, cls, database=None, db_table=None, indexes=None,
                 ordering=None, pk_sequence=None, primary_key=None):
        self.model_class = cls
        self.name = cls.__name__.lower()
        self.fields = {}

        self.database = database or default_database
        self.db_table = db_table
        self.indexes = indexes or []
        self.ordering = ordering
        self.pk_sequence = pk_sequence
        self.primary_key = primary_key

        self.rel = {}
        self.reverse_rel = {}

    def get_sorted_fields(self):
        return sorted(self.fields.items(), key=lambda (k,v): (v == self.primary_key and 1 or 2, v._order))

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
    inheritable_options = ['database', 'indexes', 'ordering', 'primary_key', 'pk_sequence']

    def __new__(cls, name, bases, attrs):
        if not bases:
            return super(BaseModel, cls).__new__(cls, name, bases, attrs)

        meta_options = {}
        meta = attrs.pop('Meta', None)
        if meta:
            meta_options.update((k, v) for k, v in meta.__dict__.items() if not k.startswith('_'))

        # inherit any field descriptors by deep copying the underlying field obj
        # into the attrs of the new model, additionally see if the bases define
        # inheritable model options and swipe them
        for b in bases:
            if not hasattr(b, '_meta'):
                continue

            base_meta = getattr(b, '_meta')
            for (k, v) in base_meta.__dict__.items():
                if k in cls.inheritable_options and k not in meta_options:
                    meta_options[k] = v

            for (k, v) in b.__dict__.items():
                if isinstance(v, FieldDescriptor) and k not in attrs:
                    if not v.field.primary_key:
                        attrs[k] = deepcopy(v.field)

        # initialize the new class and set the magic attributes
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        cls._meta = ModelOptions(cls, **meta_options)
        cls._data = None

        primary_key = None

        # replace the fields with field descriptors, calling the add_to_class hook
        for name, attr in cls.__dict__.items():
            if isinstance(attr, Field):
                attr.add_to_class(cls, name)
                cls._meta.fields[attr.name] = attr
                if attr.index:
                    cls._meta.indexes.append(attr.name)
                if attr.primary_key:
                    primary_key = attr

        if not primary_key:
            primary_key = PrimaryKeyField(primary_key=True)
            primary_key.add_to_class(cls, 'id')
            cls._meta.fields['id'] = primary_key

        cls._meta.primary_key = primary_key
        cls._meta.db_table = re.sub('[^\w]+', '_', cls.__name__.lower())

        # create a repr and error class before finalizing
        if hasattr(cls, '__unicode__'):
            setattr(cls, '__repr__', lambda self: '<%s: %r>' % (
                cls.__name__, self.__unicode__()))

        exception_class = type('%sDoesNotExist' % cls.__name__, (DoesNotExist,), {})
        cls.DoesNotExist = exception_class

        return cls


class Model(object):
    __metaclass__ = BaseModel

    def __init__(self, *args, **kwargs):
        self._data = {} # attributes
        self._obj_cache = {} # cache of related objects
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

    @classmethod
    def select(cls, *selection):
        return SelectQuery(cls, *selection)

    @classmethod
    def update(cls, **update):
        return UpdateQuery(cls, **update)

    @classmethod
    def insert(cls, **insert):
        return InsertQuery(cls, **insert)

    @classmethod
    def delete(cls):
        return DeleteQuery(cls)

    def get_id(self):
        return getattr(self, self._meta.id_field.name)

    def set_id(self, id):
        setattr(self, self._meta.id_field.name, id)


if __name__ == '__main__':
    class Blog(Model):
        title = CharField()
        pub_date= DateTimeField()
        votes = IntegerField(null=True)

    class Entry(Model):
        blog = ForeignKeyField(Blog)
        headline = CharField()
        content = TextField()

    q = SelectQuery(Blog)
    qc = QueryCompiler()
    q = q.where((Blog.title == 'alpha') | (Blog.title == 'bravo'))
    q = q.where(Blog.votes - 10 == Blog.pub_date)
    print qc.parse_node(q._where)
    print q.sql(qc)

    q = SelectQuery(Entry)
    q = q.join(Blog)
    q = q.where((Entry.headline=='headline') | (Blog.title == 'titttle'))
    print q.sql(qc)
    print

    class A(Model):
        a_field = CharField()
    class B(Model):
        a = ForeignKeyField(A)
        b_field = CharField()
    class B2(Model):
        a = ForeignKeyField(A)
        b2_field = CharField()
    class C(Model):
        b = ForeignKeyField(B)
        c_field = CharField()

    q = SelectQuery(C).join(B).join(A).join(B2).where(
        (A.a_field == 'a') | (B.b_field == 'b')
    )
    print q.sql(qc)
    print

    q = SelectQuery(A).join(B).switch(A)
    q = q.join(B2)
    q = q.switch(B)
    q = q.join(C).where(
        (A.a_field=='a') | (B2.b2_field=='bbb222')
    )
    q = q.limit(10).offset(100)
    print q.sql(qc)
    print

    q = q.group_by(B).having((B.b_field > 'bfasd'))
    print q.sql(qc)
    print

    q = UpdateQuery(B, {B.b_field: 'bz', B.a: 'a'}).where(B.id > 3)
    print q.sql(qc)
    print

    q = InsertQuery(B, {B.b_field: 'bnew', B.a: 'anew'})
    print q.sql(qc)
    print

    q = DeleteQuery(B).where((B.b_field < 'blt') & (B.a > 'agt'))
    print q.sql(qc)
    print

    q = SelectQuery(A).where(A.id << [1, 2, 3]).where(A.a_field == 'af')
    print q.sql(qc)
    print

    q = SelectQuery(A).join(B).where(B.id << SelectQuery(B).where(B.b_field=='hurb'))
    print q.sql(qc)

    db = Database('')
    print
    print db.execute(q)

    print '--------------------------------'
    print qc.create_table(Blog)
    print qc.create_table(Entry)
    #q = SelectQuery(None)
    #q = q.where(fn.SUBSTR(fn.LOWER(f1), 0, 1) == 'b')
    #print qc.parse_node(q._where)
    #q = SelectQuery(None, f1, f2, (f1+1).set_alias('baz'))
    #print qc.parse_select(q._select, None)
    #sq = SelectQuery('a', f1, f2, (f1 + 10).set_alias('f1plusten'))
    #sq = sq.join('b').join('c').switch('a').join('b2')
    #sq = sq.where((f1 == 'b') | (f2 == 'c'))
    #sq.sql()
