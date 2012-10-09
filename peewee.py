#     (\
#     (  \  /(o)\     caw!
#     (   \/  ()/ /)
#      (   `;.))'".)
#       `(/////.-'
#    =====))=))===()
#      ///'
#     //
#    '
from __future__ import with_statement
import datetime
import decimal
import logging
import os
import re
import threading
import time
from collections import deque, namedtuple
from copy import deepcopy

__all__ = [
    'IntegerField', 'BigIntegerField', 'PrimaryKeyField', 'FloatField', 'DoubleField',
    'DecimalField', 'CharField', 'TextField', 'DateTimeField', 'DateField', 'TimeField',
    'BooleanField', 'ForeignKeyField', 'Model', 'DoesNotExist', 'ImproperlyConfigured',
    'Q', 'DQ', 'fn', 'SqliteDatabase', 'MySQLDatabase', 'PostgresqlDatabase', 'Field',
    'JOIN_LEFT_OUTER', 'JOIN_INNER', 'JOIN_FULL',
]

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
OP_IS = 7
OP_LIKE = 8
OP_ILIKE = 9

DJANGO_MAP = {
    'eq': OP_EQ,
    'lt': OP_LT,
    'lte': OP_LTE,
    'gt': OP_GT,
    'gte': OP_GTE,
    'ne': OP_NE,
    'in': OP_IN,
    'is': OP_IS,
    'like': OP_LIKE,
    'ilike': OP_ILIKE,
}

JOIN_INNER = 1
JOIN_LEFT_OUTER = 2
JOIN_FULL = 3

def dict_update(orig, extra):
    new = {}
    new.update(orig)
    new.update(extra)
    return new


class Node(object):
    def __init__(self, connector, children=None, negated=False):
        self.connector = connector
        self.children = children or []
        self.negated = negated

    def connect(self, rhs, connector):
        if isinstance(rhs, Leaf):
            if connector == self.connector and rhs.negated == self.negated:
                self.children.append(rhs)
                return self
        elif isinstance(rhs, Node):
            if connector == self.connector and connector == rhs.connector and rhs.negated == self.negated:
                self.children.extend(rhs.children)
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
    def __init__(self, lhs, op, rhs, negated=False):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        self.negated = negated
        super(Q, self).__init__()

    def clone(self):
        return Q(self.lhs, self.op, self.rhs, self.negated)


class DQ(Leaf):
    def __init__(self, **query):
        self.query = query
        super(DQ, self).__init__()

    def clone(self):
        return DQ(**self.query)


class Expr(object):
    def __init__(self):
        self._alias = None

    def alias(self, a=None):
        self._alias = a
        return self

    def asc(self):
        return Ordering(self, True)

    def desc(self):
        return Ordering(self, False)

    def _expr(op, n=False, inv=False):
        def inner(self, value):
            lhs, rhs = (self, value) if not inv else (value, self)
            return BinaryExpr(lhs, op, rhs)
        return inner

    __add__ = _expr(OP_ADD)
    __sub__ = _expr(OP_SUB)
    __mul__ = _expr(OP_MUL)
    __div__ = _expr(OP_DIV)
    __and__ = _expr(OP_AND)
    __or__ = _expr(OP_OR)
    __xor__ = _expr(OP_XOR)
    __radd__ = _expr(OP_ADD, inv=True)
    __rsub__ = _expr(OP_SUB, inv=True)
    __rmul__ = _expr(OP_MUL, inv=True)
    __rdiv__ = _expr(OP_DIV, inv=True)
    __rand__ = _expr(OP_AND, inv=True)
    __ror__ = _expr(OP_OR, inv=True)
    __rxor__ = _expr(OP_XOR, inv=True)

    def _q(op):
        def inner(self, value):
            return Q(self, op, value)
        return inner

    __eq__ = _q(OP_EQ)
    __lt__ = _q(OP_LT)
    __le__ = _q(OP_LTE)
    __gt__ = _q(OP_GT)
    __ge__ = _q(OP_GTE)
    __ne__ = _q(OP_NE)
    __lshift__ = _q(OP_IN)
    __rshift__ = _q(OP_IS)
    __mod__ = _q(OP_LIKE)
    __pow__ = _q(OP_ILIKE)


class BinaryExpr(Expr):
    def __init__(self, lhs, op, rhs):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        super(BinaryExpr, self).__init__()


class Param(Expr):
    def __init__(self, data):
        self.data = data


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


Ordering = namedtuple('Ordering', ('param', 'asc'))
R = namedtuple('R', ('value',))


class Field(Expr):
    _field_counter = 0
    _order = 0
    db_field = 'unknown'
    template = '%(column_type)s'

    def __init__(self, null=False, index=False, unique=False, verbose_name=None,
                 help_text=None, db_column=None, default=None, choices=None,
                 primary_key=False, sequence=None, *args, **kwargs):
        self.null = null
        self.index = index
        self.unique = unique
        self.verbose_name = verbose_name
        self.help_text = help_text
        self.db_column = db_column
        self.default = default
        self.choices = choices
        self.primary_key = primary_key
        self.sequence = sequence

        self.attributes = self.field_attributes()
        self.attributes.update(kwargs)

        Field._field_counter += 1
        self._order = Field._field_counter

        super(Field, self).__init__()

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        self.db_column = self.db_column or self.name
        self.verbose_name = self.verbose_name or re.sub('_+', ' ', name).title()

        model_class._meta.fields[self.name] = self
        model_class._meta.columns[self.db_column] = self
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
        if rel_id or self.att_name in instance._obj_cache:
            if self.att_name not in instance._obj_cache:
                obj = self.rel_model.get(self.rel_model._meta.primary_key==rel_id)
                instance._obj_cache[self.att_name] = obj
            return instance._obj_cache[self.att_name]
        elif not self.field.null:
            raise self.rel_model.DoesNotExist
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
        self.rel_model = field.model_class

    def __get__(self, instance, instance_type=None):
        if instance:
            return self.rel_model.select().where(self.field==instance.get_id())
        return self


class ForeignKeyField(IntegerField):
    def __init__(self, rel_model, null=False, related_name=None, cascade=False, extra=None, *args, **kwargs):
        self.rel_model = rel_model
        self._related_name = related_name
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
        self.verbose_name = self.verbose_name or re.sub('_+', ' ', name).title()

        model_class._meta.fields[self.name] = self
        model_class._meta.columns[self.db_column] = self

        self.related_name = self._related_name or '%s_set' % (model_class._meta.name)

        if self.rel_model == 'self':
            self.rel_model = self.model_class

        setattr(model_class, name, RelationDescriptor(self, self.rel_model))
        setattr(self.rel_model, self.related_name, ReverseRelationDescriptor(self))

        model_class._meta.rel[self.name] = self
        self.rel_model._meta.reverse_rel[self.related_name] = self

    def get_db_field(self):
        to_pk = self.rel_model._meta.primary_key
        if not isinstance(to_pk, PrimaryKeyField):
            return to_pk.get_db_field()
        return super(ForeignKeyField, self).get_db_field()

    def coerce(self, value):
        return self.rel_model._meta.primary_key.coerce(value)

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
        OP_IS: 'IS',
        OP_LIKE: 'LIKE',
        OP_ILIKE: 'ILIKE',
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

    def __init__(self, quote_char='"', interpolation='?', field_overrides=None,
                 q_overrides=None, expr_overrides=None):
        self.quote_char = quote_char
        self.interpolation = interpolation
        self._field_map = dict_update(self.field_map, field_overrides or {})
        self._op_map = dict_update(self.q_op_map, q_overrides or {})
        self._expr_map = dict_update(self.expr_op_map, expr_overrides or {})

    def quote(self, s):
        return ''.join((self.quote_char, s, self.quote_char))

    def get_field(self, f):
        return self._field_map[f]

    def get_op(self, q):
        return self._op_map[q]

    def get_expr(self, expr):
        return self._expr_map[expr]

    def _add_alias(self, expr_str, expr):
        if expr._alias:
            expr_str = ' '.join((expr_str, 'AS', expr._alias))
        return expr_str

    def _max_alias(self, am):
        max_alias = 0
        if am:
            for a in am.values():
                i = int(a.lstrip('t'))
                if i > max_alias:
                    max_alias = i
        return max_alias + 1

    def _parse_field(self, field, alias_map):
        expr_str = self.quote(field.db_column)
        if alias_map and field.model_class in alias_map:
            expr_str = '.'.join((alias_map[field.model_class], expr_str))
        return self._add_alias(expr_str, field), []

    def parse_expr(self, expr, alias_map=None):
        if isinstance(expr, BinaryExpr):
            lhs, lparams = self.parse_expr(expr.lhs, alias_map)
            rhs, rparams = self.parse_expr(expr.rhs, alias_map)
            expr_str = '(%s %s %s)' % (lhs, self.get_expr(expr.op), rhs)
            return self._add_alias(expr_str, expr), lparams + rparams
        if isinstance(expr, Field):
            return self._parse_field(expr, alias_map)
        elif isinstance(expr, Ordering):
            expr_str, params = self.parse_expr(expr.param, alias_map)
            expr_str += ' ASC' if expr.asc else ' DESC'
            return expr_str, params
        elif isinstance(expr, Func):
            scalars = []
            exprs = []
            for p in expr.params:
                parsed, params = self.parse_expr(p, alias_map)
                exprs.append(parsed)
                scalars.extend(params)
            expr_str = '%s(%s)' % (expr.fn_name, ', '.join(exprs))
            return self._add_alias(expr_str, expr), scalars
        elif isinstance(expr, R):
            return expr.value, []
        elif isinstance(expr, Param):
            return self.interpolation, [expr.data]
        elif isinstance(expr, SelectQuery):
            max_alias = self._max_alias(alias_map)
            clone = expr.clone()
            clone._select = (clone.model_class._meta.primary_key,)
            subselect, params = self.parse_select_query(clone, max_alias, alias_map)
            return '(%s)' % subselect, params
        elif isinstance(expr, (list, tuple)):
            exprs = []
            vals = []
            for i in expr:
                e, v = self.parse_expr(i, alias_map)
                exprs.append(e)
                vals.extend(v)
            expr_str = '(%s)' % ','.join(exprs)
            return expr_str, vals
        elif isinstance(expr, Model):
            return self.interpolation, [expr.get_id()]
        return self.interpolation, [expr]

    def parse_q(self, q, alias_map=None):
        lhs_expr, lparams = self.parse_expr(q.lhs, alias_map)
        rhs_expr, rparams = self.parse_expr(q.rhs, alias_map)
        not_expr = q.negated and 'NOT ' or ''
        return '%s%s %s %s' % (not_expr, lhs_expr, self.get_op(q.op), rhs_expr), lparams + rparams

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
        seen = set()

        def _traverse(curr):
            if curr not in joins or curr in seen:
                return
            seen.add(curr)
            for join in joins[curr]:
                from_model = curr
                to_model = join.model_class

                field = from_model._meta.rel_for_model(to_model, join.column)
                if field:
                    left_field = field.db_column
                    right_field = to_model._meta.primary_key.db_column
                else:
                    field = to_model._meta.rel_for_model(from_model, join.column)
                    left_field = from_model._meta.primary_key.db_column
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

    def parse_select_query(self, query, start=1, alias_map=None):
        model = query.model_class
        alias_map = alias_map or {}
        alias_map.update(self.calculate_alias_map(query, start))

        parts = ['SELECT']
        params = []

        if query._distinct:
            parts.append('DISTINCT')

        selection = query._select
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

        if query._order_by:
            order_by, _ = self.parse_expr_list(query._order_by, alias_map)
            parts.append('ORDER BY %s' % order_by)

        if query._limit:
            parts.append('LIMIT %s' % query._limit)
        if query._offset:
            parts.append('OFFSET %s' % query._offset)
        if query._for_update:
            parts.append('FOR UPDATE')

        return ' '.join(parts), params

    def _parse_field_dictionary(self, d):
        sets, params = [], []
        for field, expr in d.items():
            field_str, _ = self.parse_expr(field)
            val_str, val_params = self.parse_expr(expr)
            val_params = [field.db_value(vp) for vp in val_params]
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

    def field_sql(self, field):
        attrs = field.attributes
        attrs['column_type'] = self.get_field(field.get_db_field())
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
        elif field.sequence:
            parts.append("DEFAULT NEXTVAL('%s')" % self.quote(field.sequence))
        return ' '.join(p % attrs for p in parts)

    def parse_create_table(self, model_class, safe=False):
        parts = ['CREATE TABLE']
        if safe:
            parts.append('IF NOT EXISTS')
        parts.append(self.quote(model_class._meta.db_table))
        columns = ', '.join(self.field_sql(f) for f in model_class._meta.get_fields())
        parts.append('(%s)' % columns)
        return parts

    def create_table(self, model_class, safe=False):
        return ' '.join(self.parse_create_table(model_class, safe))

    def drop_table(self, model_class, fail_silently=False, cascade=False):
        parts = ['DROP TABLE']
        if fail_silently:
            parts.append('IF EXISTS')
        parts.append(self.quote(model_class._meta.db_table))
        if cascade:
            parts.append('CASCADE')
        return ' '.join(parts)

    def parse_create_index(self, model_class, fields, unique):
        tbl_name = model_class._meta.db_table
        colnames = [f.db_column for f in fields]
        parts = ['CREATE %s' % ('UNIQUE INDEX' if unique else 'INDEX')]
        parts.append(self.quote('%s_%s' % (tbl_name, '_'.join(colnames))))
        parts.append('ON %s' % self.quote(tbl_name))
        parts.append('(%s)' % ', '.join(map(self.quote, colnames)))
        return parts

    def create_index(self, model_class, fields, unique):
        return ' '.join(self.parse_create_index(model_class, fields, unique))

    def create_sequence(self, sequence_name):
        return 'CREATE SEQUENCE %s;' % self.quote(sequence_name)

    def drop_sequence(self, sequence_name):
        return 'DROP SEQUENCE %s;' % self.quote(sequence_name)


class QueryResultWrapper(object):
    """
    Provides an iterator over the results of a raw Query, additionally doing
    two things:
    - converts rows from the database into model instances
    - ensures that multiple iterations do not result in multiple queries
    """
    def __init__(self, model, cursor, meta=None):
        self.model = model
        self.cursor = cursor
        self.naive = not meta

        if self.naive:
            cols = []
            non_cols = []
            for i in range(len(self.cursor.description)):
                col = self.cursor.description[i][0]
                if col in model._meta.columns:
                    cols.append((i, model._meta.columns[col]))
                else:
                    non_cols.append((i, col))
            self._cols = cols
            self._non_cols = non_cols
        else:
            self.column_meta, self.join_meta = meta

        self.__ct = 0
        self.__idx = 0

        self._result_cache = []
        self._populated = False

    def simple_iter(self, row):
        instance = self.model()
        for i, f in self._cols:
            setattr(instance, f.name, f.python_value(row[i]))
        for i, f in self._non_cols:
            setattr(instance, f, row[i])
        return instance

    def construct_instance(self, row):
        # we have columns, models, and a graph of joins to reconstruct
        collected_models = {}
        cols = [c[0] for c in self.cursor.description]
        for i, expr in enumerate(self.column_meta):
            value = row[i]
            if isinstance(expr, Field):
                model = expr.model_class
            else:
                model = self.model

            if model not in collected_models:
                collected_models[model] = model()
            instance = collected_models[model]

            if isinstance(expr, Field):
                setattr(instance, expr.name, expr.python_value(value))
            elif isinstance(expr, Expr) and expr._alias:
                setattr(instance, expr._alias, value)
            else:
                setattr(instance, cols[i], value)

        return self.follow_joins(self.join_meta, collected_models, self.model)

    def follow_joins(self, joins, collected_models, current):
        inst = collected_models[current]

        if current not in joins:
            return inst

        for joined_model, _, _ in joins[current]:
            if joined_model in collected_models:
                joined_inst = self.follow_joins(joins, collected_models, joined_model)
                fk_field = current._meta.rel_for_model(joined_model)

                if not fk_field:
                    continue

                if not joined_inst.get_id():
                    rel_inst_id = inst._data[fk_field.name]
                    joined_inst.set_id(rel_inst_id)

                setattr(inst, fk_field.name, joined_inst)

        return inst

    def __iter__(self):
        self.__idx = 0

        if not self._populated:
            return self
        else:
            return iter(self._result_cache)

    def iterate(self):
        row = self.cursor.fetchone()
        if not row:
            self._populated = True
            raise StopIteration

        if self.naive:
            return self.simple_iter(row)
        else:
            return self.construct_instance(row)

    def iterator(self):
        while 1:
            yield self.iterate()

    def next(self):
        if self.__idx < self.__ct:
            inst = self._result_cache[self.__idx]
            self.__idx += 1
            return inst

        instance = self.iterate()
        instance.prepared() # <-- model prepared hook
        self._result_cache.append(instance)
        self.__ct += 1
        self.__idx += 1
        return instance

def returns_clone(func):
    def inner(self, *args, **kwargs):
        clone = self.clone()
        func(clone, *args, **kwargs)
        return clone
    inner.call_local = func
    return inner

def not_allowed(fn):
    def inner(self, *args, **kwargs):
        raise NotImplementedError('%s is not allowed on %s instances' % (
            fn, type(self).__name__,
        ))
    return inner


Join = namedtuple('Join', ('model_class', 'join_type', 'column'))

class Query(object):
    require_commit = True

    def __init__(self, model_class):
        self.model_class = model_class
        self.database = model_class._meta.database

        self._dirty = True
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
    def where(self, *q_or_node):
        if self._where is None:
            self._where = Node(OP_AND)
        for piece in q_or_node:
            self._where &= piece

    @returns_clone
    def join(self, model_class, join_type=None, on=None):
        if not self._query_ctx._meta.rel_exists(model_class):
            raise ValueError('No foreign key between %s and %s' % (
                self._query_ctx, model_class,
            ))
        if on and isinstance(on, basestring):
            on = self._query_ctx._meta.fields[on]
        self._joins.setdefault(self._query_ctx, [])
        self._joins[self._query_ctx].append(Join(model_class, join_type, on))
        self._query_ctx = model_class

    @returns_clone
    def switch(self, model_class=None):
        self._query_ctx = model_class or self.model_class

    def ensure_join(self, lm, rm, on=None):
        ctx = self._query_ctx
        for join in self._joins.get(lm, []):
            if join.model_class == rm:
                return self
        query = self.switch(lm).join(rm, on=on).switch(ctx)
        return query

    def convert_dict_to_node(self, qdict):
        accum = []
        joins = []
        for key, value in sorted(qdict.items()):
            curr = self.model_class
            if '__' in key and key.rsplit('__', 1)[1] in DJANGO_MAP:
                key, op = key.rsplit('__', 1)
                op = DJANGO_MAP[op]
            else:
                op = OP_EQ
            for piece in key.split('__'):
                model_attr = getattr(curr, piece)
                if isinstance(model_attr, (ForeignKeyField, ReverseRelationDescriptor)):
                    curr = model_attr.rel_model
                    joins.append(model_attr)
            accum.append(Q(model_attr, op, value))
        return accum, joins

    def filter(self, *args, **kwargs):
        # normalize args and kwargs into a new node
        dq_node = Node(OP_AND)
        if kwargs:
            dq_node &= DQ(**kwargs)
        for arg in args:
            dq_node &= arg.clone()

        # breadth-first search all nodes replacing DQ with Q
        q = deque([dq_node])
        dq_joins = set()
        while q:
            query = []
            curr = q.popleft()
            for child in curr.children:
                if isinstance(child, Node):
                    q.append(child)
                    query.append(child)
                elif isinstance(child, DQ):
                    accum, joins = self.convert_dict_to_node(child.query)
                    dq_joins.update(joins)
                    query.extend(accum)
                else:
                    query.append(child)
            curr.children = query

        query = self.clone()
        for field in dq_joins:
            if isinstance(field, ForeignKeyField):
                lm, rm = field.model_class, field.rel_model
                field_obj = field
            elif isinstance(field, ReverseRelationDescriptor):
                lm, rm = field.field.rel_model, field.rel_model
                field_obj = field.field
            query = query.ensure_join(lm, rm, field_obj)
        return query.where(dq_node)

    def sql(self, compiler):
        raise NotImplementedError()

    def execute(self):
        raise NotImplementedError


class RawQuery(Query):
    def __init__(self, model, query, *params):
        self._sql = query
        self._params = list(params)
        self._qr = None
        super(RawQuery, self).__init__(model)

    def clone(self):
        return RawQuery(self.model_class, self._sql, *self._params)

    def sql(self, compiler):
        return self._sql, self._params

    join = not_allowed('joining')
    where = not_allowed('where')
    switch = not_allowed('switch')

    def execute(self):
        if self._qr is None:
            self._qr = QueryResultWrapper(self.model_class, self.database.execute(self), None)
        return self._qr

    def __iter__(self):
        return iter(self.execute())


class SelectQuery(Query):
    require_commit = False

    def __init__(self, model_class, *selection):
        self._select = self._model_shorthand(selection or model_class._meta.get_fields())
        self._group_by = None
        self._having = None
        self._order_by = None
        self._limit = None
        self._offset = None
        self._distinct = False
        self._for_update = False
        self._naive = False
        self._qr = None
        super(SelectQuery, self).__init__(model_class)

    def clone(self):
        query = super(SelectQuery, self).clone()
        query._select = list(self._select)
        if self._group_by is not None:
            query._group_by = list(self._group_by)
        if self._having:
            query._having = self._having.clone()
        if self._order_by is not None:
            query._order_by = list(self._order_by)
        query._limit = self._limit
        query._offset = self._offset
        query._distinct = self._distinct
        query._for_update = self._for_update
        query._naive = self._naive
        return query

    def _model_shorthand(self, args):
        accum = []
        for arg in args:
            if isinstance(arg, Expr):
                accum.append(arg)
            elif issubclass(arg, Model):
                accum.extend(arg._meta.get_fields())
        return accum

    @returns_clone
    def group_by(self, *args):
        self._group_by = self._model_shorthand(args)

    @returns_clone
    def having(self, *q_or_node):
        if self._having is None:
            self._having = Node(OP_AND)
        for piece in q_or_node:
            self._having &= piece

    @returns_clone
    def order_by(self, *args):
        self._order_by = list(args)

    @returns_clone
    def limit(self, lim):
        self._limit = lim

    @returns_clone
    def offset(self, off):
        self._offset = off

    @returns_clone
    def paginate(self, page, paginate_by=20):
        if page > 0:
            page -= 1
        self._limit = paginate_by
        self._offset = page * paginate_by

    @returns_clone
    def distinct(self, is_distinct=True):
        self._distinct = is_distinct

    @returns_clone
    def for_update(self, for_update=True):
        self._for_update = for_update

    @returns_clone
    def naive(self, naive=True):
        self._naive = naive

    def annotate(self, rel_model, annotation=None):
        annotation = annotation or fn.Count(rel_model._meta.primary_key).alias('count')
        query = self.clone()
        query = query.ensure_join(query._query_ctx, rel_model)
        if not query._group_by:
            query._group_by = list(query._select)
        query._select = tuple(query._select) + (annotation,)
        return query

    def _aggregate(self, aggregation=None):
        aggregation = aggregation or fn.Count(self.model_class._meta.primary_key)
        query = self.order_by()
        query._select = (aggregation,)
        return query

    def aggregate(self, aggregation=None):
        query = self._aggregate(aggregation)
        compiler = self.database.get_compiler()
        sql, params = query.sql(compiler)
        curs = query.database.execute_sql(sql, params, require_commit=False)
        return curs.fetchone()[0]

    def count(self):
        if self._distinct or self._group_by:
            return self.wrapped_count()

        clone = self.order_by()
        clone._limit = clone._offset = None
        clone._select = [fn.Count(clone.model_class._meta.primary_key)]

        res = clone.database.execute(clone)
        return (res.fetchone() or [0])[0]

    def wrapped_count(self):
        clone = self.order_by()
        clone._limit = clone._offset = None

        compiler = self.database.get_compiler()
        sql, params = clone.sql(compiler)
        query = 'SELECT COUNT(1) FROM (%s) AS wrapped_select' % sql

        res = clone.database.execute_sql(query, params, require_commit=False)
        return res.fetchone()[0]

    def exists(self):
        clone = self.paginate(1, 1)
        clone._select = [self.model_class._meta.primary_key]
        res = self.database.execute(clone)
        return bool(res.fetchone())

    def get(self):
        clone = self.paginate(1, 1)
        try:
            return clone.execute().next()
        except StopIteration:
            raise self.model_class.DoesNotExist('instance matching query does not exist:\nSQL: %s\nPARAMS: %s' % (
                self.sql(self.database.get_compiler())
            ))

    def sql(self, compiler):
        return compiler.parse_select_query(self)

    def verify_naive(self):
        for expr in self._select:
            if isinstance(expr, Field) and expr.model_class != self.model_class:
                return False
        return True

    def execute(self):
        if self._dirty or not self._qr:
            if self._naive or not self._joins or self.verify_naive():
                query_meta = None
            else:
                query_meta = [self._select, self._joins]
            self._qr = QueryResultWrapper(self.model_class, self.database.execute(self), query_meta)
            self._dirty = False
            return self._qr
        else:
            return self._qr

    def __iter__(self):
        return iter(self.execute())


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

    def execute(self):
        result = self.database.execute(self)
        return self.database.rows_affected(result)

class InsertQuery(Query):
    def __init__(self, model_class, insert=None):
        mm = model_class._meta
        query = dict((mm.fields[f], v) for f, v in mm.get_default_dict().items())
        query.update(insert)
        self._insert = query
        super(InsertQuery, self).__init__(model_class)

    def clone(self):
        query = super(InsertQuery, self).clone()
        query._insert = dict(self._insert)
        return query

    join = not_allowed('joining')
    where = not_allowed('where clause')

    def sql(self, compiler):
        return compiler.parse_insert_query(self)

    def execute(self):
        result = self.database.execute(self)
        return self.database.last_insert_id(result, self.model_class)

class DeleteQuery(Query):
    join = not_allowed('joining')

    def sql(self, compiler):
        return compiler.parse_delete_query(self)

    def execute(self):
        result = self.database.execute(self)
        return self.database.rows_affected(result)


class Database(object):
    compiler_class = QueryCompiler
    expr_overrides = {}
    field_overrides = {}
    for_update = False
    interpolation = '?'
    op_overrides = {}
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

    def _close(self, conn):
        conn.close()

    def _connect(self, database, **kwargs):
        raise NotImplementedError

    def last_insert_id(self, cursor, model):
        if model._meta.auto_increment:
            return cursor.lastrowid

    def rows_affected(self, cursor):
        return cursor.rowcount

    def get_compiler(self):
        return self.compiler_class(
            self.quote_char, self.interpolation, self.field_overrides,
            self.op_overrides, self.expr_overrides)

    def execute(self, query):
        sql, params = query.sql(self.get_compiler())
        return self.execute_sql(sql, params, query.require_commit)

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

    def get_tables(self):
        raise NotImplementedError

    def get_indexes_for_table(self, table):
        raise NotImplementedError

    def sequence_exists(self, seq):
        raise NotImplementedError

    def create_table(self, model_class):
        qc = self.get_compiler()
        return self.execute_sql(qc.create_table(model_class))

    def create_index(self, model_class, fields, unique=False):
        qc = self.get_compiler()
        field_objs = [model_class._meta.fields[f] if isinstance(f, basestring) else f for f in fields]
        return self.execute_sql(qc.create_index(model_class, field_objs, unique))

    def create_foreign_key(self, model_class, field):
        if not field.primary_key:
            return self.create_index(model_class, [field], field.unique)

    def create_sequence(self, seq):
        if self.sequences:
            qc = self.get_compiler()
            return self.execute_sql(qc.create_sequence(seq))

    def drop_table(self, model_class, fail_silently=False):
        qc = self.get_compiler()
        return self.execute_sql(qc.drop_table(model_class, fail_silently))

    def drop_sequence(self, seq):
        if self.sequences:
            qc = self.get_compiler()
            return self.execute_sql(qc.drop_sequence(seq))

    def transaction(self):
        return transaction(self)

    def commit_on_success(self, func):
        def inner(*args, **kwargs):
            orig = self.get_autocommit()
            self.set_autocommit(False)
            self.begin()
            try:
                res = func(*args, **kwargs)
                self.commit()
            except:
                self.rollback()
                raise
            else:
                return res
            finally:
                self.set_autocommit(orig)
        return inner


class SqliteDatabase(Database):
    op_overrides = {
        OP_LIKE: 'GLOB',
    }

    def _connect(self, database, **kwargs):
        if not sqlite3:
            raise ImproperlyConfigured('sqlite3 must be installed on the system')
        return sqlite3.connect(database, **kwargs)

    def get_indexes_for_table(self, table):
        res = self.execute_sql('PRAGMA index_list(%s);' % self.quote(table))
        rows = sorted([(r[1], r[2] == 1) for r in res.fetchall()])
        return rows

    def get_tables(self):
        res = self.execute_sql('select name from sqlite_master where type="table" order by name')
        return [r[0] for r in res.fetchall()]


class PostgresqlDatabase(Database):
    field_overrides = {
        'bigint': 'BIGINT',
        'bool': 'BOOLEAN',
        'datetime': 'TIMESTAMP',
        'decimal': 'NUMERIC',
        'double': 'DOUBLE PRECISION',
        'primary_key': 'SERIAL',
    }
    for_update = True
    interpolation = '%s'
    reserved_tables = ['user']
    sequences = True

    def _connect(self, database, **kwargs):
        if not psycopg2:
            raise ImproperlyConfigured('psycopg2 must be installed on the system')
        return psycopg2.connect(database=database, **kwargs)

    def last_insert_id(self, cursor, model):
        seq = model._meta.primary_key.sequence
        if seq:
            cursor.execute("SELECT CURRVAL('\"%s\"')" % (seq))
            return cursor.fetchone()[0]
        elif model._meta.auto_increment:
            cursor.execute("SELECT CURRVAL('\"%s_%s_seq\"')" % (
                model._meta.db_table, model._meta.primary_key.db_column))
            return cursor.fetchone()[0]

    def get_indexes_for_table(self, table):
        res = self.execute_sql("""
            SELECT c2.relname, i.indisprimary, i.indisunique
            FROM pg_catalog.pg_class c, pg_catalog.pg_class c2, pg_catalog.pg_index i
            WHERE c.relname = %s AND c.oid = i.indrelid AND i.indexrelid = c2.oid
            ORDER BY i.indisprimary DESC, i.indisunique DESC, c2.relname""", (table,))
        return sorted([(r[0], r[1]) for r in res.fetchall()])

    def get_tables(self):
        res = self.execute_sql("""
            SELECT c.relname
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'v', '')
                AND n.nspname NOT IN ('pg_catalog', 'pg_toast')
                AND pg_catalog.pg_table_is_visible(c.oid)
            ORDER BY c.relname""")
        return [row[0] for row in res.fetchall()]

    def sequence_exists(self, sequence):
        res = self.execute_sql("""
            SELECT COUNT(*)
            FROM pg_class, pg_namespace
            WHERE relkind='S'
                AND pg_class.relnamespace = pg_namespace.oid
                AND relname=%s""", (sequence,))
        return bool(res.fetchone()[0])

    def set_search_path(self, *search_path):
        path_params = ','.join(['%s'] * len(search_path))
        self.execute_sql('SET search_path TO %s' % path_params, search_path)


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
    interpolation = '%s'
    op_overrides = {OP_LIKE: 'LIKE BINARY'}
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

    def create_foreign_key(self, model_class, field):
        framing = """
            ALTER TABLE %(table)s ADD CONSTRAINT %(constraint)s
            FOREIGN KEY (%(field)s) REFERENCES %(to)s(%(to_field)s)%(cascade)s;
        """
        db_table = model_class._meta.db_table
        constraint = 'fk_%s_%s_%s' % (
            db_table,
            field.to._meta.db_table,
            field.db_column,
        )

        query = framing % {
            'table': self.quote(db_table),
            'constraint': self.quote(constraint),
            'field': self.quote(field.db_column),
            'to': self.quote(field.to._meta.db_table),
            'to_field': self.quote(field.to._meta.primary_key.db_column),
            'cascade': ' ON DELETE CASCADE' if field.cascade else '',
        }

        self.execute_sql(query)
        return super(MySQLDatabase, self).create_foreign_key(model_class, field)

    def get_indexes_for_table(self, table):
        res = self.execute_sql('SHOW INDEXES IN %s;' % self.quote(table))
        rows = sorted([(r[2], r[1] == 0) for r in res.fetchall()])
        return rows

    def get_tables(self):
        res = self.execute_sql('SHOW TABLES;')
        return [r[0] for r in res.fetchall()]


class transaction(object):
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self._orig = self.db.get_autocommit()
        self.db.set_autocommit(False)
        self.db.begin()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.db.rollback()
        else:
            self.db.commit()
        self.db.set_autocommit(self._orig)

class DoesNotExist(Exception):
    pass

# doing an IN on empty set
class EmptyResultException(Exception):
    pass


default_database = SqliteDatabase('peewee.db')


class ModelOptions(object):
    def __init__(self, cls, database=None, db_table=None, indexes=None,
                 order_by=None, primary_key=None):
        self.model_class = cls
        self.name = cls.__name__.lower()
        self.fields = {}
        self.columns = {}
        self.defaults = {}

        self.database = database or default_database
        self.db_table = db_table
        self.indexes = indexes or []
        self.order_by = order_by
        self.primary_key = primary_key

        self.auto_increment = None
        self.rel = {}
        self.reverse_rel = {}

    def prepared(self):
        for field in self.fields.values():
            if field.default is not None:
                self.defaults[field] = field.default

        if self.order_by:
            norm_order_by = []
            for clause in self.order_by:
                field = self.fields[clause.lstrip('-')]
                if clause.startswith('-'):
                    norm_order_by.append(field.desc())
                else:
                    norm_order_by.append(field.asc())
            self.order_by = norm_order_by

    def get_default_dict(self):
        dd = {}
        for field, default in self.defaults.items():
            if callable(default):
                dd[field.name] = default()
            else:
                dd[field.name] = default
        return dd

    def get_sorted_fields(self):
        return sorted(self.fields.items(), key=lambda (k,v): (v is self.primary_key and 1 or 2, v._order))

    def get_field_names(self):
        return [f[0] for f in self.get_sorted_fields()]

    def get_fields(self):
        return [f[1] for f in self.get_sorted_fields()]

    def rel_for_model(self, model, field_obj=None):
        for field in self.get_fields():
            if isinstance(field, ForeignKeyField) and field.rel_model == model:
                if field_obj is None or field_obj.name == field.name:
                    return field

    def reverse_rel_for_model(self, model):
        return model._meta.rel_for_model(self.model_class)

    def rel_exists(self, model):
        return self.rel_for_model(model) or self.reverse_rel_for_model(model)


class BaseModel(type):
    inheritable_options = ['database', 'indexes', 'order_by', 'primary_key']

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
                if attr.index:
                    cls._meta.indexes.append(attr.name)
                if attr.primary_key:
                    primary_key = attr

        if not primary_key:
            primary_key = PrimaryKeyField(primary_key=True)
            primary_key.add_to_class(cls, 'id')

        cls._meta.primary_key = primary_key
        cls._meta.auto_increment = isinstance(primary_key, PrimaryKeyField) or primary_key.sequence
        if not cls._meta.db_table:
            cls._meta.db_table = re.sub('[^\w]+', '_', cls.__name__.lower())

        # create a repr and error class before finalizing
        if hasattr(cls, '__unicode__'):
            setattr(cls, '__repr__', lambda self: '<%s: %r>' % (
                cls.__name__, self.__unicode__()))

        exception_class = type('%sDoesNotExist' % cls.__name__, (DoesNotExist,), {})
        cls.DoesNotExist = exception_class
        cls._meta.prepared()

        return cls


class Model(object):
    __metaclass__ = BaseModel

    def __init__(self, *args, **kwargs):
        self._data = self._meta.get_default_dict()
        self._obj_cache = {} # cache of related objects

        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def raw(cls, sql, *params):
        return RawQuery(cls, sql, *params)

    @classmethod
    def select(cls, *selection):
        query = SelectQuery(cls, *selection)
        if cls._meta.order_by:
            query = query.order_by(*cls._meta.order_by)
        return query

    @classmethod
    def update(cls, **update):
        fdict = dict((cls._meta.fields[f], v) for f, v in update.items())
        return UpdateQuery(cls, fdict)

    @classmethod
    def insert(cls, **insert):
        fdict = dict((cls._meta.fields[f], v) for f, v in insert.items())
        return InsertQuery(cls, fdict)

    @classmethod
    def delete(cls):
        return DeleteQuery(cls)

    @classmethod
    def create(cls, **query):
        inst = cls(**query)
        inst.save(force_insert=True)
        return inst

    @classmethod
    def filter(cls, *dq, **query):
        return cls.select().filter(*dq, **query)

    @classmethod
    def get(cls, query=None, **kwargs):
        sq = cls.select().naive()
        if query:
            sq = sq.where(query)
        if kwargs:
            sq = sq.filter(**kwargs)
        return sq.get()

    @classmethod
    def get_or_create(cls, **kwargs):
        sq = cls.select().filter(**kwargs)
        try:
            return sq.get()
        except cls.DoesNotExist:
            return cls.create(**kwargs)

    @classmethod
    def table_exists(cls):
        return cls._meta.db_table in cls._meta.database.get_tables()

    @classmethod
    def create_table(cls, fail_silently=False):
        if fail_silently and cls.table_exists():
            return

        db = cls._meta.database
        pk = cls._meta.primary_key
        if db.sequences and pk.sequence and not db.sequence_exists(pk.sequence):
            db.create_sequence(pk.sequence)

        db.create_table(cls)

        for field_name, field_obj in cls._meta.fields.items():
            if isinstance(field_obj, ForeignKeyField):
                db.create_foreign_key(cls, field_obj)
            elif field_obj.index or field_obj.unique:
                db.create_index(cls, [field_obj], field_obj.unique)

        if cls._meta.indexes:
            for fields, unique in cls._meta.indexes:
                db.create_index(cls, fields, unique)

    @classmethod
    def drop_table(cls, fail_silently=False):
        cls._meta.database.drop_table(cls, fail_silently)

    def get_id(self):
        return getattr(self, self._meta.primary_key.name)

    def set_id(self, id):
        setattr(self, self._meta.primary_key.name, id)

    def prepared(self):
        pass

    def save(self, force_insert=False):
        field_dict = dict(self._data)
        pk = self._meta.primary_key
        if self.get_id() and not force_insert:
            field_dict.pop(pk.name)
            update = self.update(
                **field_dict
            ).where(pk == self.get_id())
            update.execute()
        else:
            if self._meta.auto_increment:
                field_dict.pop(pk.name, None)
            insert = self.insert(**field_dict)
            new_pk = insert.execute()
            if self._meta.auto_increment:
                self.set_id(new_pk)

    def dependencies(self, search_nullable=False):
        stack = [(type(self), self.select().where(self._meta.primary_key == self.get_id()))]
        seen = set()

        while stack:
            klass, query = stack.pop()
            if klass in seen:
                continue
            seen.add(klass)
            for rel_name, fk in klass._meta.reverse_rel.items():
                rel_model = fk.model_class
                expr = fk << query
                if not fk.null or search_nullable:
                    stack.append((rel_model, rel_model.select().where(expr)))
                yield (expr, fk)

    def delete_instance(self, recursive=False, delete_nullable=False):
        if recursive:
            for query, fk in reversed(list(self.dependencies(delete_nullable))):
                if fk.null and not delete_nullable:
                    fk.model_class.update(**{fk.name: None}).where(query).execute()
                else:
                    fk.model_class.delete().where(query).execute()
        return self.delete().where(self._meta.primary_key == self.get_id()).execute()

    def __eq__(self, other):
        return other.__class__ == self.__class__ and \
               self.get_id() and \
               other.get_id() == self.get_id()

    def __ne__(self, other):
        return not self == other


def create_model_tables(models, **create_table_kwargs):
    """Create tables for all given models (in the right order)."""
    for m in sort_models_topologically(models):
        m.create_table(**create_table_kwargs)

def drop_model_tables(models, **drop_table_kwargs):
    """Drop tables for all given models (in the right order)."""
    for m in reversed(sort_models_topologically(models)):
        m.drop_table(**drop_table_kwargs)

def sort_models_topologically(models):
    """Sort models topologically so that parents will precede children."""
    models = set(models)
    seen = set()
    ordering = []
    def dfs(model):
        if model in models and model not in seen:
            seen.add(model)
            for child_model in model._meta.reverse_rel.values():
                dfs(child_model)
            ordering.append(model)  # parent will follow descendants
    # order models by name and table initially to guarantee a total ordering
    names = lambda m: (m._meta.name, m._meta.db_table)
    for m in sorted(models, key=names, reverse=True):
        dfs(m)
    return list(reversed(ordering))  # want parents first in output ordering
