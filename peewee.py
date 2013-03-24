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
import operator
import re
import threading
from collections import deque, namedtuple
from copy import deepcopy

__all__ = [
    'IntegerField', 'BigIntegerField', 'PrimaryKeyField', 'FloatField', 'DoubleField',
    'DecimalField', 'CharField', 'TextField', 'DateTimeField', 'DateField', 'TimeField',
    'BooleanField', 'ForeignKeyField', 'Model', 'DoesNotExist', 'ImproperlyConfigured',
    'DQ', 'fn', 'SqliteDatabase', 'MySQLDatabase', 'PostgresqlDatabase', 'Field',
    'JOIN_LEFT_OUTER', 'JOIN_INNER', 'JOIN_FULL', 'prefetch',
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
    try:
        import pymysql as mysql
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

logger = logging.getLogger('peewee')

OP_AND = 0
OP_OR = 1

OP_ADD = 10
OP_SUB = 11
OP_MUL = 12
OP_DIV = 13
OP_AND = 14
OP_OR = 15
OP_XOR = 16
OP_USER = 19

OP_EQ = 20
OP_LT = 21
OP_LTE = 22
OP_GT = 23
OP_GTE = 24
OP_NE = 25
OP_IN = 26
OP_IS = 27
OP_LIKE = 28
OP_ILIKE = 29

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


class Leaf(object):
    def __init__(self):
        self.negated = False
        self._alias = None

    def clone_base(self):
        return type(self)()

    def clone(self):
        inst = self.clone_base()
        inst.negated = self.negated
        inst._alias = self._alias
        return inst

    @returns_clone
    def __invert__(self):
        self.negated = not self.negated

    @returns_clone
    def alias(self, a=None):
        self._alias = a

    def asc(self):
        return Ordering(self, True)

    def desc(self):
        return Ordering(self, False)

    def _e(op, inv=False):
        def inner(self, rhs):
            if inv:
                return Expr(rhs, op, self)
            return Expr(self, op, rhs)
        return inner
    __and__ = _e(OP_AND)
    __or__ = _e(OP_OR)

    __add__ = _e(OP_ADD)
    __sub__ = _e(OP_SUB)
    __mul__ = _e(OP_MUL)
    __div__ = _e(OP_DIV)
    __xor__ = _e(OP_XOR)
    __radd__ = _e(OP_ADD, inv=True)
    __rsub__ = _e(OP_SUB, inv=True)
    __rmul__ = _e(OP_MUL, inv=True)
    __rdiv__ = _e(OP_DIV, inv=True)
    __rand__ = _e(OP_AND, inv=True)
    __ror__ = _e(OP_OR, inv=True)
    __rxor__ = _e(OP_XOR, inv=True)

    __eq__ = _e(OP_EQ)
    __lt__ = _e(OP_LT)
    __le__ = _e(OP_LTE)
    __gt__ = _e(OP_GT)
    __ge__ = _e(OP_GTE)
    __ne__ = _e(OP_NE)
    __lshift__ = _e(OP_IN)
    __rshift__ = _e(OP_IS)
    __mod__ = _e(OP_LIKE)
    __pow__ = _e(OP_ILIKE)


class Expr(Leaf):
    def __init__(self, lhs, op, rhs):
        super(Expr, self).__init__()
        self.lhs = lhs
        self.op = op
        self.rhs = rhs

    def clone_base(self):
        return Expr(self.lhs, self.op, self.rhs)

class DQ(Leaf):
    def __init__(self, **query):
        super(DQ, self).__init__()
        self.query = query

    def clone_base(self):
        return DQ(**self.query)

class Param(Leaf):
    def __init__(self, data):
        self.data = data
        super(Param, self).__init__()

    def clone_base(self):
        return Param(self.data)

class R(Leaf):
    def __init__(self, value):
        self.value = value
        super(R, self).__init__()

    def clone_base(self):
        return R(self.value)

class Ordering(Leaf):
    def __init__(self, param, asc):
        self.param = param
        self.asc = asc
        super(Ordering, self).__init__()

    def clone_base(self):
        return Ordering(self.param, self.asc)

class Func(Leaf):
    def __init__(self, name, *params):
        self.name = name
        self.params = params
        super(Func, self).__init__()

    def clone_base(self):
        return Func(self.name, *self.params)

    def __getattr__(self, attr):
        def dec(*args, **kwargs):
            return Func(attr, *args, **kwargs)
        return dec

fn = Func(None)


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


class Field(Leaf):
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

    def clone_base(self, **kwargs):
       inst = type(self)(
           null=self.null,
           index=self.index,
           unique=self.unique,
           help_text=self.help_text,
           default=self.default,
           choices=self.choices,
           primary_key=self.primary_key,
           sequence=self.sequence,
           **kwargs
       )
       inst.attributes = dict(self.attributes)
       inst.name = self.name
       inst.model_class = self.model_class
       inst.db_column = self.db_column
       inst.verbose_name = self.verbose_name
       return inst

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

def format_unicode(s, encoding='utf-8'):
    if isinstance(s, unicode):
        return s
    elif isinstance(s, basestring):
        return s.decode(encoding)
    elif hasattr(s, '__unicode__'):
        return s.__unicode__()
    else:
        return unicode(bytes(s), encoding)

class CharField(Field):
    db_field = 'string'
    template = '%(column_type)s(%(max_length)s)'

    def field_attributes(self):
        return {'max_length': 255}

    def coerce(self, value):
        value = format_unicode(value or '')
        return value[:self.attributes['max_length']]

class TextField(Field):
    db_field = 'text'

    def coerce(self, value):
        return format_unicode(value or '')

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
        if rel_id is not None or self.att_name in instance._obj_cache:
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

    def clone_base(self):
        inst = super(ForeignKeyField, self).clone_base(
            rel_model=self.rel_model,
            cascade=self.cascade,
            extra=self.extra,
        )
        inst.related_name = self.related_name
        inst.rel_model = self.rel_model
        return inst

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
        if self.related_name in self.rel_model._meta.fields:
            raise AttributeError('Foreign key: %s.%s related name "%s" collision with field of same name' % (
                self.model_class._meta.name, self.name, self.related_name))

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

    op_map = {
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
        OP_ADD: '+',
        OP_SUB: '-',
        OP_MUL: '*',
        OP_DIV: '/',
        OP_XOR: '^',
        OP_AND: 'AND',
        OP_OR: 'OR',
    }

    join_map = {
        JOIN_INNER: 'INNER',
        JOIN_LEFT_OUTER: 'LEFT OUTER',
        JOIN_FULL: 'FULL',
    }

    def __init__(self, quote_char='"', interpolation='?', field_overrides=None,
                 op_overrides=None):
        self.quote_char = quote_char
        self.interpolation = interpolation
        self._field_map = dict_update(self.field_map, field_overrides or {})
        self._op_map = dict_update(self.op_map, op_overrides or {})

    def quote(self, s):
        return ''.join((self.quote_char, s, self.quote_char))

    def get_field(self, f):
        return self._field_map[f]

    def get_op(self, q):
        return self._op_map[q]

    def _max_alias(self, am):
        max_alias = 0
        if am:
            for a in am.values():
                i = int(a.lstrip('t'))
                if i > max_alias:
                    max_alias = i
        return max_alias + 1

    def parse_expr(self, expr, alias_map=None, conv=None):
        s = self.interpolation
        p = [expr]
        if isinstance(expr, Expr):
            if isinstance(expr.lhs, Field):
                conv = expr.lhs
            lhs, lparams = self.parse_expr(expr.lhs, alias_map, conv)
            rhs, rparams = self.parse_expr(expr.rhs, alias_map, conv)
            s = '(%s %s %s)' % (lhs, self.get_op(expr.op), rhs)
            p = lparams + rparams
        elif isinstance(expr, Field):
            s = self.quote(expr.db_column)
            if alias_map and expr.model_class in alias_map:
                s = '.'.join((alias_map[expr.model_class], s))
            p = []
        elif isinstance(expr, Func):
            p = []
            exprs = []
            for param in expr.params:
                parsed, params = self.parse_expr(param, alias_map, conv)
                exprs.append(parsed)
                p.extend(params)
            s = '%s(%s)' % (expr.name, ', '.join(exprs))
        elif isinstance(expr, Param):
            s = self.interpolation
            p = [expr.data]
        elif isinstance(expr, Ordering):
            s, p = self.parse_expr(expr.param, alias_map, conv)
            s += ' ASC' if expr.asc else ' DESC'
        elif isinstance(expr, R):
            s = expr.value
            p = []
        elif isinstance(expr, SelectQuery):
            max_alias = self._max_alias(alias_map)
            alias_copy = alias_map and alias_map.copy() or None
            clone = expr.clone()
            if not expr._explicit_selection:
                clone._select = (clone.model_class._meta.primary_key,)
            subselect, p = self.generate_select(clone, max_alias, alias_copy)
            s = '(%s)' % subselect
        elif isinstance(expr, (list, tuple)):
            exprs = []
            p = []
            for i in expr:
                e, v = self.parse_expr(i, alias_map, conv)
                exprs.append(e)
                p.extend(v)
            s = '(%s)' % ','.join(exprs)
        elif isinstance(expr, Model):
            s = self.interpolation
            p = [expr.get_id()]
        elif conv and p:
            p = [conv.db_value(i) for i in p]

        if isinstance(expr, Leaf):
            if expr.negated:
                s = 'NOT %s' % s
            if expr._alias:
                s = ' '.join((s, 'AS', expr._alias))

        return s, p

    def parse_expr_list(self, s, alias_map):
        parsed = []
        data = []
        for expr in s:
            expr_str, vars = self.parse_expr(expr, alias_map)
            parsed.append(expr_str)
            data.extend(vars)
        return ', '.join(parsed), data

    def parse_field_dict(self, d):
        sets, params = [], []
        for field, expr in d.items():
            field_str, _ = self.parse_expr(field)
            # because we don't know whether to call db_value or parse_expr first,
            # we'd prefer to call parse_expr since its more general, but it does
            # special things with lists -- it treats them as if it were buliding
            # up an IN query. for some things we don't want that, so here, if the
            # expr is *not* a special object, we'll pass thru parse_expr and let
            # db_value handle it
            if not isinstance(expr, (Leaf, Model, Query)):
                expr = Param(expr) # pass through to the fields db_value func
            val_str, val_params = self.parse_expr(expr)
            val_params = [field.db_value(vp) for vp in val_params]
            sets.append((field_str, val_str))
            params.extend(val_params)
        return sets, params

    def parse_query_node(self, qnode, alias_map):
        if qnode is not None:
            return self.parse_expr(qnode, alias_map)
        return '', []

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

    def generate_joins(self, joins, model_class, alias_map):
        parsed = []
        params = []
        seen = set()
        q = [model_class]
        while q:
            curr = q.pop()
            if curr not in joins or curr in seen:
                continue
            seen.add(curr)
            for join in joins[curr]:
                from_model = curr
                to_model = join.model_class
                if isinstance(join.on, Expr):
                    join_expr = join.on
                else:
                    field = from_model._meta.rel_for_model(to_model, join.on)
                    if field:
                        left_field = field
                        right_field = to_model._meta.primary_key
                    else:
                        field = to_model._meta.rel_for_model(from_model, join.on)
                        left_field = from_model._meta.primary_key
                        right_field = field
                    join_expr = (left_field == right_field)

                join_type = join.join_type or JOIN_INNER
                parsed_join, join_params = self.parse_expr(join_expr, alias_map)

                parsed.append('%s JOIN %s AS %s ON %s' % (
                    self.join_map[join_type],
                    self.quote(to_model._meta.db_table),
                    alias_map[to_model],
                    parsed_join,
                ))
                params.extend(join_params)

                q.append(to_model)
        return parsed, params

    def generate_select(self, query, start=1, alias_map=None):
        model = query.model_class
        db = model._meta.database

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

        joins, j_params = self.generate_joins(query._joins, query.model_class, alias_map)
        if joins:
            parts.append(' '.join(joins))
            params.extend(j_params)

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

        if query._limit or (query._offset and not db.empty_limit):
            limit = query._limit or -1
            parts.append('LIMIT %s' % limit)
        if query._offset:
            parts.append('OFFSET %s' % query._offset)
        if query._for_update:
            parts.append('FOR UPDATE')

        return ' '.join(parts), params

    def generate_update(self, query):
        model = query.model_class

        parts = ['UPDATE %s SET' % self.quote(model._meta.db_table)]
        sets, params = self.parse_field_dict(query._update)

        parts.append(', '.join('%s=%s' % (f, v) for f, v in sets))

        where, w_params = self.parse_query_node(query._where, None)
        if where:
            parts.append('WHERE %s' % where)
            params.extend(w_params)
        return ' '.join(parts), params

    def generate_insert(self, query):
        model = query.model_class

        parts = ['INSERT INTO %s' % self.quote(model._meta.db_table)]
        sets, params = self.parse_field_dict(query._insert)

        parts.append('(%s)' % ', '.join(s[0] for s in sets))
        parts.append('VALUES (%s)' % ', '.join(s[1] for s in sets))

        return ' '.join(parts), params

    def generate_delete(self, query):
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
        template = field.template

        if isinstance(field, ForeignKeyField):
            to_pk = field.rel_model._meta.primary_key
            if not isinstance(to_pk, PrimaryKeyField):
                template = to_pk.template
                attrs.update(to_pk.attributes)

        parts = [self.quote(field.db_column), template]
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

    def create_table_sql(self, model_class, safe=False):
        parts = ['CREATE TABLE']
        if safe:
            parts.append('IF NOT EXISTS')
        parts.append(self.quote(model_class._meta.db_table))
        columns = ', '.join(self.field_sql(f) for f in model_class._meta.get_fields())
        parts.append('(%s)' % columns)
        return parts

    def create_table(self, model_class, safe=False):
        return ' '.join(self.create_table_sql(model_class, safe))

    def drop_table(self, model_class, fail_silently=False, cascade=False):
        parts = ['DROP TABLE']
        if fail_silently:
            parts.append('IF EXISTS')
        parts.append(self.quote(model_class._meta.db_table))
        if cascade:
            parts.append('CASCADE')
        return ' '.join(parts)

    def create_index_sql(self, model_class, fields, unique):
        tbl_name = model_class._meta.db_table
        colnames = [f.db_column for f in fields]
        parts = ['CREATE %s' % ('UNIQUE INDEX' if unique else 'INDEX')]
        parts.append(self.quote('%s_%s' % (tbl_name, '_'.join(colnames))))
        parts.append('ON %s' % self.quote(tbl_name))
        parts.append('(%s)' % ', '.join(map(self.quote, colnames)))
        return parts

    def create_index(self, model_class, fields, unique):
        return ' '.join(self.create_index_sql(model_class, fields, unique))

    def create_sequence(self, sequence_name):
        return 'CREATE SEQUENCE %s;' % self.quote(sequence_name)

    def drop_sequence(self, sequence_name):
        return 'DROP SEQUENCE %s;' % self.quote(sequence_name)


class QueryResultWrapper(object):
    """
    Provides an iterator over the results of a raw Query, additionally doing
    two things:
    - converts rows from the database into python representations
    - ensures that multiple iterations do not result in multiple queries
    """
    def __init__(self, model, cursor, meta=None):
        self.model = model
        self.cursor = cursor

        self.__ct = 0
        self.__idx = 0

        self._result_cache = []
        self._populated = False

    def __iter__(self):
        self.__idx = 0

        if not self._populated:
            return self
        else:
            return iter(self._result_cache)

    def process_row(self, row):
        return row

    def iterate(self):
        row = self.cursor.fetchone()
        if not row:
            self._populated = True
            raise StopIteration
        return self.process_row(row)

    def iterator(self):
        while True:
            yield self.iterate()

    def next(self):
        if self.__idx < self.__ct:
            inst = self._result_cache[self.__idx]
            self.__idx += 1
            return inst

        obj = self.iterate()
        self._result_cache.append(obj)
        self.__ct += 1
        self.__idx += 1
        return obj

    def fill_cache(self, n=None):
        n = n or float('Inf')
        self.__idx = self.__ct
        while not self._populated and (n > self.__ct):
            try:
                self.next()
            except StopIteration:
                break

class NaiveQueryResultWrapper(QueryResultWrapper):
    def __init__(self, model, cursor, meta=None):
        super(NaiveQueryResultWrapper, self).__init__(model, cursor, meta)

        cols = []
        non_cols = []
        for i in range(len(self.cursor.description)):
            col = self.cursor.description[i][0]
            if col in model._meta.columns:
                field_obj = model._meta.columns[col]
                cols.append((i, field_obj.name, field_obj.python_value))
            else:
                non_cols.append((i, col))
        self._cols = cols
        self._non_cols = non_cols

    def process_row(self, row):
        instance = self.model()
        for i, fname, pv in self._cols:
            setattr(instance, fname, pv(row[i]))
        for i, f in self._non_cols:
            setattr(instance, f, row[i])
        instance.prepared()
        return instance

class DictQueryResultWrapper(NaiveQueryResultWrapper):
    def process_row(self, row):
        res = {}
        for i, fname, pv in self._cols:
            res[fname] = pv(row[i])
        for i, f in self._non_cols:
            res[f] = row[i]
        return res

class ModelQueryResultWrapper(QueryResultWrapper):
    def __init__(self, model, cursor, meta=None):
        super(ModelQueryResultWrapper, self).__init__(model, cursor, meta)
        self.column_meta, self.join_meta = meta

    def process_row(self, row):
        collected = self.construct_instance(row)
        instances = self.follow_joins(collected)
        map(lambda i: i.prepared(), instances)
        return instances[0]

    def construct_instance(self, row):
        # we have columns, models, and a graph of joins to reconstruct
        collected_models = {}
        cols = [c[0] for c in self.cursor.description]
        for i, expr in enumerate(self.column_meta):
            value = row[i]
            if isinstance(expr, FieldProxy):
                key = expr._model_alias # model alias
                constructor = expr.model # instance constructor
            elif isinstance(expr, Field):
                key = constructor = expr.model_class
            else:
                key = constructor = self.model

            if key not in collected_models:
                collected_models[key] = constructor()
            instance = collected_models[key]

            if isinstance(expr, Field):
                setattr(instance, expr.name, expr.python_value(value))
            elif isinstance(expr, Expr) and expr._alias:
                setattr(instance, expr._alias, value)
            else:
                setattr(instance, cols[i], value)

        return collected_models

    def follow_joins(self, collected):
        joins = self.join_meta
        stack = [self.model]
        prepared = [collected[self.model]]
        while stack:
            current = stack.pop()
            if current not in joins:
                continue

            inst = collected[current]
            for join in joins[current]:
                if join.model_class in collected:
                    joined_inst = collected[join.model_class]
                    fk_field = current._meta.rel_for_model(join.model_class)
                    if not fk_field:
                        if isinstance(join.on, Expr):
                            fk_field = join.on.lhs
                        else:
                            continue

                    if joined_inst.get_id() is None and fk_field.name in inst._data:
                        rel_inst_id = inst._data[fk_field.name]
                        joined_inst.set_id(rel_inst_id)

                    setattr(inst, fk_field.name, joined_inst)
                    stack.append(join.model_class)
                    prepared.append(joined_inst)

        return prepared

Join = namedtuple('Join', ('model_class', 'join_type', 'on'))

class Query(Leaf):
    require_commit = True

    def __init__(self, model_class):
        super(Query, self).__init__()

        self.model_class = model_class
        self.database = model_class._meta.database

        self._dirty = True
        self._query_ctx = model_class
        self._joins = {self.model_class: []} # adjacency graph
        self._where = None

    def __repr__(self):
        sql, params = self.sql()
        return '%s %s %s' % (self.model_class, sql, params)

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
            self._where = reduce(operator.and_, q_or_node)
        else:
            for piece in q_or_node:
                self._where &= piece

    @returns_clone
    def join(self, model_class, join_type=None, on=None):
        if not self._query_ctx._meta.rel_exists(model_class) and on is None:
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
            accum.append(Expr(model_attr, op, value))
        return accum, joins

    def filter(self, *args, **kwargs):
        # normalize args and kwargs into a new expression
        dq_node = Leaf()
        if args:
            dq_node &= reduce(operator.and_, [a.clone() for a in args])
        if kwargs:
            dq_node &= DQ(**kwargs)

        # dq_node should now be an Expr, lhs = Leaf(), rhs = ...
        q = deque([dq_node])
        dq_joins = set()
        while q:
            curr = q.popleft()
            if not isinstance(curr, Expr):
                continue
            for side, piece in (('lhs', curr.lhs), ('rhs', curr.rhs)):
                if isinstance(piece, DQ):
                    query, joins = self.convert_dict_to_node(piece.query)
                    dq_joins.update(joins)
                    setattr(curr, side, reduce(operator.and_, query))
                else:
                    q.append(piece)

        dq_node = dq_node.rhs

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

    def compiler(self):
        return self.database.compiler()

    def sql(self):
        raise NotImplementedError

    def _execute(self):
        sql, params = self.sql()
        return self.database.execute_sql(sql, params, self.require_commit)

    def execute(self):
        raise NotImplementedError

    def scalar(self, as_tuple=False):
        row = self._execute().fetchone()
        if row and not as_tuple:
            return row[0]
        else:
            return row


class RawQuery(Query):
    def __init__(self, model, query, *params):
        self._sql = query
        self._params = list(params)
        self._qr = None
        self._tuples = False
        self._dicts = False
        super(RawQuery, self).__init__(model)

    def clone(self):
        query = RawQuery(self.model_class, self._sql, *self._params)
        query._tuples = self._tuples
        query._dicts = self._dicts
        return query

    join = not_allowed('joining')
    where = not_allowed('where')
    switch = not_allowed('switch')

    @returns_clone
    def tuples(self, tuples=True):
        self._tuples = tuples

    @returns_clone
    def dicts(self, dicts=True):
        self._dicts = dicts

    def sql(self):
        return self._sql, self._params

    def execute(self):
        if self._qr is None:
            if self._tuples:
                ResultWrapper = QueryResultWrapper
            elif self._dicts:
                ResultWrapper = DictQueryResultWrapper
            else:
                ResultWrapper = NaiveQueryResultWrapper
            self._qr = ResultWrapper(self.model_class, self._execute(), None)
        return self._qr

    def __iter__(self):
        return iter(self.execute())


class SelectQuery(Query):
    def __init__(self, model_class, *selection):
        super(SelectQuery, self).__init__(model_class)
        self.require_commit = self.database.commit_select
        self._explicit_selection = len(selection) > 0
        self._select = self._model_shorthand(selection or model_class._meta.get_fields())
        self._group_by = None
        self._having = None
        self._order_by = None
        self._limit = None
        self._offset = None
        self._distinct = False
        self._for_update = False
        self._naive = False
        self._tuples = False
        self._dicts = False
        self._alias = None
        self._qr = None

    def clone(self):
        query = super(SelectQuery, self).clone()
        query._explicit_selection = self._explicit_selection
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
        query._tuples = self._tuples
        query._dicts = self._dicts
        query._alias = self._alias
        return query

    def _model_shorthand(self, args):
        accum = []
        for arg in args:
            if isinstance(arg, Leaf):
                accum.append(arg)
            elif isinstance(arg, Query):
                accum.append(arg)
            elif isinstance(arg, ModelAlias):
                accum.extend(arg.get_proxy_fields())
            elif issubclass(arg, Model):
                accum.extend(arg._meta.get_fields())
        return accum

    @returns_clone
    def group_by(self, *args):
        self._group_by = self._model_shorthand(args)

    @returns_clone
    def having(self, *q_or_node):
        if self._having is None:
            self._having = reduce(operator.and_, q_or_node)
        else:
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

    @returns_clone
    def tuples(self, tuples=True):
        self._tuples = tuples

    @returns_clone
    def dicts(self, dicts=True):
        self._dicts = dicts

    @returns_clone
    def alias(self, alias=None):
        self._alias = alias

    def annotate(self, rel_model, annotation=None):
        annotation = annotation or fn.Count(rel_model._meta.primary_key).alias('count')
        query = self.clone()
        query = query.ensure_join(query._query_ctx, rel_model)
        if not query._group_by:
            query._group_by = [x.alias() for x in query._select]
        query._select = tuple(query._select) + (annotation,)
        return query

    def _aggregate(self, aggregation=None):
        aggregation = aggregation or fn.Count(self.model_class._meta.primary_key)
        query = self.order_by()
        query._select = [aggregation]
        return query

    def aggregate(self, aggregation=None):
        return self._aggregate(aggregation).scalar()

    def count(self):
        if self._distinct or self._group_by:
            return self.wrapped_count()

        # defaults to a count() of the primary key
        return self.aggregate() or 0

    def wrapped_count(self):
        clone = self.order_by()
        clone._limit = clone._offset = None

        sql, params = clone.sql()
        wrapped = 'SELECT COUNT(1) FROM (%s) AS wrapped_select' % sql
        rq = RawQuery(self.model_class, wrapped, *params)
        return rq.scalar() or 0

    def exists(self):
        clone = self.paginate(1, 1)
        clone._select = [self.model_class._meta.primary_key]
        return bool(clone.scalar())

    def get(self):
        clone = self.paginate(1, 1)
        try:
            return clone.execute().next()
        except StopIteration:
            raise self.model_class.DoesNotExist('instance matching query does not exist:\nSQL: %s\nPARAMS: %s' % (
                self.sql()
            ))

    def first(self):
        res = self.execute()
        res.fill_cache(1)
        try:
            return res._result_cache[0]
        except IndexError:
            pass

    def sql(self):
        return self.compiler().generate_select(self)

    def verify_naive(self):
        for expr in self._select:
            if isinstance(expr, Field) and expr.model_class != self.model_class:
                return False
        return True

    def execute(self):
        if self._dirty or not self._qr:
            query_meta = None
            if self._tuples:
                ResultWrapper = QueryResultWrapper
            elif self._dicts:
                ResultWrapper = DictQueryResultWrapper
            elif self._naive or not self._joins or self.verify_naive():
                ResultWrapper = NaiveQueryResultWrapper
            else:
                query_meta = [self._select, self._joins]
                ResultWrapper = ModelQueryResultWrapper
            self._qr = ResultWrapper(self.model_class, self._execute(), query_meta)
            self._dirty = False
            return self._qr
        else:
            return self._qr

    def __iter__(self):
        return iter(self.execute())

    def __getitem__(self, value):
        offset = limit = None
        if isinstance(value, slice):
            if value.start:
                offset = value.start
            if value.stop:
                limit = value.stop - (value.start or 0)
        else:
            if value < 0:
                raise ValueError('Negative indexes are not supported, try ordering in reverse')
            offset = value
            limit = 1
        if self._limit != limit or self._offset != offset:
            self._qr = None
        self._limit = limit
        self._offset = offset
        res = list(self)
        return limit == 1 and res[0] or res


class UpdateQuery(Query):
    def __init__(self, model_class, update=None):
        self._update = update
        super(UpdateQuery, self).__init__(model_class)

    def clone(self):
        query = super(UpdateQuery, self).clone()
        query._update = dict(self._update)
        return query

    join = not_allowed('joining')

    def sql(self):
        return self.compiler().generate_update(self)

    def execute(self):
        return self.database.rows_affected(self._execute())

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

    def sql(self):
        return self.compiler().generate_insert(self)

    def execute(self):
        return self.database.last_insert_id(self._execute(), self.model_class)

class DeleteQuery(Query):
    join = not_allowed('joining')

    def sql(self):
        return self.compiler().generate_delete(self)

    def execute(self):
        return self.database.rows_affected(self._execute())


class Database(object):
    commit_select = False
    compiler_class = QueryCompiler
    empty_limit = False
    field_overrides = {}
    for_update = False
    interpolation = '?'
    op_overrides = {}
    quote_char = '"'
    reserved_tables = []
    sequences = False
    subquery_delete_same_table = True

    def __init__(self, database, threadlocals=False, autocommit=True,
                 fields=None, ops=None, **connect_kwargs):
        self.init(database, **connect_kwargs)

        if threadlocals:
            self.__local = threading.local()
        else:
            self.__local = type('DummyLocal', (object,), {})

        self._conn_lock = threading.Lock()
        self.autocommit = autocommit

        self.field_overrides = dict_update(self.field_overrides, fields or {})
        self.op_overrides = dict_update(self.op_overrides, ops or {})

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

    @classmethod
    def register_fields(cls, fields):
        cls.field_overrides = dict_update(cls.field_overrides, fields)

    @classmethod
    def register_ops(cls, ops):
        cls.op_overrides = dict_update(cls.op_overrides, ops)

    def last_insert_id(self, cursor, model):
        if model._meta.auto_increment:
            return cursor.lastrowid

    def rows_affected(self, cursor):
        return cursor.rowcount

    def compiler(self):
        return self.compiler_class(
            self.quote_char, self.interpolation, self.field_overrides,
            self.op_overrides)

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

    def get_tables(self):
        raise NotImplementedError

    def get_indexes_for_table(self, table):
        raise NotImplementedError

    def sequence_exists(self, seq):
        raise NotImplementedError

    def create_table(self, model_class):
        qc = self.compiler()
        return self.execute_sql(qc.create_table(model_class))

    def create_index(self, model_class, fields, unique=False):
        qc = self.compiler()
        if not isinstance(fields, (list, tuple)):
            raise ValueError('fields passed to "create_index" must be a list or tuple: "%s"' % fields)
        field_objs = [model_class._meta.fields[f] if isinstance(f, basestring) else f for f in fields]
        return self.execute_sql(qc.create_index(model_class, field_objs, unique))

    def create_foreign_key(self, model_class, field):
        if not field.primary_key:
            return self.create_index(model_class, [field], field.unique)

    def create_sequence(self, seq):
        if self.sequences:
            qc = self.compiler()
            return self.execute_sql(qc.create_sequence(seq))

    def drop_table(self, model_class, fail_silently=False):
        qc = self.compiler()
        return self.execute_sql(qc.drop_table(model_class, fail_silently))

    def drop_sequence(self, seq):
        if self.sequences:
            qc = self.compiler()
            return self.execute_sql(qc.drop_sequence(seq))


class SqliteDatabase(Database):
    op_overrides = {
        OP_LIKE: 'GLOB',
        OP_ILIKE: 'LIKE',
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
    commit_select = True
    empty_limit = True
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
    commit_select = True
    field_overrides = {
        'bigint': 'BIGINT',
        'boolean': 'BOOL',
        'decimal': 'NUMERIC',
        'double': 'DOUBLE PRECISION',
        'float': 'FLOAT',
        'primary_key': 'INTEGER AUTO_INCREMENT',
        'text': 'LONGTEXT',
    }
    for_update = True
    interpolation = '%s'
    op_overrides = {OP_LIKE: 'LIKE BINARY', OP_ILIKE: 'LIKE'}
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
        compiler = self.compiler()
        framing = """
            ALTER TABLE %(table)s ADD CONSTRAINT %(constraint)s
            FOREIGN KEY (%(field)s) REFERENCES %(to)s(%(to_field)s)%(cascade)s;
        """
        db_table = model_class._meta.db_table
        constraint = 'fk_%s_%s_%s' % (
            db_table,
            field.rel_model._meta.db_table,
            field.db_column,
        )

        query = framing % {
            'table': compiler.quote(db_table),
            'constraint': compiler.quote(constraint),
            'field': compiler.quote(field.db_column),
            'to': compiler.quote(field.rel_model._meta.db_table),
            'to_field': compiler.quote(field.rel_model._meta.primary_key.db_column),
            'cascade': ' ON DELETE CASCADE' if field.cascade else '',
        }

        self.execute_sql(query)
        return super(MySQLDatabase, self).create_foreign_key(model_class, field)

    def get_indexes_for_table(self, table):
        res = self.execute_sql('SHOW INDEXES IN `%s`;' % table)
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
        success = True
        if exc_type:
            self.db.rollback()
            success = False
        else:
            self.db.commit()
        self.db.set_autocommit(self._orig)
        return success


class DoesNotExist(Exception):
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
        return sorted(self.fields.items(), key=lambda i: (i[1] is self.primary_key and 1 or 2, i[1]._order))

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

        orig_primary_key = None

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
                    elif not orig_primary_key:
                        orig_primary_key = deepcopy(v.field)

        # initialize the new class and set the magic attributes
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        cls._meta = ModelOptions(cls, **meta_options)
        cls._data = None

        primary_key = None

        # replace the fields with field descriptors, calling the add_to_class hook
        for name, attr in cls.__dict__.items():
            cls._meta.indexes = list(cls._meta.indexes)
            if isinstance(attr, Field):
                attr.add_to_class(cls, name)
                if attr.primary_key:
                    primary_key = attr

        if primary_key is None:
            if orig_primary_key:
                primary_key = orig_primary_key
                name = primary_key.name
            else:
                primary_key = PrimaryKeyField(primary_key=True)
                name = 'id'
            primary_key.add_to_class(cls, name)

        cls._meta.primary_key = primary_key
        cls._meta.auto_increment = isinstance(primary_key, PrimaryKeyField) or bool(primary_key.sequence)
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


class FieldProxy(Field):
    def __init__(self, alias, field_instance):
        self._model_alias = alias
        self.model = self._model_alias.model_class
        self.field_instance = field_instance

    def clone_base(self):
        return FieldProxy(self._model_alias, self.field_instance)

    def __getattr__(self, attr):
        if attr == 'model_class':
            return self._model_alias
        return getattr(self.field_instance, attr)

class ModelAlias(object):
    def __init__(self, model_class):
        self.__dict__['model_class'] = model_class

    def __getattr__(self, attr):
        model_attr = getattr(self.model_class, attr)
        if isinstance(model_attr, Field):
            return FieldProxy(self, model_attr)
        return model_attr

    def __setattr__(self, attr, value):
        raise AttributeError('Cannot set attributes on ModelAlias instances')

    def get_proxy_fields(self):
        return [FieldProxy(self, f) for f in self.model_class._meta.get_fields()]


class Model(object):
    __metaclass__ = BaseModel

    def __init__(self, *args, **kwargs):
        self._data = self._meta.get_default_dict()
        self._obj_cache = {} # cache of related objects

        for k, v in kwargs.items():
            setattr(self, k, v)

    @classmethod
    def alias(cls):
        return ModelAlias(cls)

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
    def raw(cls, sql, *params):
        return RawQuery(cls, sql, *params)

    @classmethod
    def create(cls, **query):
        inst = cls(**query)
        inst.save(force_insert=True)
        return inst

    @classmethod
    def get(cls, *query, **kwargs):
        sq = cls.select().naive()
        if query:
            sq = sq.where(*query)
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
    def filter(cls, *dq, **query):
        return cls.select().filter(*dq, **query)

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

    def _prune_fields(self, field_dict, only):
        new_data = {}
        for field in only:
            if field.name in field_dict:
                new_data[field.name] = field_dict[field.name]
        return new_data

    def save(self, force_insert=False, only=None):
        field_dict = dict(self._data)
        pk = self._meta.primary_key
        if only:
            field_dict = self._prune_fields(field_dict, only)
        if self.get_id() is not None and not force_insert:
            field_dict.pop(pk.name, None)
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
               self.get_id() is not None and \
               other.get_id() == self.get_id()

    def __ne__(self, other):
        return not self == other


def prefetch_add_subquery(sq, subqueries):
    fixed_queries = [(sq, None)]
    for i, subquery in enumerate(subqueries):
        if not isinstance(subquery, Query) and issubclass(subquery, Model):
            subquery = subquery.select()
        subquery_model = subquery.model_class
        fkf = None
        for j in range(i, -1, -1):
            last_query = fixed_queries[j][0]
            fkf = subquery_model._meta.rel_for_model(last_query.model_class)
            if fkf:
                break
        if not fkf:
            raise AttributeError('Error: unable to find foreign key for query: %s' % subquery)
        fixed_queries.append((subquery.where(fkf << last_query), fkf))

    return fixed_queries

def prefetch(sq, *subqueries):
    if not subqueries:
        return sq
    fixed_queries = prefetch_add_subquery(sq, subqueries)

    deps = {}
    rel_map = {}
    for query, foreign_key_field in reversed(fixed_queries):
        query_model = query.model_class
        deps[query_model] = {}
        id_map = deps[query_model]
        has_relations = bool(rel_map.get(query_model))

        for result in query:
            if foreign_key_field:
                fk_val = result._data[foreign_key_field.name]
                id_map.setdefault(fk_val, [])
                id_map[fk_val].append(result)
            if has_relations:
                for rel_model, rel_fk in rel_map[query_model]:
                    rel_name = '%s_prefetch' % rel_fk.related_name
                    rel_instances = deps[rel_model].get(result.get_id(), [])
                    for inst in rel_instances:
                        setattr(inst, rel_fk.name, result)
                    setattr(result, rel_name, rel_instances)
        if foreign_key_field:
            rel_model = foreign_key_field.rel_model
            rel_map.setdefault(rel_model, [])
            rel_map[rel_model].append((query_model, foreign_key_field))

    return query

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
            for foreign_key in model._meta.reverse_rel.values():
                dfs(foreign_key.model_class)
            ordering.append(model)  # parent will follow descendants
    # order models by name and table initially to guarantee a total ordering
    names = lambda m: (m._meta.name, m._meta.db_table)
    for m in sorted(models, key=names, reverse=True):
        dfs(m)
    return list(reversed(ordering))  # want parents first in output ordering
