#     (\
#     (  \  /(o)\     caw!
#     (   \/  ()/ /)
#      (   `;.))'".)
#       `(/////.-'
#    =====))=))===()
#      ///'
#     //
#    '
import datetime
import decimal
import logging
import operator
import re
import sys
import threading
from collections import deque
from collections import namedtuple
from copy import deepcopy
from inspect import isclass

__all__ = [
    'BareField',
    'BigIntegerField',
    'BlobField',
    'BooleanField',
    'CharField',
    'Clause',
    'CompositeKey',
    'DateField',
    'DateTimeField',
    'DecimalField',
    'DoesNotExist',
    'DoubleField',
    'DQ',
    'Entity',
    'Field',
    'FloatField',
    'fn',
    'ForeignKeyField',
    'ImproperlyConfigured',
    'IntegerField',
    'JOIN_FULL',
    'JOIN_INNER',
    'JOIN_LEFT_OUTER',
    'Model',
    'MySQLDatabase',
    'PostgresqlDatabase',
    'prefetch',
    'PrimaryKeyField',
    'R',
    'SqliteDatabase',
    'TextField',
    'TimeField',
]

# Python 2/3 compat
def with_metaclass(meta, base=object):
    return meta("NewBase", (base,), {})

PY3 = sys.version_info[0] == 3
if PY3:
    import builtins
    from collections import Callable
    from functools import reduce
    callable = lambda c: isinstance(c, Callable)
    unicode_type = str
    string_type = bytes
    basestring = str
    print_ = getattr(builtins, 'print')
    binary_construct = lambda s: bytes(s.encode('raw_unicode_escape'))
else:
    unicode_type = unicode
    string_type = basestring
    binary_construct = buffer
    def print_(s):
        sys.stdout.write(s)
        sys.stdout.write('\n')

# DB libraries
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

class ImproperlyConfigured(Exception): pass

if sqlite3 is None and psycopg2 is None and mysql is None:
    raise ImproperlyConfigured('Either sqlite3, psycopg2 or MySQLdb must be '
                               'installed')

if sqlite3:
    sqlite3.register_adapter(decimal.Decimal, str)
    sqlite3.register_adapter(datetime.date, str)
    sqlite3.register_adapter(datetime.time, str)

SQLITE_DT_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d',
    '%H:%M:%S',
    '%H:%M:%S.%f',
    '%H:%M')
DT_PARTS = ['year', 'month', 'day', 'hour', 'minute', 'second']
DT_LOOKUPS = set(DT_PARTS)

def _sqlite_date_part(lookup_type, datetime_string):
    assert lookup_type in DT_LOOKUPS
    dt = format_date_time(datetime_string, SQLITE_DT_FORMATS)
    return getattr(dt, lookup_type)

if psycopg2:
    from psycopg2 import extensions as pg_extensions

# Peewee
logger = logging.getLogger('peewee')

OP_AND = 'and'
OP_OR = 'or'

OP_ADD = '+'
OP_SUB = '-'
OP_MUL = '*'
OP_DIV = '/'
OP_BIN_AND = '&'
OP_BIN_OR = '|'
OP_XOR = '^'
OP_MOD = '%'

OP_EQ = '='
OP_LT = '<'
OP_LTE = '<='
OP_GT = '>'
OP_GTE = '>='
OP_NE = '!='
OP_IN = 'in'
OP_IS = 'is'
OP_LIKE = 'like'
OP_ILIKE = 'ilike'
OP_BETWEEN = 'between'

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

JOIN_INNER = 'inner'
JOIN_LEFT_OUTER = 'left outer'
JOIN_FULL = 'full'

def dict_update(orig, extra):
    new = orig.copy()
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
            fn, type(self).__name__))
    return inner


class Node(object):
    def __init__(self):
        self._negated = False
        self._alias = None
        self._ordering = None

    def clone_base(self):
        return type(self)()

    def clone(self):
        inst = self.clone_base()
        inst._negated = self._negated
        inst._alias = self._alias
        return inst

    @returns_clone
    def __invert__(self):
        self._negated = not self._negated

    @returns_clone
    def alias(self, a=None):
        self._alias = a

    @returns_clone
    def asc(self):
        self._ordering = 'ASC'

    @returns_clone
    def desc(self):
        self._ordering = 'DESC'

    def _e(op, inv=False):
        def inner(self, rhs):
            if inv:
                return Expression(rhs, op, self)
            return Expression(self, op, rhs)
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

    bin_and = _e(OP_BIN_AND)
    bin_or = _e(OP_BIN_OR)

    def between(self, low, high):
        return Expression(self, OP_BETWEEN, Clause(low, R('AND'), high))

class Expression(Node):
    def __init__(self, lhs, op, rhs):
        super(Expression, self).__init__()
        self.lhs = lhs
        self.op = op
        self.rhs = rhs

    def clone_base(self):
        return Expression(self.lhs, self.op, self.rhs)

class DQ(Node):
    def __init__(self, **query):
        super(DQ, self).__init__()
        self.query = query

    def clone_base(self):
        return DQ(**self.query)

class Param(Node):
    def __init__(self, value):
        self.value = value
        super(Param, self).__init__()

    def clone_base(self):
        return Param(self.value)

class R(Node):
    def __init__(self, value):
        self.value = value
        super(R, self).__init__()

    def clone_base(self):
        return R(self.value)

class Func(Node):
    def __init__(self, name, *nodes):
        self.name = name
        self.nodes = nodes
        super(Func, self).__init__()

    def clone_base(self):
        return Func(self.name, *self.nodes)

    def __getattr__(self, attr):
        def dec(*args, **kwargs):
            return Func(attr, *args, **kwargs)
        return dec

fn = Func(None)

class Clause(Node):
    def __init__(self, *nodes):
        super(Clause, self).__init__()
        self.nodes = nodes

    def clone_base(self):
        return Clause(*self.nodes)

class Entity(Node):
    def __init__(self, *path):
        super(Entity, self).__init__()
        self.path = path

    def clone_base(self):
        return Entity(*self.path)

    def __getattr__(self, attr):
        return Entity(*self.path + (attr,))

Join = namedtuple('Join', ('model_class', 'join_type', 'on'))

class FieldDescriptor(object):
    def __init__(self, field):
        self.field = field
        self.att_name = self.field.name

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return instance._data.get(self.att_name)
        return self.field

    def __set__(self, instance, value):
        instance._data[self.att_name] = value

class Field(Node):
    _field_counter = 0
    _order = 0
    db_field = 'unknown'
    template = '%(column_type)s'
    template_extra = ''

    def __init__(self, null=False, index=False, unique=False,
                 verbose_name=None, help_text=None, db_column=None,
                 default=None, choices=None, primary_key=False, sequence=None,
                 *args, **kwargs):
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

        self._is_bound = False
        super(Field, self).__init__()

    def clone_base(self, **kwargs):
       inst = type(self)(
           null=self.null,
           index=self.index,
           unique=self.unique,
           verbose_name=self.verbose_name,
           help_text=self.help_text,
           db_column=self.db_column,
           default=self.default,
           choices=self.choices,
           primary_key=self.primary_key,
           sequence=self.sequence,
           **kwargs
       )
       inst.attributes = dict(self.attributes)
       if self._is_bound:
           inst.name = self.name
           inst.model_class = self.model_class
       return inst

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        self.db_column = self.db_column or self.name
        if not self.verbose_name:
            self.verbose_name = re.sub('_+', ' ', name).title()

        model_class._meta.fields[self.name] = self
        model_class._meta.columns[self.db_column] = self

        setattr(model_class, name, FieldDescriptor(self))
        self._is_bound = True

    def get_database(self):
        return self.model_class._meta.database

    def field_attributes(self):
        return {}

    def get_db_field(self):
        return self.db_field

    def get_template(self):
        return self.template

    def coerce(self, value):
        return value

    def db_value(self, value):
        return value if value is None else self.coerce(value)

    def python_value(self, value):
        return value if value is None else self.coerce(value)

    def __hash__(self):
        return hash(self.name + '.' + self.model_class.__name__)

class BareField(Field):
    db_field = 'bare'
    template = ''

class IntegerField(Field):
    db_field = 'int'
    coerce = int

class BigIntegerField(IntegerField):
    db_field = 'bigint'

class PrimaryKeyField(IntegerField):
    db_field = 'primary_key'

    def __init__(self, *args, **kwargs):
        kwargs['primary_key'] = True
        super(PrimaryKeyField, self).__init__(*args, **kwargs)

class FloatField(Field):
    db_field = 'float'
    coerce = float

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
            exp = D(10) ** (-self.attributes['decimal_places'])
            rounding = self.attributes['rounding']
            return D(str(value)).quantize(exp, rounding=rounding)
        return value

    def python_value(self, value):
        if value is not None:
            if isinstance(value, decimal.Decimal):
                return value
            return decimal.Decimal(str(value))

def format_unicode(s, encoding='utf-8'):
    if isinstance(s, unicode_type):
        return s
    elif isinstance(s, string_type):
        return s.decode(encoding)
    return unicode_type(s)

class CharField(Field):
    db_field = 'string'
    template = '%(column_type)s(%(max_length)s)'

    def field_attributes(self):
        return {'max_length': 255}

    def coerce(self, value):
        return format_unicode(value or '')

class TextField(Field):
    db_field = 'text'

    def coerce(self, value):
        return format_unicode(value or '')

class BlobField(Field):
    db_field = 'blob'

    def db_value(self, value):
        if isinstance(value, basestring):
            return binary_construct(value)
        return value

def format_date_time(value, formats, post_process=None):
    post_process = post_process or (lambda x: x)
    for fmt in formats:
        try:
            return post_process(datetime.datetime.strptime(value, fmt))
        except ValueError:
            pass
    return value

def _date_part(date_part):
    def dec(self):
        return self.model_class._meta.database.extract_date(date_part, self)
    return dec

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

    year = property(_date_part('year'))
    month = property(_date_part('month'))
    day = property(_date_part('day'))
    hour = property(_date_part('hour'))
    minute = property(_date_part('minute'))
    second = property(_date_part('second'))

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

    year = property(_date_part('year'))
    month = property(_date_part('month'))
    day = property(_date_part('day'))

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

    hour = property(_date_part('hour'))
    minute = property(_date_part('minute'))
    second = property(_date_part('second'))

class BooleanField(Field):
    db_field = 'bool'
    coerce = bool

class RelationDescriptor(FieldDescriptor):
    def __init__(self, field, rel_model):
        self.rel_model = rel_model
        super(RelationDescriptor, self).__init__(field)

    def get_object_or_id(self, instance):
        rel_id = instance._data.get(self.att_name)
        if rel_id is not None or self.att_name in instance._obj_cache:
            if self.att_name not in instance._obj_cache:
                obj = self.rel_model.get(
                    self.rel_model._meta.primary_key == rel_id)
                instance._obj_cache[self.att_name] = obj
            return instance._obj_cache[self.att_name]
        elif not self.field.null:
            raise self.rel_model.DoesNotExist
        return rel_id

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return self.get_object_or_id(instance)
        return self.field

    def __set__(self, instance, value):
        if isinstance(value, self.rel_model):
            instance._data[self.att_name] = value.get_id()
            instance._obj_cache[self.att_name] = value
        else:
            orig_value = instance._data.get(self.att_name)
            instance._data[self.att_name] = value
            if orig_value != value and self.att_name in instance._obj_cache:
                del instance._obj_cache[self.att_name]

class ReverseRelationDescriptor(object):
    def __init__(self, field):
        self.field = field
        self.rel_model = field.model_class

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return self.rel_model.select().where(self.field==instance.get_id())
        return self

class ForeignKeyField(IntegerField):
    def __init__(self, rel_model, null=False, related_name=None, cascade=False,
                 extra=None, *args, **kwargs):
        self.rel_model = rel_model
        self._related_name = related_name
        self.cascade = cascade
        self.extra = extra

        kwargs.update(dict(
            cascade='ON DELETE CASCADE' if self.cascade else '',
            extra=extra or ''))

        super(ForeignKeyField, self).__init__(null=null, *args, **kwargs)

    def clone_base(self):
         return super(ForeignKeyField, self).clone_base(
            rel_model=self.rel_model,
            related_name=self.related_name,
            cascade=self.cascade,
            extra=self.extra)

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        self.db_column = self.db_column or '%s_id' % self.name
        if not self.verbose_name:
            self.verbose_name = re.sub('_+', ' ', name).title()

        model_class._meta.fields[self.name] = self
        model_class._meta.columns[self.db_column] = self

        model_name = model_class._meta.name
        self.related_name = self._related_name or '%s_set' % (model_name)

        if self.rel_model == 'self':
            self.rel_model = self.model_class
        if self.related_name in self.rel_model._meta.fields:
            error = ('Foreign key: %s.%s related name "%s" collision with '
                     'field of the same name.')
            params = self.model_class._meta.name, self.name, self.related_name
            raise AttributeError(error % params)
        if self.related_name in self.rel_model._meta.reverse_rel:
            error = ('Foreign key: %s.%s related name "%s" collision with '
                     'foreign key using same related_name.')
            params = self.model_class._meta.name, self.name, self.related_name
            raise AttributeError(error % params)

        fk_descriptor = RelationDescriptor(self, self.rel_model)
        backref_descriptor = ReverseRelationDescriptor(self)
        setattr(model_class, name, fk_descriptor)
        setattr(self.rel_model, self.related_name, backref_descriptor)
        self._is_bound = True

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


class CompositeKey(object):
    sequence = None

    def __init__(self, *fields):
        self.fields = fields

    def add_to_class(self, model_class, name):
        self.name = name
        setattr(model_class, name, self)

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return [getattr(instance, field) for field in self.fields]
        return self

    def __set__(self, instance, value):
        pass


class QueryCompiler(object):
    field_map = {
        'bare': '',
        'bigint': 'BIGINT',
        'blob': 'BLOB',
        'bool': 'SMALLINT',
        'date': 'DATE',
        'datetime': 'DATETIME',
        'decimal': 'DECIMAL',
        'double': 'REAL',
        'float': 'REAL',
        'int': 'INTEGER',
        'primary_key': 'INTEGER',
        'string': 'VARCHAR',
        'text': 'TEXT',
        'time': 'TIME',
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
        OP_BIN_AND: '&',
        OP_BIN_OR: '|',
        OP_LIKE: 'LIKE',
        OP_ILIKE: 'ILIKE',
        OP_BETWEEN: 'BETWEEN',
        OP_ADD: '+',
        OP_SUB: '-',
        OP_MUL: '*',
        OP_DIV: '/',
        OP_XOR: '#',
        OP_AND: 'AND',
        OP_OR: 'OR',
        OP_MOD: '%',
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
        return s.join((self.quote_char, self.quote_char))

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

    def _parse(self, node, alias_map, conv):
        # By default treat the incoming node as a raw value that should be
        # parameterized.
        sql = self.interpolation
        params = [node]
        unknown = False
        if isinstance(node, Expression):
            if isinstance(node.lhs, Field):
                conv = node.lhs
            lhs, lparams = self.parse_node(node.lhs, alias_map, conv)
            rhs, rparams = self.parse_node(node.rhs, alias_map, conv)
            sql = '(%s %s %s)' % (lhs, self.get_op(node.op), rhs)
            params = lparams + rparams
        elif isinstance(node, Field):
            sql = self.quote(node.db_column)
            if alias_map and node.model_class in alias_map:
                sql = '.'.join((alias_map[node.model_class], sql))
            params = []
        elif isinstance(node, Func):
            sql, params = self.parse_node_list(node.nodes, alias_map, conv)
            sql = '%s(%s)' % (node.name, sql)
        elif isinstance(node, Clause):
            sql, params = self.parse_node_list(
                node.nodes, alias_map, conv, ' ')
        elif isinstance(node, Param):
            params = [node.value]
        elif isinstance(node, R):
            sql = node.value
            params = []
        elif isinstance(node, SelectQuery):
            max_alias = self._max_alias(alias_map)
            alias_copy = alias_map and alias_map.copy() or None
            clone = node.clone()
            if not node._explicit_selection:
                clone._select = (clone.model_class._meta.primary_key,)
            sub, params = self.generate_select(clone, max_alias, alias_copy)
            sql = '(%s)' % sub
        elif isinstance(node, (list, tuple)):
            sql, params = self.parse_node_list(node, alias_map, conv)
            sql = '(%s)' % sql
        elif isinstance(node, Model):
            sql = self.interpolation
            params = [node.get_id()]
        elif isinstance(node, Entity):
            sql = '.'.join(map(self.quote, node.path))
            params = []
        elif isclass(node) and issubclass(node, Model):
            sql = self.quote(node._meta.db_table)
            params = []
        else:
            unknown = True
        return sql, params, unknown

    def parse_node(self, node, alias_map=None, conv=None):
        sql, params, unknown = self._parse(node, alias_map, conv)
        if unknown and conv and params:
            params = [conv.db_value(i) for i in params]

        if isinstance(node, Node):
            if node._negated:
                sql = 'NOT %s' % sql
            if node._alias:
                sql = ' '.join((sql, 'AS', node._alias))
            if node._ordering:
                sql = ' '.join((sql, node._ordering))
        return sql, params

    def parse_node_list(self, nodes, alias_map, conv=None, glue=', '):
        sql = []
        params = []
        for node in nodes:
            node_sql, node_params = self.parse_node(node, alias_map, conv)
            sql.append(node_sql)
            params.extend(node_params)
        return glue.join(sql), params

    def parse_field_dict(self, d):
        sets, params = [], []
        for field, value in d.items():
            field_sql, _ = self.parse_node(field)
            # because we don't know whether to call db_value or parse_node
            # first, we'd prefer to call parse_node since its more general, but
            # it does special things with lists -- it treats them as if it were
            # buliding up an IN query. for some things we don't want that, so
            # here, if the node is *not* a special object, we'll pass thru
            # parse_node and let db_value handle it
            if not isinstance(value, (Node, Model, Query)):
                value = Param(value)  # passthru to the field's db_value func
            val_sql, val_params = self.parse_node(value)
            val_params = [field.db_value(vp) for vp in val_params]
            sets.append((field_sql, val_sql))
            params.extend(val_params)
        return sets, params

    def parse_query_node(self, node, alias_map):
        if node is not None:
            return self.parse_node(node, alias_map)
        return '', []

    def calculate_alias_map(self, query, start=1):
        make_alias = lambda model: model._meta.table_alias or 't%s' % start
        alias_map = {query.model_class: make_alias(query.model_class)}
        for model, joins in query._joins.items():
            if model not in alias_map:
                start += 1
                alias_map[model] = make_alias(model)
            for join in joins:
                if join.model_class not in alias_map:
                    start += 1
                    alias_map[join.model_class] = make_alias(join.model_class)
        return alias_map

    def generate_joins(self, joins, model_class, alias_map):
        sql = []
        params = []
        seen = set()
        q = [model_class]
        while q:
            curr = q.pop()
            if curr not in joins or curr in seen:
                continue
            seen.add(curr)
            for join in joins[curr]:
                src = curr
                dest = join.model_class
                if isinstance(join.on, Expression):
                    # Clear any alias on the join expression.
                    join_node = join.on.clone().alias()
                else:
                    field = src._meta.rel_for_model(dest, join.on)
                    if field:
                        left_field = field
                        right_field = dest._meta.primary_key
                    else:
                        field = dest._meta.rel_for_model(src, join.on)
                        left_field = src._meta.primary_key
                        right_field = field
                    join_node = (left_field == right_field)

                join_type = join.join_type or JOIN_INNER
                join_sql, join_params = self.parse_node(join_node, alias_map)

                sql.append('%s JOIN %s AS %s ON %s' % (
                    self.join_map[join_type],
                    self.quote(dest._meta.db_table),
                    alias_map[dest],
                    join_sql))
                params.extend(join_params)

                q.append(dest)
        return sql, params

    def generate_select(self, query, start=1, alias_map=None):
        model = query.model_class
        db = model._meta.database

        alias_map = alias_map or {}
        alias_map.update(self.calculate_alias_map(query, start))

        parts = ['SELECT']
        params = []

        if query._distinct:
            parts.append('DISTINCT')

        select, s_params = self.parse_node_list(query._select, alias_map)
        parts.append(select)
        params.extend(s_params)

        parts.append('FROM %s AS %s' % (
            self.quote(model._meta.db_table),
            alias_map[model]))

        joins, j_params = self.generate_joins(query._joins, model, alias_map)
        if joins:
            parts.append(' '.join(joins))
            params.extend(j_params)

        where, w_params = self.parse_query_node(query._where, alias_map)
        if where:
            parts.append('WHERE %s' % where)
            params.extend(w_params)

        if query._group_by:
            group, g_params = self.parse_node_list(query._group_by, alias_map)
            parts.append('GROUP BY %s' % group)
            params.extend(g_params)

        if query._having:
            having, h_params = self.parse_query_node(query._having, alias_map)
            parts.append('HAVING %s' % having)
            params.extend(h_params)

        if query._order_by:
            order, o_params = self.parse_node_list(query._order_by, alias_map)
            parts.append('ORDER BY %s' % order)
            params.extend(o_params)

        if query._limit or (query._offset and db.limit_max):
            limit = query._limit or db.limit_max
            parts.append('LIMIT %s' % limit)
        if query._offset:
            parts.append('OFFSET %s' % query._offset)
        for_update, no_wait = query._for_update
        if for_update:
            parts.append('FOR UPDATE')
            if no_wait:
                parts.append('NOWAIT')

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

        if sets:
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
        template = field.get_template()

        if isinstance(field, ForeignKeyField):
            to_pk = field.rel_model._meta.primary_key
            if not isinstance(to_pk, PrimaryKeyField):
                template = to_pk.get_template()
                attrs.update(to_pk.attributes)

        parts = [self.quote(field.db_column), template]
        if not field.null:
            parts.append('NOT NULL')
        if field.primary_key:
            parts.append('PRIMARY KEY')
        if field.template_extra:
            parts.append(field.template_extra)
        if isinstance(field, ForeignKeyField):
            ref_mc = (
                self.quote(field.rel_model._meta.db_table),
                self.quote(field.rel_model._meta.primary_key.db_column))
            parts.append('REFERENCES %s (%s)' % ref_mc)
            parts.append('%(cascade)s%(extra)s')
        elif field.sequence:
            parts.append("DEFAULT NEXTVAL('%s')" % self.quote(field.sequence))
        return ' '.join(p % attrs for p in parts)

    def create_table_sql(self, model_class, safe=False):
        parts = ['CREATE TABLE']
        if safe:
            parts.append('IF NOT EXISTS')
        meta = model_class._meta
        parts.append(self.quote(meta.db_table))
        columns = map(self.field_sql, meta.get_fields())
        if isinstance(meta.primary_key, CompositeKey):
            pk_cols = map(self.quote, (
                meta.fields[f].db_column for f in meta.primary_key.fields))
            columns.append('PRIMARY KEY (%s)' % ', '.join(pk_cols))
        parts.append('(%s)' % ', '.join(columns))
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
        self._initialized = False

        if meta is not None:
            self.column_meta, self.join_meta = meta
        else:
            self.column_meta = self.join_meta = None

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
        elif not self._initialized:
            self.initialize(self.cursor.description)
            self._initialized = True
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
    __next__ = next

    def fill_cache(self, n=None):
        n = n or float('Inf')
        if n < 0:
            raise ValueError('Negative values are not supported.')
        self.__idx = self.__ct
        while not self._populated and (n > self.__ct):
            try:
                self.next()
            except StopIteration:
                break

class ExtQueryResultWrapper(QueryResultWrapper):
    def initialize(self, description):
        model = self.model
        conv = []
        identity = lambda x: x
        for i in range(len(description)):
            column = description[i][0]
            func = identity
            if column in model._meta.columns:
                field_obj = model._meta.columns[column]
                column = field_obj.name
                func = field_obj.python_value
            elif self.column_meta is not None:
                select_column = self.column_meta[i]
                # Special-case handling aggregations.
                if (isinstance(select_column, Func) and
                        isinstance(select_column.nodes[0], Field)):
                    func = select_column.nodes[0].python_value
            conv.append((i, column, func))
        self.conv = conv

class TuplesQueryResultWrapper(ExtQueryResultWrapper):
    def process_row(self, row):
        return tuple([self.conv[i][2](col) for i, col in enumerate(row)])

class NaiveQueryResultWrapper(ExtQueryResultWrapper):
    def process_row(self, row):
        instance = self.model()
        for i, column, func in self.conv:
            setattr(instance, column, func(row[i]))
        instance.prepared()
        return instance

class DictQueryResultWrapper(ExtQueryResultWrapper):
    def process_row(self, row):
        res = {}
        for i, column, func in self.conv:
            res[column] = func(row[i])
        return res

class ModelQueryResultWrapper(QueryResultWrapper):
    def initialize(self, description):
        column_map = []
        join_map = []
        models = set([self.model])
        for i, node in enumerate(self.column_meta):
            attr = conv = None
            if isinstance(node, Field):
                if isinstance(node, FieldProxy):
                    key = node._model_alias
                    constructor = node.model
                else:
                    key = constructor = node.model_class
                attr = node.name
                conv = node.python_value
            else:
                key = constructor = self.model
                if isinstance(node, Expression) and node._alias:
                    attr = node._alias
            column_map.append((key, constructor, attr, conv))
            models.add(key)

        joins = self.join_meta
        stack = [self.model]
        while stack:
            current = stack.pop()
            if current not in joins:
                continue

            for join in joins[current]:
                join_model = join.model_class
                if join_model in models:
                    fk_field = current._meta.rel_for_model(join_model)
                    if not fk_field:
                        if isinstance(join.on, Expression):
                            fk_name = join.on._alias or join.on.lhs.name
                        else:
                            # Patch the joined model using the name of the
                            # database table.
                            fk_name = join_model._meta.db_table
                    else:
                        fk_name = fk_field.name

                    stack.append(join_model)
                    join_map.append((current, fk_name, join_model))

        self.column_map, self.join_map = column_map, join_map

    def process_row(self, row):
        collected = self.construct_instance(row)
        instances = self.follow_joins(collected)
        for i in instances:
            i.prepared()
        return instances[0]

    def construct_instance(self, row):
        collected_models = {}
        for i, (key, constructor, attr, conv) in enumerate(self.column_map):
            value = row[i]
            if key not in collected_models:
                collected_models[key] = constructor()
            instance = collected_models[key]
            if attr is None:
                attr = self.cursor.description[i][0]
            if conv is not None:
                value = conv(value)
            setattr(instance, attr, value)

        return collected_models

    def follow_joins(self, collected):
        prepared = [collected[self.model]]
        for (lhs, attr, rhs) in self.join_map:
            inst = collected[lhs]
            joined_inst = collected[rhs]

            if joined_inst.get_id() is None and attr in inst._data:
                joined_inst.set_id(inst._data[attr])

            setattr(inst, attr, joined_inst)
            prepared.append(joined_inst)

        return prepared


class Query(Node):
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
        return self._clone_attributes(query)

    def _clone_attributes(self, query):
        if self._where is not None:
            query._where = self._where.clone()
        query._joins = self._clone_joins()
        query._query_ctx = self._query_ctx
        return query

    def _clone_joins(self):
        return dict(
            (mc, list(j)) for mc, j in self._joins.items()
        )

    def _build_tree(self, initial, expressions):
        reduced = reduce(operator.and_, expressions)
        if initial is None:
            return reduced
        return initial & reduced

    @returns_clone
    def where(self, *expressions):
        self._where = self._build_tree(self._where, expressions)

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
        relationship = (ForeignKeyField, ReverseRelationDescriptor)
        for key, value in sorted(qdict.items()):
            curr = self.model_class
            if '__' in key and key.rsplit('__', 1)[1] in DJANGO_MAP:
                key, op = key.rsplit('__', 1)
                op = DJANGO_MAP[op]
            else:
                op = OP_EQ
            for piece in key.split('__'):
                model_attr = getattr(curr, piece)
                if isinstance(model_attr, relationship):
                    curr = model_attr.rel_model
                    joins.append(model_attr)
            accum.append(Expression(model_attr, op, value))
        return accum, joins

    def filter(self, *args, **kwargs):
        # normalize args and kwargs into a new expression
        dq_node = Node()
        if args:
            dq_node &= reduce(operator.and_, [a.clone() for a in args])
        if kwargs:
            dq_node &= DQ(**kwargs)

        # dq_node should now be an Expression, lhs = Node(), rhs = ...
        q = deque([dq_node])
        dq_joins = set()
        while q:
            curr = q.popleft()
            if not isinstance(curr, Expression):
                continue
            for side, piece in (('lhs', curr.lhs), ('rhs', curr.rhs)):
                if isinstance(piece, DQ):
                    query, joins = self.convert_dict_to_node(piece.query)
                    dq_joins.update(joins)
                    expression = reduce(operator.and_, query)
                    # Apply values from the DQ object.
                    expression._negated = piece._negated
                    expression._alias = piece._alias
                    setattr(curr, side, expression)
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

    def scalar(self, as_tuple=False, convert=False):
        if convert:
            row = self.tuples().first()
        else:
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
                ResultWrapper = TuplesQueryResultWrapper
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
        selection = selection or model_class._meta.get_fields()
        self._select = self._model_shorthand(selection)
        self._group_by = None
        self._having = None
        self._order_by = None
        self._limit = None
        self._offset = None
        self._distinct = False
        self._for_update = (False, False)
        self._naive = False
        self._tuples = False
        self._dicts = False
        self._alias = None
        self._qr = None

    def _clone_attributes(self, query):
        query = super(SelectQuery, self)._clone_attributes(query)
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
            if isinstance(arg, Node):
                accum.append(arg)
            elif isinstance(arg, Query):
                accum.append(arg)
            elif isinstance(arg, ModelAlias):
                accum.extend(arg.get_proxy_fields())
            elif isclass(arg) and issubclass(arg, Model):
                accum.extend(arg._meta.get_fields())
        return accum

    @returns_clone
    def group_by(self, *args):
        self._group_by = self._model_shorthand(args)

    @returns_clone
    def having(self, *expressions):
        self._having = self._build_tree(self._having, expressions)

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
    def for_update(self, for_update=True, nowait=False):
        self._for_update = (for_update, nowait)

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
        if annotation is None:
            annotation = fn.Count(rel_model._meta.primary_key).alias('count')
        query = self.clone()
        query = query.ensure_join(query._query_ctx, rel_model)
        if not query._group_by:
            query._group_by = [x.alias() for x in query._select]
        query._select = tuple(query._select) + (annotation,)
        return query

    def _aggregate(self, aggregation=None):
        if aggregation is None:
            aggregation = fn.Count(self.model_class._meta.primary_key)
        query = self.order_by()
        query._select = [aggregation]
        return query

    def aggregate(self, aggregation=None, convert=True):
        return self._aggregate(aggregation).scalar(convert=convert)

    def count(self):
        if self._distinct or self._group_by:
            return self.wrapped_count()

        # defaults to a count() of the primary key
        return self.aggregate(convert=False) or 0

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
            raise self.model_class.DoesNotExist(
                'Instance matching query does not exist:\nSQL: %s\nPARAMS: %s'
                % self.sql())

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
        model_class = self.model_class
        for node in self._select:
            if isinstance(node, Field) and node.model_class != model_class:
                return False
        return True

    def execute(self):
        if self._dirty or not self._qr:
            model_class = self.model_class
            query_meta = [self._select, self._joins]
            if self._tuples:
                ResultWrapper = TuplesQueryResultWrapper
            elif self._dicts:
                ResultWrapper = DictQueryResultWrapper
            elif self._naive or not self._joins or self.verify_naive():
                ResultWrapper = NaiveQueryResultWrapper
            else:
                ResultWrapper = ModelQueryResultWrapper
            self._qr = ResultWrapper(model_class, self._execute(), query_meta)
            self._dirty = False
            return self._qr
        else:
            return self._qr

    def __iter__(self):
        return iter(self.execute())

    def iterator(self):
        return iter(self.execute().iterator())

    def __getitem__(self, value):
        start = end = None
        res = self.execute()
        if isinstance(value, slice):
            index = value.stop
        else:
            index = value
        if index >= 0:
            index += 1
        res.fill_cache(index)
        return res._result_cache[value]

class UpdateQuery(Query):
    def __init__(self, model_class, update=None):
        self._update = update
        super(UpdateQuery, self).__init__(model_class)

    def _clone_attributes(self, query):
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
        defaults = mm.get_default_dict()
        query = dict((mm.fields[f], v) for f, v in defaults.items())
        query.update(insert)
        self._insert = query
        super(InsertQuery, self).__init__(model_class)

    def _clone_attributes(self, query):
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
    field_overrides = {}
    for_update = False
    interpolation = '?'
    limit_max = None
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
                raise Exception('Error, database not properly initialized '
                                'before opening connection')
            self.__local.conn = self._connect(
                self.database,
                **self.connect_kwargs)
            self.__local.closed = False

    def close(self):
        with self._conn_lock:
            if self.deferred:
                raise Exception('Error, database not properly initialized '
                                'before closing connection')
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

    def sql_error_handler(self, exception, sql, params, require_commit):
        raise exception

    def compiler(self):
        return self.compiler_class(
            self.quote_char, self.interpolation, self.field_overrides,
            self.op_overrides)

    def execute_sql(self, sql, params=None, require_commit=True):
        logger.debug((sql, params))
        cursor = self.get_cursor()
        try:
            res = cursor.execute(sql, params or ())
        except Exception as exc:
            logger.error('Error executing query %s (%s)' % (sql, params))
            return self.sql_error_handler(exc, sql, params, require_commit)
        if require_commit and self.get_autocommit():
            self.commit()
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

    def create_table(self, model_class, safe=False):
        qc = self.compiler()
        return self.execute_sql(qc.create_table(model_class, safe))

    def create_index(self, model_class, fields, unique=False):
        qc = self.compiler()
        if not isinstance(fields, (list, tuple)):
            raise ValueError('Fields passed to "create_index" must be a list '
                             'or tuple: "%s"' % fields)
        fobjs = [
            model_class._meta.fields[f] if isinstance(f, basestring) else f
            for f in fields]
        return self.execute_sql(qc.create_index(model_class, fobjs, unique))

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

    def extract_date(self, date_part, date_field):
        return fn.EXTRACT(Clause(date_part, R('FROM'), date_field))

class SqliteDatabase(Database):
    limit_max = -1
    op_overrides = {
        OP_LIKE: 'GLOB',
        OP_ILIKE: 'LIKE',
    }
    if sqlite3:
        ConnectionError = sqlite3.OperationalError

    def _connect(self, database, **kwargs):
        if not sqlite3:
            raise ImproperlyConfigured('sqlite3 must be installed on the system')
        conn = sqlite3.connect(database, **kwargs)
        conn.create_function('date_part', 2, _sqlite_date_part)
        return conn

    def get_indexes_for_table(self, table):
        res = self.execute_sql('PRAGMA index_list(%s);' % self.quote(table))
        rows = sorted([(r[1], r[2] == 1) for r in res.fetchall()])
        return rows

    def get_tables(self):
        res = self.execute_sql('select name from sqlite_master where '
                               'type="table" order by name;')
        return [r[0] for r in res.fetchall()]

    def extract_date(self, date_part, date_field):
        return fn.date_part(date_part, date_field)

class PostgresqlDatabase(Database):
    commit_select = True
    field_overrides = {
        'blob': 'BYTEA',
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

    register_unicode = True

    def _connect(self, database, **kwargs):
        if not psycopg2:
            raise ImproperlyConfigured('psycopg2 must be installed.')
        conn = psycopg2.connect(database=database, **kwargs)
        if self.register_unicode:
            pg_extensions.register_type(pg_extensions.UNICODE, conn)
            pg_extensions.register_type(pg_extensions.UNICODEARRAY, conn)
        return conn

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
            FROM
                pg_catalog.pg_class c,
                pg_catalog.pg_class c2,
                pg_catalog.pg_index i
            WHERE
                c.relname = %s AND c.oid = i.indrelid AND i.indexrelid = c2.oid
            ORDER BY i.indisprimary DESC, i.indisunique DESC, c2.relname""",
            (table,))
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
        'bool': 'BOOL',
        'decimal': 'NUMERIC',
        'double': 'DOUBLE PRECISION',
        'float': 'FLOAT',
        'primary_key': 'INTEGER AUTO_INCREMENT',
        'text': 'LONGTEXT',
    }
    for_update = True
    interpolation = '%s'
    limit_max = 2 ** 64 - 1  # MySQL quirk
    op_overrides = {
        OP_LIKE: 'LIKE BINARY',
        OP_ILIKE: 'LIKE',
        OP_XOR: 'XOR',
    }
    quote_char = '`'
    subquery_delete_same_table = False

    def _connect(self, database, **kwargs):
        if not mysql:
            raise ImproperlyConfigured('MySQLdb must be installed.')
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

        quote = compiler.quote
        query = framing % {
            'table': quote(db_table),
            'constraint': quote(constraint),
            'field': quote(field.db_column),
            'to': quote(field.rel_model._meta.db_table),
            'to_field': quote(field.rel_model._meta.primary_key.db_column),
            'cascade': ' ON DELETE CASCADE' if field.cascade else ''}

        self.execute_sql(query)
        return super(MySQLDatabase, self).create_foreign_key(
            model_class, field)

    def get_indexes_for_table(self, table):
        res = self.execute_sql('SHOW INDEXES IN `%s`;' % table)
        rows = sorted([(r[2], r[1] == 0) for r in res.fetchall()])
        return rows

    def get_tables(self):
        res = self.execute_sql('SHOW TABLES;')
        return [r[0] for r in res.fetchall()]

    def extract_date(self, date_part, date_field):
        assert date_part.lower() in DT_LOOKUPS
        return fn.EXTRACT(Clause(R(date_part), R('FROM'), date_field))


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
        return [
            FieldProxy(self, f) for f in self.model_class._meta.get_fields()]


class DoesNotExist(Exception): pass

default_database = SqliteDatabase('peewee.db')

class ModelOptions(object):
    def __init__(self, cls, database=None, db_table=None, indexes=None,
                 order_by=None, primary_key=None, table_alias=None, **kwargs):
        self.model_class = cls
        self.name = cls.__name__.lower()
        self.fields = {}
        self.columns = {}
        self.defaults = {}

        self.database = database or default_database
        self.db_table = db_table
        self.indexes = list(indexes or [])
        self.order_by = order_by
        self.primary_key = primary_key
        self.table_alias = table_alias

        self.auto_increment = None
        self.rel = {}
        self.reverse_rel = {}

        for key, value in kwargs.items():
            setattr(self, key, value)
        self._additional_keys = set(kwargs.keys())

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
        key = lambda i: (i[1] is self.primary_key and 1 or 2, i[1]._order)
        return sorted(self.fields.items(), key=key)

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
    inheritable = set(['database', 'indexes', 'order_by', 'primary_key'])

    def __new__(cls, name, bases, attrs):
        if not bases:
            return super(BaseModel, cls).__new__(cls, name, bases, attrs)

        meta_options = {}
        meta = attrs.pop('Meta', None)
        if meta:
            for k, v in meta.__dict__.items():
                if not k.startswith('_'):
                    meta_options[k] = v

        model_pk = getattr(meta, 'primary_key', None)
        parent_pk = None

        # inherit any field descriptors by deep copying the underlying field
        # into the attrs of the new model, additionally see if the bases define
        # inheritable model options and swipe them
        for b in bases:
            if not hasattr(b, '_meta'):
                continue

            base_meta = getattr(b, '_meta')
            if parent_pk is None:
                parent_pk = deepcopy(base_meta.primary_key)
            all_inheritable = cls.inheritable | base_meta._additional_keys
            for (k, v) in base_meta.__dict__.items():
                if k in all_inheritable and k not in meta_options:
                    meta_options[k] = v

            for (k, v) in b.__dict__.items():
                if isinstance(v, FieldDescriptor) and k not in attrs:
                    if not v.field.primary_key:
                        attrs[k] = deepcopy(v.field)

        # initialize the new class and set the magic attributes
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        cls._meta = ModelOptions(cls, **meta_options)
        cls._data = None
        cls._meta.indexes = list(cls._meta.indexes)

        # replace fields with field descriptors, calling the add_to_class hook
        for name, attr in list(cls.__dict__.items()):
            if isinstance(attr, Field):
                attr.add_to_class(cls, name)
                if attr.primary_key and model_pk:
                    raise ValueError('primary key is overdetermined.')
                elif attr.primary_key:
                    model_pk = attr

        if model_pk is None:
            if parent_pk:
                model_pk, name = parent_pk, parent_pk.name
            else:
                model_pk, name = PrimaryKeyField(primary_key=True), 'id'
            model_pk.add_to_class(cls, name)
        elif isinstance(model_pk, CompositeKey):
            model_pk.add_to_class(cls, '_composite_key')

        cls._meta.primary_key = model_pk
        cls._meta.auto_increment = (
            isinstance(model_pk, PrimaryKeyField) or
            bool(model_pk.sequence))
        if not cls._meta.db_table:
            cls._meta.db_table = re.sub('[^\w]+', '_', cls.__name__.lower())

        # create a repr and error class before finalizing
        if hasattr(cls, '__unicode__'):
            setattr(cls, '__repr__', lambda self: '<%s: %r>' % (
                cls.__name__, self.__unicode__()))

        exc_name = '%sDoesNotExist' % cls.__name__
        exception_class = type(exc_name, (DoesNotExist,), {})
        cls.DoesNotExist = exception_class
        cls._meta.prepared()

        return cls

class Model(with_metaclass(BaseModel)):
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
        if db.sequences and pk.sequence:
            if not db.sequence_exists(pk.sequence):
                db.create_sequence(pk.sequence)

        db.create_table(cls)
        cls._create_indexes()

    @classmethod
    def _create_indexes(cls):
        db = cls._meta.database
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

    def pk_expr(self):
        return self._meta.primary_key == self.get_id()

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
            self.update(**field_dict).where(self.pk_expr()).execute()
        else:
            pk = self.get_id()
            ret_pk = self.insert(**field_dict).execute()
            if ret_pk is not None:
                pk = ret_pk
            self.set_id(pk)

    def dependencies(self, search_nullable=False):
        query = self.select().where(self.pk_expr())
        stack = [(type(self), query)]
        seen = set()

        while stack:
            klass, query = stack.pop()
            if klass in seen:
                continue
            seen.add(klass)
            for rel_name, fk in klass._meta.reverse_rel.items():
                rel_model = fk.model_class
                node = fk << query
                if not fk.null or search_nullable:
                    stack.append((rel_model, rel_model.select().where(node)))
                yield (node, fk)

    def delete_instance(self, recursive=False, delete_nullable=False):
        if recursive:
            dependencies = self.dependencies(delete_nullable)
            for query, fk in reversed(list(dependencies)):
                model = fk.model_class
                if fk.null and not delete_nullable:
                    model.update(**{fk.name: None}).where(query).execute()
                else:
                    model.delete().where(query).execute()
        return self.delete().where(self.pk_expr()).execute()

    def __eq__(self, other):
        return (
            other.__class__ == self.__class__ and
            self.get_id() is not None and
            other.get_id() == self.get_id())

    def __ne__(self, other):
        return not self == other


def prefetch_add_subquery(sq, subqueries):
    fixed_queries = [(sq, None)]
    for i, subquery in enumerate(subqueries):
        if not isinstance(subquery, Query) and issubclass(subquery, Model):
            subquery = subquery.select()
        subquery_model = subquery.model_class
        fkf = None
        for j in reversed(range(i + 1)):
            last_query = fixed_queries[j][0]
            fkf = subquery_model._meta.rel_for_model(last_query.model_class)
            if fkf:
                break
        if not fkf:
            raise AttributeError('Error: unable to find foreign key for '
                                 'query: %s' % subquery)
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
