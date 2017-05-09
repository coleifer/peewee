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

import calendar
import datetime
import decimal
import hashlib
import itertools
import logging
import operator
import re
import sys
import threading
import time
import uuid
import weakref
from bisect import bisect_left
from bisect import bisect_right
from collections import deque
from collections import namedtuple
try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict
from copy import deepcopy
from functools import wraps
from inspect import isclass

__version__ = '2.10.1'
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
    'DeferredRelation',
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
    'SmallIntegerField',
    'SqliteDatabase',
    'SQL',
    'TextField',
    'TimeField',
    'TimestampField',
    'Tuple',
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
_METACLASS_ = '_metaclass_helper_'
def with_metaclass(meta, base=object):
    return meta(_METACLASS_, (base,), {})

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
    long = int
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

if PY26:
    _D, _M = 24 * 3600., 10**6
    total_seconds = lambda t: (t.microseconds+(t.seconds+t.days*_D)*_M)/_M
else:
    total_seconds = lambda t: t.total_seconds()

# By default, peewee supports Sqlite, MySQL and Postgresql.
try:
    from pysqlite2 import dbapi2 as pysq3
except ImportError:
    pysq3 = None
try:
    import sqlite3
except ImportError:
    sqlite3 = pysq3
else:
    if pysq3 and pysq3.sqlite_version_info >= sqlite3.sqlite_version_info:
        sqlite3 = pysq3

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
    from playhouse._speedups import format_date_time
    from playhouse._speedups import sort_models_topologically
    from playhouse._speedups import strip_parens
except ImportError:
    def format_date_time(value, formats, post_process=None):
        post_process = post_process or (lambda x: x)
        for fmt in formats:
            try:
                return post_process(datetime.datetime.strptime(value, fmt))
            except ValueError:
                pass
        return value

    def sort_models_topologically(models):
        """Sort models topologically so that parents will precede children."""
        models = set(models)
        seen = set()
        ordering = []
        def dfs(model):
            # Omit models which are already sorted
            # or should not be in the list at all
            if model in models and model not in seen:
                seen.add(model)

                # First create models on which current model depends
                # (either through foreign keys or through depends_on),
                # then create current model itself
                for foreign_key in model._meta.rel.values():
                    dfs(foreign_key.rel_model)
                if model._meta.depends_on:
                    for dependency in model._meta.depends_on:
                        dfs(dependency)
                ordering.append(model)

        # Order models by name and table initially to guarantee total ordering.
        names = lambda m: (m._meta.name, m._meta.db_table)
        for m in sorted(models, key=names):
            dfs(m)
        return ordering

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

try:
    from playhouse._speedups import _DictQueryResultWrapper
    from playhouse._speedups import _ModelQueryResultWrapper
    from playhouse._speedups import _SortedFieldList
    from playhouse._speedups import _TuplesQueryResultWrapper
except ImportError:
    _DictQueryResultWrapper = _ModelQueryResultWrapper = _SortedFieldList =\
            _TuplesQueryResultWrapper = None

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

def _sqlite_regexp(regex, value, case_sensitive=False):
    flags = 0 if case_sensitive else re.I
    return re.search(regex, value, flags) is not None

class attrdict(dict):
    def __getattr__(self, attr):
        return self[attr]

SENTINEL = object()

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
    CROSS='CROSS',
)
JOIN_INNER = JOIN.INNER
JOIN_LEFT_OUTER = JOIN.LEFT_OUTER
JOIN_FULL = JOIN.FULL

RESULTS_NAIVE = 1
RESULTS_MODELS = 2
RESULTS_TUPLES = 3
RESULTS_DICTS = 4
RESULTS_AGGREGATE_MODELS = 5

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
    __slots__ = ('obj', '_callbacks')

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

class DeferredRelation(object):
    _unresolved = set()

    def __init__(self, rel_model_name=None):
        self.fields = []
        if rel_model_name is not None:
            self._rel_model_name = rel_model_name.lower()
            self._unresolved.add(self)

    def set_field(self, model_class, field, name):
        self.fields.append((model_class, field, name))

    def set_model(self, rel_model):
        for model, field, name in self.fields:
            field.rel_model = rel_model
            field.add_to_class(model, name)

    @staticmethod
    def resolve(model_cls):
        unresolved = list(DeferredRelation._unresolved)
        for dr in unresolved:
            if dr._rel_model_name == model_cls.__name__.lower():
                dr.set_model(model_cls)
                DeferredRelation._unresolved.discard(dr)


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
        return StringExpression(self, OP.CONCAT, rhs)

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
    _no_coerce = set(('count', 'sum'))

    def __init__(self, name, *arguments):
        self.name = name
        self.arguments = arguments
        self._coerce = (name.lower() not in self._no_coerce) if name else False
        super(Func, self).__init__()

    @returns_clone
    def coerce(self, coerce=True):
        self._coerce = coerce

    def clone_base(self):
        res = Func(self.name, *self.arguments)
        res._coerce = self._coerce
        return res

    def over(self, partition_by=None, order_by=None, start=None, end=None,
             window=None):
        if isinstance(partition_by, Window) and window is None:
            window = partition_by
        if start is not None and not isinstance(start, SQL):
            start = SQL(*start)
        if end is not None and not isinstance(end, SQL):
            end = SQL(*end)

        if window is None:
            sql = Window(partition_by=partition_by, order_by=order_by,
                         start=start, end=end).__sql__()
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

class StringExpression(Expression):
    def __add__(self, other):
        return self.concat(other)
    def __radd__(self, other):
        return other.concat(self)

class Param(Node):
    """
    Arbitrary parameter passed into a query. Instructs the query compiler to
    specifically treat this value as a parameter, useful for `list` which is
    special-cased for `IN` lookups.
    """
    _node_type = 'param'

    def __init__(self, value, adapt=None):
        self.value = value
        self.adapt = adapt
        super(Param, self).__init__()

    def clone_base(self):
        return Param(self.value, self.adapt)

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
Tuple = EnclosedClause

class Window(Node):
    CURRENT_ROW = 'CURRENT ROW'

    def __init__(self, partition_by=None, order_by=None, start=None, end=None):
        super(Window, self).__init__()
        self.partition_by = partition_by
        self.order_by = order_by
        self.start = start
        self.end = end
        if self.start is None and self.end is not None:
            raise ValueError('Cannot specify WINDOW end without start.')
        self._alias = self._alias or 'w'

    @staticmethod
    def following(value=None):
        if value is None:
            return SQL('UNBOUNDED FOLLOWING')
        return SQL('%d FOLLOWING' % value)

    @staticmethod
    def preceding(value=None):
        if value is None:
            return SQL('UNBOUNDED PRECEDING')
        return SQL('%d PRECEDING' % value)

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
        if self.start is not None and self.end is not None:
            over_clauses.append(Clause(
                SQL('RANGE BETWEEN'),
                self.start,
                SQL('AND'),
                self.end))
        elif self.start is not None:
            over_clauses.append(Clause(SQL('RANGE'), self.start))
        return EnclosedClause(Clause(*over_clauses))

    def clone_base(self):
        return Window(self.partition_by, self.order_by)

def Check(value):
    return SQL('CHECK (%s)' % value)

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
                 constraints=None, schema=None, undeclared=False):
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
        self.undeclared = undeclared  # Whether this field is part of schema.

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
            undeclared=self.undeclared,
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

        model_class._meta.add_field(self)
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

    def __init__(self, coerce=None, *args, **kwargs):
        super(BareField, self).__init__(*args, **kwargs)
        if coerce is not None:
            self.coerce = coerce

    def clone_base(self, **kwargs):
        return super(BareField, self).clone_base(coerce=self.coerce, **kwargs)

class IntegerField(Field):
    db_field = 'int'
    coerce = int

class BigIntegerField(IntegerField):
    db_field = 'bigint'

class SmallIntegerField(IntegerField):
    db_field = 'smallint'

class PrimaryKeyField(IntegerField):
    db_field = 'primary_key'

    def __init__(self, *args, **kwargs):
        kwargs['primary_key'] = True
        super(PrimaryKeyField, self).__init__(*args, **kwargs)

class _AutoPrimaryKeyField(PrimaryKeyField):
    _column_name = None

    def __init__(self, *args, **kwargs):
        if 'undeclared' in kwargs and not kwargs['undeclared']:
            raise ValueError('%r must be created with undeclared=True.' % self)
        kwargs['undeclared'] = True
        super(_AutoPrimaryKeyField, self).__init__(*args, **kwargs)

    def add_to_class(self, model_class, name):
        if name != self._column_name:
            raise ValueError('%s must be named `%s`.' % (type(self), name))
        super(_AutoPrimaryKeyField, self).add_to_class(model_class, name)

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
        self._exp = decimal.Decimal(10) ** (-self.decimal_places)
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
        elif self.auto_round or not isinstance(value, D):
            value = D(str(value))
            if value.is_normal() and self.auto_round:
                value = value.quantize(self._exp, rounding=self.rounding)
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
        try:
            return s.decode(encoding)
        except UnicodeDecodeError:
            return s
    return unicode_type(s)

class _StringField(Field):
    def coerce(self, value):
        return coerce_to_unicode(value or '')

    def __add__(self, other):
        return self.concat(other)
    def __radd__(self, other):
        return other.concat(self)

class CharField(_StringField):
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

class FixedCharField(CharField):
    db_field = 'fixed_char'

    def python_value(self, value):
        value = super(FixedCharField, self).python_value(value)
        if value:
            value = value.strip()
        return value

class TextField(_StringField):
    db_field = 'text'

class BlobField(Field):
    db_field = 'blob'
    _constructor = binary_construct

    def add_to_class(self, model_class, name):
        if isinstance(model_class._meta.database, Proxy):
            model_class._meta.database.attach_callback(self._set_constructor)
        return super(BlobField, self).add_to_class(model_class, name)

    def _set_constructor(self, database):
        self._constructor = database.get_binary_type()

    def db_value(self, value):
        if isinstance(value, unicode_type):
            value = value.encode('raw_unicode_escape')
        if isinstance(value, basestring):
            return self._constructor(value)
        return value

class UUIDField(Field):
    db_field = 'uuid'

    def db_value(self, value):
        if isinstance(value, uuid.UUID):
            return value.hex
        try:
            return uuid.UUID(value).hex
        except:
            return value

    def python_value(self, value):
        if isinstance(value, uuid.UUID):
            return value
        return None if value is None else uuid.UUID(value)

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
        if value is not None and isinstance(value, datetime.timedelta):
            return (datetime.datetime.min + value).time()
        return value

    hour = property(_date_part('hour'))
    minute = property(_date_part('minute'))
    second = property(_date_part('second'))

class TimestampField(IntegerField):
    # Support second -> microsecond resolution.
    valid_resolutions = [10**i for i in range(7)]

    def __init__(self, *args, **kwargs):
        self.resolution = kwargs.pop('resolution', 1) or 1
        if self.resolution not in self.valid_resolutions:
            raise ValueError('TimestampField resolution must be one of: %s' %
                             ', '.join(str(i) for i in self.valid_resolutions))

        self.utc = kwargs.pop('utc', False) or False
        _dt = datetime.datetime
        self._conv = _dt.utcfromtimestamp if self.utc else _dt.fromtimestamp
        _default = _dt.utcnow if self.utc else _dt.now
        kwargs.setdefault('default', _default)
        super(TimestampField, self).__init__(*args, **kwargs)

    def get_db_field(self):
        # For second resolution we can get away (for a while) with using
        # 4 bytes to store the timestamp (as long as they're not > ~2038).
        # Otherwise we'll need to use a BigInteger type.
        return (self.db_field if self.resolution == 1
                else BigIntegerField.db_field)

    def db_value(self, value):
        if value is None:
            return

        if isinstance(value, datetime.datetime):
            pass
        elif isinstance(value, datetime.date):
            value = datetime.datetime(value.year, value.month, value.day)
        else:
            return int(round(value * self.resolution))

        if self.utc:
            timestamp = calendar.timegm(value.utctimetuple())
        else:
            timestamp = time.mktime(value.timetuple())
        timestamp += (value.microsecond * .000001)
        if self.resolution > 1:
            timestamp *= self.resolution
        return int(round(timestamp))

    def python_value(self, value):
        if value is not None and isinstance(value, (int, float, long)):
            if value == 0:
                return
            elif self.resolution > 1:
                ticks_to_microsecond = 1000000 // self.resolution
                value, ticks = divmod(value, self.resolution)
                microseconds = ticks * ticks_to_microsecond
                return self._conv(value).replace(microsecond=microseconds)
            else:
                return self._conv(value)
        return value

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
        self.field = weakref.ref(field)

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return instance._data.get(self.attr_name)
        return self.field()

    def __set__(self, instance, value):
        setattr(instance, self.attr_name, value)

class ForeignKeyField(IntegerField):
    def __init__(self, rel_model, related_name=None, on_delete=None,
                 on_update=None, extra=None, to_field=None, *args, **kwargs):
        if rel_model != 'self' and not \
                isinstance(rel_model, (Proxy, DeferredRelation)) and not \
                issubclass(rel_model, Model):
            raise TypeError('Unexpected value for `rel_model`.  Expected '
                            '`Model`, `Proxy`, `DeferredRelation`, or "self"')
        self.rel_model = rel_model
        self._related_name = related_name
        self.deferred = isinstance(rel_model, (Proxy, DeferredRelation))
        self.on_delete = on_delete
        self.on_update = on_update
        self.extra = extra
        self.to_field = to_field
        super(ForeignKeyField, self).__init__(*args, **kwargs)

    def clone_base(self, **kwargs):
        return super(ForeignKeyField, self).clone_base(
            rel_model=self.rel_model,
            related_name=self._get_related_name(),
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
        if self._related_name and callable(self._related_name):
            return self._related_name(self)
        return self._related_name or ('%s_set' % self.model_class._meta.name)

    def add_to_class(self, model_class, name):
        if isinstance(self.rel_model, Proxy):
            def callback(rel_model):
                self.rel_model = rel_model
                self.add_to_class(model_class, name)
            self.rel_model.attach_callback(callback)
            return
        elif isinstance(self.rel_model, DeferredRelation):
            self.rel_model.set_field(model_class, self, name)
            return

        self.name = name
        self.model_class = model_class
        self.db_column = obj_id_name = self.db_column or '%s_id' % self.name
        if obj_id_name == self.name:
            obj_id_name += '_id'
        if not self.verbose_name:
            self.verbose_name = re.sub('_+', ' ', name).title()

        model_class._meta.add_field(self)

        self.related_name = self._get_related_name()
        if self.rel_model == 'self':
            self.rel_model = self.model_class

        if self.to_field is not None:
            if not isinstance(self.to_field, Field):
                self.to_field = getattr(self.rel_model, self.to_field)
        else:
            self.to_field = self.rel_model._meta.primary_key

        # TODO: factor into separate method.
        if model_class._meta.validate_backrefs:
            def invalid(msg, **context):
                context.update(
                    field='%s.%s' % (model_class._meta.name, name),
                    backref=self.related_name,
                    obj_id_name=obj_id_name)
                raise AttributeError(msg % context)

            if self.related_name in self.rel_model._meta.fields:
                invalid('The related_name of %(field)s ("%(backref)s") '
                        'conflicts with a field of the same name.')
            elif self.related_name in self.rel_model._meta.reverse_rel:
                invalid('The related_name of %(field)s ("%(backref)s") '
                        'is already in use by another foreign key.')

            if obj_id_name in model_class._meta.fields:
                invalid('The object id descriptor of %(field)s conflicts '
                        'with a field named %(obj_id_name)s')
            elif obj_id_name in model_class.__dict__:
                invalid('Model attribute "%(obj_id_name)s" would be shadowed '
                        'by the object id descriptor of %(field)s.')

        setattr(model_class, name, self._get_descriptor())
        setattr(model_class, obj_id_name,  self._get_id_descriptor())
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

    def python_value(self, value):
        if isinstance(value, self.rel_model):
            return value
        return self.to_field.python_value(value)


class CompositeKey(object):
    """A primary key composed of multiple columns."""
    _node_type = 'composite_key'
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

    def __ne__(self, other):
        return ~(self == other)

    def __hash__(self):
        return hash((self.model_class.__name__, self.field_names))


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
        'smallint': 'SMALLINT',
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
        JOIN.CROSS: 'CROSS JOIN',
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
            'passthrough': self._parse_passthrough,
            'func': self._parse_func,
            'clause': self._parse_clause,
            'entity': self._parse_entity,
            'field': self._parse_field,
            'sql': self._parse_sql,
            'select_query': self._parse_select_query,
            'compound_select_query': self._parse_compound_select_query,
            'strip_parens': self._parse_strip_parens,
            'composite_key': self._parse_composite_key,
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
        if node.op == OP.IN and rhs == '()' and not rparams:
            return ('0 = 1' if node.flat else '(0 = 1)'), []
        template = '%s %s %s' if node.flat else '(%s %s %s)'
        sql = template % (lhs, self.get_op(node.op), rhs)
        return sql, lparams + rparams

    def _parse_passthrough(self, node, alias_map, conv):
        if node.adapt:
            return self.parse_node(node.adapt(node.value), alias_map, None)
        return self.interpolation, [node.value]

    def _parse_param(self, node, alias_map, conv):
        if node.adapt:
            if conv and conv.db_value is node.adapt:
                conv = None
            return self.parse_node(node.adapt(node.value), alias_map, conv)
        elif conv is not None:
            return self.parse_node(conv.db_value(node.value), alias_map)
        else:
            return self.interpolation, [node.value]

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

    def _parse_composite_key(self, node, alias_map, conv):
        fields = []
        for field_name in node.field_names:
            fields.append(node.model_class._meta.fields[field_name])
        return self._parse_clause(CommaClause(*fields), alias_map, conv)

    def _parse_compound_select_query(self, node, alias_map, conv):
        csq = 'compound_select_query'
        lhs, rhs = node.lhs, node.rhs
        inv = rhs._node_type == csq and lhs._node_type != csq
        if inv:
            lhs, rhs = rhs, lhs

        new_map = self.alias_map_class()
        if lhs._node_type == csq:
            new_map._counter = alias_map._counter

        sql1, p1 = self.generate_select(lhs, new_map)
        sql2, p2 = self.generate_select(rhs, self.calculate_alias_map(rhs,
                                                                      new_map))

        # We add outer parentheses in the event the compound query is used in
        # the `from_()` clause, in which case we'll need them.
        if node.database.compound_select_parentheses:
            if lhs._node_type != csq:
                sql1 = '(%s)' % sql1
            if rhs._node_type != csq:
                sql2 = '(%s)' % sql2

        if inv:
            sql1, p1, sql2, p2 = sql2, p2, sql1, p1

        return '(%s %s %s)' % (sql1, node.operator, sql2), (p1 + p2)

    def _parse_select_query(self, node, alias_map, conv):
        clone = node.clone()
        if not node._explicit_selection:
            if conv and isinstance(conv, ForeignKeyField):
                clone._select = (conv.to_field,)
            else:
                clone._select = clone.model_class._meta.get_primary_key_fields()
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
            unknown = (node_type in self._unknown_types and
                       node.adapt is None and
                       conv is None)
        elif isinstance(node, (list, tuple, set)):
            # If you're wondering how to pass a list into your query, simply
            # wrap it in Param().
            sql, params = self.parse_node_list(node, alias_map, conv)
            sql = '(%s)' % sql
        elif isinstance(node, Model):
            sql = self.interpolation
            if conv and isinstance(conv, ForeignKeyField):
                to_field = conv.to_field
                if isinstance(to_field, ForeignKeyField):
                    value = conv.db_value(node)
                else:
                    value = to_field.db_value(getattr(node, to_field.name))
            else:
                value = node._get_pk_value()
            params = [value]
        elif (isclass(node) and issubclass(node, Model)) or \
                isinstance(node, ModelAlias):
            entity = node.as_entity().alias(alias_map[node])
            sql, params = self.parse_node(entity, alias_map, conv)
        elif conv is not None:
            value = conv.db_value(node)
            sql, params, _ = self._parse(value, alias_map, None)
        else:
            sql, params = self._parse_default(node, alias_map, None)
            unknown = True

        return sql, params, unknown

    def parse_node(self, node, alias_map=None, conv=None):
        sql, params, unknown = self._parse(node, alias_map, conv)
        if unknown and (conv is not None) and params:
            params = [conv.db_value(i) for i in params]

        if isinstance(node, Node):
            if node._negated:
                sql = 'NOT %s' % sql
            if node._alias:
                sql = ' '.join((sql, 'AS', node._alias))
            if node._ordering:
                sql = ' '.join((sql, node._ordering))

        if params and any(isinstance(p, Node) for p in params):
            clean_params = []
            clean_sql = []
            for idx, param in enumerate(params):
                if isinstance(param, Node):
                    csql, cparams = self.parse_node(param)

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
                join_type = join.get_join_type()
                if isinstance(join.on, (Expression, Func, Clause, Entity)):
                    # Clear any alias on the join expression.
                    constraint = join.on.clone().alias()
                elif join_type != JOIN.CROSS:
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

                join_sql = SQL(self.join_map.get(join_type) or join_type)
                if join_type == JOIN.CROSS:
                    clauses.append(Clause(join_sql, dest_n))
                else:
                    clauses.append(Clause(join_sql, dest_n, SQL('ON'),
                                          constraint))

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

        join_clauses = self.generate_joins(query._joins, model, alias_map)
        if join_clauses:
            clauses.extend(join_clauses)

        if query._where is not None:
            clauses.extend([SQL('WHERE'), query._where])

        if query._group_by:
            clauses.extend([SQL('GROUP BY'), CommaClause(*query._group_by)])

        if query._having:
            clauses.extend([SQL('HAVING'), query._having])

        if query._windows is not None:
            clauses.append(SQL('WINDOW'))
            clauses.append(CommaClause(*[
                Clause(
                    SQL(window._alias),
                    SQL('AS'),
                    window.__sql__())
                for window in query._windows]))

        if query._order_by:
            clauses.extend([SQL('ORDER BY'), CommaClause(*query._order_by)])

        if query._limit is not None or (query._offset and db.limit_max):
            limit = query._limit if query._limit is not None else db.limit_max
            clauses.append(SQL('LIMIT %d' % limit))
        if query._offset is not None:
            clauses.append(SQL('OFFSET %d' % query._offset))

        if query._for_update:
            clauses.append(SQL(query._for_update))

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
                value = Param(value, adapt=field.db_value)
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
            statement = meta.database.upsert_sql
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
                        value = Param(value, adapt=field.db_value)
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
        for field in meta.declared_fields:
            columns.append(self.field_definition(field))
            if isinstance(field, ForeignKeyField) and not field.deferred:
                constraints.append(self.foreign_key_constraint(field))

        if model_class._meta.constraints:
            for constraint in model_class._meta.constraints:
                if not isinstance(constraint, Node):
                    constraint = SQL(constraint)
                constraints.append(constraint)

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

    def _truncate_table(self, model_class, restart_identity=False,
                        cascade=False):
        ddl = [SQL('TRUNCATE TABLE'), model_class.as_entity()]
        if restart_identity:
            ddl.append(SQL('RESTART IDENTITY'))
        if cascade:
            ddl.append(SQL('CASCADE'))
        return Clause(*ddl)
    truncate_table = return_parsed_node('_truncate_table')

    def index_name(self, table, columns):
        index = '%s_%s' % (table, '_'.join(columns))
        if len(index) > 64:
            index_hash = hashlib.md5(index.encode('utf-8')).hexdigest()
            index = '%s_%s' % (table[:55], index_hash[:8])  # 55 + 1 + 8 = 64
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

    def _drop_index(self, model_class, fields, fail_silently=False):
        tbl_name = model_class._meta.db_table
        statement = 'DROP INDEX IF EXISTS' if fail_silently else 'DROP INDEX'
        index_name = self.index_name(tbl_name, [f.db_column for f in fields])
        return Clause(SQL(statement), Entity(index_name))
    drop_index = return_parsed_node('_drop_index')

    def _create_sequence(self, sequence_name):
        return Clause(SQL('CREATE SEQUENCE'), Entity(sequence_name))
    create_sequence = return_parsed_node('_create_sequence')

    def _drop_sequence(self, sequence_name):
        return Clause(SQL('DROP SEQUENCE'), Entity(sequence_name))
    drop_sequence = return_parsed_node('_drop_sequence')


class SqliteQueryCompiler(QueryCompiler):
    def truncate_table(self, model_class, restart_identity=False,
                       cascade=False):
        return model_class.delete().sql()


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

    def __len__(self):
        return self.count

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
                next(self)
            except StopIteration:
                break

class ExtQueryResultWrapper(QueryResultWrapper):
    def initialize(self, description):
        n_cols = len(description)
        self.conv = conv = []
        if self.column_meta is not None:
            n_meta = len(self.column_meta)
            for i, node in enumerate(self.column_meta):
                if not self._initialize_node(node, i):
                    self._initialize_by_name(description[i][0], i)
            if n_cols == n_meta:
                return
        else:
            i = 0

        for i in range(i, n_cols):
            self._initialize_by_name(description[i][0], i)

    def _initialize_by_name(self, name, i):
        model_cols = self.model._meta.columns
        if name in model_cols:
            field = model_cols[name]
            self.conv.append((i, field.name, field.python_value))
        else:
            self.conv.append((i, name, None))

    def _initialize_node(self, node, i):
        if isinstance(node, Field):
            self.conv.append((i, node._alias or node.name, node.python_value))
            return True
        elif isinstance(node, Func) and len(node.arguments):
            arg = node.arguments[0]
            if isinstance(arg, Field):
                name = node._alias or arg._alias or arg.name
                func = node._coerce and arg.python_value or None
                self.conv.append((i, name, func))
                return True
        return False


class TuplesQueryResultWrapper(ExtQueryResultWrapper):
    def process_row(self, row):
        return tuple([col if self.conv[i][2] is None else self.conv[i][2](col)
                      for i, col in enumerate(row)])

if _TuplesQueryResultWrapper is None:
    _TuplesQueryResultWrapper = TuplesQueryResultWrapper

class NaiveQueryResultWrapper(ExtQueryResultWrapper):
    def process_row(self, row):
        instance = self.model()
        for i, column, f in self.conv:
            setattr(instance, column, f(row[i]) if f is not None else row[i])
        instance._prepare_instance()
        return instance

if _ModelQueryResultWrapper is None:
    _ModelQueryResultWrapper = NaiveQueryResultWrapper

class DictQueryResultWrapper(ExtQueryResultWrapper):
    def process_row(self, row):
        res = {}
        for i, column, f in self.conv:
            res[column] = f(row[i]) if f is not None else row[i]
        return res

if _DictQueryResultWrapper is None:
    _DictQueryResultWrapper = DictQueryResultWrapper

class ModelQueryResultWrapper(QueryResultWrapper):
    def initialize(self, description):
        self.column_map, model_set = self.generate_column_map()
        self._col_set = set(col for col in self.column_meta
                            if isinstance(col, Field))
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
                    if metadata.foreign_key is not None:
                        fk_present = metadata.foreign_key in self._col_set
                        pk_present = metadata.primary_key in self._col_set
                        check = metadata.foreign_key.null and (fk_present or
                                                               pk_present)
                    else:
                        check = fk_present = pk_present = False

                    join_list.append((
                        metadata,
                        check,
                        fk_present,
                        pk_present))
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
            setattr(instance, attr, value if conv is None else conv(value))

        return collected_models

    def follow_joins(self, collected):
        prepared = [collected[self.model]]
        for (metadata, check_null, fk_present, pk_present) in self.join_list:
            inst = collected[metadata.src]
            try:
                joined_inst = collected[metadata.dest]
            except KeyError:
                joined_inst = collected[metadata.dest_model]

            has_fk = True
            if check_null:
                if fk_present:
                    has_fk = inst._data.get(metadata.foreign_key.name)
                elif pk_present:
                    has_fk = joined_inst._data.get(metadata.primary_key.name)

            if not has_fk:
                continue

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

        for (metadata, _, _, _) in self.join_list:
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
                accum.extend(arg._meta.declared_fields)
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
        if on is None:
            require_join_condition = join_type != JOIN.CROSS and (
                isinstance(dest, SelectQuery) or
                (isclass(dest) and not src._meta.rel_exists(dest)))
            if require_join_condition:
                raise ValueError('A join condition must be specified.')
        elif join_type == JOIN.CROSS:
            raise ValueError('A CROSS join cannot have a constraint.')
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

    def ensure_join(self, lm, rm, on=None, **join_kwargs):
        ctx = self._query_ctx
        for join in self._joins.get(lm, []):
            if join.dest == rm:
                return self
        return self.switch(lm).join(rm, on=on, **join_kwargs).switch(ctx)

    def convert_dict_to_node(self, qdict):
        accum = []
        joins = []
        relationship = (ForeignKeyField, ReverseRelationDescriptor)
        for key, value in sorted(qdict.items()):
            curr = self.model_class
            if '__' in key and key.rsplit('__', 1)[1] in DJANGO_MAP:
                key, op = key.rsplit('__', 1)
                op = DJANGO_MAP[op]
            elif value is None:
                op = OP.IS
            else:
                op = OP.EQ
            for piece in key.split('__'):
                model_attr = getattr(curr, piece)
                if value is not None and isinstance(model_attr, relationship):
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
                QRW = self.database.get_result_wrapper(RESULTS_TUPLES)
            elif self._dicts:
                QRW = self.database.get_result_wrapper(RESULTS_DICTS)
            else:
                QRW = self.database.get_result_wrapper(RESULTS_NAIVE)
            self._qr = QRW(self.model_class, self._execute(), None)
        return self._qr

    def __iter__(self):
        return iter(self.execute())

def allow_extend(orig, new_val, **kwargs):
    extend = kwargs.pop('extend', False)
    if kwargs:
        raise ValueError('"extend" is the only valid keyword argument.')
    if extend:
        return ((orig or []) + new_val) or None
    elif new_val:
        return new_val

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
        self._for_update = None
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
        selection = selection or self.model_class._meta.declared_fields
        self._select = self._model_shorthand(selection)
    select = returns_clone(__select)

    @returns_clone
    def from_(self, *args):
        self._from = list(args) if args else None

    @returns_clone
    def group_by(self, *args, **kwargs):
        self._group_by = self._model_shorthand(args) if args else None

    @returns_clone
    def having(self, *expressions):
        self._having = self._add_query_clauses(self._having, expressions)

    @returns_clone
    def order_by(self, *args, **kwargs):
        self._order_by = allow_extend(self._order_by, list(args), **kwargs)

    @returns_clone
    def window(self, *windows, **kwargs):
        self._windows = allow_extend(self._windows, list(windows), **kwargs)

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
        self._for_update = 'FOR UPDATE NOWAIT' if for_update and nowait else \
                'FOR UPDATE' if for_update else None

    @returns_clone
    def with_lock(self, lock_type='UPDATE'):
        self._for_update = ('FOR %s' % lock_type) if lock_type else None

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
            return next(clone.execute())
        except StopIteration:
            raise self.model_class.DoesNotExist(
                'Instance matching query does not exist:\nSQL: %s\nPARAMS: %s'
                % self.sql())

    def peek(self, n=1):
        res = self.execute()
        res.fill_cache(n)
        models = res._result_cache[:n]
        if models:
            return models[0] if n == 1 else models

    def first(self, n=1):
        if self._limit != n:
            self._limit = n
            self._dirty = True
        return self.peek(n=n)

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
            return self.database.get_result_wrapper(RESULTS_TUPLES)
        elif self._dicts:
            return self.database.get_result_wrapper(RESULTS_DICTS)
        elif self._naive or not self._joins or self.verify_naive():
            return self.database.get_result_wrapper(RESULTS_NAIVE)
        elif self._aggregate_rows:
            return self.database.get_result_wrapper(RESULTS_AGGREGATE_MODELS)
        else:
            return self.database.get_result_wrapper(RESULTS_MODELS)

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
        if index is not None:
            index = index + 1 if index >= 0 else None
        res.fill_cache(index)
        return res._result_cache[value]

    def __len__(self):
        return len(self.execute())

    if PY3:
        def __hash__(self):
            return id(self)

class NoopSelectQuery(SelectQuery):
    def sql(self):
        return (self.database.get_noop_sql(), ())

    def get_query_meta(self):
        return None, None

    def _get_result_wrapper(self):
        return self.database.get_result_wrapper(RESULTS_TUPLES)

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

    def count(self, clear_limit=False):
        return self.wrapped_count(clear_limit=clear_limit)

    def get_query_meta(self):
        return self.lhs.get_query_meta()

    def verify_naive(self):
        return self.lhs.verify_naive() and self.rhs.verify_naive()

    def _get_result_wrapper(self):
        if self._tuples:
            return self.database.get_result_wrapper(RESULTS_TUPLES)
        elif self._dicts:
            return self.database.get_result_wrapper(RESULTS_DICTS)
        elif self._aggregate_rows:
            return self.database.get_result_wrapper(RESULTS_AGGREGATE_MODELS)

        has_joins = self.lhs._joins or self.rhs._joins
        is_naive = self.lhs._naive or self.rhs._naive or self._naive
        if is_naive or not has_joins or self.verify_naive():
            return self.database.get_result_wrapper(RESULTS_NAIVE)
        else:
            return self.database.get_result_wrapper(RESULTS_MODELS)

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
                selection = self.model_class._meta.declared_fields
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
                return self.database.get_result_wrapper(RESULTS_TUPLES)
            elif self._dicts:
                return self.database.get_result_wrapper(RESULTS_DICTS)
        return self.database.get_result_wrapper(RESULTS_NAIVE)

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
                 fields=None, query=None, validate_fields=False):
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
        self._validate_fields = validate_fields
        self._on_conflict = None

    def _iter_rows(self):
        model_meta = self.model_class._meta
        if self._validate_fields:
            valid_fields = model_meta.valid_fields
            def validate_field(field):
                if field not in valid_fields:
                    raise KeyError('"%s" is not a recognized field.' % field)

        defaults = model_meta._default_dict
        callables = model_meta._default_callables

        for row_dict in self._rows:
            field_row = defaults.copy()
            seen = set()
            for key in row_dict:
                if self._validate_fields:
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
        query._validate_fields = self._validate_fields
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
    upsert_sql = None
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
                 fields=None, ops=None, autorollback=False, use_speedups=True,
                 **connect_kwargs):
        self.connect_kwargs = {}
        if threadlocals:
            self._local = _ConnectionLocal()
        else:
            self._local = _BaseConnectionLocal()
        self.init(database, **connect_kwargs)

        self._conn_lock = threading.Lock()
        self.autocommit = autocommit
        self.autorollback = autorollback
        self.use_speedups = use_speedups

        self.field_overrides = merge_dict(self.field_overrides, fields or {})
        self.op_overrides = merge_dict(self.op_overrides, ops or {})
        self.exception_wrapper = ExceptionWrapper(self.exceptions)

    def init(self, database, **connect_kwargs):
        if not self.is_closed():
            self.close()
        self.deferred = database is None
        self.database = database
        self.connect_kwargs.update(connect_kwargs)

    def connect(self):
        with self._conn_lock:
            if self.deferred:
                raise OperationalError('Database has not been initialized')
            if not self._local.closed:
                raise OperationalError('Connection already open')
            self._local.conn = self._create_connection()
            self._local.closed = False
            with self.exception_wrapper:
                self.initialize_connection(self._local.conn)

    def initialize_connection(self, conn):
        pass

    def close(self):
        with self._conn_lock:
            if self.deferred:
                raise Exception('Error, database not properly initialized '
                                'before closing connection')
            with self.exception_wrapper:
                self._close(self._local.conn)
                self._local.closed = True

    def get_conn(self):
        if self._local.context_stack:
            conn = self._local.context_stack[-1].connection
            if conn is not None:
                return conn
        if self._local.closed:
            self.connect()
        return self._local.conn

    def _create_connection(self):
        with self.exception_wrapper:
            return self._connect(self.database, **self.connect_kwargs)

    def is_closed(self):
        return self._local.closed

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

    def get_result_wrapper(self, wrapper_type):
        if wrapper_type == RESULTS_NAIVE:
            return (_ModelQueryResultWrapper if self.use_speedups
                    else NaiveQueryResultWrapper)
        elif wrapper_type == RESULTS_MODELS:
            return ModelQueryResultWrapper
        elif wrapper_type == RESULTS_TUPLES:
            return (_TuplesQueryResultWrapper if self.use_speedups
                    else TuplesQueryResultWrapper)
        elif wrapper_type == RESULTS_DICTS:
            return (_DictQueryResultWrapper if self.use_speedups
                    else DictQueryResultWrapper)
        elif wrapper_type == RESULTS_AGGREGATE_MODELS:
            return AggregateQueryResultWrapper
        else:
            return (_ModelQueryResultWrapper if self.use_speedups
                    else NaiveQueryResultWrapper)

    def last_insert_id(self, cursor, model):
        if model._meta.auto_increment:
            return cursor.lastrowid

    def rows_affected(self, cursor):
        return cursor.rowcount

    def compiler(self):
        return self.compiler_class(
            self.quote_char, self.interpolation, self.field_overrides,
            self.op_overrides)

    def execute(self, clause):
        return self.execute_sql(*self.compiler().parse_node(clause))

    def execute_sql(self, sql, params=None, require_commit=True):
        logger.debug((sql, params))
        with self.exception_wrapper:
            cursor = self.get_cursor()
            try:
                cursor.execute(sql, params or ())
            except Exception:
                if self.autorollback and self.get_autocommit():
                    self.rollback()
                raise
            else:
                if require_commit and self.get_autocommit():
                    self.commit()
        return cursor

    def begin(self):
        pass

    def commit(self):
        with self.exception_wrapper:
            self.get_conn().commit()

    def rollback(self):
        with self.exception_wrapper:
            self.get_conn().rollback()

    def set_autocommit(self, autocommit):
        self._local.autocommit = autocommit

    def get_autocommit(self):
        if self._local.autocommit is None:
            self.set_autocommit(self.autocommit)
        return self._local.autocommit

    def push_execution_context(self, transaction):
        self._local.context_stack.append(transaction)

    def pop_execution_context(self):
        self._local.context_stack.pop()

    def execution_context_depth(self):
        return len(self._local.context_stack)

    def execution_context(self, with_transaction=True, transaction_type=None):
        return ExecutionContext(self, with_transaction, transaction_type)

    __call__ = execution_context

    def push_transaction(self, transaction):
        self._local.transactions.append(transaction)

    def pop_transaction(self):
        self._local.transactions.pop()

    def transaction_depth(self):
        return len(self._local.transactions)

    def transaction(self, transaction_type=None):
        return transaction(self, transaction_type)
    commit_on_success = property(transaction)

    def savepoint(self, sid=None):
        if not self.savepoints:
            raise NotImplementedError
        return savepoint(self, sid)

    def atomic(self, transaction_type=None):
        return _atomic(self, transaction_type)

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

    def drop_index(self, model_class, fields, safe=False):
        qc = self.compiler()
        if not isinstance(fields, (list, tuple)):
            raise ValueError('Fields passed to "drop_index" must be a list '
                             'or tuple: "%s"' % fields)
        fobjs = [
            model_class._meta.fields[f] if isinstance(f, basestring) else f
            for f in fields]
        return self.execute_sql(*qc.drop_index(model_class, fobjs, safe))

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
        if cascade and not self.drop_cascade:
            raise ValueError('Database does not support DROP TABLE..CASCADE.')
        return self.execute_sql(*qc.drop_table(
            model_class, fail_silently, cascade))

    def drop_tables(self, models, safe=False, cascade=False):
        drop_model_tables(models, fail_silently=safe, cascade=cascade)

    def truncate_table(self, model_class, restart_identity=False,
                       cascade=False):
        qc = self.compiler()
        return self.execute_sql(*qc.truncate_table(
            model_class, restart_identity, cascade))

    def truncate_tables(self, models, restart_identity=False, cascade=False):
        for model in reversed(sort_models_topologically(models)):
            model.truncate_table(restart_identity, cascade)

    def drop_sequence(self, seq):
        if self.sequences:
            qc = self.compiler()
            return self.execute_sql(*qc.drop_sequence(seq))

    def extract_date(self, date_part, date_field):
        return fn.EXTRACT(Clause(date_part, R('FROM'), date_field))

    def truncate_date(self, date_part, date_field):
        return fn.DATE_TRUNC(date_part, date_field)

    def default_insert_clause(self, model_class):
        return SQL('DEFAULT VALUES')

    def get_noop_sql(self):
        return 'SELECT 0 WHERE 0'

    def get_binary_type(self):
        return binary_construct

def __pragma__(name):
    def __get__(self):
        return self.pragma(name)
    def __set__(self, value):
        return self.pragma(name, value)
    return property(__get__, __set__)

class SqliteDatabase(Database):
    compiler_class = SqliteQueryCompiler
    field_overrides = {
        'bool': 'INTEGER',
        'smallint': 'INTEGER',
        'uuid': 'TEXT',
    }
    foreign_keys = False
    insert_many = sqlite3 and sqlite3.sqlite_version_info >= (3, 7, 11, 0)
    limit_max = -1
    op_overrides = {
        OP.LIKE: 'GLOB',
        OP.ILIKE: 'LIKE',
    }
    upsert_sql = 'INSERT OR REPLACE INTO'

    def __init__(self, database, pragmas=None, *args, **kwargs):
        self._pragmas = pragmas or []
        journal_mode = kwargs.pop('journal_mode', None)  # Backwards-compat.
        if journal_mode:
            self._pragmas.append(('journal_mode', journal_mode))

        super(SqliteDatabase, self).__init__(database, *args, **kwargs)

    def _connect(self, database, **kwargs):
        if not sqlite3:
            raise ImproperlyConfigured('pysqlite or sqlite3 must be installed.')
        conn = sqlite3.connect(database, **kwargs)
        conn.isolation_level = None
        try:
            self._add_conn_hooks(conn)
        except:
            conn.close()
            raise
        return conn

    def _add_conn_hooks(self, conn):
        self._set_pragmas(conn)
        conn.create_function('date_part', 2, _sqlite_date_part)
        conn.create_function('date_trunc', 2, _sqlite_date_trunc)
        conn.create_function('regexp', -1, _sqlite_regexp)

    def _set_pragmas(self, conn):
        if self._pragmas:
            cursor = conn.cursor()
            for pragma, value in self._pragmas:
                cursor.execute('PRAGMA %s = %s;' % (pragma, value))
            cursor.close()

    def pragma(self, key, value=SENTINEL):
        sql = 'PRAGMA %s' % key
        if value is not SENTINEL:
            sql += ' = %s' % value
        return self.execute_sql(sql).fetchone()

    cache_size = __pragma__('cache_size')
    foreign_keys = __pragma__('foreign_keys')
    journal_mode = __pragma__('journal_mode')
    journal_size_limit = __pragma__('journal_size_limit')
    mmap_size = __pragma__('mmap_size')
    page_size = __pragma__('page_size')
    read_uncommitted = __pragma__('read_uncommitted')
    synchronous = __pragma__('synchronous')
    wal_autocheckpoint = __pragma__('wal_autocheckpoint')

    def begin(self, lock_type=None):
        statement = 'BEGIN %s' % lock_type if lock_type else 'BEGIN'
        self.execute_sql(statement, require_commit=False)

    def transaction(self, transaction_type=None):
        return transaction_sqlite(self, transaction_type)

    def create_foreign_key(self, model_class, field, constraint=None):
        raise OperationalError('SQLite does not support ALTER TABLE '
                               'statements to add constraints.')

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

    def get_binary_type(self):
        return sqlite3.Binary

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
        if meta.primary_key is not False and meta.primary_key.sequence:
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

    def get_noop_sql(self):
        return 'SELECT 0 WHERE false'

    def get_binary_type(self):
        return psycopg2.Binary

class MySQLDatabase(Database):
    commit_select = True
    compound_select_parentheses = True
    compound_operations = ['UNION', 'UNION ALL']
    field_overrides = {
        'bool': 'BOOL',
        'decimal': 'NUMERIC',
        'double': 'DOUBLE PRECISION',
        'float': 'FLOAT',
        'primary_key': 'INTEGER AUTO_INCREMENT',
        'text': 'LONGTEXT',
        'uuid': 'VARCHAR(40)',
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
    upsert_sql = 'REPLACE INTO'

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

    def get_noop_sql(self):
        return 'DO 0'

    def get_binary_type(self):
        return mysql.Binary


class _callable_context_manager(object):
    __slots__ = ()
    def __call__(self, fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)
        return inner

class ExecutionContext(_callable_context_manager):
    def __init__(self, database, with_transaction=True, transaction_type=None):
        self.database = database
        self.with_transaction = with_transaction
        self.transaction_type = transaction_type
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
    __slots__ = ('db', 'transaction_type', 'context_manager')
    def __init__(self, db, transaction_type=None):
        self.db = db
        self.transaction_type = transaction_type

    def __enter__(self):
        if self.db.transaction_depth() == 0:
            self.context_manager = self.db.transaction(self.transaction_type)
        else:
            self.context_manager = self.db.savepoint()
        return self.context_manager.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self.context_manager.__exit__(exc_type, exc_val, exc_tb)

class transaction(_callable_context_manager):
    __slots__ = ('db', 'autocommit', 'transaction_type')
    def __init__(self, db, transaction_type=None):
        self.db = db
        self.transaction_type = transaction_type

    def _begin(self):
        if self.transaction_type:
            self.db.begin(self.transaction_type)
        else:
            self.db.begin()

    def commit(self, begin=True):
        self.db.commit()
        if begin: self._begin()

    def rollback(self, begin=True):
        self.db.rollback()
        if begin: self._begin()

    def __enter__(self):
        self.autocommit = self.db.get_autocommit()
        self.db.set_autocommit(False)
        if self.db.transaction_depth() == 0: self._begin()
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
            self.db.set_autocommit(self.autocommit)
            self.db.pop_transaction()

class savepoint(_callable_context_manager):
    __slots__ = ('db', 'sid', 'quoted_sid', 'autocommit')
    def __init__(self, db, sid=None):
        self.db = db
        _compiler = db.compiler()
        self.sid = sid or 's' + uuid.uuid4().hex
        self.quoted_sid = _compiler.quote(self.sid)

    def _execute(self, query):
        self.db.execute_sql(query, require_commit=False)

    def _begin(self):
        self._execute('SAVEPOINT %s;' % self.quoted_sid)

    def commit(self, begin=True):
        self._execute('RELEASE SAVEPOINT %s;' % self.quoted_sid)
        if begin: self._begin()

    def rollback(self):
        self._execute('ROLLBACK TO SAVEPOINT %s;' % self.quoted_sid)

    def __enter__(self):
        self.autocommit = self.db.get_autocommit()
        self.db.set_autocommit(False)
        self._begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self.rollback()
            else:
                try:
                    self.commit(begin=False)
                except:
                    self.rollback()
                    raise
        finally:
            self.db.set_autocommit(self.autocommit)

class transaction_sqlite(transaction):
    __slots__ = ()
    def _begin(self):
        self.db.begin(lock_type=self.transaction_type)

class savepoint_sqlite(savepoint):
    __slots__ = ('isolation_level',)
    def __enter__(self):
        conn = self.db.get_conn()
        # For sqlite, the connection's isolation_level *must* be set to None.
        # The act of setting it, though, will break any existing savepoints,
        # so only write to it if necessary.
        if conn.isolation_level is not None:
            self.isolation_level = conn.isolation_level
            conn.isolation_level = None
        else:
            self.isolation_level = None
        return super(savepoint_sqlite, self).__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super(savepoint_sqlite, self).__exit__(
                exc_type, exc_val, exc_tb)
        finally:
            if self.isolation_level is not None:
                self.db.get_conn().isolation_level = self.isolation_level

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

    def get_proxy_fields(self, declared_fields=False):
        mm = self.model_class._meta
        fields = mm.declared_fields if declared_fields else mm.sorted_fields
        return [FieldProxy(self, f) for f in fields]

    def select(self, *selection):
        if not selection:
            selection = self.get_proxy_fields()
        query = SelectQuery(self, *selection)
        if self._meta.order_by:
            query = query.order_by(*self._meta.order_by)
        return query

    def __call__(self, **kwargs):
        return self.model_class(**kwargs)

if _SortedFieldList is None:
    class _SortedFieldList(object):
        __slots__ = ('_keys', '_items')

        def __init__(self):
            self._keys = []
            self._items = []

        def __getitem__(self, i):
            return self._items[i]

        def __iter__(self):
            return iter(self._items)

        def __contains__(self, item):
            k = item._sort_key
            i = bisect_left(self._keys, k)
            j = bisect_right(self._keys, k)
            return item in self._items[i:j]

        def index(self, field):
            return self._keys.index(field._sort_key)

        def insert(self, item):
            k = item._sort_key
            i = bisect_left(self._keys, k)
            self._keys.insert(i, k)
            self._items.insert(i, item)

        def remove(self, item):
            idx = self.index(item)
            del self._items[idx]
            del self._keys[idx]

class DoesNotExist(Exception): pass

if sqlite3:
    default_database = SqliteDatabase('peewee.db')
else:
    default_database = None

class ModelOptions(object):
    def __init__(self, cls, database=None, db_table=None, db_table_func=None,
                 indexes=None, order_by=None, primary_key=None,
                 table_alias=None, constraints=None, schema=None,
                 validate_backrefs=True, only_save_dirty=False,
                 depends_on=None, **kwargs):
        self.model_class = cls
        self.name = cls.__name__.lower()
        self.fields = {}
        self.columns = {}
        self.defaults = {}
        self._default_by_name = {}
        self._default_dict = {}
        self._default_callables = {}
        self._default_callable_list = []
        self._sorted_field_list = _SortedFieldList()
        self.sorted_fields = []
        self.sorted_field_names = []
        self.valid_fields = set()
        self.declared_fields = []

        self.database = database if database is not None else default_database
        self.db_table = db_table
        self.db_table_func = db_table_func
        self.indexes = list(indexes or [])
        self.order_by = order_by
        self.primary_key = primary_key
        self.table_alias = table_alias
        self.constraints = constraints
        self.schema = schema
        self.validate_backrefs = validate_backrefs
        self.only_save_dirty = only_save_dirty
        self.depends_on = depends_on

        self.auto_increment = None
        self.composite_key = False
        self.rel = {}
        self.reverse_rel = {}

        for key, value in kwargs.items():
            setattr(self, key, value)
        self._additional_keys = set(kwargs.keys())

        if self.db_table_func and not self.db_table:
            self.db_table = self.db_table_func(cls)

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.name)

    def prepared(self):
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

    def _update_field_lists(self):
        self.sorted_fields = list(self._sorted_field_list)
        self.sorted_field_names = [f.name for f in self.sorted_fields]
        self.valid_fields = (set(self.fields.keys()) |
                             set(self.fields.values()) |
                             set((self.primary_key,)))
        self.declared_fields = [field for field in self.sorted_fields
                                if not field.undeclared]

    def add_field(self, field):
        self.remove_field(field.name)
        self.fields[field.name] = field
        self.columns[field.db_column] = field

        self._sorted_field_list.insert(field)
        self._update_field_lists()

        if field.default is not None:
            self.defaults[field] = field.default
            if callable(field.default):
                self._default_callables[field] = field.default
                self._default_callable_list.append((field.name, field.default))
            else:
                self._default_dict[field] = field.default
                self._default_by_name[field.name] = field.default

    def remove_field(self, field_name):
        if field_name not in self.fields:
            return
        original = self.fields.pop(field_name)
        del self.columns[original.db_column]
        self._sorted_field_list.remove(original)
        self._update_field_lists()

        if original.default is not None:
            del self.defaults[original]
            if self._default_callables.pop(original, None):
                for i, (name, _) in enumerate(self._default_callable_list):
                    if name == field_name:
                        self._default_callable_list.pop(i)
                        break
            else:
                self._default_dict.pop(original, None)
                self._default_by_name.pop(original.name, None)

    def get_default_dict(self):
        dd = self._default_by_name.copy()
        for field_name, default in self._default_callable_list:
            dd[field_name] = default()
        return dd

    def get_field_index(self, field):
        try:
            return self._sorted_field_list.index(field)
        except ValueError:
            return -1

    def get_primary_key_fields(self):
        if self.composite_key:
            return [
                self.fields[field_name]
                for field_name in self.primary_key.field_names]
        return [self.primary_key]

    def rel_for_model(self, model, field_obj=None, multi=False):
        is_field = isinstance(field_obj, Field)
        is_node = not is_field and isinstance(field_obj, Node)
        if multi:
            accum = []
        for field in self.sorted_fields:
            if isinstance(field, ForeignKeyField) and field.rel_model == model:
                is_match = (
                    (field_obj is None) or
                    (is_field and field_obj.name == field.name) or
                    (is_node and field_obj._alias == field.name))
                if is_match:
                    if not multi:
                        return field
                    accum.append(field)
        if multi:
            return accum

    def reverse_rel_for_model(self, model, field_obj=None, multi=False):
        return model._meta.rel_for_model(self.model_class, field_obj, multi)

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
        'primary_key', 'schema', 'validate_backrefs', 'only_save_dirty'])

    def __new__(cls, name, bases, attrs):
        if name == _METACLASS_ or bases[0].__name__ == _METACLASS_:
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
        ModelOptionsBase = meta_options.get('model_options_base', ModelOptions)
        cls._meta = ModelOptionsBase(cls, **meta_options)
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
        exc_attrs = {'__module__': cls.__module__}
        exception_class = type(exc_name, (DoesNotExist,), exc_attrs)
        cls.DoesNotExist = exception_class
        cls._meta.prepared()

        if hasattr(cls, 'validate_model'):
            cls.validate_model()

        DeferredRelation.resolve(cls)

        return cls

    def __iter__(self):
        return iter(self.select())

class Model(with_metaclass(BaseModel)):
    def __init__(self, *args, **kwargs):
        self._data = self._meta.get_default_dict()
        self._dirty = set(self._data)
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
    def update(cls, __data=None, **update):
        fdict = __data or {}
        fdict.update([(cls._meta.fields[f], update[f]) for f in update])
        return UpdateQuery(cls, fdict)

    @classmethod
    def insert(cls, __data=None, **insert):
        fdict = __data or {}
        fdict.update([(cls._meta.fields[f], insert[f]) for f in insert])
        return InsertQuery(cls, fdict)

    @classmethod
    def insert_many(cls, rows, validate_fields=True):
        return InsertQuery(cls, rows=rows, validate_fields=validate_fields)

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
        query = cls.select()
        for field, value in kwargs.items():
            if '__' in field:
                query = query.filter(**{field: value})
            else:
                query = query.where(getattr(cls, field) == value)

        try:
            return query.get(), False
        except cls.DoesNotExist:
            try:
                params = dict((k, v) for k, v in kwargs.items()
                              if '__' not in k)
                params.update(defaults)
                with cls._meta.database.atomic():
                    return cls.create(**params), True
            except IntegrityError as exc:
                try:
                    return query.get(), False
                except cls.DoesNotExist:
                    raise exc

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
        if db.sequences and pk is not False and pk.sequence:
            if not db.sequence_exists(pk.sequence):
                db.create_sequence(pk.sequence)

        db.create_table(cls)
        cls._create_indexes()

    @classmethod
    def _fields_to_index(cls):
        fields = []
        for field in cls._meta.sorted_fields:
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
    def _index_data(cls):
        return itertools.chain(
            [((field,), field.unique) for field in cls._fields_to_index()],
            cls._meta.indexes or ())

    @classmethod
    def _create_indexes(cls):
        for field_list, is_unique in cls._index_data():
            cls._meta.database.create_index(cls, field_list, is_unique)

    @classmethod
    def _drop_indexes(cls, safe=False):
        for field_list, is_unique in cls._index_data():
            cls._meta.database.drop_index(cls, field_list, safe)

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
    def truncate_table(cls, restart_identity=False, cascade=False):
        cls._meta.database.truncate_table(cls, restart_identity, cascade)

    @classmethod
    def as_entity(cls):
        if cls._meta.schema:
            return Entity(cls._meta.schema, cls._meta.db_table)
        return Entity(cls._meta.db_table)

    @classmethod
    def noop(cls, *args, **kwargs):
        return NoopSelectQuery(cls, *args, **kwargs)

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
        if self._meta.primary_key is not False:
            pk_field = self._meta.primary_key
            pk_value = self._get_pk_value()
        else:
            pk_field = pk_value = None
        if only:
            field_dict = self._prune_fields(field_dict, only)
        elif self._meta.only_save_dirty and not force_insert:
            field_dict = self._prune_fields(
                field_dict,
                self.dirty_fields)
            if not field_dict:
                self._dirty.clear()
                return False

        self._populate_unsaved_relations(field_dict)
        if pk_value is not None and not force_insert:
            if self._meta.composite_key:
                for pk_part_name in pk_field.field_names:
                    field_dict.pop(pk_part_name, None)
            else:
                field_dict.pop(pk_field.name, None)
            rows = self.update(**field_dict).where(self._pk_expr()).execute()
        elif pk_field is None:
            self.insert(**field_dict).execute()
            rows = 1
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
        return [f for f in self._meta.sorted_fields if f.name in self._dirty]

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

    def __hash__(self):
        return hash((self.__class__, self._get_pk_value()))

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
        if isinstance(subquery, tuple):
            subquery, target_model = subquery
        else:
            target_model = None
        if not isinstance(subquery, Query) and issubclass(subquery, Model):
            subquery = subquery.select()
        subquery_model = subquery.model_class
        fks = backrefs = None
        for j in reversed(range(i + 1)):
            prefetch_result = fixed_queries[j]
            last_query = prefetch_result.query
            last_model = prefetch_result.model
            rels = subquery_model._meta.rel_for_model(last_model, multi=True)
            if rels:
                fks = [getattr(subquery_model, fk.name) for fk in rels]
                pks = [getattr(last_model, fk.to_field.name) for fk in rels]
            else:
                backrefs = last_model._meta.rel_for_model(
                    subquery_model,
                    multi=True)

            if (fks or backrefs) and ((target_model is last_model) or
                                      (target_model is None)):
                break

        if not (fks or backrefs):
            tgt_err = ' using %s' % target_model if target_model else ''
            raise AttributeError('Error: unable to find foreign key for '
                                 'query: %s%s' % (subquery, tgt_err))

        if fks:
            expr = reduce(operator.or_, [
                (fk << last_query.select(pk))
                for (fk, pk) in zip(fks, pks)])
            subquery = subquery.where(expr)
            fixed_queries.append(PrefetchResult(subquery, fks, False))
        elif backrefs:
            expr = reduce(operator.or_, [
                (backref.to_field << last_query.select(backref))
                for backref in backrefs])
            subquery = subquery.where(expr)
            fixed_queries.append(PrefetchResult(subquery, backrefs, True))

    return fixed_queries

__prefetched = namedtuple('__prefetched', (
    'query', 'fields', 'backref', 'rel_models', 'field_to_name', 'model'))

class PrefetchResult(__prefetched):
    def __new__(cls, query, fields=None, backref=None, rel_models=None,
                field_to_name=None, model=None):
        if fields:
            if backref:
                rel_models = [field.model_class for field in fields]
                foreign_key_attrs = [field.to_field.name for field in fields]
            else:
                rel_models = [field.rel_model for field in fields]
                foreign_key_attrs = [field.name for field in fields]
            field_to_name = list(zip(fields, foreign_key_attrs))
        model = query.model_class
        return super(PrefetchResult, cls).__new__(
            cls, query, fields, backref, rel_models, field_to_name, model)

    def populate_instance(self, instance, id_map):
        if self.backref:
            for field in self.fields:
                identifier = instance._data[field.name]
                key = (field, identifier)
                if key in id_map:
                    setattr(instance, field.name, id_map[key])
        else:
            for field, attname in self.field_to_name:
                identifier = instance._data[field.to_field.name]
                key = (field, identifier)
                rel_instances = id_map.get(key, [])
                dest = '%s_prefetch' % field.related_name
                for inst in rel_instances:
                    setattr(inst, attname, instance)
                setattr(instance, dest, rel_instances)

    def store_instance(self, instance, id_map):
        for field, attname in self.field_to_name:
            identity = field.to_field.python_value(instance._data[attname])
            key = (field, identity)
            if self.backref:
                id_map[key] = instance
            else:
                id_map.setdefault(key, [])
                id_map[key].append(instance)


def prefetch(sq, *subqueries):
    if not subqueries:
        return sq
    fixed_queries = prefetch_add_subquery(sq, subqueries)

    deps = {}
    rel_map = {}
    for prefetch_result in reversed(fixed_queries):
        query_model = prefetch_result.model
        if prefetch_result.fields:
            for rel_model in prefetch_result.rel_models:
                rel_map.setdefault(rel_model, [])
                rel_map[rel_model].append(prefetch_result)

        deps[query_model] = {}
        id_map = deps[query_model]
        has_relations = bool(rel_map.get(query_model))

        for instance in prefetch_result.query:
            if prefetch_result.fields:
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
