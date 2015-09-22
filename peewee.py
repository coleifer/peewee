# May you do good and not evil
# May you find forgiveness for yourself and forgive others
# May you share freely, never taking more than you give.  -- SQLite source code
#
# As we enjoy great advantages from the inventions of others, we should be glad
# of an opportunity to serve others by an invention of ours, and this we should
# do freely and generously.  -- Ben Franklin
#
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
import hashlib
import logging
import operator
import re
import sys
import threading
import uuid
from collections import deque
from collections import namedtuple
try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict
from copy import deepcopy
from functools import wraps
from inspect import isclass

__version__ = '2.6.4'
__all__ = [
    'BareField',
    'BigIntegerField',
    'BlobField',
    'BooleanField',
    'CharField',
    'Check',
    'Clause',
    'CompositeKey',
    'DatabaseError',
    'DataError',
    'DateField',
    'DateTimeField',
    'DecimalField',
    'DoesNotExist',
    'DoubleField',
    'DQ',
    'Field',
    'FixedCharField',
    'FloatField',
    'fn',
    'ForeignKeyField',
    'ImproperlyConfigured',
    'IntegerField',
    'IntegrityError',
    'InterfaceError',
    'InternalError',
    'JOIN',
    'JOIN_FULL',
    'JOIN_INNER',
    'JOIN_LEFT_OUTER',
    'Model',
    'MySQLDatabase',
    'NotSupportedError',
    'OperationalError',
    'Param',
    'PostgresqlDatabase',
    'prefetch',
    'PrimaryKeyField',
    'ProgrammingError',
    'Proxy',
    'R',
    'SqliteDatabase',
    'SQL',
    'TextField',
    'TimeField',
    'Using',
    'UUIDField',
    'Window',
]

# Set default logging handler to avoid "No handlers could be found for logger
# "peewee"" warnings.
try:  # Python 2.7+
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

# All peewee-generated logs are logged to this namespace.
logger = logging.getLogger('peewee')
logger.addHandler(NullHandler())

# Python 2/3 compatibility helpers. These helpers are used internally and are
# not exported.
def with_metaclass(meta, base=object):
    return meta("NewBase", (base,), {})

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3
PY26 = sys.version_info[:2] == (2, 6)
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
    def reraise(tp, value, tb=None):
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value
elif PY2:
    unicode_type = unicode
    string_type = basestring
    binary_construct = buffer
    def print_(s):
        sys.stdout.write(s)
        sys.stdout.write('\n')
    exec('def reraise(tp, value, tb=None): raise tp, value, tb')
else:
    raise RuntimeError('Unsupported python version.')

# By default, peewee supports Sqlite, MySQL and Postgresql.
try:
    import sqlite3
except ImportError:
    try:
        from pysqlite2 import dbapi2 as sqlite3
    except ImportError:
        sqlite3 = None
try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass
try:
    import psycopg2
    from psycopg2 import extensions as pg_extensions
except ImportError:
    psycopg2 = None
try:
    import MySQLdb as mysql  # prefer the C module.
except ImportError:
    try:
        import pymysql as mysql
    except ImportError:
        mysql = None

try:
    from playhouse.speedups import strip_parens
except ImportError:
    def strip_parens(s):
        # Quick sanity check.
        if not s or s[0] != '(':
            return s

        ct = i = 0
        l = len(s)
        while i < l:
            if s[i] == '(' and s[l - 1] == ')':
                ct += 1
                i += 1
                l -= 1
            else:
                break
        if ct:
            # If we ever end up with negatively-balanced parentheses, then we
            # know that one of the outer parentheses was required.
            unbalanced_ct = 0
            required = 0
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

if sqlite3:
    sqlite3.register_adapter(decimal.Decimal, str)
    sqlite3.register_adapter(datetime.date, str)
    sqlite3.register_adapter(datetime.time, str)

DATETIME_PARTS = ['year', 'month', 'day', 'hour', 'minute', 'second']
DATETIME_LOOKUPS = set(DATETIME_PARTS)

# Sqlite does not support the `date_part` SQL function, so we will define an
# implementation in python.
SQLITE_DATETIME_FORMATS = (
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f',
    '%Y-%m-%d',
    '%H:%M:%S',
    '%H:%M:%S.%f',
    '%H:%M')

def _sqlite_date_part(lookup_type, datetime_string):
    assert lookup_type in DATETIME_LOOKUPS
    if not datetime_string:
        return
    dt = format_date_time(datetime_string, SQLITE_DATETIME_FORMATS)
    return getattr(dt, lookup_type)

SQLITE_DATE_TRUNC_MAPPING = {
    'year': '%Y',
    'month': '%Y-%m',
    'day': '%Y-%m-%d',
    'hour': '%Y-%m-%d %H',
    'minute': '%Y-%m-%d %H:%M',
    'second': '%Y-%m-%d %H:%M:%S'}
MYSQL_DATE_TRUNC_MAPPING = SQLITE_DATE_TRUNC_MAPPING.copy()
MYSQL_DATE_TRUNC_MAPPING['minute'] = '%Y-%m-%d %H:%i'
MYSQL_DATE_TRUNC_MAPPING['second'] = '%Y-%m-%d %H:%i:%S'

def _sqlite_date_trunc(lookup_type, datetime_string):
    assert lookup_type in SQLITE_DATE_TRUNC_MAPPING
    if not datetime_string:
        return
    dt = format_date_time(datetime_string, SQLITE_DATETIME_FORMATS)
    return dt.strftime(SQLITE_DATE_TRUNC_MAPPING[lookup_type])

def _sqlite_regexp(regex, value):
    return re.search(regex, value, re.I) is not None

class attrdict(dict):
    def __getattr__(self, attr):
        return self[attr]

# Operators used in binary expressions.
OP = attrdict(
    AND='and',
    OR='or',
    ADD='+',
    SUB='-',
    MUL='*',
    DIV='/',
    BIN_AND='&',
    BIN_OR='|',
    XOR='^',
    MOD='%',
    EQ='=',
    LT='<',
    LTE='<=',
    GT='>',
    GTE='>=',
    NE='!=',
    IN='in',
    NOT_IN='not in',
    IS='is',
    IS_NOT='is not',
    LIKE='like',
    ILIKE='ilike',
    BETWEEN='between',
    REGEXP='regexp',
    CONCAT='||',
)

JOIN = attrdict(
    INNER='INNER',
    LEFT_OUTER='LEFT OUTER',
    RIGHT_OUTER='RIGHT OUTER',
    FULL='FULL',
)
JOIN_INNER = JOIN.INNER
JOIN_LEFT_OUTER = JOIN.LEFT_OUTER
JOIN_FULL = JOIN.FULL

# To support "django-style" double-underscore filters, create a mapping between
# operation name and operation code, e.g. "__eq" == OP.EQ.
DJANGO_MAP = {
    'eq': OP.EQ,
    'lt': OP.LT,
    'lte': OP.LTE,
    'gt': OP.GT,
    'gte': OP.GTE,
    'ne': OP.NE,
    'in': OP.IN,
    'is': OP.IS,
    'like': OP.LIKE,
    'ilike': OP.ILIKE,
    'regexp': OP.REGEXP,
}

# Helper functions that are used in various parts of the codebase.
def merge_dict(source, overrides):
    merged = source.copy()
    merged.update(overrides)
    return merged

def returns_clone(func):
    """
    Method decorator that will "clone" the object before applying the given
    method.  This ensures that state is mutated in a more predictable fashion,
    and promotes the use of method-chaining.
    """
    def inner(self, *args, **kwargs):
        clone = self.clone()  # Assumes object implements `clone`.
        func(clone, *args, **kwargs)
        return clone
    inner.call_local = func  # Provide a way to call without cloning.
    return inner

def not_allowed(func):
    """
    Method decorator to indicate a method is not allowed to be called.  Will
    raise a `NotImplementedError`.
    """
    def inner(self, *args, **kwargs):
        raise NotImplementedError('%s is not allowed on %s instances' % (
            func, type(self).__name__))
    return inner

class Proxy(object):
    """
    Proxy class useful for situations when you wish to defer the initialization
    of an object.
    """
    __slots__ = ['obj', '_callbacks']

    def __init__(self):
        self._callbacks = []
        self.initialize(None)

    def initialize(self, obj):
        self.obj = obj
        for callback in self._callbacks:
            callback(obj)

    def attach_callback(self, callback):
        self._callbacks.append(callback)
        return callback

    def __getattr__(self, attr):
        if self.obj is None:
            raise AttributeError('Cannot use uninitialized Proxy.')
        return getattr(self.obj, attr)

    def __setattr__(self, attr, value):
        if attr not in self.__slots__:
            raise AttributeError('Cannot set attribute on proxy.')
        return super(Proxy, self).__setattr__(attr, value)

class _CDescriptor(object):
    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return Entity(instance._alias)
        return self

# Classes representing the query tree.

class Node(object):
    """Base-class for any part of a query which shall be composable."""
    c = _CDescriptor()
    _node_type = 'node'

    def __init__(self):
        self._negated = False
        self._alias = None
        self._bind_to = None
        self._ordering = None  # ASC or DESC.

    @classmethod
    def extend(cls, name=None, clone=False):
        def decorator(method):
            method_name = name or method.__name__
            if clone:
                method = returns_clone(method)
            setattr(cls, method_name, method)
            return method
        return decorator

    def clone_base(self):
        return type(self)()

    def clone(self):
        inst = self.clone_base()
        inst._negated = self._negated
        inst._alias = self._alias
        inst._ordering = self._ordering
        inst._bind_to = self._bind_to
        return inst

    @returns_clone
    def __invert__(self):
        self._negated = not self._negated

    @returns_clone
    def alias(self, a=None):
        self._alias = a

    @returns_clone
    def bind_to(self, bt):
        """
        Bind the results of an expression to a specific model type. Useful
        when adding expressions to a select, where the result of the expression
        should be placed on a joined instance.
        """
        self._bind_to = bt

    @returns_clone
    def asc(self):
        self._ordering = 'ASC'

    @returns_clone
    def desc(self):
        self._ordering = 'DESC'

    def __pos__(self):
        return self.asc()

    def __neg__(self):
        return self.desc()

    def _e(op, inv=False):
        """
        Lightweight factory which returns a method that builds an Expression
        consisting of the left-hand and right-hand operands, using `op`.
        """
        def inner(self, rhs):
            if inv:
                return Expression(rhs, op, self)
            return Expression(self, op, rhs)
        return inner
    __and__ = _e(OP.AND)
    __or__ = _e(OP.OR)

    __add__ = _e(OP.ADD)
    __sub__ = _e(OP.SUB)
    __mul__ = _e(OP.MUL)
    __div__ = __truediv__ = _e(OP.DIV)
    __xor__ = _e(OP.XOR)
    __radd__ = _e(OP.ADD, inv=True)
    __rsub__ = _e(OP.SUB, inv=True)
    __rmul__ = _e(OP.MUL, inv=True)
    __rdiv__ = __rtruediv__ = _e(OP.DIV, inv=True)
    __rand__ = _e(OP.AND, inv=True)
    __ror__ = _e(OP.OR, inv=True)
    __rxor__ = _e(OP.XOR, inv=True)

    def __eq__(self, rhs):
        if rhs is None:
            return Expression(self, OP.IS, None)
        return Expression(self, OP.EQ, rhs)
    def __ne__(self, rhs):
        if rhs is None:
            return Expression(self, OP.IS_NOT, None)
        return Expression(self, OP.NE, rhs)

    __lt__ = _e(OP.LT)
    __le__ = _e(OP.LTE)
    __gt__ = _e(OP.GT)
    __ge__ = _e(OP.GTE)
    __lshift__ = _e(OP.IN)
    __rshift__ = _e(OP.IS)
    __mod__ = _e(OP.LIKE)
    __pow__ = _e(OP.ILIKE)

    bin_and = _e(OP.BIN_AND)
    bin_or = _e(OP.BIN_OR)

    # Special expressions.
    def in_(self, rhs):
        return Expression(self, OP.IN, rhs)
    def not_in(self, rhs):
        return Expression(self, OP.NOT_IN, rhs)
    def is_null(self, is_null=True):
        if is_null:
            return Expression(self, OP.IS, None)
        return Expression(self, OP.IS_NOT, None)
    def contains(self, rhs):
        return Expression(self, OP.ILIKE, '%%%s%%' % rhs)
    def startswith(self, rhs):
        return Expression(self, OP.ILIKE, '%s%%' % rhs)
    def endswith(self, rhs):
        return Expression(self, OP.ILIKE, '%%%s' % rhs)
    def between(self, low, high):
        return Expression(self, OP.BETWEEN, Clause(low, R('AND'), high))
    def regexp(self, expression):
        return Expression(self, OP.REGEXP, expression)
    def concat(self, rhs):
        return Expression(self, OP.CONCAT, rhs)

class SQL(Node):
    """An unescaped SQL string, with optional parameters."""
    _node_type = 'sql'

    def __init__(self, value, *params):
        self.value = value
        self.params = params
        super(SQL, self).__init__()

    def clone_base(self):
        return SQL(self.value, *self.params)
R = SQL  # backwards-compat.

class Entity(Node):
    """A quoted-name or entity, e.g. "table"."column"."""
    _node_type = 'entity'

    def __init__(self, *path):
        super(Entity, self).__init__()
        self.path = path

    def clone_base(self):
        return Entity(*self.path)

    def __getattr__(self, attr):
        return Entity(*filter(None, self.path + (attr,)))

class Func(Node):
    """An arbitrary SQL function call."""
    _node_type = 'func'

    def __init__(self, name, *arguments):
        self.name = name
        self.arguments = arguments
        self._coerce = True
        super(Func, self).__init__()

    @returns_clone
    def coerce(self, coerce=True):
        self._coerce = coerce

    def clone_base(self):
        res = Func(self.name, *self.arguments)
        res._coerce = self._coerce
        return res

    def over(self, partition_by=None, order_by=None, window=None):
        if isinstance(partition_by, Window) and window is None:
            window = partition_by
        if window is None:
            sql = Window(
                partition_by=partition_by, order_by=order_by).__sql__()
        else:
            sql = SQL(window._alias)
        return Clause(self, SQL('OVER'), sql)

    def __getattr__(self, attr):
        def dec(*args, **kwargs):
            return Func(attr, *args, **kwargs)
        return dec

# fn is a factory for creating `Func` objects and supports a more friendly
# API.  So instead of `Func("LOWER", param)`, `fn.LOWER(param)`.
fn = Func(None)

class Expression(Node):
    """A binary expression, e.g `foo + 1` or `bar < 7`."""
    _node_type = 'expression'

    def __init__(self, lhs, op, rhs, flat=False):
        super(Expression, self).__init__()
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        self.flat = flat

    def clone_base(self):
        return Expression(self.lhs, self.op, self.rhs, self.flat)

class Param(Node):
    """
    Arbitrary parameter passed into a query. Instructs the query compiler to
    specifically treat this value as a parameter, useful for `list` which is
    special-cased for `IN` lookups.
    """
    _node_type = 'param'

    def __init__(self, value, conv=None):
        self.value = value
        self.conv = conv
        super(Param, self).__init__()

    def clone_base(self):
        return Param(self.value, self.conv)

class Passthrough(Param):
    _node_type = 'passthrough'

class Clause(Node):
    """A SQL clause, one or more Node objects joined by spaces."""
    _node_type = 'clause'

    glue = ' '
    parens = False

    def __init__(self, *nodes, **kwargs):
        if 'glue' in kwargs:
            self.glue = kwargs['glue']
        if 'parens' in kwargs:
            self.parens = kwargs['parens']
        super(Clause, self).__init__()
        self.nodes = list(nodes)

    def clone_base(self):
        clone = Clause(*self.nodes)
        clone.glue = self.glue
        clone.parens = self.parens
        return clone

class CommaClause(Clause):
    """One or more Node objects joined by commas, no parens."""
    glue = ', '

class EnclosedClause(CommaClause):
    """One or more Node objects joined by commas and enclosed in parens."""
    parens = True

class Window(Node):
    def __init__(self, partition_by=None, order_by=None):
        super(Window, self).__init__()
        self.partition_by = partition_by
        self.order_by = order_by
        self._alias = self._alias or 'w'

    def __sql__(self):
        over_clauses = []
        if self.partition_by:
            over_clauses.append(Clause(
                SQL('PARTITION BY'),
                CommaClause(*self.partition_by)))
        if self.order_by:
            over_clauses.append(Clause(
                SQL('ORDER BY'),
                CommaClause(*self.order_by)))
        return EnclosedClause(Clause(*over_clauses))

    def clone_base(self):
        return Window(self.partition_by, self.order_by)

class Check(SQL):
    """Check constraint, usage: `Check('price > 10')`."""
    def __init__(self, value):
        super(Check, self).__init__('CHECK (%s)' % value)

class DQ(Node):
    """A "django-style" filter expression, e.g. {'foo__eq': 'x'}."""
    def __init__(self, **query):
        super(DQ, self).__init__()
        self.query = query

    def clone_base(self):
        return DQ(**self.query)

class _StripParens(Node):
    _node_type = 'strip_parens'

    def __init__(self, node):
        super(_StripParens, self).__init__()
        self.node = node

JoinMetadata = namedtuple('JoinMetadata', (
    'src_model',  # Source Model class.
    'dest_model',   # Dest Model class.
    'src',   # Source, may be Model, ModelAlias
    'dest',  # Dest, may be Model, ModelAlias, or SelectQuery.
    'attr',  # Attribute name joined instance(s) should be assigned to.
    'primary_key',  # Primary key being joined on.
    'foreign_key',  # Foreign key being joined from.
    'is_backref',  # Is this a backref, i.e. 1 -> N.
    'alias',  # Explicit alias given to join expression.
    'is_self_join',  # Is this a self-join?
    'is_expression',  # Is the join ON clause an Expression?
))

class Join(namedtuple('_Join', ('src', 'dest', 'join_type', 'on'))):
    def get_foreign_key(self, source, dest, field=None):
        if isinstance(source, SelectQuery) or isinstance(dest, SelectQuery):
            return None, None
        fk_field = source._meta.rel_for_model(dest, field)
        if fk_field is not None:
            return fk_field, False
        reverse_rel = source._meta.reverse_rel_for_model(dest, field)
        if reverse_rel is not None:
            return reverse_rel, True
        return None, None

    def get_join_type(self):
        return self.join_type or JOIN.INNER

    def model_from_alias(self, model_or_alias):
        if isinstance(model_or_alias, ModelAlias):
            return model_or_alias.model_class
        elif isinstance(model_or_alias, SelectQuery):
            return model_or_alias.model_class
        return model_or_alias

    def _join_metadata(self):
        # Get the actual tables being joined.
        src = self.model_from_alias(self.src)
        dest = self.model_from_alias(self.dest)

        join_alias = isinstance(self.on, Node) and self.on._alias or None
        is_expression = isinstance(self.on, (Expression, Func, SQL))

        on_field = isinstance(self.on, (Field, FieldProxy)) and self.on or None
        if on_field:
            fk_field = on_field
            is_backref = on_field.name not in src._meta.fields
        else:
            fk_field, is_backref = self.get_foreign_key(src, dest, self.on)
            if fk_field is None and self.on is not None:
                fk_field, is_backref = self.get_foreign_key(src, dest)

        if fk_field is not None:
            primary_key = fk_field.to_field
        else:
            primary_key = None

        if not join_alias:
            if fk_field is not None:
                if is_backref:
                    target_attr = dest._meta.db_table
                else:
                    target_attr = fk_field.name
            else:
                try:
                    target_attr = self.on.lhs.name
                except AttributeError:
                    target_attr = dest._meta.db_table
        else:
            target_attr = None

        return JoinMetadata(
            src_model=src,
            dest_model=dest,
            src=self.src,
            dest=self.dest,
            attr=join_alias or target_attr,
            primary_key=primary_key,
            foreign_key=fk_field,
            is_backref=is_backref,
            alias=join_alias,
            is_self_join=src is dest,
            is_expression=is_expression)

    @property
    def metadata(self):
        if not hasattr(self, '_cached_metadata'):
            self._cached_metadata = self._join_metadata()
        return self._cached_metadata

class FieldDescriptor(object):
    # Fields are exposed as descriptors in order to control access to the
    # underlying "raw" data.
    def __init__(self, field):
        self.field = field
        self.att_name = self.field.name

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return instance._data.get(self.att_name)
        return self.field

    def __set__(self, instance, value):
        instance._data[self.att_name] = value
        instance._dirty.add(self.att_name)

class Field(Node):
    """A column on a table."""
    _field_counter = 0
    _order = 0
    _node_type = 'field'
    db_field = 'unknown'

    def __init__(self, null=False, index=False, unique=False,
                 verbose_name=None, help_text=None, db_column=None,
                 default=None, choices=None, primary_key=False, sequence=None,
                 constraints=None, schema=None):
        self.null = null
        self.index = index
        self.unique = unique
        self.verbose_name = verbose_name
        self.help_text = help_text
        self.db_column = db_column
        self.default = default
        self.choices = choices  # Used for metadata purposes, not enforced.
        self.primary_key = primary_key
        self.sequence = sequence  # Name of sequence, e.g. foo_id_seq.
        self.constraints = constraints  # List of column constraints.
        self.schema = schema  # Name of schema, e.g. 'public'.

        # Used internally for recovering the order in which Fields were defined
        # on the Model class.
        Field._field_counter += 1
        self._order = Field._field_counter
        self._sort_key = (self.primary_key and 1 or 2), self._order

        self._is_bound = False  # Whether the Field is "bound" to a Model.
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
            constraints=self.constraints,
            schema=self.schema,
            **kwargs)
        if self._is_bound:
            inst.name = self.name
            inst.model_class = self.model_class
        inst._is_bound = self._is_bound
        return inst

    def add_to_class(self, model_class, name):
        """
        Hook that replaces the `Field` attribute on a class with a named
        `FieldDescriptor`. Called by the metaclass during construction of the
        `Model`.
        """
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

    def get_column_type(self):
        field_type = self.get_db_field()
        return self.get_database().compiler().get_column_type(field_type)

    def get_db_field(self):
        return self.db_field

    def get_modifiers(self):
        return None

    def coerce(self, value):
        return value

    def db_value(self, value):
        """Convert the python value for storage in the database."""
        return value if value is None else self.coerce(value)

    def python_value(self, value):
        """Convert the database value to a pythonic value."""
        return value if value is None else self.coerce(value)

    def as_entity(self, with_table=False):
        if with_table:
            return Entity(self.model_class._meta.db_table, self.db_column)
        return Entity(self.db_column)

    def __ddl_column__(self, column_type):
        """Return the column type, e.g. VARCHAR(255) or REAL."""
        modifiers = self.get_modifiers()
        if modifiers:
            return SQL(
                '%s(%s)' % (column_type, ', '.join(map(str, modifiers))))
        return SQL(column_type)

    def __ddl__(self, column_type):
        """Return a list of Node instances that defines the column."""
        ddl = [self.as_entity(), self.__ddl_column__(column_type)]
        if not self.null:
            ddl.append(SQL('NOT NULL'))
        if self.primary_key:
            ddl.append(SQL('PRIMARY KEY'))
        if self.sequence:
            ddl.append(SQL("DEFAULT NEXTVAL('%s')" % self.sequence))
        if self.constraints:
            ddl.extend(self.constraints)
        return ddl

    def __hash__(self):
        return hash(self.name + '.' + self.model_class.__name__)

class BareField(Field):
    db_field = 'bare'

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

    def __init__(self, max_digits=10, decimal_places=5, auto_round=False,
                 rounding=None, *args, **kwargs):
        self.max_digits = max_digits
        self.decimal_places = decimal_places
        self.auto_round = auto_round
        self.rounding = rounding or decimal.DefaultContext.rounding
        super(DecimalField, self).__init__(*args, **kwargs)

    def clone_base(self, **kwargs):
        return super(DecimalField, self).clone_base(
            max_digits=self.max_digits,
            decimal_places=self.decimal_places,
            auto_round=self.auto_round,
            rounding=self.rounding,
            **kwargs)

    def get_modifiers(self):
        return [self.max_digits, self.decimal_places]

    def db_value(self, value):
        D = decimal.Decimal
        if not value:
            return value if value is None else D(0)
        if self.auto_round:
            exp = D(10) ** (-self.decimal_places)
            rounding = self.rounding
            return D(str(value)).quantize(exp, rounding=rounding)
        return value

    def python_value(self, value):
        if value is not None:
            if isinstance(value, decimal.Decimal):
                return value
            return decimal.Decimal(str(value))

def coerce_to_unicode(s, encoding='utf-8'):
    if isinstance(s, unicode_type):
        return s
    elif isinstance(s, string_type):
        return s.decode(encoding)
    return unicode_type(s)

class CharField(Field):
    db_field = 'string'

    def __init__(self, max_length=255, *args, **kwargs):
        self.max_length = max_length
        super(CharField, self).__init__(*args, **kwargs)

    def clone_base(self, **kwargs):
        return super(CharField, self).clone_base(
            max_length=self.max_length,
            **kwargs)

    def get_modifiers(self):
        return self.max_length and [self.max_length] or None

    def coerce(self, value):
        return coerce_to_unicode(value or '')

class FixedCharField(CharField):
    db_field = 'fixed_char'

    def python_value(self, value):
        value = super(FixedCharField, self).python_value(value)
        if value:
            value = value.strip()
        return value

class TextField(Field):
    db_field = 'text'

    def coerce(self, value):
        return coerce_to_unicode(value or '')

class BlobField(Field):
    db_field = 'blob'

    def db_value(self, value):
        if isinstance(value, basestring):
            return binary_construct(value)
        return value

class UUIDField(Field):
    db_field = 'uuid'

    def db_value(self, value):
        return None if value is None else str(value)

    def python_value(self, value):
        return None if value is None else uuid.UUID(value)

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

class _BaseFormattedField(Field):
    formats = None
    def __init__(self, formats=None, *args, **kwargs):
        if formats is not None:
            self.formats = formats
        super(_BaseFormattedField, self).__init__(*args, **kwargs)

    def clone_base(self, **kwargs):
        return super(_BaseFormattedField, self).clone_base(
            formats=self.formats,
            **kwargs)

class DateTimeField(_BaseFormattedField):
    db_field = 'datetime'
    formats = [
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]

    def python_value(self, value):
        if value and isinstance(value, basestring):
            return format_date_time(value, self.formats)
        return value

    year = property(_date_part('year'))
    month = property(_date_part('month'))
    day = property(_date_part('day'))
    hour = property(_date_part('hour'))
    minute = property(_date_part('minute'))
    second = property(_date_part('second'))

class DateField(_BaseFormattedField):
    db_field = 'date'
    formats = [
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
    ]

    def python_value(self, value):
        if value and isinstance(value, basestring):
            pp = lambda x: x.date()
            return format_date_time(value, self.formats, pp)
        elif value and isinstance(value, datetime.datetime):
            return value.date()
        return value

    year = property(_date_part('year'))
    month = property(_date_part('month'))
    day = property(_date_part('day'))

class TimeField(_BaseFormattedField):
    db_field = 'time'
    formats = [
        '%H:%M:%S.%f',
        '%H:%M:%S',
        '%H:%M',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
    ]

    def python_value(self, value):
        if value:
            if isinstance(value, basestring):
                pp = lambda x: x.time()
                return format_date_time(value, self.formats, pp)
            elif isinstance(value, datetime.datetime):
                return value.time()
        elif value is not None and isinstance(value, datetime.timedelta):
            return (datetime.datetime.min + value).time()
        return value

    hour = property(_date_part('hour'))
    minute = property(_date_part('minute'))
    second = property(_date_part('second'))

class BooleanField(Field):
    db_field = 'bool'
    coerce = bool

class RelationDescriptor(FieldDescriptor):
    """Foreign-key abstraction to replace a related PK with a related model."""
    def __init__(self, field, rel_model):
        self.rel_model = rel_model
        super(RelationDescriptor, self).__init__(field)

    def get_object_or_id(self, instance):
        rel_id = instance._data.get(self.att_name)
        if rel_id is not None or self.att_name in instance._obj_cache:
            if self.att_name not in instance._obj_cache:
                obj = self.rel_model.get(self.field.to_field == rel_id)
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
            instance._data[self.att_name] = getattr(
                value, self.field.to_field.name)
            instance._obj_cache[self.att_name] = value
        else:
            orig_value = instance._data.get(self.att_name)
            instance._data[self.att_name] = value
            if orig_value != value and self.att_name in instance._obj_cache:
                del instance._obj_cache[self.att_name]
        instance._dirty.add(self.att_name)

class ReverseRelationDescriptor(object):
    """Back-reference to expose related objects as a `SelectQuery`."""
    def __init__(self, field):
        self.field = field
        self.rel_model = field.model_class

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return self.rel_model.select().where(
                self.field == getattr(instance, self.field.to_field.name))
        return self

class ObjectIdDescriptor(object):
    """Gives direct access to the underlying id"""
    def __init__(self, field):
        self.attr_name = field.name

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return instance._data.get(self.attr_name)

class ForeignKeyField(IntegerField):
    def __init__(self, rel_model, related_name=None, on_delete=None,
                 on_update=None, extra=None, to_field=None, *args, **kwargs):
        if rel_model != 'self' and not isinstance(rel_model, Proxy) and not \
                issubclass(rel_model, Model):
            raise TypeError('Unexpected value for `rel_model`.  Expected '
                            '`Model`, `Proxy` or "self"')
        self.rel_model = rel_model
        self._related_name = related_name
        self.deferred = isinstance(rel_model, Proxy)
        self.on_delete = on_delete
        self.on_update = on_update
        self.extra = extra
        self.to_field = to_field
        super(ForeignKeyField, self).__init__(*args, **kwargs)

    def clone_base(self, **kwargs):
        return super(ForeignKeyField, self).clone_base(
            rel_model=self.rel_model,
            related_name=self.related_name,
            on_delete=self.on_delete,
            on_update=self.on_update,
            extra=self.extra,
            to_field=self.to_field,
            **kwargs)

    def _get_descriptor(self):
        return RelationDescriptor(self, self.rel_model)

    def _get_id_descriptor(self):
        return ObjectIdDescriptor(self)

    def _get_backref_descriptor(self):
        return ReverseRelationDescriptor(self)

    def _get_related_name(self):
        return self._related_name or ('%s_set' % self.model_class._meta.name)

    def add_to_class(self, model_class, name):
        if isinstance(self.rel_model, Proxy):
            def callback(rel_model):
                self.rel_model = rel_model
                self.add_to_class(model_class, name)
            self.rel_model.attach_callback(callback)
            return

        self.name = name
        self.model_class = model_class
        self.db_column = self.db_column or '%s_id' % self.name
        if not self.verbose_name:
            self.verbose_name = re.sub('_+', ' ', name).title()

        model_class._meta.fields[self.name] = self
        model_class._meta.columns[self.db_column] = self

        self.related_name = self._get_related_name()

        if self.rel_model == 'self':
            self.rel_model = self.model_class

        if self.to_field is not None:
            if not isinstance(self.to_field, Field):
                self.to_field = getattr(self.rel_model, self.to_field)
        else:
            self.to_field = self.rel_model._meta.primary_key

        if model_class._meta.validate_backrefs:
            if self.related_name in self.rel_model._meta.fields:
                error = ('Foreign key: %s.%s related name "%s" collision with '
                         'model field of the same name.')
                raise AttributeError(error % (
                    self.model_class._meta.name, self.name, self.related_name))
            if self.related_name in self.rel_model._meta.reverse_rel:
                error = ('Foreign key: %s.%s related name "%s" collision with '
                         'foreign key using same related_name.')
                raise AttributeError(error % (
                    self.model_class._meta.name, self.name, self.related_name))

        setattr(model_class, name, self._get_descriptor())
        setattr(model_class, name + '_id', self._get_id_descriptor())
        setattr(self.rel_model,
                self.related_name,
                self._get_backref_descriptor())
        self._is_bound = True

        model_class._meta.rel[self.name] = self
        self.rel_model._meta.reverse_rel[self.related_name] = self

    def get_db_field(self):
        """
        Overridden to ensure Foreign Keys use same column type as the primary
        key they point to.
        """
        if not isinstance(self.to_field, PrimaryKeyField):
            return self.to_field.get_db_field()
        return super(ForeignKeyField, self).get_db_field()

    def get_modifiers(self):
        if not isinstance(self.to_field, PrimaryKeyField):
            return self.to_field.get_modifiers()
        return super(ForeignKeyField, self).get_modifiers()

    def coerce(self, value):
        return self.to_field.coerce(value)

    def db_value(self, value):
        if isinstance(value, self.rel_model):
            value = value._get_pk_value()
        return self.to_field.db_value(value)


class CompositeKey(object):
    """A primary key composed of multiple columns."""
    sequence = None

    def __init__(self, *field_names):
        self.field_names = field_names

    def add_to_class(self, model_class, name):
        self.name = name
        self.model_class = model_class
        setattr(model_class, name, self)

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return tuple([getattr(instance, field_name)
                          for field_name in self.field_names])
        return self

    def __set__(self, instance, value):
        pass

    def __eq__(self, other):
        expressions = [(self.model_class._meta.fields[field] == value)
                       for field, value in zip(self.field_names, other)]
        return reduce(operator.and_, expressions)


class AliasMap(object):
    prefix = 't'

    def __init__(self, start=0):
        self._alias_map = {}
        self._counter = start

    def __repr__(self):
        return '<AliasMap: %s>' % self._alias_map

    def add(self, obj, alias=None):
        if obj in self._alias_map:
            return
        self._counter += 1
        self._alias_map[obj] = alias or '%s%s' % (self.prefix, self._counter)

    def __getitem__(self, obj):
        if obj not in self._alias_map:
            self.add(obj)
        return self._alias_map[obj]

    def __contains__(self, obj):
        return obj in self._alias_map

    def update(self, alias_map):
        if alias_map:
            for obj, alias in alias_map._alias_map.items():
                if obj not in self:
                    self._alias_map[obj] = alias
        return self


class QueryCompiler(object):
    # Mapping of `db_type` to actual column type used by database driver.
    # Database classes may provide additional column types or overrides.
    field_map = {
        'bare': '',
        'bigint': 'BIGINT',
        'blob': 'BLOB',
        'bool': 'SMALLINT',
        'date': 'DATE',
        'datetime': 'DATETIME',
        'decimal': 'DECIMAL',
        'double': 'REAL',
        'fixed_char': 'CHAR',
        'float': 'REAL',
        'int': 'INTEGER',
        'primary_key': 'INTEGER',
        'string': 'VARCHAR',
        'text': 'TEXT',
        'time': 'TIME',
    }

    # Mapping of OP. to actual SQL operation.  For most databases this will be
    # the same, but some column types or databases may support additional ops.
    # Like `field_map`, Database classes may extend or override these.
    op_map = {
        OP.EQ: '=',
        OP.LT: '<',
        OP.LTE: '<=',
        OP.GT: '>',
        OP.GTE: '>=',
        OP.NE: '!=',
        OP.IN: 'IN',
        OP.NOT_IN: 'NOT IN',
        OP.IS: 'IS',
        OP.IS_NOT: 'IS NOT',
        OP.BIN_AND: '&',
        OP.BIN_OR: '|',
        OP.LIKE: 'LIKE',
        OP.ILIKE: 'ILIKE',
        OP.BETWEEN: 'BETWEEN',
        OP.ADD: '+',
        OP.SUB: '-',
        OP.MUL: '*',
        OP.DIV: '/',
        OP.XOR: '#',
        OP.AND: 'AND',
        OP.OR: 'OR',
        OP.MOD: '%',
        OP.REGEXP: 'REGEXP',
        OP.CONCAT: '||',
    }

    join_map = {
        JOIN.INNER: 'INNER JOIN',
        JOIN.LEFT_OUTER: 'LEFT OUTER JOIN',
        JOIN.RIGHT_OUTER: 'RIGHT OUTER JOIN',
        JOIN.FULL: 'FULL JOIN',
    }
    alias_map_class = AliasMap

    def __init__(self, quote_char='"', interpolation='?', field_overrides=None,
                 op_overrides=None):
        self.quote_char = quote_char
        self.interpolation = interpolation
        self._field_map = merge_dict(self.field_map, field_overrides or {})
        self._op_map = merge_dict(self.op_map, op_overrides or {})
        self._parse_map = self.get_parse_map()
        self._unknown_types = set(['param'])

    def get_parse_map(self):
        # To avoid O(n) lookups when parsing nodes, use a lookup table for
        # common node types O(1).
        return {
            'expression': self._parse_expression,
            'param': self._parse_param,
            'passthrough': self._parse_param,
            'func': self._parse_func,
            'clause': self._parse_clause,
            'entity': self._parse_entity,
            'field': self._parse_field,
            'sql': self._parse_sql,
            'select_query': self._parse_select_query,
            'compound_select_query': self._parse_compound_select_query,
            'strip_parens': self._parse_strip_parens,
        }

    def quote(self, s):
        return '%s%s%s' % (self.quote_char, s, self.quote_char)

    def get_column_type(self, f):
        return self._field_map[f] if f in self._field_map else f.upper()

    def get_op(self, q):
        return self._op_map[q]

    def _sorted_fields(self, field_dict):
        return sorted(field_dict.items(), key=lambda i: i[0]._sort_key)

    def _parse_default(self, node, alias_map, conv):
        return self.interpolation, [node]

    def _parse_expression(self, node, alias_map, conv):
        if isinstance(node.lhs, Field):
            conv = node.lhs
        lhs, lparams = self.parse_node(node.lhs, alias_map, conv)
        rhs, rparams = self.parse_node(node.rhs, alias_map, conv)
        template = '%s %s %s' if node.flat else '(%s %s %s)'
        sql = template % (lhs, self.get_op(node.op), rhs)
        return sql, lparams + rparams

    def _parse_param(self, node, alias_map, conv):
        if node.conv:
            params = [node.conv(node.value)]
        else:
            params = [node.value]
        return self.interpolation, params

    def _parse_func(self, node, alias_map, conv):
        conv = node._coerce and conv or None
        sql, params = self.parse_node_list(node.arguments, alias_map, conv)
        return '%s(%s)' % (node.name, strip_parens(sql)), params

    def _parse_clause(self, node, alias_map, conv):
        sql, params = self.parse_node_list(
            node.nodes, alias_map, conv, node.glue)
        if node.parens:
            sql = '(%s)' % strip_parens(sql)
        return sql, params

    def _parse_entity(self, node, alias_map, conv):
        return '.'.join(map(self.quote, node.path)), []

    def _parse_sql(self, node, alias_map, conv):
        return node.value, list(node.params)

    def _parse_field(self, node, alias_map, conv):
        if alias_map:
            sql = '.'.join((
                self.quote(alias_map[node.model_class]),
                self.quote(node.db_column)))
        else:
            sql = self.quote(node.db_column)
        return sql, []

    def _parse_compound_select_query(self, node, alias_map, conv):
        csq = 'compound_select_query'
        if node.rhs._node_type == csq and node.lhs._node_type != csq:
            first_q, second_q = node.rhs, node.lhs
            inv = True
        else:
            first_q, second_q = node.lhs, node.rhs
            inv = False

        new_map = self.alias_map_class()
        if first_q._node_type == csq:
            new_map._counter = alias_map._counter

        first, first_p = self.generate_select(first_q, new_map)
        second, second_p = self.generate_select(
            second_q,
            self.calculate_alias_map(second_q, new_map))

        if inv:
            l, lp, r, rp = second, second_p, first, first_p
        else:
            l, lp, r, rp = first, first_p , second, second_p

        # We add outer parentheses in the event the compound query is used in
        # the `from_()` clause, in which case we'll need them.
        if node.database.compound_select_parentheses:
            sql = '((%s) %s (%s))' % (l, node.operator, r)
        else:
            sql = '(%s %s %s)' % (l, node.operator, r)
        return  sql, lp + rp

    def _parse_select_query(self, node, alias_map, conv):
        clone = node.clone()
        if not node._explicit_selection:
            if conv and isinstance(conv, ForeignKeyField):
                select_field = conv.to_field
            else:
                select_field = clone.model_class._meta.primary_key
            clone._select = (select_field,)
        sub, params = self.generate_select(clone, alias_map)
        return '(%s)' % strip_parens(sub), params

    def _parse_strip_parens(self, node, alias_map, conv):
        sql, params = self.parse_node(node.node, alias_map, conv)
        return strip_parens(sql), params

    def _parse(self, node, alias_map, conv):
        # By default treat the incoming node as a raw value that should be
        # parameterized.
        node_type = getattr(node, '_node_type', None)
        unknown = False
        if node_type in self._parse_map:
            sql, params = self._parse_map[node_type](node, alias_map, conv)
            unknown = node_type in self._unknown_types
        elif isinstance(node, (list, tuple)):
            # If you're wondering how to pass a list into your query, simply
            # wrap it in Param().
            sql, params = self.parse_node_list(node, alias_map, conv)
            sql = '(%s)' % sql
        elif isinstance(node, Model):
            sql = self.interpolation
            if conv and isinstance(conv, ForeignKeyField) and \
                    not isinstance(conv.to_field, ForeignKeyField):
                params = [
                    conv.to_field.db_value(getattr(node, conv.to_field.name))]
            else:
                params = [node._get_pk_value()]
        elif (isclass(node) and issubclass(node, Model)) or \
                isinstance(node, ModelAlias):
            entity = node.as_entity().alias(alias_map[node])
            sql, params = self.parse_node(entity, alias_map, conv)
        else:
            sql, params = self._parse_default(node, alias_map, conv)
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

    def calculate_alias_map(self, query, alias_map=None):
        new_map = self.alias_map_class()
        if alias_map is not None:
            new_map._counter = alias_map._counter

        new_map.add(query.model_class, query.model_class._meta.table_alias)
        for src_model, joined_models in query._joins.items():
            new_map.add(src_model, src_model._meta.table_alias)
            for join_obj in joined_models:
                if isinstance(join_obj.dest, Node):
                    new_map.add(join_obj.dest, join_obj.dest.alias)
                else:
                    new_map.add(join_obj.dest, join_obj.dest._meta.table_alias)

        return new_map.update(alias_map)

    def build_query(self, clauses, alias_map=None):
        return self.parse_node(Clause(*clauses), alias_map)

    def generate_joins(self, joins, model_class, alias_map):
        # Joins are implemented as an adjancency-list graph. Perform a
        # depth-first search of the graph to generate all the necessary JOINs.
        clauses = []
        seen = set()
        q = [model_class]
        while q:
            curr = q.pop()
            if curr not in joins or curr in seen:
                continue
            seen.add(curr)
            for join in joins[curr]:
                src = curr
                dest = join.dest
                if isinstance(join.on, (Expression, Func, Clause, Entity)):
                    # Clear any alias on the join expression.
                    constraint = join.on.clone().alias()
                else:
                    metadata = join.metadata
                    if metadata.is_backref:
                        fk_model = join.dest
                        pk_model = join.src
                    else:
                        fk_model = join.src
                        pk_model = join.dest

                    fk = metadata.foreign_key
                    if fk:
                        lhs = getattr(fk_model, fk.name)
                        rhs = getattr(pk_model, fk.to_field.name)
                        if metadata.is_backref:
                            lhs, rhs = rhs, lhs
                        constraint = (lhs == rhs)
                    else:
                        raise ValueError('Missing required join predicate.')

                if isinstance(dest, Node):
                    # TODO: ensure alias?
                    dest_n = dest
                else:
                    q.append(dest)
                    dest_n = dest.as_entity().alias(alias_map[dest])

                join_type = join.get_join_type()
                if join_type in self.join_map:
                    join_sql = SQL(self.join_map[join_type])
                else:
                    join_sql = SQL(join_type)
                clauses.append(
                    Clause(join_sql, dest_n, SQL('ON'), constraint))

        return clauses

    def generate_select(self, query, alias_map=None):
        model = query.model_class
        db = model._meta.database

        alias_map = self.calculate_alias_map(query, alias_map)

        if isinstance(query, CompoundSelect):
            clauses = [_StripParens(query)]
        else:
            if not query._distinct:
                clauses = [SQL('SELECT')]
            else:
                clauses = [SQL('SELECT DISTINCT')]
                if query._distinct not in (True, False):
                    clauses += [SQL('ON'), EnclosedClause(*query._distinct)]

            select_clause = Clause(*query._select)
            select_clause.glue = ', '

            clauses.extend((select_clause, SQL('FROM')))
            if query._from is None:
                clauses.append(model.as_entity().alias(alias_map[model]))
            else:
                clauses.append(CommaClause(*query._from))

        if query._windows is not None:
            clauses.append(SQL('WINDOW'))
            clauses.append(CommaClause(*[
                Clause(
                    SQL(window._alias),
                    SQL('AS'),
                    window.__sql__())
                for window in query._windows]))

        join_clauses = self.generate_joins(query._joins, model, alias_map)
        if join_clauses:
            clauses.extend(join_clauses)

        if query._where is not None:
            clauses.extend([SQL('WHERE'), query._where])

        if query._group_by:
            clauses.extend([SQL('GROUP BY'), CommaClause(*query._group_by)])

        if query._having:
            clauses.extend([SQL('HAVING'), query._having])

        if query._order_by:
            clauses.extend([SQL('ORDER BY'), CommaClause(*query._order_by)])

        if query._limit or (query._offset and db.limit_max):
            limit = query._limit or db.limit_max
            clauses.append(SQL('LIMIT %s' % limit))
        if query._offset:
            clauses.append(SQL('OFFSET %s' % query._offset))

        for_update, no_wait = query._for_update
        if for_update:
            stmt = 'FOR UPDATE NOWAIT' if no_wait else 'FOR UPDATE'
            clauses.append(SQL(stmt))

        return self.build_query(clauses, alias_map)

    def generate_update(self, query):
        model = query.model_class
        alias_map = self.alias_map_class()
        alias_map.add(model, model._meta.db_table)
        if query._on_conflict:
            statement = 'UPDATE OR %s' % query._on_conflict
        else:
            statement = 'UPDATE'
        clauses = [SQL(statement), model.as_entity(), SQL('SET')]

        update = []
        for field, value in self._sorted_fields(query._update):
            if not isinstance(value, (Node, Model)):
                value = Param(value, conv=field.db_value)
            update.append(Expression(
                field.as_entity(with_table=False),
                OP.EQ,
                value,
                flat=True))  # No outer parens, no table alias.
        clauses.append(CommaClause(*update))

        if query._where:
            clauses.extend([SQL('WHERE'), query._where])

        if query._returning is not None:
            returning_clause = Clause(*query._returning)
            returning_clause.glue = ', '
            clauses.extend([SQL('RETURNING'), returning_clause])

        return self.build_query(clauses, alias_map)

    def _get_field_clause(self, fields, clause_type=EnclosedClause):
        return clause_type(*[
            field.as_entity(with_table=False) for field in fields])

    def generate_insert(self, query):
        model = query.model_class
        meta = model._meta
        alias_map = self.alias_map_class()
        alias_map.add(model, model._meta.db_table)
        if query._upsert:
            statement = 'INSERT OR REPLACE INTO'
        elif query._on_conflict:
            statement = 'INSERT OR %s INTO' % query._on_conflict
        else:
            statement = 'INSERT INTO'
        clauses = [SQL(statement), model.as_entity()]

        if query._query is not None:
            # This INSERT query is of the form INSERT INTO ... SELECT FROM.
            if query._fields:
                clauses.append(self._get_field_clause(query._fields))
            clauses.append(_StripParens(query._query))

        elif query._rows is not None:
            fields, value_clauses = [], []
            have_fields = False

            for row_dict in query._iter_rows():
                if not have_fields:
                    fields = sorted(
                        row_dict.keys(), key=operator.attrgetter('_sort_key'))
                    have_fields = True

                values = []
                for field in fields:
                    value = row_dict[field]
                    if not isinstance(value, (Node, Model)):
                        value = Param(value, conv=field.db_value)
                    values.append(value)

                value_clauses.append(EnclosedClause(*values))

            if fields:
                clauses.extend([
                    self._get_field_clause(fields),
                    SQL('VALUES'),
                    CommaClause(*value_clauses)])
            elif query.model_class._meta.auto_increment:
                # Bare insert, use default value for primary key.
                clauses.append(query.database.default_insert_clause(
                    query.model_class))

        if query.is_insert_returning:
            clauses.extend([
                SQL('RETURNING'),
                self._get_field_clause(
                    meta.get_primary_key_fields(),
                    clause_type=CommaClause)])
        elif query._returning is not None:
            returning_clause = Clause(*query._returning)
            returning_clause.glue = ', '
            clauses.extend([SQL('RETURNING'), returning_clause])


        return self.build_query(clauses, alias_map)

    def generate_delete(self, query):
        model = query.model_class
        clauses = [SQL('DELETE FROM'), model.as_entity()]
        if query._where:
            clauses.extend([SQL('WHERE'), query._where])
        if query._returning is not None:
            returning_clause = Clause(*query._returning)
            returning_clause.glue = ', '
            clauses.extend([SQL('RETURNING'), returning_clause])
        return self.build_query(clauses)

    def field_definition(self, field):
        column_type = self.get_column_type(field.get_db_field())
        ddl = field.__ddl__(column_type)
        return Clause(*ddl)

    def foreign_key_constraint(self, field):
        ddl = [
            SQL('FOREIGN KEY'),
            EnclosedClause(field.as_entity()),
            SQL('REFERENCES'),
            field.rel_model.as_entity(),
            EnclosedClause(field.to_field.as_entity())]
        if field.on_delete:
            ddl.append(SQL('ON DELETE %s' % field.on_delete))
        if field.on_update:
            ddl.append(SQL('ON UPDATE %s' % field.on_update))
        return Clause(*ddl)

    def return_parsed_node(function_name):
        # TODO: treat all `generate_` functions as returning clauses, instead
        # of SQL/params.
        def inner(self, *args, **kwargs):
            fn = getattr(self, function_name)
            return self.parse_node(fn(*args, **kwargs))
        return inner

    def _create_foreign_key(self, model_class, field, constraint=None):
        constraint = constraint or 'fk_%s_%s_refs_%s' % (
            model_class._meta.db_table,
            field.db_column,
            field.rel_model._meta.db_table)
        fk_clause = self.foreign_key_constraint(field)
        return Clause(
            SQL('ALTER TABLE'),
            model_class.as_entity(),
            SQL('ADD CONSTRAINT'),
            Entity(constraint),
            *fk_clause.nodes)
    create_foreign_key = return_parsed_node('_create_foreign_key')

    def _create_table(self, model_class, safe=False):
        statement = 'CREATE TABLE IF NOT EXISTS' if safe else 'CREATE TABLE'
        meta = model_class._meta

        columns, constraints = [], []
        if meta.composite_key:
            pk_cols = [meta.fields[f].as_entity()
                       for f in meta.primary_key.field_names]
            constraints.append(Clause(
                SQL('PRIMARY KEY'), EnclosedClause(*pk_cols)))
        for field in meta.get_fields():
            columns.append(self.field_definition(field))
            if isinstance(field, ForeignKeyField) and not field.deferred:
                constraints.append(self.foreign_key_constraint(field))

        return Clause(
            SQL(statement),
            model_class.as_entity(),
            EnclosedClause(*(columns + constraints)))
    create_table = return_parsed_node('_create_table')

    def _drop_table(self, model_class, fail_silently=False, cascade=False):
        statement = 'DROP TABLE IF EXISTS' if fail_silently else 'DROP TABLE'
        ddl = [SQL(statement), model_class.as_entity()]
        if cascade:
            ddl.append(SQL('CASCADE'))
        return Clause(*ddl)
    drop_table = return_parsed_node('_drop_table')

    def index_name(self, table, columns):
        index = '%s_%s' % (table, '_'.join(columns))
        if len(index) > 64:
            index_hash = hashlib.md5(index.encode('utf-8')).hexdigest()
            index = '%s_%s' % (table, index_hash)
        return index

    def _create_index(self, model_class, fields, unique, *extra):
        tbl_name = model_class._meta.db_table
        statement = 'CREATE UNIQUE INDEX' if unique else 'CREATE INDEX'
        index_name = self.index_name(tbl_name, [f.db_column for f in fields])
        return Clause(
            SQL(statement),
            Entity(index_name),
            SQL('ON'),
            model_class.as_entity(),
            EnclosedClause(*[field.as_entity() for field in fields]),
            *extra)
    create_index = return_parsed_node('_create_index')

    def _create_sequence(self, sequence_name):
        return Clause(SQL('CREATE SEQUENCE'), Entity(sequence_name))
    create_sequence = return_parsed_node('_create_sequence')

    def _drop_sequence(self, sequence_name):
        return Clause(SQL('DROP SEQUENCE'), Entity(sequence_name))
    drop_sequence = return_parsed_node('_drop_sequence')


class ResultIterator(object):
    def __init__(self, qrw):
        self.qrw = qrw
        self._idx = 0

    def next(self):
        if self._idx < self.qrw._ct:
            obj = self.qrw._result_cache[self._idx]
        elif not self.qrw._populated:
            obj = self.qrw.iterate()
            self.qrw._result_cache.append(obj)
            self.qrw._ct += 1
        else:
            raise StopIteration
        self._idx += 1
        return obj
    __next__ = next


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

        self._ct = 0
        self._idx = 0

        self._result_cache = []
        self._populated = False
        self._initialized = False

        if meta is not None:
            self.column_meta, self.join_meta = meta
        else:
            self.column_meta = self.join_meta = None

    def __iter__(self):
        if self._populated:
            return iter(self._result_cache)
        else:
            return ResultIterator(self)

    @property
    def count(self):
        self.fill_cache()
        return self._ct

    def process_row(self, row):
        return row

    def iterate(self):
        row = self.cursor.fetchone()
        if not row:
            self._populated = True
            if not getattr(self.cursor, 'name', None):
                self.cursor.close()
            raise StopIteration
        elif not self._initialized:
            self.initialize(self.cursor.description)
            self._initialized = True
        return self.process_row(row)

    def iterator(self):
        while True:
            yield self.iterate()

    def next(self):
        if self._idx < self._ct:
            inst = self._result_cache[self._idx]
            self._idx += 1
            return inst
        elif self._populated:
            raise StopIteration

        obj = self.iterate()
        self._result_cache.append(obj)
        self._ct += 1
        self._idx += 1
        return obj
    __next__ = next

    def fill_cache(self, n=None):
        n = n or float('Inf')
        if n < 0:
            raise ValueError('Negative values are not supported.')
        self._idx = self._ct
        while not self._populated and (n > self._ct):
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
            func = identity
            column = description[i][0]
            found = False
            if self.column_meta is not None:
                try:
                    select_column = self.column_meta[i]
                except IndexError:
                    pass
                else:
                    if isinstance(select_column, Field):
                        func = select_column.python_value
                        column = select_column._alias or select_column.name
                        found = True
                    elif (isinstance(select_column, Func) and
                            len(select_column.arguments) and
                            isinstance(select_column.arguments[0], Field)):
                        if select_column._coerce:
                            # Special-case handling aggregations.
                            func = select_column.arguments[0].python_value
                        found = True

            if not found and column in model._meta.columns:
                field_obj = model._meta.columns[column]
                column = field_obj.name
                func = field_obj.python_value

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
        instance._prepare_instance()
        return instance

class DictQueryResultWrapper(ExtQueryResultWrapper):
    def process_row(self, row):
        res = {}
        for i, column, func in self.conv:
            res[column] = func(row[i])
        return res

class ModelQueryResultWrapper(QueryResultWrapper):
    def initialize(self, description):
        self.column_map, model_set = self.generate_column_map()
        self.join_list = self.generate_join_list(model_set)

    def generate_column_map(self):
        column_map = []
        models = set([self.model])
        for i, node in enumerate(self.column_meta):
            attr = conv = None
            if isinstance(node, Field):
                if isinstance(node, FieldProxy):
                    key = node._model_alias
                    constructor = node.model
                    conv = node.field_instance.python_value
                else:
                    key = constructor = node.model_class
                    conv = node.python_value
                attr = node._alias or node.name
            else:
                if node._bind_to is None:
                    key = constructor = self.model
                else:
                    key = constructor = node._bind_to
                if isinstance(node, Node) and node._alias:
                    attr = node._alias
                elif isinstance(node, Entity):
                    attr = node.path[-1]
            column_map.append((key, constructor, attr, conv))
            models.add(key)

        return column_map, models

    def generate_join_list(self, models):
        join_list = []
        joins = self.join_meta
        stack = [self.model]
        while stack:
            current = stack.pop()
            if current not in joins:
                continue

            for join in joins[current]:
                metadata = join.metadata
                if metadata.dest in models or metadata.dest_model in models:
                    join_list.append(metadata)
                    stack.append(join.dest)

        return join_list

    def process_row(self, row):
        collected = self.construct_instances(row)
        instances = self.follow_joins(collected)
        for i in instances:
            i._prepare_instance()
        return instances[0]

    def construct_instances(self, row, keys=None):
        collected_models = {}
        for i, (key, constructor, attr, conv) in enumerate(self.column_map):
            if keys is not None and key not in keys:
                continue
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
        for metadata in self.join_list:
            inst = collected[metadata.src]
            try:
                joined_inst = collected[metadata.dest]
            except KeyError:
                joined_inst = collected[metadata.dest_model]

            # Can we populate a value on the joined instance using the current?
            mpk = metadata.primary_key is not None
            can_populate_joined_pk = (
                mpk and
                (metadata.attr in inst._data) and
                (getattr(joined_inst, metadata.primary_key.name) is None))
            if can_populate_joined_pk:
                setattr(
                    joined_inst,
                    metadata.primary_key.name,
                    inst._data[metadata.attr])

            if metadata.is_backref:
                can_populate_joined_fk = (
                    mpk and
                    (metadata.foreign_key is not None) and
                    (getattr(inst, metadata.primary_key.name) is not None) and
                    (joined_inst._data.get(metadata.foreign_key.name) is None))
                if can_populate_joined_fk:
                    setattr(
                        joined_inst,
                        metadata.foreign_key.name,
                        inst)

            setattr(inst, metadata.attr, joined_inst)
            prepared.append(joined_inst)

        return prepared


JoinCache = namedtuple('JoinCache', ('metadata', 'attr'))


class AggregateQueryResultWrapper(ModelQueryResultWrapper):
    def __init__(self, *args, **kwargs):
        self._row = []
        super(AggregateQueryResultWrapper, self).__init__(*args, **kwargs)

    def initialize(self, description):
        super(AggregateQueryResultWrapper, self).initialize(description)

        # Collect the set of all models (and ModelAlias objects) queried.
        self.all_models = set()
        for key, _, _, _ in self.column_map:
            self.all_models.add(key)

        # Prepare data structures for analyzing unique rows. Also cache
        # foreign key and attribute names for joined models.
        self.models_with_aggregate = set()
        self.back_references = {}
        self.source_to_dest = {}
        self.dest_to_source = {}

        for metadata in self.join_list:
            if metadata.is_backref:
                att_name = metadata.foreign_key.related_name
            else:
                att_name = metadata.attr

            is_backref = metadata.is_backref or metadata.is_self_join
            if is_backref:
                self.models_with_aggregate.add(metadata.src)
            else:
                self.dest_to_source.setdefault(metadata.dest, set())
                self.dest_to_source[metadata.dest].add(metadata.src)

            self.source_to_dest.setdefault(metadata.src, {})
            self.source_to_dest[metadata.src][metadata.dest] = JoinCache(
                metadata=metadata,
                attr=metadata.alias or att_name)

        # Determine which columns could contain "duplicate" data, e.g. if
        # getting Users and their Tweets, this would be the User columns.
        self.columns_to_compare = {}
        key_to_columns = {}
        for idx, (key, model_class, col_name, _) in enumerate(self.column_map):
            if key in self.models_with_aggregate:
                self.columns_to_compare.setdefault(key, [])
                self.columns_to_compare[key].append((idx, col_name))

            key_to_columns.setdefault(key, [])
            key_to_columns[key].append((idx, col_name))

        # Also compare columns for joins -> many-related model.
        for model_or_alias in self.models_with_aggregate:
            if model_or_alias not in self.columns_to_compare:
                continue
            sources = self.dest_to_source.get(model_or_alias, ())
            for joined_model in sources:
                self.columns_to_compare[model_or_alias].extend(
                    key_to_columns[joined_model])

    def read_model_data(self, row):
        models = {}
        for model_class, column_data in self.columns_to_compare.items():
            models[model_class] = []
            for idx, col_name in column_data:
                models[model_class].append(row[idx])
        return models

    def iterate(self):
        if self._row:
            row = self._row.pop()
        else:
            row = self.cursor.fetchone()

        if not row:
            self._populated = True
            if not getattr(self.cursor, 'name', None):
                self.cursor.close()
            raise StopIteration
        elif not self._initialized:
            self.initialize(self.cursor.description)
            self._initialized = True

        def _get_pk(instance):
            if instance._meta.composite_key:
                return tuple([
                    instance._data[field_name]
                    for field_name in instance._meta.primary_key.field_names])
            return instance._get_pk_value()

        identity_map = {}
        _constructed = self.construct_instances(row)
        primary_instance = _constructed[self.model]
        for model_or_alias, instance in _constructed.items():
            identity_map[model_or_alias] = OrderedDict()
            identity_map[model_or_alias][_get_pk(instance)] = instance

        model_data = self.read_model_data(row)
        while True:
            cur_row = self.cursor.fetchone()
            if cur_row is None:
                break

            duplicate_models = set()
            cur_row_data = self.read_model_data(cur_row)
            for model_class, data in cur_row_data.items():
                if model_data[model_class] == data:
                    duplicate_models.add(model_class)

            if not duplicate_models:
                self._row.append(cur_row)
                break

            different_models = self.all_models - duplicate_models

            new_instances = self.construct_instances(cur_row, different_models)
            for model_or_alias, instance in new_instances.items():
                # Do not include any instances which are comprised solely of
                # NULL values.
                all_none = True
                for value in instance._data.values():
                    if value is not None:
                        all_none = False
                if not all_none:
                    identity_map[model_or_alias][_get_pk(instance)] = instance

        stack = [self.model]
        instances = [primary_instance]
        while stack:
            current = stack.pop()
            if current not in self.join_meta:
                continue

            for join in self.join_meta[current]:
                try:
                    metadata, attr = self.source_to_dest[current][join.dest]
                except KeyError:
                    continue

                if metadata.is_backref or metadata.is_self_join:
                    for instance in identity_map[current].values():
                        setattr(instance, attr, [])

                    if join.dest not in identity_map:
                        continue

                    for pk, inst in identity_map[join.dest].items():
                        if pk is None:
                            continue
                        try:
                            # XXX: if no FK exists, unable to join.
                            joined_inst = identity_map[current][
                                inst._data[metadata.foreign_key.name]]
                        except KeyError:
                            continue

                        getattr(joined_inst, attr).append(inst)
                        instances.append(inst)
                elif attr:
                    if join.dest not in identity_map:
                        continue

                    for pk, instance in identity_map[current].items():
                        # XXX: if no FK exists, unable to join.
                        joined_inst = identity_map[join.dest][
                            instance._data[metadata.foreign_key.name]]
                        setattr(
                            instance,
                            metadata.foreign_key.name,
                            joined_inst)
                        instances.append(joined_inst)

                stack.append(join.dest)

        for instance in instances:
            instance._prepare_instance()

        return primary_instance


class Query(Node):
    """Base class representing a database query on one or more tables."""
    require_commit = True

    def __init__(self, model_class):
        super(Query, self).__init__()

        self.model_class = model_class
        self.database = model_class._meta.database

        self._dirty = True
        self._query_ctx = model_class
        self._joins = {self.model_class: []}  # Join graph as adjacency list.
        self._where = None

    def __repr__(self):
        sql, params = self.sql()
        return '%s %s %s' % (self.model_class, sql, params)

    def clone(self):
        query = type(self)(self.model_class)
        query.database = self.database
        return self._clone_attributes(query)

    def _clone_attributes(self, query):
        if self._where is not None:
            query._where = self._where.clone()
        query._joins = self._clone_joins()
        query._query_ctx = self._query_ctx
        return query

    def _clone_joins(self):
        return dict(
            (mc, list(j)) for mc, j in self._joins.items())

    def _add_query_clauses(self, initial, expressions, conjunction=None):
        reduced = reduce(operator.and_, expressions)
        if initial is None:
            return reduced
        conjunction = conjunction or operator.and_
        return conjunction(initial, reduced)

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
    def where(self, *expressions):
        self._where = self._add_query_clauses(self._where, expressions)

    @returns_clone
    def orwhere(self, *expressions):
        self._where = self._add_query_clauses(
            self._where, expressions, operator.or_)

    @returns_clone
    def join(self, dest, join_type=None, on=None):
        src = self._query_ctx
        if not on:
            require_join_condition = (
                isinstance(dest, SelectQuery) or
                (isclass(dest) and not src._meta.rel_exists(dest)))
            if require_join_condition:
                raise ValueError('A join condition must be specified.')
        elif isinstance(on, basestring):
            on = src._meta.fields[on]
        self._joins.setdefault(src, [])
        self._joins[src].append(Join(src, dest, join_type, on))
        if not isinstance(dest, SelectQuery):
            self._query_ctx = dest

    @returns_clone
    def switch(self, model_class=None):
        """Change or reset the query context."""
        self._query_ctx = model_class or self.model_class

    def ensure_join(self, lm, rm, on=None):
        ctx = self._query_ctx
        for join in self._joins.get(lm, []):
            if join.dest == rm:
                return self
        return self.switch(lm).join(rm, on=on).switch(ctx)

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
                op = OP.EQ
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
    """
    Execute a SQL query, returning a standard iterable interface that returns
    model instances.
    """
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
    _node_type = 'select_query'

    def __init__(self, model_class, *selection):
        super(SelectQuery, self).__init__(model_class)
        self.require_commit = self.database.commit_select
        self.__select(*selection)
        self._from = None
        self._group_by = None
        self._having = None
        self._order_by = None
        self._windows = None
        self._limit = None
        self._offset = None
        self._distinct = False
        self._for_update = (False, False)
        self._naive = False
        self._tuples = False
        self._dicts = False
        self._aggregate_rows = False
        self._alias = None
        self._qr = None

    def _clone_attributes(self, query):
        query = super(SelectQuery, self)._clone_attributes(query)
        query._explicit_selection = self._explicit_selection
        query._select = list(self._select)
        if self._from is not None:
            query._from = []
            for f in self._from:
                if isinstance(f, Node):
                    query._from.append(f.clone())
                else:
                    query._from.append(f)
        if self._group_by is not None:
            query._group_by = list(self._group_by)
        if self._having:
            query._having = self._having.clone()
        if self._order_by is not None:
            query._order_by = list(self._order_by)
        if self._windows is not None:
            query._windows = list(self._windows)
        query._limit = self._limit
        query._offset = self._offset
        query._distinct = self._distinct
        query._for_update = self._for_update
        query._naive = self._naive
        query._tuples = self._tuples
        query._dicts = self._dicts
        query._aggregate_rows = self._aggregate_rows
        query._alias = self._alias
        return query

    def compound_op(operator):
        def inner(self, other):
            supported_ops = self.model_class._meta.database.compound_operations
            if operator not in supported_ops:
                raise ValueError(
                    'Your database does not support %s' % operator)
            return CompoundSelect(self.model_class, self, operator, other)
        return inner
    _compound_op_static = staticmethod(compound_op)
    __or__ = compound_op('UNION')
    __and__ = compound_op('INTERSECT')
    __sub__ = compound_op('EXCEPT')

    def __xor__(self, rhs):
        # Symmetric difference, should just be (self | rhs) - (self & rhs)...
        wrapped_rhs = self.model_class.select(SQL('*')).from_(
            EnclosedClause((self & rhs)).alias('_')).order_by()
        return (self | rhs) - wrapped_rhs

    def union_all(self, rhs):
        return SelectQuery._compound_op_static('UNION ALL')(self, rhs)

    def __select(self, *selection):
        self._explicit_selection = len(selection) > 0
        selection = selection or self.model_class._meta.get_fields()
        self._select = self._model_shorthand(selection)
    select = returns_clone(__select)

    @returns_clone
    def from_(self, *args):
        self._from = None
        if args:
            self._from = list(args)

    @returns_clone
    def group_by(self, *args):
        self._group_by = self._model_shorthand(args)

    @returns_clone
    def having(self, *expressions):
        self._having = self._add_query_clauses(self._having, expressions)

    @returns_clone
    def order_by(self, *args):
        self._order_by = list(args)

    @returns_clone
    def window(self, *windows):
        self._windows = list(windows)

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
    def aggregate_rows(self, aggregate_rows=True):
        self._aggregate_rows = aggregate_rows

    @returns_clone
    def alias(self, alias=None):
        self._alias = alias

    def annotate(self, rel_model, annotation=None):
        if annotation is None:
            annotation = fn.Count(rel_model._meta.primary_key).alias('count')
        if self._query_ctx == rel_model:
            query = self.switch(self.model_class)
        else:
            query = self.clone()
        query = query.ensure_join(query._query_ctx, rel_model)
        if not query._group_by:
            query._group_by = [x.alias() for x in query._select]
        query._select = tuple(query._select) + (annotation,)
        return query

    def _aggregate(self, aggregation=None):
        if aggregation is None:
            aggregation = fn.Count(SQL('*'))
        query = self.order_by()
        query._select = [aggregation]
        return query

    def aggregate(self, aggregation=None, convert=True):
        return self._aggregate(aggregation).scalar(convert=convert)

    def count(self, clear_limit=False):
        if self._distinct or self._group_by or self._limit or self._offset:
            return self.wrapped_count(clear_limit=clear_limit)

        # defaults to a count() of the primary key
        return self.aggregate(convert=False) or 0

    def wrapped_count(self, clear_limit=False):
        clone = self.order_by()
        if clear_limit:
            clone._limit = clone._offset = None

        sql, params = clone.sql()
        wrapped = 'SELECT COUNT(1) FROM (%s) AS wrapped_select' % sql
        rq = self.model_class.raw(wrapped, *params)
        return rq.scalar() or 0

    def exists(self):
        clone = self.paginate(1, 1)
        clone._select = [SQL('1')]
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
            elif isinstance(node, Node) and node._bind_to is not None:
                if node._bind_to != model_class:
                    return False
        return True

    def get_query_meta(self):
        return (self._select, self._joins)

    def _get_result_wrapper(self):
        if self._tuples:
            return TuplesQueryResultWrapper
        elif self._dicts:
            return DictQueryResultWrapper
        elif self._naive or not self._joins or self.verify_naive():
            return NaiveQueryResultWrapper
        elif self._aggregate_rows:
            return AggregateQueryResultWrapper
        else:
            return ModelQueryResultWrapper

    def execute(self):
        if self._dirty or self._qr is None:
            model_class = self.model_class
            query_meta = self.get_query_meta()
            ResultWrapper = self._get_result_wrapper()
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
        res = self.execute()
        if isinstance(value, slice):
            index = value.stop
        else:
            index = value
        if index is not None and index >= 0:
            index += 1
        res.fill_cache(index)
        return res._result_cache[value]

    if PY3:
        def __hash__(self):
            return id(self)

class CompoundSelect(SelectQuery):
    _node_type = 'compound_select_query'

    def __init__(self, model_class, lhs=None, operator=None, rhs=None):
        self.lhs = lhs
        self.operator = operator
        self.rhs = rhs
        super(CompoundSelect, self).__init__(model_class, [])

    def _clone_attributes(self, query):
        query = super(CompoundSelect, self)._clone_attributes(query)
        query.lhs = self.lhs
        query.operator = self.operator
        query.rhs = self.rhs
        return query

    def get_query_meta(self):
        return self.lhs.get_query_meta()

    def verify_naive(self):
        return self.lhs.verify_naive() and self.rhs.verify_naive()

    def _get_result_wrapper(self):
        if self._tuples:
            return TuplesQueryResultWrapper
        elif self._dicts:
            return DictQueryResultWrapper
        elif self._aggregate_rows:
            return AggregateQueryResultWrapper

        has_joins = self.lhs._joins or self.rhs._joins
        is_naive = self.lhs._naive or self.rhs._naive or self._naive
        if is_naive or not has_joins or self.verify_naive():
            return NaiveQueryResultWrapper
        else:
            return ModelQueryResultWrapper

class _WriteQuery(Query):
    def __init__(self, model_class):
        self._returning = None
        self._tuples = False
        self._dicts = False
        self._qr = None
        super(_WriteQuery, self).__init__(model_class)

    def _clone_attributes(self, query):
        query = super(_WriteQuery, self)._clone_attributes(query)
        if self._returning:
            query._returning = list(self._returning)
            query._tuples = self._tuples
            query._dicts = self._dicts
        return query

    def requires_returning(method):
        def inner(self, *args, **kwargs):
            db = self.model_class._meta.database
            if not db.returning_clause:
                raise ValueError('RETURNING is not supported by your '
                                 'database: %s' % type(db))
            return method(self, *args, **kwargs)
        return inner

    @requires_returning
    @returns_clone
    def returning(self, *selection):
        if len(selection) == 1 and selection[0] is None:
            self._returning = None
        else:
            if not selection:
                selection = self.model_class._meta.get_fields()
            self._returning = self._model_shorthand(selection)

    @requires_returning
    @returns_clone
    def tuples(self, tuples=True):
        self._tuples = tuples

    @requires_returning
    @returns_clone
    def dicts(self, dicts=True):
        self._dicts = dicts

    def get_result_wrapper(self):
        if self._returning is not None:
            if self._tuples:
                return TuplesQueryResultWrapper
            elif self._dicts:
                return DictQueryResultWrapper
        return NaiveQueryResultWrapper

    def _execute_with_result_wrapper(self):
        ResultWrapper = self.get_result_wrapper()
        meta = (self._returning, {self.model_class: []})
        self._qr = ResultWrapper(self.model_class, self._execute(), meta)
        return self._qr


class UpdateQuery(_WriteQuery):
    def __init__(self, model_class, update=None):
        self._update = update
        self._on_conflict = None
        super(UpdateQuery, self).__init__(model_class)

    def _clone_attributes(self, query):
        query = super(UpdateQuery, self)._clone_attributes(query)
        query._update = dict(self._update)
        query._on_conflict = self._on_conflict
        return query

    @returns_clone
    def on_conflict(self, action=None):
        self._on_conflict = action

    join = not_allowed('joining')

    def sql(self):
        return self.compiler().generate_update(self)

    def execute(self):
        if self._returning is not None and self._qr is None:
            return self._execute_with_result_wrapper()
        elif self._qr is not None:
            return self._qr
        else:
            return self.database.rows_affected(self._execute())

    def __iter__(self):
        if not self.model_class._meta.database.returning_clause:
            raise ValueError('UPDATE queries cannot be iterated over unless '
                             'they specify a RETURNING clause, which is not '
                             'supported by your database.')
        return iter(self.execute())

    def iterator(self):
        return iter(self.execute().iterator())

class InsertQuery(_WriteQuery):
    def __init__(self, model_class, field_dict=None, rows=None,
                 fields=None, query=None):
        super(InsertQuery, self).__init__(model_class)

        self._upsert = False
        self._is_multi_row_insert = rows is not None or query is not None
        self._return_id_list = False
        if rows is not None:
            self._rows = rows
        else:
            self._rows = [field_dict or {}]

        self._fields = fields
        self._query = query
        self._on_conflict = None

    def _iter_rows(self):
        model_meta = self.model_class._meta
        valid_fields = (set(model_meta.fields.keys()) |
                        set(model_meta.fields.values()))
        def validate_field(field):
            if field not in valid_fields:
                raise KeyError('"%s" is not a recognized field.' % field)

        defaults = model_meta._default_dict
        callables = model_meta._default_callables

        for row_dict in self._rows:
            field_row = defaults.copy()
            seen = set()
            for key in row_dict:
                validate_field(key)
                if key in model_meta.fields:
                    field = model_meta.fields[key]
                else:
                    field = key
                field_row[field] = row_dict[key]
                seen.add(field)
            if callables:
                for field in callables:
                    if field not in seen:
                        field_row[field] = callables[field]()
            yield field_row

    def _clone_attributes(self, query):
        query = super(InsertQuery, self)._clone_attributes(query)
        query._rows = self._rows
        query._upsert = self._upsert
        query._is_multi_row_insert = self._is_multi_row_insert
        query._fields = self._fields
        query._query = self._query
        query._return_id_list = self._return_id_list
        query._on_conflict = self._on_conflict
        return query

    join = not_allowed('joining')
    where = not_allowed('where clause')

    @returns_clone
    def upsert(self, upsert=True):
        self._upsert = upsert

    @returns_clone
    def on_conflict(self, action=None):
        self._on_conflict = action

    @returns_clone
    def return_id_list(self, return_id_list=True):
        self._return_id_list = return_id_list

    @property
    def is_insert_returning(self):
        if self.database.insert_returning:
            if not self._is_multi_row_insert or self._return_id_list:
                return True
        return False

    def sql(self):
        return self.compiler().generate_insert(self)

    def _insert_with_loop(self):
        id_list = []
        last_id = None
        return_id_list = self._return_id_list
        for row in self._rows:
            last_id = (InsertQuery(self.model_class, row)
                       .upsert(self._upsert)
                       .execute())
            if return_id_list:
                id_list.append(last_id)

        if return_id_list:
            return id_list
        else:
            return last_id

    def execute(self):
        insert_with_loop = (
            self._is_multi_row_insert and
            self._query is None and
            self._returning is None and
            not self.database.insert_many)
        if insert_with_loop:
            return self._insert_with_loop()

        if self._returning is not None and self._qr is None:
            return self._execute_with_result_wrapper()
        elif self._qr is not None:
            return self._qr
        else:
            cursor = self._execute()
            if not self._is_multi_row_insert:
                if self.database.insert_returning:
                    pk_row = cursor.fetchone()
                    meta = self.model_class._meta
                    clean_data = [
                        field.python_value(column)
                        for field, column
                        in zip(meta.get_primary_key_fields(), pk_row)]
                    if self.model_class._meta.composite_key:
                        return clean_data
                    return clean_data[0]
                return self.database.last_insert_id(cursor, self.model_class)
            elif self._return_id_list:
                return map(operator.itemgetter(0), cursor.fetchall())
            else:
                return True

class DeleteQuery(_WriteQuery):
    join = not_allowed('joining')

    def sql(self):
        return self.compiler().generate_delete(self)

    def execute(self):
        if self._returning is not None and self._qr is None:
            return self._execute_with_result_wrapper()
        elif self._qr is not None:
            return self._qr
        else:
            return self.database.rows_affected(self._execute())


IndexMetadata = namedtuple(
    'IndexMetadata',
    ('name', 'sql', 'columns', 'unique', 'table'))
ColumnMetadata = namedtuple(
    'ColumnMetadata',
    ('name', 'data_type', 'null', 'primary_key', 'table'))
ForeignKeyMetadata = namedtuple(
    'ForeignKeyMetadata',
    ('column', 'dest_table', 'dest_column', 'table'))


class PeeweeException(Exception): pass
class ImproperlyConfigured(PeeweeException): pass
class DatabaseError(PeeweeException): pass
class DataError(DatabaseError): pass
class IntegrityError(DatabaseError): pass
class InterfaceError(PeeweeException): pass
class InternalError(DatabaseError): pass
class NotSupportedError(DatabaseError): pass
class OperationalError(DatabaseError): pass
class ProgrammingError(DatabaseError): pass


class ExceptionWrapper(object):
    __slots__ = ['exceptions']

    def __init__(self, exceptions):
        self.exceptions = exceptions

    def __enter__(self): pass
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            return
        if exc_type.__name__ in self.exceptions:
            new_type = self.exceptions[exc_type.__name__]
            if PY26:
                exc_args = exc_value
            else:
                exc_args = exc_value.args
            reraise(new_type, new_type(*exc_args), traceback)

class _BaseConnectionLocal(object):
    def __init__(self, **kwargs):
        super(_BaseConnectionLocal, self).__init__(**kwargs)
        self.autocommit = None
        self.closed = True
        self.conn = None
        self.context_stack = []
        self.transactions = []

class _ConnectionLocal(_BaseConnectionLocal, threading.local):
    pass

class Database(object):
    commit_select = False
    compiler_class = QueryCompiler
    compound_operations = ['UNION', 'INTERSECT', 'EXCEPT', 'UNION ALL']
    compound_select_parentheses = False
    distinct_on = False
    drop_cascade = False
    field_overrides = {}
    foreign_keys = True
    for_update = False
    for_update_nowait = False
    insert_many = True
    insert_returning = False
    interpolation = '?'
    limit_max = None
    op_overrides = {}
    quote_char = '"'
    reserved_tables = []
    returning_clause = False
    savepoints = True
    sequences = False
    subquery_delete_same_table = True
    window_functions = False

    exceptions = {
        'ConstraintError': IntegrityError,
        'DatabaseError': DatabaseError,
        'DataError': DataError,
        'IntegrityError': IntegrityError,
        'InterfaceError': InterfaceError,
        'InternalError': InternalError,
        'NotSupportedError': NotSupportedError,
        'OperationalError': OperationalError,
        'ProgrammingError': ProgrammingError}

    def __init__(self, database, threadlocals=True, autocommit=True,
                 fields=None, ops=None, autorollback=False, **connect_kwargs):
        self.init(database, **connect_kwargs)

        if threadlocals:
            self.__local = _ConnectionLocal()
        else:
            self.__local = _BaseConnectionLocal()

        self._conn_lock = threading.Lock()
        self.autocommit = autocommit
        self.autorollback = autorollback

        self.field_overrides = merge_dict(self.field_overrides, fields or {})
        self.op_overrides = merge_dict(self.op_overrides, ops or {})

    def init(self, database, **connect_kwargs):
        self.deferred = database is None
        self.database = database
        self.connect_kwargs = connect_kwargs

    def exception_wrapper(self):
        return ExceptionWrapper(self.exceptions)

    def connect(self):
        with self._conn_lock:
            if self.deferred:
                raise Exception('Error, database not properly initialized '
                                'before opening connection')
            with self.exception_wrapper():
                self.__local.conn = self._connect(
                    self.database,
                    **self.connect_kwargs)
                self.__local.closed = False
                self.initialize_connection(self.__local.conn)

    def initialize_connection(self, conn):
        pass

    def close(self):
        with self._conn_lock:
            if self.deferred:
                raise Exception('Error, database not properly initialized '
                                'before closing connection')
            with self.exception_wrapper():
                self._close(self.__local.conn)
                self.__local.closed = True

    def get_conn(self):
        if self.__local.context_stack:
            conn = self.__local.context_stack[-1].connection
            if conn is not None:
                return conn
        if self.__local.closed:
            self.connect()
        return self.__local.conn

    def is_closed(self):
        return self.__local.closed

    def get_cursor(self):
        return self.get_conn().cursor()

    def _close(self, conn):
        conn.close()

    def _connect(self, database, **kwargs):
        raise NotImplementedError

    @classmethod
    def register_fields(cls, fields):
        cls.field_overrides = merge_dict(cls.field_overrides, fields)

    @classmethod
    def register_ops(cls, ops):
        cls.op_overrides = merge_dict(cls.op_overrides, ops)

    def last_insert_id(self, cursor, model):
        if model._meta.auto_increment:
            return cursor.lastrowid

    def rows_affected(self, cursor):
        return cursor.rowcount

    def sql_error_handler(self, exception, sql, params, require_commit):
        return True

    def compiler(self):
        return self.compiler_class(
            self.quote_char, self.interpolation, self.field_overrides,
            self.op_overrides)

    def execute_sql(self, sql, params=None, require_commit=True):
        logger.debug((sql, params))
        with self.exception_wrapper():
            cursor = self.get_cursor()
            try:
                cursor.execute(sql, params or ())
            except Exception as exc:
                if self.get_autocommit() and self.autorollback:
                    self.rollback()
                if self.sql_error_handler(exc, sql, params, require_commit):
                    raise
            else:
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
        if self.__local.autocommit is None:
            self.set_autocommit(self.autocommit)
        return self.__local.autocommit

    def push_execution_context(self, transaction):
        self.__local.context_stack.append(transaction)

    def pop_execution_context(self):
        self.__local.context_stack.pop()

    def execution_context_depth(self):
        return len(self.__local.context_stack)

    def execution_context(self, with_transaction=True):
        return ExecutionContext(self, with_transaction=with_transaction)

    def push_transaction(self, transaction):
        self.__local.transactions.append(transaction)

    def pop_transaction(self):
        self.__local.transactions.pop()

    def transaction_depth(self):
        return len(self.__local.transactions)

    def transaction(self):
        return transaction(self)

    def commit_on_success(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            with self.transaction():
                return func(*args, **kwargs)
        return inner

    def savepoint(self, sid=None):
        if not self.savepoints:
            raise NotImplementedError
        return savepoint(self, sid)

    def atomic(self):
        return _atomic(self)

    def get_tables(self, schema=None):
        raise NotImplementedError

    def get_indexes(self, table, schema=None):
        raise NotImplementedError

    def get_columns(self, table, schema=None):
        raise NotImplementedError

    def get_primary_keys(self, table, schema=None):
        raise NotImplementedError

    def get_foreign_keys(self, table, schema=None):
        raise NotImplementedError

    def sequence_exists(self, seq):
        raise NotImplementedError

    def create_table(self, model_class, safe=False):
        qc = self.compiler()
        return self.execute_sql(*qc.create_table(model_class, safe))

    def create_tables(self, models, safe=False):
        create_model_tables(models, fail_silently=safe)

    def create_index(self, model_class, fields, unique=False):
        qc = self.compiler()
        if not isinstance(fields, (list, tuple)):
            raise ValueError('Fields passed to "create_index" must be a list '
                             'or tuple: "%s"' % fields)
        fobjs = [
            model_class._meta.fields[f] if isinstance(f, basestring) else f
            for f in fields]
        return self.execute_sql(*qc.create_index(model_class, fobjs, unique))

    def create_foreign_key(self, model_class, field, constraint=None):
        qc = self.compiler()
        return self.execute_sql(*qc.create_foreign_key(
            model_class, field, constraint))

    def create_sequence(self, seq):
        if self.sequences:
            qc = self.compiler()
            return self.execute_sql(*qc.create_sequence(seq))

    def drop_table(self, model_class, fail_silently=False, cascade=False):
        qc = self.compiler()
        return self.execute_sql(*qc.drop_table(
            model_class, fail_silently, cascade))

    def drop_tables(self, models, safe=False, cascade=False):
        drop_model_tables(models, fail_silently=safe, cascade=cascade)

    def drop_sequence(self, seq):
        if self.sequences:
            qc = self.compiler()
            return self.execute_sql(*qc.drop_sequence(seq))

    def extract_date(self, date_part, date_field):
        return fn.EXTRACT(Clause(date_part, R('FROM'), date_field))

    def truncate_date(self, date_part, date_field):
        return fn.DATE_TRUNC(SQL(date_part), date_field)

    def default_insert_clause(self, model_class):
        return SQL('DEFAULT VALUES')

class SqliteDatabase(Database):
    foreign_keys = False
    insert_many = sqlite3 and sqlite3.sqlite_version_info >= (3, 7, 11, 0)
    limit_max = -1
    op_overrides = {
        OP.LIKE: 'GLOB',
        OP.ILIKE: 'LIKE',
    }

    def __init__(self, database, pragmas=None, *args, **kwargs):
        self._pragmas = pragmas or []
        journal_mode = kwargs.pop('journal_mode', None)  # Backwards-compat.
        if journal_mode:
            self._pragmas.append(('journal_mode', journal_mode))

        super(SqliteDatabase, self).__init__(database, *args, **kwargs)
        if not self.database:
            self.database = ':memory:'

    def _connect(self, database, **kwargs):
        conn = sqlite3.connect(database, **kwargs)
        conn.isolation_level = None
        self._add_conn_hooks(conn)
        return conn

    def _add_conn_hooks(self, conn):
        self._set_pragmas(conn)
        conn.create_function('date_part', 2, _sqlite_date_part)
        conn.create_function('date_trunc', 2, _sqlite_date_trunc)
        conn.create_function('regexp', 2, _sqlite_regexp)

    def _set_pragmas(self, conn):
        if self._pragmas:
            cursor = conn.cursor()
            for pragma, value in self._pragmas:
                cursor.execute('PRAGMA %s = %s;' % (pragma, value))
            cursor.close()

    def begin(self, lock_type='DEFERRED'):
        self.execute_sql('BEGIN %s' % lock_type, require_commit=False)

    def get_tables(self, schema=None):
        cursor = self.execute_sql('SELECT name FROM sqlite_master WHERE '
                                  'type = ? ORDER BY name;', ('table',))
        return [row[0] for row in cursor.fetchall()]

    def get_indexes(self, table, schema=None):
        query = ('SELECT name, sql FROM sqlite_master '
                 'WHERE tbl_name = ? AND type = ? ORDER BY name')
        cursor = self.execute_sql(query, (table, 'index'))
        index_to_sql = dict(cursor.fetchall())

        # Determine which indexes have a unique constraint.
        unique_indexes = set()
        cursor = self.execute_sql('PRAGMA index_list("%s")' % table)
        for row in cursor.fetchall():
            name = row[1]
            is_unique = int(row[2]) == 1
            if is_unique:
                unique_indexes.add(name)

        # Retrieve the indexed columns.
        index_columns = {}
        for index_name in sorted(index_to_sql):
            cursor = self.execute_sql('PRAGMA index_info("%s")' % index_name)
            index_columns[index_name] = [row[2] for row in cursor.fetchall()]

        return [
            IndexMetadata(
                name,
                index_to_sql[name],
                index_columns[name],
                name in unique_indexes,
                table)
            for name in sorted(index_to_sql)]

    def get_columns(self, table, schema=None):
        cursor = self.execute_sql('PRAGMA table_info("%s")' % table)
        return [ColumnMetadata(row[1], row[2], not row[3], bool(row[5]), table)
                for row in cursor.fetchall()]

    def get_primary_keys(self, table, schema=None):
        cursor = self.execute_sql('PRAGMA table_info("%s")' % table)
        return [row[1] for row in cursor.fetchall() if row[-1]]

    def get_foreign_keys(self, table, schema=None):
        cursor = self.execute_sql('PRAGMA foreign_key_list("%s")' % table)
        return [ForeignKeyMetadata(row[3], row[2], row[4], table)
                for row in cursor.fetchall()]

    def savepoint(self, sid=None):
        return savepoint_sqlite(self, sid)

    def extract_date(self, date_part, date_field):
        return fn.date_part(date_part, date_field)

    def truncate_date(self, date_part, date_field):
        return fn.strftime(SQLITE_DATE_TRUNC_MAPPING[date_part], date_field)

class PostgresqlDatabase(Database):
    commit_select = True
    compound_select_parentheses = True
    distinct_on = True
    drop_cascade = True
    field_overrides = {
        'blob': 'BYTEA',
        'bool': 'BOOLEAN',
        'datetime': 'TIMESTAMP',
        'decimal': 'NUMERIC',
        'double': 'DOUBLE PRECISION',
        'primary_key': 'SERIAL',
        'uuid': 'UUID',
    }
    for_update = True
    for_update_nowait = True
    insert_returning = True
    interpolation = '%s'
    op_overrides = {
        OP.REGEXP: '~',
    }
    reserved_tables = ['user']
    returning_clause = True
    sequences = True
    window_functions = True

    register_unicode = True

    def _connect(self, database, encoding=None, **kwargs):
        if not psycopg2:
            raise ImproperlyConfigured('psycopg2 must be installed.')
        conn = psycopg2.connect(database=database, **kwargs)
        if self.register_unicode:
            pg_extensions.register_type(pg_extensions.UNICODE, conn)
            pg_extensions.register_type(pg_extensions.UNICODEARRAY, conn)
        if encoding:
            conn.set_client_encoding(encoding)
        return conn

    def _get_pk_sequence(self, model):
        meta = model._meta
        if meta.primary_key.sequence:
            return meta.primary_key.sequence
        elif meta.auto_increment:
            return '%s_%s_seq' % (meta.db_table, meta.primary_key.db_column)

    def last_insert_id(self, cursor, model):
        sequence = self._get_pk_sequence(model)
        if not sequence:
            return

        meta = model._meta
        if meta.schema:
            schema = '%s.' % meta.schema
        else:
            schema = ''

        cursor.execute("SELECT CURRVAL('%s\"%s\"')" % (schema, sequence))
        result = cursor.fetchone()[0]
        if self.get_autocommit():
            self.commit()
        return result

    def get_tables(self, schema='public'):
        query = ('SELECT tablename FROM pg_catalog.pg_tables '
                 'WHERE schemaname = %s ORDER BY tablename')
        return [r for r, in self.execute_sql(query, (schema,)).fetchall()]

    def get_indexes(self, table, schema='public'):
        query = """
            SELECT
                i.relname, idxs.indexdef, idx.indisunique,
                array_to_string(array_agg(cols.attname), ',')
            FROM pg_catalog.pg_class AS t
            INNER JOIN pg_catalog.pg_index AS idx ON t.oid = idx.indrelid
            INNER JOIN pg_catalog.pg_class AS i ON idx.indexrelid = i.oid
            INNER JOIN pg_catalog.pg_indexes AS idxs ON
                (idxs.tablename = t.relname AND idxs.indexname = i.relname)
            LEFT OUTER JOIN pg_catalog.pg_attribute AS cols ON
                (cols.attrelid = t.oid AND cols.attnum = ANY(idx.indkey))
            WHERE t.relname = %s AND t.relkind = %s AND idxs.schemaname = %s
            GROUP BY i.relname, idxs.indexdef, idx.indisunique
            ORDER BY idx.indisunique DESC, i.relname;"""
        cursor = self.execute_sql(query, (table, 'r', schema))
        return [IndexMetadata(row[0], row[1], row[3].split(','), row[2], table)
                for row in cursor.fetchall()]

    def get_columns(self, table, schema='public'):
        query = """
            SELECT column_name, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = %s
            ORDER BY ordinal_position"""
        cursor = self.execute_sql(query, (table, schema))
        pks = set(self.get_primary_keys(table, schema))
        return [ColumnMetadata(name, dt, null == 'YES', name in pks, table)
                for name, null, dt in cursor.fetchall()]

    def get_primary_keys(self, table, schema='public'):
        query = """
            SELECT kc.column_name
            FROM information_schema.table_constraints AS tc
            INNER JOIN information_schema.key_column_usage AS kc ON (
                tc.table_name = kc.table_name AND
                tc.table_schema = kc.table_schema AND
                tc.constraint_name = kc.constraint_name)
            WHERE
                tc.constraint_type = %s AND
                tc.table_name = %s AND
                tc.table_schema = %s"""
        cursor = self.execute_sql(query, ('PRIMARY KEY', table, schema))
        return [row for row, in cursor.fetchall()]

    def get_foreign_keys(self, table, schema='public'):
        sql = """
            SELECT
                kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON (tc.constraint_name = kcu.constraint_name AND
                    tc.constraint_schema = kcu.constraint_schema)
            JOIN information_schema.constraint_column_usage AS ccu
                ON (ccu.constraint_name = tc.constraint_name AND
                    ccu.constraint_schema = tc.constraint_schema)
            WHERE
                tc.constraint_type = 'FOREIGN KEY' AND
                tc.table_name = %s AND
                tc.table_schema = %s"""
        cursor = self.execute_sql(sql, (table, schema))
        return [ForeignKeyMetadata(row[0], row[1], row[2], table)
                for row in cursor.fetchall()]

    def sequence_exists(self, sequence):
        res = self.execute_sql("""
            SELECT COUNT(*) FROM pg_class, pg_namespace
            WHERE relkind='S'
                AND pg_class.relnamespace = pg_namespace.oid
                AND relname=%s""", (sequence,))
        return bool(res.fetchone()[0])

    def set_search_path(self, *search_path):
        path_params = ','.join(['%s'] * len(search_path))
        self.execute_sql('SET search_path TO %s' % path_params, search_path)

class MySQLDatabase(Database):
    commit_select = True
    compound_operations = ['UNION', 'UNION ALL']
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
        OP.LIKE: 'LIKE BINARY',
        OP.ILIKE: 'LIKE',
        OP.XOR: 'XOR',
    }
    quote_char = '`'
    subquery_delete_same_table = False

    def _connect(self, database, **kwargs):
        if not mysql:
            raise ImproperlyConfigured('MySQLdb or PyMySQL must be installed.')
        conn_kwargs = {
            'charset': 'utf8',
            'use_unicode': True,
        }
        conn_kwargs.update(kwargs)
        if 'password' in conn_kwargs:
            conn_kwargs['passwd'] = conn_kwargs.pop('password')
        return mysql.connect(db=database, **conn_kwargs)

    def get_tables(self, schema=None):
        return [row for row, in self.execute_sql('SHOW TABLES')]

    def get_indexes(self, table, schema=None):
        cursor = self.execute_sql('SHOW INDEX FROM `%s`' % table)
        unique = set()
        indexes = {}
        for row in cursor.fetchall():
            if not row[1]:
                unique.add(row[2])
            indexes.setdefault(row[2], [])
            indexes[row[2]].append(row[4])
        return [IndexMetadata(name, None, indexes[name], name in unique, table)
                for name in indexes]

    def get_columns(self, table, schema=None):
        sql = """
            SELECT column_name, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = DATABASE()"""
        cursor = self.execute_sql(sql, (table,))
        pks = set(self.get_primary_keys(table))
        return [ColumnMetadata(name, dt, null == 'YES', name in pks, table)
                for name, null, dt in cursor.fetchall()]

    def get_primary_keys(self, table, schema=None):
        cursor = self.execute_sql('SHOW INDEX FROM `%s`' % table)
        return [row[4] for row in cursor.fetchall() if row[2] == 'PRIMARY']

    def get_foreign_keys(self, table, schema=None):
        query = """
            SELECT column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_name = %s
                AND table_schema = DATABASE()
                AND referenced_table_name IS NOT NULL
                AND referenced_column_name IS NOT NULL"""
        cursor = self.execute_sql(query, (table,))
        return [
            ForeignKeyMetadata(column, dest_table, dest_column, table)
            for column, dest_table, dest_column in cursor.fetchall()]

    def extract_date(self, date_part, date_field):
        return fn.EXTRACT(Clause(R(date_part), R('FROM'), date_field))

    def truncate_date(self, date_part, date_field):
        return fn.DATE_FORMAT(date_field, MYSQL_DATE_TRUNC_MAPPING[date_part])

    def default_insert_clause(self, model_class):
        return Clause(
            EnclosedClause(model_class._meta.primary_key),
            SQL('VALUES (DEFAULT)'))


class _callable_context_manager(object):
    def __call__(self, fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)
        return inner

class ExecutionContext(_callable_context_manager):
    def __init__(self, database, with_transaction=True):
        self.database = database
        self.with_transaction = with_transaction
        self.connection = None

    def __enter__(self):
        with self.database._conn_lock:
            self.database.push_execution_context(self)
            self.connection = self.database._connect(
                self.database.database,
                **self.database.connect_kwargs)
            if self.with_transaction:
                self.txn = self.database.transaction()
                self.txn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self.database._conn_lock:
            if self.connection is None:
                self.database.pop_execution_context()
            else:
                try:
                    if self.with_transaction:
                        if not exc_type:
                            self.txn.commit(False)
                        self.txn.__exit__(exc_type, exc_val, exc_tb)
                finally:
                    self.database.pop_execution_context()
                    self.database._close(self.connection)

class Using(ExecutionContext):
    def __init__(self, database, models, with_transaction=True):
        super(Using, self).__init__(database, with_transaction)
        self.models = models

    def __enter__(self):
        self._orig = []
        for model in self.models:
            self._orig.append(model._meta.database)
            model._meta.database = self.database
        return super(Using, self).__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        super(Using, self).__exit__(exc_type, exc_val, exc_tb)
        for i, model in enumerate(self.models):
            model._meta.database = self._orig[i]

class _atomic(_callable_context_manager):
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        if self.db.transaction_depth() == 0:
            self._helper = self.db.transaction()
        else:
            self._helper = self.db.savepoint()
        return self._helper.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._helper.__exit__(exc_type, exc_val, exc_tb)

class transaction(_callable_context_manager):
    def __init__(self, db):
        self.db = db

    def _begin(self):
        self.db.begin()

    def commit(self, begin=True):
        self.db.commit()
        if begin:
            self._begin()

    def rollback(self, begin=True):
        self.db.rollback()
        if begin:
            self._begin()

    def __enter__(self):
        self._orig = self.db.get_autocommit()
        self.db.set_autocommit(False)
        if self.db.transaction_depth() == 0:
            self._begin()
        self.db.push_transaction(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self.rollback(False)
            elif self.db.transaction_depth() == 1:
                try:
                    self.commit(False)
                except:
                    self.rollback(False)
                    raise
        finally:
            self.db.set_autocommit(self._orig)
            self.db.pop_transaction()

class savepoint(_callable_context_manager):
    def __init__(self, db, sid=None):
        self.db = db
        _compiler = db.compiler()
        self.sid = sid or 's' + uuid.uuid4().hex
        self.quoted_sid = _compiler.quote(self.sid)

    def _execute(self, query):
        self.db.execute_sql(query, require_commit=False)

    def commit(self):
        self._execute('RELEASE SAVEPOINT %s;' % self.quoted_sid)

    def rollback(self):
        self._execute('ROLLBACK TO SAVEPOINT %s;' % self.quoted_sid)

    def __enter__(self):
        self._orig_autocommit = self.db.get_autocommit()
        self.db.set_autocommit(False)
        self._execute('SAVEPOINT %s;' % self.quoted_sid)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self.rollback()
            else:
                try:
                    self.commit()
                except:
                    self.rollback()
                    raise
        finally:
            self.db.set_autocommit(self._orig_autocommit)

class savepoint_sqlite(savepoint):
    def __enter__(self):
        conn = self.db.get_conn()
        # For sqlite, the connection's isolation_level *must* be set to None.
        # The act of setting it, though, will break any existing savepoints,
        # so only write to it if necessary.
        if conn.isolation_level is not None:
            self._orig_isolation_level = conn.isolation_level
            conn.isolation_level = None
        else:
            self._orig_isolation_level = None
        return super(savepoint_sqlite, self).__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super(savepoint_sqlite, self).__exit__(
                exc_type, exc_val, exc_tb)
        finally:
            if self._orig_isolation_level is not None:
                self.db.get_conn().isolation_level = self._orig_isolation_level

class FieldProxy(Field):
    def __init__(self, alias, field_instance):
        self._model_alias = alias
        self.model = self._model_alias.model_class
        self.field_instance = field_instance

    def clone_base(self):
        return FieldProxy(self._model_alias, self.field_instance)

    def coerce(self, value):
        return self.field_instance.coerce(value)

    def python_value(self, value):
        return self.field_instance.python_value(value)

    def db_value(self, value):
        return self.field_instance.db_value(value)

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

    def select(self, *selection):
        if not selection:
            selection = self.get_proxy_fields()
        query = SelectQuery(self, *selection)
        if self._meta.order_by:
            query = query.order_by(*self._meta.order_by)
        return query

    def __call__(self, **kwargs):
        return self.model_class(**kwargs)


class DoesNotExist(Exception): pass

if sqlite3:
    default_database = SqliteDatabase('peewee.db')
else:
    default_database = None

class ModelOptions(object):
    def __init__(self, cls, database=None, db_table=None, db_table_func=None,
                 indexes=None, order_by=None, primary_key=None,
                 table_alias=None, constraints=None, schema=None,
                 validate_backrefs=True, **kwargs):
        self.model_class = cls
        self.name = cls.__name__.lower()
        self.fields = {}
        self.columns = {}
        self.defaults = {}
        self._default_by_name = {}
        self._default_dict = {}
        self._default_callables = {}

        self.database = database or default_database
        self.db_table = db_table
        self.db_table_func = db_table_func
        self.indexes = list(indexes or [])
        self.order_by = order_by
        self.primary_key = primary_key
        self.table_alias = table_alias
        self.constraints = constraints
        self.schema = schema
        self.validate_backrefs = validate_backrefs

        self.auto_increment = None
        self.composite_key = False
        self.rel = {}
        self.reverse_rel = {}

        for key, value in kwargs.items():
            setattr(self, key, value)
        self._additional_keys = set(kwargs.keys())

        if self.db_table_func and not self.db_table:
            self.db_table = self.db_table_func(cls)

    def prepared(self):
        for field in self.fields.values():
            if field.default is not None:
                self.defaults[field] = field.default
                if callable(field.default):
                    self._default_callables[field] = field.default
                else:
                    self._default_dict[field] = field.default
                    self._default_by_name[field.name] = field.default

        if self.order_by:
            norm_order_by = []
            for item in self.order_by:
                if isinstance(item, Field):
                    prefix = '-' if item._ordering == 'DESC' else ''
                    item = prefix + item.name
                field = self.fields[item.lstrip('-')]
                if item.startswith('-'):
                    norm_order_by.append(field.desc())
                else:
                    norm_order_by.append(field.asc())
            self.order_by = norm_order_by

    def get_default_dict(self):
        dd = self._default_by_name.copy()
        if self._default_callables:
            for field, default in self._default_callables.items():
                dd[field.name] = default()
        return dd

    def get_sorted_fields(self):
        key = lambda i: i[1]._sort_key
        return sorted(self.fields.items(), key=key)

    def get_field_names(self):
        return [f[0] for f in self.get_sorted_fields()]

    def get_fields(self):
        return [f[1] for f in self.get_sorted_fields()]

    def get_field_index(self, field):
        for i, (field_name, field_obj) in enumerate(self.get_sorted_fields()):
            if field_name == field.name:
                return i
        return -1

    def get_primary_key_fields(self):
        if self.composite_key:
            return [
                self.fields[field_name]
                for field_name in self.primary_key.field_names]
        return [self.primary_key]

    def rel_for_model(self, model, field_obj=None):
        is_field = isinstance(field_obj, Field)
        is_node = not is_field and isinstance(field_obj, Node)
        for field in self.get_fields():
            if isinstance(field, ForeignKeyField) and field.rel_model == model:
                is_match = (
                    (field_obj is None) or
                    (is_field and field_obj.name == field.name) or
                    (is_node and field_obj._alias == field.name))
                if is_match:
                    return field

    def reverse_rel_for_model(self, model, field_obj=None):
        return model._meta.rel_for_model(self.model_class, field_obj)

    def rel_exists(self, model):
        return self.rel_for_model(model) or self.reverse_rel_for_model(model)

    def related_models(self, backrefs=False):
        models = []
        stack = [self.model_class]
        while stack:
            model = stack.pop()
            if model in models:
                continue
            models.append(model)
            for fk in model._meta.rel.values():
                stack.append(fk.rel_model)
            if backrefs:
                for fk in model._meta.reverse_rel.values():
                    stack.append(fk.model_class)
        return models


class BaseModel(type):
    inheritable = set([
        'constraints', 'database', 'db_table_func', 'indexes', 'order_by',
        'primary_key', 'schema', 'validate_backrefs'])

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
                if k in attrs:
                    continue
                if isinstance(v, FieldDescriptor):
                    if not v.field.primary_key:
                        attrs[k] = deepcopy(v.field)

        # initialize the new class and set the magic attributes
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        cls._meta = ModelOptions(cls, **meta_options)
        cls._data = None
        cls._meta.indexes = list(cls._meta.indexes)

        if not cls._meta.db_table:
            cls._meta.db_table = re.sub('[^\w]+', '_', cls.__name__.lower())

        # replace fields with field descriptors, calling the add_to_class hook
        fields = []
        for name, attr in cls.__dict__.items():
            if isinstance(attr, Field):
                if attr.primary_key and model_pk:
                    raise ValueError('primary key is overdetermined.')
                elif attr.primary_key:
                    model_pk, pk_name = attr, name
                else:
                    fields.append((attr, name))

        composite_key = False
        if model_pk is None:
            if parent_pk:
                model_pk, pk_name = parent_pk, parent_pk.name
            else:
                model_pk, pk_name = PrimaryKeyField(primary_key=True), 'id'
        elif isinstance(model_pk, CompositeKey):
            pk_name = '_composite_key'
            composite_key = True

        if model_pk is not False:
            model_pk.add_to_class(cls, pk_name)
            cls._meta.primary_key = model_pk
            cls._meta.auto_increment = (
                isinstance(model_pk, PrimaryKeyField) or
                bool(model_pk.sequence))
            cls._meta.composite_key = composite_key

        for field, name in fields:
            field.add_to_class(cls, name)

        # create a repr and error class before finalizing
        if hasattr(cls, '__unicode__'):
            setattr(cls, '__repr__', lambda self: '<%s: %r>' % (
                cls.__name__, self.__unicode__()))

        exc_name = '%sDoesNotExist' % cls.__name__
        exception_class = type(exc_name, (DoesNotExist,), {})
        cls.DoesNotExist = exception_class
        cls._meta.prepared()

        return cls

    def __iter__(self):
        return iter(self.select())

class Model(with_metaclass(BaseModel)):
    def __init__(self, *args, **kwargs):
        self._data = self._meta.get_default_dict()
        self._dirty = set()
        self._obj_cache = {}

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
        return InsertQuery(cls, insert)

    @classmethod
    def insert_many(cls, rows):
        return InsertQuery(cls, rows=rows)

    @classmethod
    def insert_from(cls, fields, query):
        return InsertQuery(cls, fields=fields, query=query)

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
        inst._prepare_instance()
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
        defaults = kwargs.pop('defaults', {})
        sq = cls.select().filter(**kwargs)
        try:
            return sq.get(), False
        except cls.DoesNotExist:
            try:
                params = dict((k, v) for k, v in kwargs.items()
                              if '__' not in k)
                params.update(defaults)
                with cls._meta.database.atomic():
                    return cls.create(**params), True
            except IntegrityError as exc:
                try:
                    return sq.get(), False
                except cls.DoesNotExist:
                    raise exc

    @classmethod
    def create_or_get(cls, **kwargs):
        try:
            with cls._meta.database.atomic():
                return cls.create(**kwargs), True
        except IntegrityError:
            query = []  # TODO: multi-column unique constraints.
            for field_name, value in kwargs.items():
                field = cls._meta.fields[field_name]
                if field.unique or field.primary_key:
                    query.append(field == value)
            return cls.get(*query), False

    @classmethod
    def filter(cls, *dq, **query):
        return cls.select().filter(*dq, **query)

    @classmethod
    def table_exists(cls):
        kwargs = {}
        if cls._meta.schema:
            kwargs['schema'] = cls._meta.schema
        return cls._meta.db_table in cls._meta.database.get_tables(**kwargs)

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
    def _fields_to_index(cls):
        fields = []
        for field in cls._meta.fields.values():
            if field.primary_key:
                continue
            requires_index = any((
                field.index,
                field.unique,
                isinstance(field, ForeignKeyField)))
            if requires_index:
                fields.append(field)
        return fields

    @classmethod
    def _create_indexes(cls):
        db = cls._meta.database
        for field in cls._fields_to_index():
            db.create_index(cls, [field], field.unique)

        if cls._meta.indexes:
            for fields, unique in cls._meta.indexes:
                db.create_index(cls, fields, unique)

    @classmethod
    def sqlall(cls):
        queries = []
        compiler = cls._meta.database.compiler()
        pk = cls._meta.primary_key
        if cls._meta.database.sequences and pk.sequence:
            queries.append(compiler.create_sequence(pk.sequence))
        queries.append(compiler.create_table(cls))
        for field in cls._fields_to_index():
            queries.append(compiler.create_index(cls, [field], field.unique))
        if cls._meta.indexes:
            for field_names, unique in cls._meta.indexes:
                fields = [cls._meta.fields[f] for f in field_names]
                queries.append(compiler.create_index(cls, fields, unique))
        return [sql for sql, _ in queries]

    @classmethod
    def drop_table(cls, fail_silently=False, cascade=False):
        cls._meta.database.drop_table(cls, fail_silently, cascade)

    @classmethod
    def as_entity(cls):
        if cls._meta.schema:
            return Entity(cls._meta.schema, cls._meta.db_table)
        return Entity(cls._meta.db_table)

    def _get_pk_value(self):
        return getattr(self, self._meta.primary_key.name)
    get_id = _get_pk_value  # Backwards-compatibility.

    def _set_pk_value(self, value):
        if not self._meta.composite_key:
            setattr(self, self._meta.primary_key.name, value)
    set_id = _set_pk_value  # Backwards-compatibility.

    def _pk_expr(self):
        return self._meta.primary_key == self._get_pk_value()

    def _prepare_instance(self):
        self._dirty.clear()
        self.prepared()

    def prepared(self):
        pass

    def _prune_fields(self, field_dict, only):
        new_data = {}
        for field in only:
            if field.name in field_dict:
                new_data[field.name] = field_dict[field.name]
        return new_data

    def _populate_unsaved_relations(self, field_dict):
        for key in self._meta.rel:
            conditions = (
                key in self._dirty and
                key in field_dict and
                field_dict[key] is None and
                self._obj_cache.get(key) is not None)
            if conditions:
                setattr(self, key, getattr(self, key))
                field_dict[key] = self._data[key]

    def save(self, force_insert=False, only=None):
        field_dict = dict(self._data)
        pk_field = self._meta.primary_key
        pk_value = self._get_pk_value()
        if only:
            field_dict = self._prune_fields(field_dict, only)
        self._populate_unsaved_relations(field_dict)
        if pk_value is not None and not force_insert:
            if self._meta.composite_key:
                for pk_part_name in pk_field.field_names:
                    field_dict.pop(pk_part_name, None)
            else:
                field_dict.pop(pk_field.name, None)
            rows = self.update(**field_dict).where(self._pk_expr()).execute()
        else:
            pk_from_cursor = self.insert(**field_dict).execute()
            if pk_from_cursor is not None:
                pk_value = pk_from_cursor
            self._set_pk_value(pk_value)
            rows = 1
        self._dirty.clear()
        return rows

    def is_dirty(self):
        return bool(self._dirty)

    @property
    def dirty_fields(self):
        return [f for f in self._meta.get_fields() if f.name in self._dirty]

    def dependencies(self, search_nullable=False):
        model_class = type(self)
        query = self.select().where(self._pk_expr())
        stack = [(type(self), query)]
        seen = set()

        while stack:
            klass, query = stack.pop()
            if klass in seen:
                continue
            seen.add(klass)
            for rel_name, fk in klass._meta.reverse_rel.items():
                rel_model = fk.model_class
                if fk.rel_model is model_class:
                    node = (fk == self._data[fk.to_field.name])
                    subquery = rel_model.select().where(node)
                else:
                    node = fk << query
                    subquery = rel_model.select().where(node)
                if not fk.null or search_nullable:
                    stack.append((rel_model, subquery))
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
        return self.delete().where(self._pk_expr()).execute()

    def __eq__(self, other):
        return (
            other.__class__ == self.__class__ and
            self._get_pk_value() is not None and
            other._get_pk_value() == self._get_pk_value())

    def __ne__(self, other):
        return not self == other


def prefetch_add_subquery(sq, subqueries):
    fixed_queries = [PrefetchResult(sq)]
    for i, subquery in enumerate(subqueries):
        if not isinstance(subquery, Query) and issubclass(subquery, Model):
            subquery = subquery.select()
        subquery_model = subquery.model_class
        fkf = backref = None
        for j in reversed(range(i + 1)):
            last_query = fixed_queries[j][0]
            last_model = last_query.model_class
            foreign_key = subquery_model._meta.rel_for_model(last_model)
            if foreign_key:
                fkf = getattr(subquery_model, foreign_key.name)
                to_field = getattr(last_model, foreign_key.to_field.name)
            else:
                backref = last_model._meta.rel_for_model(subquery_model)

            if fkf or backref:
                break

        if not (fkf or backref):
            raise AttributeError('Error: unable to find foreign key for '
                                 'query: %s' % subquery)

        if fkf:
            inner_query = last_query.select(to_field)
            fixed_queries.append(
                PrefetchResult(subquery.where(fkf << inner_query), fkf, False))
        elif backref:
            q = subquery.where(backref.to_field << last_query.select(backref))
            fixed_queries.append(PrefetchResult(q, backref, True))

    return fixed_queries

__prefetched = namedtuple('__prefetched', (
    'query', 'field', 'backref', 'rel_model', 'foreign_key_attr', 'model'))

class PrefetchResult(__prefetched):
    def __new__(cls, query, field=None, backref=None, rel_model=None,
                foreign_key_attr=None, model=None):
        if field:
            if backref:
                rel_model = field.model_class
                foreign_key_attr = field.to_field.name
            else:
                rel_model = field.rel_model
                foreign_key_attr = field.name
        model = query.model_class
        return super(PrefetchResult, cls).__new__(
            cls, query, field, backref, rel_model, foreign_key_attr, model)

    def populate_instance(self, instance, id_map):
        if self.backref:
            identifier = instance._data[self.field.name]
            if identifier in id_map:
                setattr(instance, self.field.name, id_map[identifier])
        else:
            identifier = instance._data[self.field.to_field.name]
            rel_instances = id_map.get(identifier, [])
            attname = self.foreign_key_attr
            dest = '%s_prefetch' % self.field.related_name
            for inst in rel_instances:
                setattr(inst, attname, instance)
            setattr(instance, dest, rel_instances)

    def store_instance(self, instance, id_map):
        identity = self.field.to_field.python_value(
            instance._data[self.foreign_key_attr])
        if self.backref:
            id_map[identity] = instance
        else:
            id_map.setdefault(identity, [])
            id_map[identity].append(instance)


def prefetch(sq, *subqueries):
    if not subqueries:
        return sq
    fixed_queries = prefetch_add_subquery(sq, subqueries)

    deps = {}
    rel_map = {}
    for prefetch_result in reversed(fixed_queries):
        query_model = prefetch_result.model
        if prefetch_result.field:
            rel_map.setdefault(prefetch_result.rel_model, [])
            rel_map[prefetch_result.rel_model].append(prefetch_result)

        deps[query_model] = {}
        id_map = deps[query_model]
        has_relations = bool(rel_map.get(query_model))

        for instance in prefetch_result.query:
            if prefetch_result.field:
                prefetch_result.store_instance(instance, id_map)

            if has_relations:
                for rel in rel_map[query_model]:
                    rel.populate_instance(instance, deps[rel.model])

    return prefetch_result.query

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
