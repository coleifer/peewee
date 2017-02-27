from bisect import bisect_left
from bisect import bisect_right
from collections import defaultdict
from collections import deque
from collections import namedtuple
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
from inspect import isclass
import calendar
import datetime
import decimal
import itertools
import logging
import operator
import re
import sys
import threading
import time
import weakref

try:
    import sqlite3
except ImportError:
    sqlite3 = None


if sys.version_info[0] == 2:
    text_type = unicode
    bytes_type = str
    exec('def reraise(tp, value, tb=None): raise tp, value, tb')
    PY26 = sys.version_info[1] == 6
else:
    text_type = str
    bytes_type = bytes
    basestring = str
    def reraise(tp, value, tb=None):
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value


class attrdict(dict):
    def __getattr__(self, attr): return self[attr]
    def __setattr__(self, attr, value): self[attr] = value
    def __iadd__(self, rhs): self.update(rhs); return self
    def __add__(self, rhs): d = attrdict(self); d.update(rhs); return d


OP = attrdict(
    AND='AND',
    OR='OR',
    ADD='+',
    SUB='-',
    MUL='*',
    DIV='/',
    BIN_AND='&',
    BIN_OR='|',
    XOR='#',
    MOD='%',
    EQ='=',
    LT='<',
    LTE='<=',
    GT='>',
    GTE='>=',
    NE='!=',
    IN='IN',
    NOT_IN='NOT IN',
    IS='IS',
    IS_NOT='IS NOT',
    LIKE='LIKE',
    ILIKE='ILIKE',
    BETWEEN='BETWEEN',
    REGEXP='REGEXP',
    CONCAT='||')

FIELD = attrdict(
    AUTO='INTEGER',
    BIGINT='BIGINT',
    BLOB='BLOB',
    BOOL='SMALLINT',
    CHAR='CHAR',
    DATE='DATE',
    DATETIME='DATETIME',
    DECIMAL='DECIMAL',
    DEFAULT='',
    DOUBLE='REAL',
    FLOAT='REAL',
    INT='INTEGER',
    SMALLINT='SMALLINT',
    TEXT='TEXT',
    TIME='TIME',
    UUID='TEXT',
    VARCHAR='VARCHAR')

JOIN = attrdict(
    INNER='INNER JOIN',
    LEFT_OUTER='LEFT OUTER JOIN',
    RIGHT_OUTER='RIGHT OUTER JOIN',
    FULL='FULL JOIN',
    FULL_OUTER='FULL OUTER JOIN',
    CROSS='CROSS JOIN')

# Row representations.
ROW = attrdict(
    TUPLE=1,
    DICT=2,
    NAMED_TUPLE=3,
    CONSTRUCTOR=4,
    MODEL=5)

# Scope rules, affect the way various SQL clauses are represented.
SCOPE_NORMAL = 1
SCOPE_SOURCE = 2
SCOPE_VALUES = 3
SCOPE_CTE = 4


# Helper functions that are used in various parts of the codebase.
MODEL_BASE = '_metaclass_helper_'

def with_metaclass(meta, base=object):
    return meta(MODEL_BASE, (base,), {})

def merge_dict(source, overrides, allow_no_copy=False):
    if not overrides:
        if allow_no_copy:
            return source
        else:
            return source.copy()
    else:
        merged = source.copy()
        merged.update(overrides)
        return merged

class _callable_context_manager(object):
    def __call__(self, fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            with self:
                return fn(*args, **kwargs)
        return inner

def is_model(obj):
    return isclass(obj) and issubclass(obj, Model)

class cached_property(object):
    __slots__ = ('fn',)

    def __call__(self, fn):
        self.fn = fn
        return self

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            instance.__dict__[self.fn.__name__] = self.fn(instance)
            return instance.__dict__[self.fn.__name__]
        return self

# SQL Generation.

class AliasManager(object):
    def __init__(self):
        self._mapping = []
        self._index = []
        self._current_index = 0
        self._prefixes = 'tabcdefghijklmnopqrstuvwxyz'
        self.push()

    def add(self, source):
        idx = self._current_index  # Obtain reference in local variable.
        if source in self._mapping[idx]:
            return
        self._index[idx] += 1
        self._mapping[idx][source] = '%s%d' % (self._prefixes[idx],
                                               self._index[idx])

    def get(self, source):
        self.add(source)
        return self._mapping[self._current_index][source]

    def set(self, source, alias):
        self._mapping[self._current_index][source] = alias
        return self

    def push(self):
        self._mapping.append({})
        self._index.append(0)
        self._current_index = len(self._index) - 1
        return self

    def pop(self):
        self._current_index = 0
        return self


class State(namedtuple('_State', ('scope', 'parentheses', 'subquery',
                                  'settings'))):
    """
    Lightweight object for representing the rules applied at a given scope.
    """
    def __new__(cls, scope=SCOPE_NORMAL, parentheses=False, subquery=False,
                **kwargs):
        return super(State, cls).__new__(cls, scope, parentheses, subquery,
                                         kwargs)

    def __call__(self, scope=None, parentheses=None, subquery=None, **kwargs):
        # All state is "inherited" except parentheses.
        scope = self.scope if scope is None else scope
        subquery = self.subquery if subquery is None else subquery
        settings = self.settings
        if kwargs:
            settings.update(kwargs)
        return State(scope, parentheses, subquery, **settings)

    def __getattr__(self, attr_name):
        return self.settings.get(attr_name)


def __scope_context__(scope):
    @contextmanager
    def inner(self, **kwargs):
        with self(scope=scope, **kwargs):
            yield self
    return inner


class Context(object):
    def __init__(self, **settings):
        self.stack = []
        self._sql = []
        self._bind_values = []
        self.alias_manager = AliasManager()
        self.state = State(**settings)
        self.refresh()

    def column_sort_key(self, item):
        return item[0].get_sort_key(self)

    def refresh(self):
        self.scope = self.state.scope
        self.parentheses = self.state.parentheses
        self.subquery = self.state.subquery
        self.settings = self.state.settings

    def __call__(self, **overrides):
        if overrides and overrides.get('scope') == self.scope:
            del overrides['scope']

        self.stack.append(self.state)
        self.state = self.state(**overrides)
        self.refresh()
        return self

    scope_normal = __scope_context__(SCOPE_NORMAL)
    scope_source = __scope_context__(SCOPE_SOURCE)
    scope_values = __scope_context__(SCOPE_VALUES)
    scope_cte = __scope_context__(SCOPE_CTE)

    def __enter__(self):
        if self.parentheses:
            self.literal('(')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.parentheses:
            self.literal(')')
        self.state = self.stack.pop()
        self.refresh()

    @contextmanager
    def push_alias(self):
        self.alias_manager.push()
        yield
        self.alias_manager.pop()

    def sql(self, obj):
        if isinstance(obj, (Node, Context)):
            return obj.__sql__(self)
        elif is_model(obj):
            return obj._meta.table.__sql__(self)
        else:
            return self.sql(BindValue(obj))

    def literal(self, keyword):
        self._sql.append(keyword)
        return self

    def bind_value(self, value, converter=None):
        if converter is None:
            converter = self.state.converter
        if converter is not None:
            value = converter(value)
        self._bind_values.append(value)
        return self

    def __sql__(self, ctx):
        ctx._sql.extend(self._sql)
        ctx._bind_values.extend(self._bind_values)
        return ctx

    def parse(self, node):
        return self.sql(node).query()

    def query(self):
        return ''.join(self._sql), self._bind_values

# AST.

class Node(object):
    def clone(self):
        obj = self.__class__.__new__(self.__class__)
        obj.__dict__ = self.__dict__.copy()
        return obj

    def __sql__(self, ctx):
        raise NotImplementedError

    @staticmethod
    def copy(method):
        def inner(self, *args, **kwargs):
            clone = self.clone()
            method(clone, *args, **kwargs)
            return clone
        return inner


class _DynamicColumn(object):
    __slots__ = ()

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return ColumnFactory(instance)  # Implements __getattr__().
        return self


class _ExplicitColumn(object):
    __slots__ = ()

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            raise AttributeError(
                '%s specifies columns explicitly, and does not support '
                'dynamic column lookups.' % instance)
        return self


class Source(Node):
    c = _DynamicColumn()

    def __init__(self, alias=None):
        super(Source, self).__init__()
        self._alias = alias

    @Node.copy
    def alias(self, name):
        self._alias = name

    def select(self, *columns):
        return Select((self,), columns)

    def join(self, dest, join_type='INNER', on=None):
        return Join(self, dest, join_type, on)

    def left_outer_join(self, dest, on=None):
        return Join(self, dest, JOIN.LEFT_OUTER, on)

    def get_sort_key(self, ctx):
        if self._alias:
            return (self._alias,)
        return (ctx.alias_manager.get(self),)

    def apply_alias(self, ctx):
        # If we are defining the source, include the "AS alias" declaration. An
        # alias is created for the source if one is not already defined.
        if ctx.scope == SCOPE_SOURCE:
            if self._alias:
                ctx.alias_manager.set(self, self._alias)
            ctx.literal(' AS ').sql(Entity(ctx.alias_manager.get(self)))
        return ctx


class _HashableSource(object):
    def __init__(self, *args, **kwargs):
        super(_HashableSource, self).__init__(*args, **kwargs)
        self._update_hash()

    @Node.copy
    def alias(self, name):
        self._alias = name
        self._update_hash()

    def _update_hash(self):
        self._hash = self._get_hash()

    def _get_hash(self):
        return hash((self.__class__, self._path, self._alias))

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        return self._hash == other._hash

    def __ne__(self, other):
        return not (self == other)


class Table(_HashableSource, Source):
    def __init__(self, name, columns=None, primary_key=None, schema=None,
                 alias=None, _model=None):
        self._name = name
        self._columns = columns
        self._schema = schema
        self._path = (schema, name) if schema else (name,)
        self._model = _model
        super(Table, self).__init__(alias=alias)

        # Allow tables to restrict what columns are available.
        if columns is not None:
            self.c = _ExplicitColumn()
            for column in columns:
                setattr(self, column, Column(self, column))

        if primary_key:
            col_src = self if self._columns else self.c
            self.primary_key = getattr(col_src, primary_key)
        else:
            self.primary_key = None

    def _get_hash(self):
        return hash((self.__class__, self._path, self._alias, self._model))

    def select(self, *columns):
        if not columns and self._columns:
            columns = [Column(self, column) for column in self._columns]
        return Select((self,), columns)

    def insert(self, insert=None, columns=None):
        return Insert(self, insert=insert, columns=columns)

    def update(self, update):
        return Update(self, update=update)

    def delete(self):
        return Delete(self)

    def __sql__(self, ctx):
        if ctx.scope == SCOPE_VALUES:
            # Return the quoted table name.
            return ctx.sql(Entity(*self._path))

        if self._alias:
            ctx.alias_manager.set(self, self._alias)

        if ctx.scope == SCOPE_SOURCE:
            # Define the table and its alias.
            return self.apply_alias(ctx.sql(Entity(*self._path)))
        else:
            # Refer to the table using the alias.
            return ctx.sql(Entity(ctx.alias_manager.get(self)))


class Join(Source):
    def __init__(self, lhs, rhs, join_type='INNER', on=None, alias=None):
        super(Join, self).__init__(alias=alias)
        self.lhs = lhs
        self.rhs = rhs
        self.join_type = join_type
        self._on = on

    def on(self, predicate):
        self._on = predicate
        return self

    def __sql__(self, ctx):
        (ctx
         .sql(self.lhs)
         .literal(' %s JOIN ' % self.join_type)
         .sql(self.rhs))
        if self._on is not None:
            ctx.literal(' ON ').sql(self._on)
        return ctx


class CTE(_HashableSource, Source):
    def __init__(self, name, query, recursive=False, columns=None):
        self._alias = name
        self._nested_cte_list = query._cte_list
        query._cte_list = ()
        self._query = query
        self._recursive = recursive
        self._columns = columns
        super(CTE, self).__init__(alias=name)

    def _get_hash(self):
        return hash((self.__class__, self._alias, id(self._query)))

    def __sql__(self, ctx):
        if ctx.scope != SCOPE_CTE:
            return ctx.sql(Entity(self._alias))

        with ctx.push_alias():
            ctx.alias_manager.set(self, self._alias)
            ctx.sql(Entity(self._alias))

            if self._columns:
                ctx.literal(' ').sql(EnclosedNodeList(self._columns))
            ctx.literal(' AS (')
            with ctx.scope_normal():
                ctx.sql(self._query)
            ctx.literal(')')
        return ctx


def build_expression(lhs, op, rhs, flat=False):
    if not isinstance(lhs, Node):
        lhs = BindValue(lhs)
    if not isinstance(rhs, Node):
        rhs = BindValue(rhs)
    return Expression(lhs, op, rhs, flat)


class ColumnBase(Node):
    def alias(self, alias):
        if alias:
            return Alias(self, alias)
        return self

    def unalias(self):
        return self

    def asc(self):
        return Asc(self)
    __pos__ = asc

    def desc(self):
        return Desc(self)
    __neg__ = desc

    def __invert__(self):
        return Negated(self)

    def _e(op, inv=False):
        """
        Lightweight factory which returns a method that builds an Expression
        consisting of the left-hand and right-hand operands, using `op`.
        """
        def inner(self, rhs):
            if inv:
                return build_expression(rhs, op, self)
            return build_expression(self, op, rhs)
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
        op = OP.IS if rhs is None else OP.EQ
        return build_expression(self, op, rhs)
    def __ne__(self, rhs):
        op = OP.IS_NOT if rhs is None else OP.NE
        return build_expression(self, op, rhs)

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
        return build_expression(self, OP.IN, rhs)
    def not_in(self, rhs):
        return build_expression(self, OP.NOT_IN, rhs)
    def is_null(self, is_null=True):
        op = OP.IS if is_null else OP.IS_NOT
        return build_expression(self, op, None)
    def contains(self, rhs):
        return build_expression(self, OP.ILIKE, '%%%s%%' % rhs)
    def startswith(self, rhs):
        return build_expression(self, OP.ILIKE, '%s%%' % rhs)
    def endswith(self, rhs):
        return build_expression(self, OP.ILIKE, '%%%s' % rhs)
    def between(self, lo, hi):
        return build_expression(self, OP.BETWEEN, NodeList((lo, OP.AND, hi)))
    def regexp(self, expression):
        return build_expression(self, OP.REGEXP, expression)
    def concat(self, rhs):
        return build_expression(self, OP.CONCAT, rhs)

    def get_sort_key(self, ctx):
        return ()


class ColumnFactory(object):
    __slots__ = ('node',)

    def __init__(self, node):
        self.node = node

    def __getattr__(self, attr):
        return Column(self.node, attr)


class Column(ColumnBase):
    def __init__(self, source, name):
        self.source = source
        self.name = name

    def get_sort_key(self, ctx):
        if ctx.scope == SCOPE_VALUES:
            return (self.name,)
        else:
            return self.source.get_sort_key(ctx) + (self.name,)

    def __sql__(self, ctx):
        if ctx.scope == SCOPE_VALUES:
            return ctx.sql(Entity(self.name))
        else:
            with ctx.scope_normal():
                return ctx.sql(self.source).literal('.').sql(Entity(self.name))


class WrappedNode(ColumnBase):
    def __init__(self, node):
        self.node = node


class Alias(WrappedNode):
    def __init__(self, node, alias):
        super(Alias, self).__init__(node)
        self._alias = alias

    @Node.copy
    def alias(self, alias):
        self._alias = alias

    def unalias(self):
        return self.node

    def __sql__(self, ctx):
        return (ctx
                .sql(self.node)
                .literal(' AS %s' % self._alias))


class Negated(WrappedNode):
    def __invert__(self):
        return self.node

    def __sql__(self, ctx):
        return ctx.literal('NOT ').sql(self.node)


class BindValue(ColumnBase):
    def __init__(self, value, converter=None):
        self.value = value
        self.converter = converter
        self.multi = isinstance(self.value, (list, tuple))
        if self.multi:
            self.bind_values = []
            for item in self.value:
                if isinstance(item, Node):
                    self.bind_values.append(item)
                else:
                    self.bind_values.append(BindValue(item, self.converter))

    def __sql__(self, ctx):
        if self.multi:
            ctx.sql(EnclosedNodeList(self.bind_values))
        else:
            (ctx
             .literal(ctx.state.param or '?')
             .bind_value(self.value, self.converter))
        return ctx


class Cast(WrappedNode):
    def __init__(self, node, cast):
        super(Cast, self).__init__(node)
        self.cast = cast

    def __sql__(self, ctx):
        return (ctx
                .literal('CAST(')
                .sql(self.node)
                .literal(' AS %s)' % self.cast))


class Ordering(WrappedNode):
    def __init__(self, node, direction, collation=None, nulls=None):
        super(Ordering, self).__init__(node)
        self.direction = direction
        self.collation = collation
        self.nulls = nulls

    def collate(self, collation=None):
        return Ordering(self.node, self.direction, collation)

    def __sql__(self, ctx):
        ctx.sql(self.node).literal(' %s' % self.direction)
        if self.collation:
            ctx.literal(' COLLATE %s' % self.collation)
        if self.nulls:
            ctx.literal(' NULLS %s' % self.nulls)
        return ctx


def Asc(node, collation=None, nulls=None):
    return Ordering(node, 'ASC', collation, nulls)


def Desc(node, collation=None, nulls=None):
    return Ordering(node, 'DESC', collation, nulls)


class Expression(ColumnBase):
    def __init__(self, lhs, op, rhs, flat=False):
        self.lhs = lhs
        self.op = op
        self.rhs = rhs
        self.flat = flat

    def __sql__(self, ctx):
        overrides = {'parentheses': not self.flat}
        if isinstance(self.lhs, Field):
            overrides['converter'] = self.lhs.db_value

        if ctx.state.operations:
            op_sql = ctx.state.operations.get(self.op, self.op)
        else:
            op_sql = self.op

        with ctx(**overrides):
            return (ctx
                    .sql(self.lhs)
                    .literal(' %s ' % op_sql)
                    .sql(self.rhs))


class Entity(ColumnBase):
    def __init__(self, *path):
        self._path = filter(None, path)

    def quoted(self, quote):
        return '.'.join('%s%s%s' % (quote, part, quote)
                        for part in self._path)

    def __getattr__(self, attr):
        return Entity(*self._path + (attr,))

    def get_sort_key(self, ctx):
        return tuple(self._path)

    def __hash__(self):
        return hash((self.__class__.__name__, self._path))

    def __sql__(self, ctx):
        return ctx.literal(self.quoted(ctx.state.quote or '"'))


class SQL(ColumnBase):
    def __init__(self, sql, params=None):
        self.sql = sql
        self.params = params

    def __sql__(self, ctx):
        ctx.literal(self.sql)
        if self.params:
            for param in self.params:
                if isinstance(param, Node):
                    ctx.sql(param)
                else:
                    ctx.bind_value(param)
        return ctx


def Check(constraint):
    return SQL('CHECK (%s)' % constraint)


class Function(ColumnBase):
    def __init__(self, name, arguments, coerce=True):
        self.name = name
        self.arguments = arguments
        if name and name.lower() in ('sum', 'count'):
            self._coerce = False
        else:
            self._coerce = coerce

    def __getattr__(self, attr):
        def decorator(*args):
            return Function(attr, args)
        return decorator

    def over(self, partition_by=None, order_by=None, window=None):
        if isinstance(partition_by, Window) and window is None:
            window = partition_by
        if window is None:
            node = Window(partition_by=partition_by, order_by=order_by)
        else:
            node = SQL(window._alias)
        return NodeList((self, SQL('OVER'), node))

    def coerce(self, coerce=True):
        self._coerce = coerce
        return self

    def __sql__(self, ctx):
        ctx.literal(self.name)
        if not len(self.arguments):
            ctx.literal('()')
        else:
            ctx.sql(EnclosedNodeList([
                (argument if isinstance(argument, Node)
                 else BindValue(argument))
                for argument in self.arguments]))
        return ctx


fn = Function(None, None)


class Window(Node):
    CURRENT_ROW = 'CURRENT ROW'

    def __init__(self, partition_by=None, order_by=None, start=None, end=None,
                 alias=None):
        super(Window, self).__init__()
        self.partition_by = partition_by
        self.order_by = order_by
        self.start = start
        self.end = end
        if self.start is None and self.end is not None:
            raise ValueError('Cannot specify WINDOW end without start.')
        self._alias = alias or 'w'

    def alias(self, alias=None):
        self._alias = alias or 'w'
        return self

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

    def __sql__(self, ctx):
        ctx.literal(self._alias)
        if self.partition_by:
            ctx.literal(' PARTITION BY ')
            ctx.sql(CommaNodeList(self.partition_by))
        if self.order_by:
            ctx.literal(' ORDER BY ')
            ctx.sql(CommaNodeList(self.order_by))
        if self.start is not None and self.end is not None:
            ctx.literal(' RANGE BETWEEN ')
            ctx.sql(self.start)
            ctx.literal(' AND ')
            ctx.sql(self.end)
        elif self.start is not None:
            ctx.literal(' RANGE ')
            ctx.sql(self.start)
        return ctx

    def clone_base(self):
        return Window(self.partition_by, self.order_by)


class NodeList(Node):
    def __init__(self, nodes, glue=' ', parens=False):
        self.nodes = nodes
        self.glue = glue
        self.parens = parens
        if parens and len(self.nodes) == 1:
            if isinstance(self.nodes[0], Expression):
                # Hack to avoid double-parentheses.
                self.nodes[0].flat = True

    def __sql__(self, ctx):
        n_nodes = len(self.nodes)
        if n_nodes == 0:
            return ctx
        with ctx(parentheses=self.parens):
            for i in range(n_nodes - 1):
                ctx.sql(self.nodes[i])
                ctx.literal(self.glue)
            ctx.sql(self.nodes[n_nodes - 1])
        return ctx


def CommaNodeList(nodes):
    return NodeList(nodes, ', ')


def EnclosedNodeList(nodes):
    return NodeList(nodes, ', ', True)


class Window(Node):
    def __init__(self, partition_by=None, order_by=None):
        self.partition_by = partition_by
        self.order_by = order_by

    def __sql__(self, ctx):
        over_clauses = []
        with ctx(parentheses=True):
            if self.partition_by:
                ctx.sql(NodeList((
                    SQL('PARTITION BY '),
                    CommaNodeList(self.partition_by))))
            if self.order_by:
                ctx.sql(NodeList((
                    SQL('ORDER BY '),
                    CommaNodeList(self.order_by))))
            return ctx

# BASE QUERY INTERFACE.

class Query(Node):
    default_row_type = ROW.DICT

    def __init__(self, order_by=None, limit=None, offset=None, **kwargs):
        super(Query, self).__init__(**kwargs)
        self._order_by, self._limit, self._offset = (order_by, limit, offset)
        self._cte_list = None
        self._cursor_wrapper = None
        self._row_type = None
        self._constructor = None

    @Node.copy
    def with_cte(self, *cte_list):
        self._cte_list = cte_list

    def clone(self):
        query = super(Query, self).clone()
        query._cursor_wrapper = None
        return query

    def dicts(self, as_dict=True):
        self._row_type = ROW.DICT if as_dict else None
        return self

    def tuples(self, as_tuple=True):
        self._row_type = ROW.TUPLE if as_tuple else None
        return self

    def namedtuples(self, as_namedtuple=True):
        self._row_type = ROW.NAMED_TUPLE if as_namedtuple else None
        return self

    def objects(self, constructor=None):
        self._row_type = ROW.CONSTRUCTOR if constructor else None
        self._constructor = constructor
        return self

    @Node.copy
    def order_by(self, *values):
        self._order_by = values

    @Node.copy
    def order_by_extend(self, *values):
        self._order_by = ((self._order_by or ()) + values) or None

    @Node.copy
    def limit(self, value=None):
        self._limit = value

    @Node.copy
    def offset(self, value=None):
        self._offset = value

    @Node.copy
    def paginate(self, page, paginate_by=20):
        if page > 0:
            page -= 1
        self._limit = paginate_by
        self._offset = page * paginate_by

    def _apply_ordering(self, ctx):
        if self._order_by:
            (ctx
             .literal(' ORDER BY ')
             .sql(CommaNodeList(self._order_by)))
        if self._limit is not None or (self._offset is not None and
                                       ctx.limit_max):
            ctx.literal(' LIMIT %d' % (self._limit or ctx.limit_max))
        if self._offset is not None:
            ctx.literal(' OFFSET %d' % self._offset)
        return ctx

    def __sql__(self, ctx):
        if self._cte_list:
            # The CTE scope is only used at the very beginning of the query,
            # when we are describing the various CTEs we will be using.
            recursive = any(cte._recursive for cte in self._cte_list)
            with ctx.scope_cte():
                (ctx
                 .literal('WITH RECURSIVE ' if recursive else 'WITH ')
                 .sql(CommaNodeList(self._cte_list))
                 .literal(' '))
        return ctx

    def _get_cursor_wrapper(self, cursor):
        row_type = self._row_type or self.default_row_type

        if row_type == ROW.DICT:
            return DictCursorWrapper(cursor)
        elif row_type == ROW.TUPLE:
            return CursorWrapper(cursor)
        elif row_type == ROW.NAMED_TUPLE:
            return NamedTupleCursorWrapper(cursor)
        elif row_type == ROW.CONSTRUCTOR:
            return ObjectCursorWrapper(cursor, self._constructor)
        else:
            raise ValueError('Unrecognized row type: "%s".' % row_type)

    def execute(self, database):
        raise NotImplementedError

    def iterator(self, database):
        return iter(self.execute(database).iterator())

    def __iter__(self):
        if not self._cursor_wrapper:
            raise ValueError('Query has not been executed.')
        return iter(self._cursor_wrapper)

    def __getitem__(self, value):
        if not self._cursor_wrapper:
            raise ValueError('Query has not been executed.')

        if isinstance(value, slice):
            index = value.stop
        else:
            index = value
        if index is not None and index >= 0:
            index += 1
        self._cursor_wrapper.fill_cache(index)
        return self._cursor_wrapper.row_cache[value]

    def __len__(self):
        if not self._cursor_wrapper:
            raise ValueError('Query has not been executed.')
        return len(self._cursor_wrapper)


class SelectQuery(Query):
    def __add__(self, rhs):
        return CompoundSelectQuery(self, 'UNION ALL', rhs)

    def __or__(self, rhs):
        return CompoundSelectQuery(self, 'UNION', rhs)

    def __and__(self, rhs):
        return CompoundSelectQuery(self, 'INTERSECT', rhs)

    def __sub__(self, rhs):
        return CompoundSelectQuery(self, 'EXCEPT', rhs)

    def cte(self, name, recursive=False, columns=None):
        return CTE(name, self, recursive=recursive, columns=None)


class SelectBase(_HashableSource, Source, SelectQuery):
    def _get_hash(self):
        return hash((self.__class__, self._alias or id(self)))

    def execute(self, database):
        cursor = database.execute(self)
        self._cursor_wrapper = self._get_cursor_wrapper(cursor)
        return self._cursor_wrapper


# QUERY IMPLEMENTATIONS.


class CompoundSelectQuery(SelectBase):
    def __init__(self, lhs, op, rhs):
        super(CompoundSelectQuery, self).__init__()
        self.lhs = lhs
        self.op = op
        self.rhs = rhs

    def _get_query_key(self):
        return (self.lhs.get_query_key(), self.rhs.get_query_key())

    def __sql__(self, ctx):
        parens_around_query = ctx.state.compound_select_parentheses
        with ctx(parentheses=ctx.scope == SCOPE_SOURCE):
            with ctx(parentheses=parens_around_query):
                ctx.sql(self.lhs)
            ctx.literal(' %s ' % self.op)
            with ctx.push_alias():
                with ctx(parentheses=parens_around_query):
                    ctx.sql(self.rhs)

        # Apply ORDER BY, LIMIT, OFFSET.
        self._apply_ordering(ctx)
        return self.apply_alias(ctx)


class Select(SelectBase):
    def __init__(self, from_list=None, columns=None, where=None,
                 group_by=None, having=None, order_by=None, limit=None,
                 offset=None, distinct=None, windows=None, for_update=None):
        super(Select, self).__init__()
        self._from_list = (list(from_list) if isinstance(from_list, tuple)
                           else from_list) or []
        self._columns = columns
        self._where = where
        self._group_by = group_by
        self._having = having
        self._order_by = order_by
        self._limit = limit
        self._offset = offset
        self._windows = None
        self._for_update = 'FOR UPDATE' if for_update is True else for_update

        self._distinct = self._simple_distinct = None
        if distinct:
            if isinstance(distinct, bool):
                self._simple_distinct = distinct
            else:
                self._distinct = distinct

        self._cursor_wrapper = None

    @Node.copy
    def join(self, dest, join_type='INNER', on=None):
        if not self._from_list:
            raise ValueError('No sources to join on.')
        item = self._from_list.pop()
        self._from_list.append(Join(item, dest, join_type, on))

    @Node.copy
    def where(self, *expressions):
        if self._where is not None:
            expressions = (self._where,) + expressions
        self._where = reduce(operator.and_, expressions)

    @Node.copy
    def group_by(self, *columns):
        self._group_by = columns

    @Node.copy
    def group_by_extend(self, *values):
        self._group_by = ((self._group_by or ()) + values) or None

    @Node.copy
    def having(self, *expressions):
        if self._having is not None:
            expressions = (self._having,) + expressions
        self._having = reduce(operator.and_, expressions)

    @Node.copy
    def distinct(self, *columns):
        if len(columns) == 1 and columns[0] is True or columns[0] is False:
            self._simple_distinct = columns[0]
        else:
            self._simple_distinct = False
            self._distinct = columns

    @Node.copy
    def window(self, *windows):
        self._windows = windows if windows else None

    @Node.copy
    def for_update(self, for_update=None):
        self._for_update = 'FOR UPDATE' if for_update is True else for_update

    def _get_query_key(self):
        return self._alias

    def __sql__(self, ctx):
        super(Select, self).__sql__(ctx)
        is_subquery = ctx.subquery
        parentheses = is_subquery or (ctx.scope == SCOPE_SOURCE)

        with ctx.scope_normal(parentheses=parentheses, subquery=True):
            ctx.literal('SELECT ')
            if self._simple_distinct or self._distinct is not None:
                ctx.literal('DISTINCT ')
                if self._distinct:
                    (ctx
                     .literal('ON ')
                     .sql(EnclosedNodeList(self._distinct))
                     .literal(' '))

            with ctx.scope_source():
                ctx.sql(CommaNodeList(self._columns))

            if self._from_list:
                with ctx.scope_source(parentheses=False):
                    ctx.literal(' FROM ').sql(CommaNodeList(self._from_list))

            if self._where is not None:
                ctx.literal(' WHERE ').sql(self._where)

            if self._group_by:
                ctx.literal(' GROUP BY ').sql(CommaNodeList(self._group_by))

            if self._having is not None:
                ctx.literal(' HAVING ').sql(self._having)

            if self._windows is not None:
                ctx.literal(' WINDOW ')
                ctx.sql(CommaNodeList(self._windows))

            # Apply ORDER BY, LIMIT, OFFSET.
            self._apply_ordering(ctx)

            if self._for_update and ctx.db_for_update:
                ctx.literal(' ')
                ctx.sql(SQL(self._for_update))

        ctx = self.apply_alias(ctx)
        return ctx


class _WriteQuery(Query):
    def __init__(self, table):
        self.table = table
        self._returning = None
        super(_WriteQuery, self).__init__()

    @Node.copy
    def returning(self, *returning):
        self._returning = returning

    def apply_returning(self, ctx):
        if self._returning:
            ctx.literal(' RETURNING ').sql(CommaNodeList(self._returning))
        return ctx

    def execute(self, database):
        if self._returning:
            return self.execute_returning(database)
        else:
            cursor = database.execute(self)
            return self.handle_result(database, cursor)

    def execute_returning(self, database):
        if self._cursor_wrapper is None:
            cursor = database.execute(self)
            self._cursor_wrapper = self._get_cursor_wrapper(cursor)
        return self._cursor_wrapper

    def handle_result(self, database, cursor):
        return database.rows_affected(cursor)


class Update(_WriteQuery):
    def __init__(self, table, update=None, where=None, order_by=None,
                 limit=None, offset=None, on_conflict=None):
        self._update = update
        self._where = where
        self._order_by = order_by
        self._limit = limit
        self._offset = offset
        self._on_conflict = on_conflict
        super(Update, self).__init__(table)

    @Node.copy
    def where(self, *expressions):
        if self._where is not None:
            expressions = (self._where,) + expressions
        self._where = reduce(operator.and_, expressions)

    @Node.copy
    def on_conflict(self, on_conflict):
        self._on_conflict = on_conflict

    def __sql__(self, ctx):
        super(Update, self).__sql__(ctx)

        with ctx.scope_values(subquery=True):
            ctx.literal('UPDATE ')
            if self._on_conflict:
                ctx.literal('OR %s ' % self._on_conflict)

            update = sorted(self._update.items(), key=ctx.column_sort_key)

            (ctx
             .sql(self.table)
             .literal(' SET ')
             .sql(CommaNodeList([
                 NodeList((key, SQL('='), value))
                 for key, value in update])))

            if self._where:
                ctx.literal(' WHERE ').sql(self._where)
            self._apply_ordering(ctx)
            return self.apply_returning(ctx)


class Insert(_WriteQuery):
    class DefaultValuesException(Exception): pass

    def __init__(self, table, insert=None, columns=None, on_conflict=None,
                 returning=None):
        super(Insert, self).__init__(table)
        self._insert = insert
        self._columns = columns
        self._on_conflict = on_conflict
        self._returning = returning

    @Node.copy
    def on_conflict(self, on_conflict):
        self._on_conflict = on_conflict

    def _simple_insert(self, ctx):
        columns = []
        values = []
        for key, value in sorted(self._insert.items(), key=ctx.column_sort_key):
            columns.append(key)
            if not isinstance(value, Node):
                converter = key.db_value if isinstance(key, Field) else None
                value = BindValue(value, converter=converter)
            values.append(value)
        return (ctx
                .sql(EnclosedNodeList(columns))
                .literal(' VALUES ')
                .sql(EnclosedNodeList(values)))

    def _multi_insert(self, ctx):
        rows_iter = iter(self._insert)
        columns = self._columns
        if not columns:
            try:
                row = next(rows_iter)
            except StopIteration:
                raise DefaultValuesException()
            columns = sorted(row.keys(), key=lambda obj: obj.get_sort_key(ctx))
            rows_iter = itertools.chain(iter((row,)), rows_iter)

        ctx.sql(EnclosedNodeList(columns)).literal(' VALUES ')
        columns_converters = [
            (column, column.db_value if isinstance(column, Field) else None)
            for column in columns]

        all_values = []
        for row in rows_iter:
            values = []
            for column, converter in columns_converters:
                value = row[column]
                if not isinstance(value, Node):
                    value = BindValue(value, converter=converter)
                values.append(value)

            all_values.append(EnclosedNodeList(values))

        return ctx.sql(CommaNodeList(all_values))

    def _query_insert(self, ctx):
        return (ctx
                .sql(EnclosedNodeList(self._columns))
                .literal(' ')
                .sql(self._insert))

    def __sql__(self, ctx):
        super(Insert, self).__sql__(ctx)
        with ctx.scope_values():
            ctx.literal('INSERT ')
            if self._on_conflict:
                ctx.literal('OR %s ' % self._on_conflict)
            ctx.literal('INTO ').sql(self.table).literal(' ')

            if isinstance(self._insert, dict) and not self._columns:
                self._simple_insert(ctx)
            elif isinstance(self._insert, SelectQuery):
                self._query_insert(ctx)
            else:
                self._multi_insert(ctx)

            return self.apply_returning(ctx)

    def execute(self, database):
        if not self._columns and database.options.returning_clause:
            self._columns = (self.table.primary_key,)
        return super(Insert, self).execute(database)

    def handle_result(self, database, cursor):
        return database.last_insert_id(cursor)


class Delete(_WriteQuery):
    def __init__(self, table, where=None, order_by=None, limit=None,
                 offset=None, returning=None):
        self._where = where
        self._order_by = order_by
        self._limit = limit
        self._offset = offset
        self._returning = returning
        super(Delete, self).__init__(table)

    @Node.copy
    def where(self, *expressions):
        if self._where is not None:
            expressions = (self._where,) + expressions
        self._where = reduce(operator.and_, expressions)

    def __sql__(self, ctx):
        super(Delete, self).__sql__(ctx)

        with ctx.scope_values(subquery=True):
            (ctx
             .literal('DELETE FROM ')
             .sql(self.table))

            if self._where is not None:
                ctx.literal(' WHERE ').sql(self._where)

            self._apply_ordering(ctx)
            return self.apply_returning(ctx)


# DB-API 2.0 EXCEPTIONS.


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
    __slots__ = ('exceptions',)
    def __init__(self, exceptions):
        self.exceptions = exceptions
    def __enter__(self): pass
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            return
        if exc_type.__name__ in self.exceptions:
            new_type = self.exceptions[exc_type.__name__]
            exc_args = exc_value if PY26 else exc_value.args
            reraise(new_type, new_type(*exc_args), traceback)

EXCEPTIONS = {
    'ConstraintError': IntegrityError,
    'DatabaseError': DatabaseError,
    'DataError': DataError,
    'IntegrityError': IntegrityError,
    'InterfaceError': InterfaceError,
    'InternalError': InternalError,
    'NotSupportedError': NotSupportedError,
    'OperationalError': OperationalError,
    'ProgrammingError': ProgrammingError}

__exception_wrapper__ = ExceptionWrapper(EXCEPTIONS)


# DATABASE INTERFACE AND CONNECTION MANAGEMENT.


IndexMetadata = namedtuple(
    'IndexMetadata',
    ('name', 'sql', 'columns', 'unique', 'table'))
ColumnMetadata = namedtuple(
    'ColumnMetadata',
    ('name', 'data_type', 'null', 'primary_key', 'table'))
ForeignKeyMetadata = namedtuple(
    'ForeignKeyMetadata',
    ('column', 'dest_table', 'dest_column', 'table'))


class _ConnectionState(object):
    def __init__(self, **kwargs):
        super(_ConnectionState, self).__init__(**kwargs)
        self.closed = True
        self.conn = None
        self.transactions = []

    def reset(self):
        self.transactions = []
        if not self.closed:
            self.conn.close()
            self.closed = True
            return True
        return False

    def set_connection(self, conn):
        self.conn = conn
        self.closed = False


class _ConnectionLocal(_ConnectionState, threading.local): pass
class _NoopLock(object):
    __slots__ = ()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): pass


class Database(_callable_context_manager):
    context_class = Context
    options = attrdict(
        # Base options.
        field_types={},
        operations={},
        param='?',
        quote='"',

        # Feature toggles.
        compound_operations=['UNION', 'INTERSECT', 'EXCEPT', 'UNION ALL'],
        compound_select_parentheses=False,
        distinct_on=False,
        drop_cascade=False,
        for_update=False,
        for_update_nowait=False,
        insert_many=True,
        limit_max=None,
        returning_clause=False,
        sequences=False,
        subquery_delete_same_table=True,
        window_functions=False,
    )

    commit_select = False
    reserved_tables = []

    def __init__(self, database, thread_safe=True, **kwargs):
        self.thread_safe = thread_safe
        if thread_safe:
            self._state = _ConnectionLocal()
            self._lock = threading.Lock()
        else:
            self._state = _ConnectionState()
            self._lock = _NoopLock()

        self.connect_params = {}
        self.init(database, **kwargs)

    def init(self, database, **kwargs):
        if not self.is_closed():
            self.close()
        self.database = database
        self.connect_params.update(kwargs)
        self.deferred = not bool(database)

        self.options.field_types = merge_dict(FIELD, self.options.field_types)
        self.options.operations = merge_dict(OP, self.options.operations)

    def __enter__(self):
        self.connect()
        self.transaction().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        top = self._state.transactions[-1]
        try:
            top.__exit__(exc_type, exc_val, exc_tb)
        finally:
            if not self.is_closed():
                self.close()

    def _connect(self):
        raise NotImplementedError

    def connect(self, reuse_if_open=False):
        with self._lock:
            if self.deferred:
                raise Exception('Error, database must be initialized before '
                                'opening a connection.')
            if reuse_if_open and not self.is_closed():
                return False

            self._state.reset()
            self._state.set_connection(self._connect())
            self._initialize_connection(self._state.conn)
        return True

    def _initialize_connection(self, conn):
        pass

    def close(self):
        with self._lock:
            if self.deferred:
                raise Exception('Error, database must be initialized before '
                                'opening a connection.')
            return self._state.reset()

    def is_closed(self):
        return self._state.closed

    def connection(self):
        if self.is_closed():
            self.connect()
        return self._state.conn

    def cursor(self):
        if self.is_closed():
            self.connect()
        return self._state.conn.cursor()

    def execute_sql(self, sql, params=None):
        with __exception_wrapper__:
            cursor = self.cursor()
            cursor.execute(sql, params or ())
            if self.commit_select or not sql.startswith('SELECT') and \
               not self.in_transaction():
                self.commit()
        return cursor

    def execute(self, query, **context_options):
        ctx = self.get_sql_context(context_options)
        sql, params = ctx.sql(query).query()
        return self.execute_sql(sql, params)

    def get_sql_context(self, context_options=None):
        if context_options:
            options = self.options.copy()
            options.update(context_options)
        else:
            options = self.options
        return self.context_class(**options)

    def last_insert_id(self, cursor):
        return cursor.lastrowid

    def rows_affected(self, cursor):
        return cursor.rowcount

    def in_transaction(self):
        return bool(self._state.transactions)

    def push_transaction(self, transaction):
        self._state.transactions.append(transaction)

    def pop_transaction(self):
        self._state.transactions.pop()

    def transaction_depth(self):
        return len(self._state.transactions)

    def atomic(self):
        return _atomic(self)

    def transaction(self):
        return _transaction(self)

    def savepoint(self):
        return _savepoint(self)

    def begin(self):
        pass

    def commit(self):
        return self._state.conn.commit()

    def rollback(self):
        return self._state.conn.rollback()

    def table_exists(self, table, schema=None):
        return table._name in self.get_tables(schema=schema)

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


class SqliteDatabase(Database):
    options = Database.options + attrdict(
        field_types={
            FIELD.BIGINT: FIELD.INT,
            FIELD.BOOL: FIELD.INT,
            FIELD.DOUBLE: FIELD.FLOAT,
            FIELD.SMALLINT: FIELD.INT,
            FIELD.UUID: FIELD.TEXT},
        operations={
            OP.LIKE: 'GLOB',
            OP.ILIKE: 'LIKE'},
        insert_many=sqlite3 and sqlite3.sqlite_version_info >= (3, 7, 11),
        limit_max=-1)

    def init(self, database, pragmas=None, timeout=5, **kwargs):
        self._pragmas = pragmas or ()
        self._timeout = timeout
        super(SqliteDatabase, self).init(database, **kwargs)

    def _connect(self):
        conn = sqlite3.connect(self.database, timeout=self._timeout,
                               **self.connect_params)
        conn.isolation_level = None
        try:
            self._add_conn_hooks(conn)
        except:
            conn.close()
            raise
        return conn

    def _add_conn_hooks(self, conn):
        self._set_pragmas(conn)

    def _set_pragmas(self, conn):
        if self._pragmas:
            cursor = conn.cursor()
            for pragma, value in self._pragmas:
                cursor.execute('PRAGMA %s = %s;' % (pragma, value))
            cursor.close()

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, seconds):
        if self._timeout == seconds:
            return

        self._timeout = seconds
        if not self.is_closed():
            self.execute_sql('PRAGMA busy_timeout=%d;' % (seconds * 1000))

    def savepoint(self):
        return _savepoint_sqlite(self)

    def get_tables(self, schema=None):
        cursor = self.execute_sql('SELECT name FROM sqlite_master WHERE '
                                  'type = ? ORDER BY name;', ('table',))
        return map(operator.itemgetter(0), cursor.fetchall())

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
        return map(operator.itemgetter(1),
                   filter(lambda row: row[-1], cursor.fetchall()))

    def get_foreign_keys(self, table, schema=None):
        cursor = self.execute_sql('PRAGMA foreign_key_list("%s")' % table)
        return [ForeignKeyMetadata(row[3], row[2], row[4], table)
                for row in cursor.fetchall()]


class PostgresqlDatabase(Database):
    options = Database.options + attrdict(
        field_types={
            FIELD.AUTO: 'SERIAL',
            FIELD.BLOB: 'BYTEA',
            FIELD.BOOL: 'BOOLEAN',
            FIELD.DATETIME: 'TIMESTAMP',
            FIELD.DECIMAL: 'NUMERIC',
            FIELD.DOUBLE: 'DOUBLE PRECISION',
            FIELD.UUID: 'UUID',
        },
        operations={OP.REGEXP: '~'},
        param='%s',

        compound_select_parentheses=True,
        distinct_on=True,
        drop_cascade=True,
        for_update=True,
        for_update_nowait=True,
        returning_clause=True,
        sequences=True,
        window_functions=True)

    commit_select = True

    def init(self, database, register_unicode=True, **kwargs):
        self._register_unicode = register_unicode
        super(SqliteDatabase, self).init(database, **kwargs)

    def _connect(self):
        conn = psycopg2.connect(database=self.database, **self.connect_params)
        if self._register_unicode:
            pg_extensions.register_type(pg_extensions.UNICODE, conn)
            pg_extensions.register_type(pg_extensions.UNICODEARRAY, conn)
        if encoding:
            conn.set_client_encoding(encoding)
        return conn

    def last_insert_id(self, cursor):
        return cursor.fetchone()[0]

    def get_tables(self, schema=None):
        query = ('SELECT tablename FROM pg_catalog.pg_tables '
                 'WHERE schemaname = %s ORDER BY tablename')
        cursor = self.execute_sql(query, (schema or 'public',))
        return map(operator.itemgetter(0), cursor.fetchall())

    def get_indexes(self, table, schema=None):
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
        cursor = self.execute_sql(query, (table, 'r', schema or 'public'))
        return [IndexMetadata(row[0], row[1], row[3].split(','), row[2], table)
                for row in cursor.fetchall()]

    def get_columns(self, table, schema=None):
        query = """
            SELECT column_name, is_nullable, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = %s
            ORDER BY ordinal_position"""
        cursor = self.execute_sql(query, (table, schema or 'public'))
        pks = set(self.get_primary_keys(table, schema))
        return [ColumnMetadata(name, dt, null == 'YES', name in pks, table)
                for name, null, dt in cursor.fetchall()]

    def get_primary_keys(self, table, schema=None):
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
        ctype = 'PRIMARY KEY'
        cursor = self.execute_sql(query, (ctype, table, schema or 'public'))
        return map(operator.itemgetter(0), cursor.fetchall())

    def get_foreign_keys(self, table, schema=None):
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
        cursor = self.execute_sql(sql, (table, schema or 'public'))
        return [ForeignKeyMetadata(row[0], row[1], row[2], table)
                for row in cursor.fetchall()]

    def sequence_exists(self, sequence):
        res = self.execute_sql("""
            SELECT COUNT(*) FROM pg_class, pg_namespace
            WHERE relkind='S'
                AND pg_class.relnamespace = pg_namespace.oid
                AND relname=%s""", (sequence,))
        return bool(res.fetchone()[0])


class MySQLDatabase(Database):
    options = Database.options + attrdict(
        field_types={
            FIELD.AUTO: 'INTEGER AUTO_INCREMENT',
            FIELD.BOOL: 'BOOL',
            FIELD.DECIMAL: 'NUMERIC',
            FIELD.DOUBLE: 'DOUBLE PRECISION',
            FIELD.FLOAT: 'FLOAT',
            FIELD.UUID: 'VARCHAR(40)',
        },
        operations={
            OP.LIKE: 'LIKE BINARY',
            OP.ILIKE: 'LIKE',
            OP.XOR: 'XOR',
        },
        param='%s',
        quote='`',

        compound_operations=['UNION', 'UNION ALL'],
        for_update=True,
        limit_max=2 ** 64 - 1,
        subquery_delete_same_table=False)

    commit_select = True

    def init(self, database, **kwargs):
        params = {'charset': 'utf8', 'use_unicode': True}
        params.update(kwargs)
        if 'password' in params:
            params['passwd'] = params.pop('password')
        super(MySQLDatabase, self).init(database, **params)

    def _connect(self):
        return mysql.connect(db=self.database, **self.connect_params)

    def get_tables(self, schema=None):
        return map(operator.itemgetter(0), self.execute_sql('SHOW TABLES'))

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
        return map(operator.itemgetter(4),
                   filter(lambda row: row[2] == 'PRIMARY', cursor.fetchall()))

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


# TRANSACTION CONTROL.


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


class _transaction(_callable_context_manager):
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
            self.db.pop_transaction()


class _savepoint(_callable_context_manager):
    def __init__(self, db, sid=None):
        self.db = db
        self.sid = sid or 's' + uuid.uuid4().hex
        self.quoted_sid = '"%s"' % self.sid

    def commit(self):
        self.db.execute_sql('RELEASE SAVEPOINT %s;' % self.quoted_sid)

    def rollback(self):
        self.db.execute_sql('ROLLBACK TO SAVEPOINT %s;' % self.quoted_sid)

    def __enter__(self):
        self.db.execute_sql('SAVEPOINT %s;' % self.quoted_sid)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            try:
                self.commit()
            except:
                self.rollback()
                raise


class _savepoint_sqlite(_callable_context_manager):
    def __enter__(self):
        self._conn = self.db.connection()

        # For sqlite, the connection's isolation_level *must* be set to None.
        # The act of setting it, though, will break any existing savepoints,
        # so only write to it if necessary.
        if self._conn.isolation_level is not None:
            self._orig_isolation_level = self._conn.isolation_level
            self._conn.isolation_level = None
        else:
            self._orig_isolation_level = None
        return super(_savepoint_sqlite, self).__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super(_savepoint_sqlite, self).__exit__(
                exc_type, exc_val, exc_tb)
        finally:
            if self._orig_isolation_level is not None:
                self._conn.isolation_level = self._orig_isolation_level


# CURSOR REPRESENTATIONS.


class CursorWrapper(object):
    def __init__(self, cursor):
        self.cursor = cursor
        self.count = 0
        self.index = 0
        self.initialized = False
        self.populated = False
        self.row_cache = []

    def __iter__(self):
        if self.populated:
            return iter(self.row_cache)
        return ResultIterator(self)

    def __getitem__(self, item):
        if isinstance(item, slice):
            # TODO: getslice
            start = item.start
            stop = item.stop
            if stop is None or stop < 0:
                self.fill_cache()
            else:
                self.fill_cache(stop)
            return self.row_cache[item]
        elif isinstance(item, int):
            self.fill_cache(item if item > 0 else 0)
            return self.row_cache[item]
        else:
            raise ValueError('CursorWrapper only supports integer and slice '
                             'indexes.')

    def initialize(self):
        pass

    def iterate(self, cache=True):
        row = self.cursor.fetchone()
        if row is None:
            self.populated = True
            self.cursor.close()
            raise StopIteration
        elif not self.initialized:
            self.initialize()  # Lazy initialization.
            self.initialized = True
        self.count += 1
        result = self.process_row(row)
        if cache:
            self.row_cache.append(result)
        return result

    def process_row(self, row):
        return row

    def iterator(self):
        """Efficient one-pass iteration over the result set."""
        while True:
            yield self.iterate(False)

    def fill_cache(self, n=0.):
        n = n or float('Inf')
        if n < 0:
            raise ValueError('Negative values are not supported.')

        iterator = ResultIterator(self)
        iterator.index = self.count
        while not self.populated and (n > self.count):
            try:
                iterator.next()
            except StopIteration:
                break


class DictCursorWrapper(CursorWrapper):
    def _initialize_columns(self):
        description = self.cursor.description
        self.columns = [t[0][t[0].find('.') + 1:]
                        for t in description]
        self.ncols = len(description)

    initialize = _initialize_columns

    def _row_to_dict(self, row):
        result = {}
        for i in range(self.ncols):
            result[self.columns[i]] = row[i]
        return result

    process_row = _row_to_dict


class NamedTupleCursorWrapper(CursorWrapper):
    def initialize(self):
        description = self.cursor.description
        self.tuple_class = namedtuple(
            'Row',
            [col[0][col[0].find('.') + 1:].strip('"') for col in description])

    def process_row(self, row):
        return self.tuple_class(*row)


class ObjectCursorWrapper(DictCursorWrapper):
    def __init__(self, cursor, constructor):
        super(ObjectCursorWrapper, self).__init__(cursor)
        self.constructor = constructor

    def process_row(self, row):
        row_dict = self._row_to_dict(row)
        return self.constructor(**row_dict)


class ResultIterator(object):
    def __init__(self, cursor_wrapper):
        self.cursor_wrapper = cursor_wrapper
        self.index = 0

    def __iter__(self):
        return self

    def next(self):
        if self.index < self.cursor_wrapper.count:
            obj = self.cursor_wrapper.row_cache[self.index]
        elif not self.cursor_wrapper.populated:
            self.cursor_wrapper.iterate()
            obj = self.cursor_wrapper.row_cache[self.index]
        else:
            raise StopIteration
        self.index += 1
        return obj

    __next__ = next


# FIELDS


class FieldAccessor(object):
    def __init__(self, model, field, name):
        self.model = model
        self.field = field
        self.name = name

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return instance.__data__.get(self.name)
        return self.field

    def __set__(self, instance, value):
        instance.__data__[self.name] = value


class ForeignKeyAccessor(FieldAccessor):
    def __init__(self, model, field, name):
        super(ForeignKeyAccessor, self).__init__(model, field, name)
        self.rel_model = field.rel_model

    def get_rel_instance(self, instance):
        value = instance.__data__.get(self.name)
        if value is not None or self.name in instance.__rel__:
            if self.name not in instance.__rel__:
                obj = self.rel_model.get(self.field.rel_field == value)
                instance.__rel__[self.name] = obj
            return instance.__rel__[self.name]
        elif not self.field.null:
            raise self.rel_model.DoesNotExist
        return value

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return self.get_rel_instance(instance)
        return self.field

    def __set__(self, instance, obj):
        if isinstance(obj, self.rel_model):
            instance.__data__[self.name] = getattr(obj, self.field.rel_field.name)
            instance.__rel__[self.name] = obj
        else:
            fk_value = instance.__data__.get(self.name)
            instance.__data__[self.name] = obj
            if obj != fk_value and self.name in instance.__rel__:
                del instance.__rel__[self.name]


class BackrefAccessor(object):
    def __init__(self, field):
        self.field = field
        self.model = field.model

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            dest = self.field.rel_field.name
            return (self.model
                    .select()
                    .where(self.field == getattr(instance, dest)))
        return self


class ObjectIdAccessor(object):
    """Gives direct access to the underlying id"""
    def __init__(self, field):
        self.name = field.name

    def __get__(self, instance, instance_type=None):
        if instance is not None:
            return instance.__data__.get(self.name)


class Field(ColumnBase):
    _field_counter = 0
    _order = 0
    accessor_class = FieldAccessor
    field_type = 'DEFAULT'

    def __init__(self, null=False, index=False, unique=False, column_name=None,
                 default=None, primary_key=False, constraints=None,
                 sequence=None, collation=None, unindexed=False):
        self.null = null
        self.index = index
        self.unique = unique
        self.column_name = column_name
        self.default = default
        self.primary_key = primary_key
        self.constraints = constraints  # List of column constraints.
        self.sequence = sequence  # Name of sequence, e.g. foo_id_seq.
        self.collation = collation
        self.unindexed = unindexed

        # Used internally for recovering the order in which Fields were defined
        # on the Model class.
        Field._field_counter += 1
        self._order = Field._field_counter
        self._sort_key = (self.primary_key and 1 or 2), self._order

    def __hash__(self):
        return hash(self.name + '.' + self.model.__name__)

    def bind(self, model, name, set_attribute=True):
        self.model = model
        self.name = name
        self.column_name = self.column_name or name
        if set_attribute:
            setattr(model, name, self.accessor_class(model, self, name))

    @property
    def column(self):
        return Column(self.model._meta.table, self.column_name)

    def coerce(self, value):
        return value

    def db_value(self, value):
        return value if value is None else self.coerce(value)

    def python_value(self, value):
        return value if value is None else self.coerce(value)

    def get_sort_key(self, ctx):
        return self._sort_key

    def __sql__(self, ctx):
        return ctx.sql(self.column)

    def get_modifiers(self):
        return

    def ddl_datatype(self, ctx):
        if ctx.state.field_types:
            column_type = ctx.state.field_types.get(self.field_type,
                                                    self.field_type)
        else:
            column_type = self.field_type

        modifiers = self.get_modifiers()
        if column_type and modifiers:
            modifier_literal = ', '.join(map(str, modifiers))
            return SQL('%s(%s)' % (column_type, modifier_literal))
        else:
            return SQL(column_type)

    def ddl(self, ctx):
        accum = [self.column, self.ddl_datatype(ctx)]
        if self.unindexed:
            accum.append(SQL('UNINDEXED'))
        if not self.null:
            accum.append(SQL('NOT NULL'))
        if self.primary_key:
            accum.append(SQL('PRIMARY KEY'))
        if self.constraints:
            accum.extend(constraints)
        if self.collation:
            accum.append(SQL('COLLATE %s' % self.collation))
        return NodeList(accum)


class IntegerField(Field):
    field_type = 'INT'
    coerce = int


class BigIntegerField(IntegerField):
    field_type = 'BIGINT'


class SmallIntegerField(IntegerField):
    field_type = 'SMALLINT'


class AutoField(IntegerField):
    field_type = 'AUTO'

    def __init__(self, *args, **kwargs):
        if kwargs.get('primary_key') is False:
            raise ValueError('AutoField must always be a primary key.')
        kwargs['primary_key'] = True
        super(AutoField, self).__init__(*args, **kwargs)


class FloatField(Field):
    field_type = 'FLOAT'
    coerce = float


class DoubleField(FloatField):
    field_type = 'DOUBLE'


class DecimalField(Field):
    field_type = 'DECIMAL'

    def __init__(self, max_digits=10, decimal_places=5, auto_round=False,
                 rounding=None, *args, **kwargs):
        self.max_digits = max_digits
        self.decimal_places = decimal_places
        self.auto_round = auto_round
        self.rounding = rounding or decimal.DefaultContext.rounding
        super(DecimalField, self).__init__(*args, **kwargs)

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


class _StringField(Field):
    def coerce(self, value):
        if isinstance(value, text_type):
            return value
        elif isinstance(value, bytes_type):
            return value.decode('utf-8')
        return text_type(value)


class CharField(_StringField):
    field_type = 'VARCHAR'

    def __init__(self, max_length=255, *args, **kwargs):
        self.max_length = max_length
        super(CharField, self).__init__(*args, **kwargs)

    def get_modifiers(self):
        return self.max_length and [self.max_length] or None


class FixedCharField(CharField):
    field_type = 'CHAR'

    def python_value(self, value):
        value = super(FixedCharField, self).python_value(value)
        if value:
            value = value.strip()
        return value


class TextField(_StringField):
    field_type = 'TEXT'


class BlobField(Field):
    field_type = 'BLOB'

    def bind(self, model, name, set_attribute=True):
        self._constructor = model._meta.database.get_binary_type()
        return super(BlobField, self).bind(model, name, set_attribute)

    def db_value(self, value):
        if isinstance(value, text_type):
            value = value.encode('raw_unicode_escape')
        if isinstance(value, bytes_type):
            return self._constructor(value)
        return value


class UUIDField(Field):
    field_type = 'UUID'

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
        return self.model._meta.database.extract_date(date_part, self)
    return dec


class _BaseFormattedField(Field):
    formats = None

    def __init__(self, formats=None, *args, **kwargs):
        if formats is not None:
            self.formats = formats
        super(_BaseFormattedField, self).__init__(*args, **kwargs)


class DateTimeField(_BaseFormattedField):
    field_type = 'DATETIME'
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
    field_type = 'DATE'
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
    field_type = 'TIME'
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
    field_type = 'BOOL'
    coerce = bool


class ForeignKeyField(Field):
    accessor_class = ForeignKeyAccessor

    def __init__(self, model, field=None, backref=None, on_delete=None,
                 on_update=None, *args, **kwargs):
        super(ForeignKeyField, self).__init__(*args, **kwargs)
        self.rel_model = model
        self.rel_field = field
        self.backref = backref
        self.on_delete = on_delete
        self.on_update = on_update

    @property
    def field_type(self):
        if not isinstance(self.rel_field, AutoField):
            return self.rel_field.field_type
        return AutoField.field_type

    def get_modifiers(self):
        if not isinstance(self.rel_field, AutoField):
            return self.rel_field.get_modifiers()
        return super(ForeignKeyField, self).get_modifiers()

    def coerce(self, value):
        return self.rel_field.coerce(value)

    def db_value(self, value):
        if isinstance(value, self.rel_model):
            value = value._get_pk_value()
        return self.rel_field.db_value(value)

    def python_value(self, value):
        if isinstance(value, self.rel_model):
            return value
        return self.rel_field.python_value(value)

    def expression(self):
        return self.column == self.rel_field.column

    def bind(self, model, name, set_attribute=True):
        self.column_name = self.column_name or name
        if self.column_name == name and not name.endswith('_id'):
            self.column_name += '_id'
        if self.rel_model == 'self':
            self.rel_model = model
        if isinstance(self.rel_field, basestring):
            self.rel_field = getattr(self.rel_model, self.rel_field)
        elif self.rel_field is None:
            self.rel_field = self.rel_model._meta.primary_key

        if not self.backref:
            self.backref = '%s_set' % self.rel_model._meta.name

        super(ForeignKeyField, self).bind(model, name, set_attribute)
        if set_attribute:
            setattr(model, name + '_id', ObjectIdAccessor(self))
            setattr(self.rel_model, self.backref, BackrefAccessor(self))

    def foreign_key_constraint(self):
        return NodeList((
            SQL('FOREIGN KEY'),
            EnclosedNodeList((self,)),
            SQL('REFERENCES'),
            self.rel_model,
            EnclosedNodeList((self.rel_field,))))


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


# MODELS


class SchemaManager(object):
    def __init__(self, model, database=None, **context_options):
        self.model = model
        self._database = database
        context_options.setdefault('scope', SCOPE_VALUES)
        self.context_options = context_options

    @property
    def database(self):
        return self._database or self.model._meta.database

    @database.setter
    def database(self, value):
        self._database = value

    def _create_context(self):
        return self.database.get_sql_context(self.context_options)

    def _create_table(self, safe=True, **options):
        ctx = self._create_context()
        ctx.literal('CREATE TABLE ')
        if safe:
            ctx.literal('IF NOT EXISTS ')
        ctx.sql(self.model).literal(' ')

        columns = []
        constraints = []
        extra = []
        for field in self.model._meta.sorted_fields:
            columns.append(field.ddl(ctx))
            if isinstance(field, ForeignKeyField):
                constraints.append(field.foreign_key_constraint())

        meta_options = getattr(self.model._meta, 'options', None) or {}
        if meta_options or options:
            meta_options.update(options or {})
            for key, value in sorted(meta_options.items()):
                if isinstance(value, Node):
                    value = value
                elif is_model(value):
                    value = value._meta.table
                else:
                    value = SQL(value)

                extra.append(Clause((SQL(key), extra), glue='='))

        ctx.sql(EnclosedNodeList(columns + constraints + extra))
        return ctx

    def create_table(self, safe=True, **options):
        self.database.execute(self._create_table(safe=safe, **options))

    def _drop_table(self, safe=True):
        ctx = self._create_context()
        return (ctx
                .literal('DROP TABLE IF EXISTS ' if safe else 'DROP TABLE ')
                .sql(self.model))

    def drop_table(self, safe=True):
        self.database.execute(self._drop_table(safe=safe))

    def index_entity(self, fields):
        index_name = '%s_%s' % (
            self.model._meta.name,
            '_'.join([field.name for field in fields]))

        if len(index_name) > 64:
            index_hash = hashlib.md5(index_name.encode('utf-8')).hexdigest()
            index_name = '%s_%s' % (index_name[:56], index_hash[:7])

        return Entity(self.model._meta.schema, index_name)

    def _create_indexes(self, safe=True):
        return [self._create_index(nodes, unique, safe)
                for (nodes, unique) in self.model._meta.fields_to_index()]

    def _create_index(self, fields, unique=False, safe=True):
        ctx = self._create_context()
        ctx.literal('CREATE UNIQUE INDEX ' if unique else 'CREATE INDEX ')
        if safe:
            ctx.literal('IF NOT EXISTS ')

        return (ctx
                .sql(self.index_entity(fields))
                .literal(' ON ')
                .sql(self.model)
                .literal(' ')
                .sql(EnclosedNodeList(fields)))

    def create_indexes(self, safe=True):
        for query in self._create_indexes(safe=safe):
            self.database.execute(query)

    def _drop_indexes(self, safe=True):
        return [self._drop_index(nodes, safe)
                for (nodes, _) in self.model._meta.fields_to_index()]

    def _drop_index(self, fields, safe):
        return (self
                ._create_context()
                .literal('DROP INDEX IF NOT EXISTS ' if safe else
                         'DROP INDEX ')
                .sql(self.index_entity(fields)))

    def drop_indexes(self, safe=True):
        for query in self._drop_indexes(safe=safe):
            self.database.execute(query)

    def _check_sequences(self, field):
        if not field.sequence or not self.database.options.sequences:
            raise ValueError('Sequences are either not supported, or are not '
                             'defined for "%s".' % field.name)

    def _create_sequence(self, field):
        self._check_sequences(field)
        if not self.database.sequence_exists(field.sequence):
            return (self
                    ._create_context()
                    .literal('CREATE SEQUENCE ')
                    .sql(Entity(field.sequence)))

    def create_sequence(self, field):
        self.database.execute(self._create_sequence(field))

    def _drop_sequence(self, field):
        self._check_sequences(field)
        if self.database.sequence_exists(field.sequence):
            return (self
                    ._create_context()
                    .literal('DROP SEQUENCE ')
                    .sql(Entity(field.sequence)))

    def drop_sequence(self, field):
        self.database.execute(self._drop_sequence(field))

    def create_all(self, safe=True, **table_options):
        if self.database.options.sequences:
            for field in self.model._meta.sorted_fields:
                if field and field.sequence:
                    self.create_sequence(field)

        self.create_table(safe, **table_options)
        self.create_indexes(safe=safe)

    def drop_all(self, safe=True):
        self.drop_table(safe)
        self.drop_indexes(safe)


class ModelMetadata(object):
    def __init__(self, model, database=None, table_name=None, indexes=None,
                 primary_key=None, constraints=None, schema=None,
                 only_save_dirty=False, **kwargs):
        self.model = model
        self.database = database

        self.fields = {}
        self.columns = {}
        self.combined = {}

        self._sorted_field_list = _SortedFieldList()
        self.sorted_fields = []
        self.sorted_field_names = []

        self.defaults = {}
        self._default_by_name = {}
        self._default_dict = {}
        self._default_callables = {}
        self._default_callable_list = []

        self.name = model.__name__.lower()
        if not table_name:
            table_name = re.sub('[^\w]+', '_', self.name)
        self.table_name = table_name
        self._table = None

        self.indexes = list(indexes) if indexes else []
        self.constraints = constraints
        self.schema = schema
        self.primary_key = primary_key
        self.composite_key = self.auto_increment = None
        self.only_save_dirty = only_save_dirty

        self.refs = {}
        self.backrefs = {}
        self.model_refs = defaultdict(list)
        self.model_backrefs = defaultdict(list)

        for key, value in kwargs.items():
            setattr(self, key, value)
        self._additional_keys = set(kwargs.keys())

    def model_graph(self, refs=True, backrefs=True, depth_first=True):
        if not refs and not backrefs:
            raise ValueError('One of `refs` or `backrefs` must be True.')

        accum = []
        seen = set()
        queue = deque(((None, self.model_class, None),))
        method = queue.popright if depth_first else queue.popleft

        while queue:
            curr = method()
            if curr in seen: continue
            seen.add(curr)

            if refs:
                for fk, model in curr.refs.items():
                    accum.append((fk, model, False))
                    queue.append(model)
            if backrefs:
                for fk, model in curr.backrefs.items():
                    accum.append((fk, model, True))
                    queue.append(model)

        return accum

    def add_ref(self, field):
        rel = field.rel_model
        self.refs[field] = rel
        self.model_refs[rel].append(field)
        rel._meta.backrefs[field] = self.model
        rel._meta.model_backrefs[self.model].append(field)

    def remove_ref(self, field):
        rel = field.rel_model
        del self.refs[field]
        self.model_ref[rel].remove(field)
        del rel._meta.backrefs[field]
        rel._meta.model_backrefs[self.model].remove(field)

    @property
    def table(self):
        if self._table is None:
            self._table = Table(self.table_name, [
                field.column_name for field in self.sorted_fields])
        return self._table

    @table.setter
    def table(self):
        raise AttributeError('Cannot set the "table".')

    @table.deleter
    def table(self):
        self._table = None

    def _update_sorted_fields(self):
        self.sorted_fields = list(self._sorted_field_list)
        self.sorted_field_names = [f.name for f in self.sorted_fields]

    def add_field(self, field_name, field, set_attribute=True):
        if field_name in self.fields:
            self.remove_field(field_name)

        del self.table
        field.bind(self.model, field_name, set_attribute)
        self.fields[field.name] = field
        self.columns[field.column_name] = field
        self.combined[field.name] = field
        self.combined[field.column_name] = field

        self._sorted_field_list.insert(field)
        self._update_sorted_fields()

        if field.default is not None:
            # This optimization helps speed up model instance construction.
            self.defaults[field] = field.default
            if callable(field.default):
                self._default_callables[field] = field.default
                self._default_callable_list.append((field.name, field.default))
            else:
                self._default_dict[field] = field.default
                self._default_by_name[field.name] = field.default

        if isinstance(field, ForeignKeyField):
            self.add_ref(field)

    def remove_field(self, field_name):
        if field_name not in self.fields:
            return

        del self.table
        original = self.fields.pop(field_name)
        del self.columns[original.column_name]
        del self.combined[field_name]
        try:
            del self.combined[original.column_name]
        except KeyError:
            pass
        self._sorted_field_list.remove(original)
        self._update_sorted_fields()

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

        if isinstance(field, ForeignKeyField):
            self.remove_ref(field)

    def set_primary_key(self, name, field):
        self.add_field(name, field)
        self.primary_key = field
        self.auto_increment = (
            isinstance(field, AutoField) or
            bool(field.sequence))
        #self.composite_key = isinstance(field, CompositeKey)

    def get_default_dict(self):
        dd = self._default_by_name.copy()
        for field_name, default in self._default_callable_list:
            dd[field_name] = default()
        return dd

    def fields_to_index(self):
        fields = []
        for f in self.sorted_fields:
            if f.primary_key:
                continue
            if f.index or f.unique or isinstance(f, ForeignKeyField):
                fields.append(((f,), f.unique))

        for index_parts, is_unique in self.indexes:
            index_nodes = []
            for part in index_parts:
                if isinstance(part, basestring):
                    index_nodes.append(self.combined[part])
                elif isinstance(part, Node):
                    index_nodes.append(part)
                else:
                    raise ValueError('Expected either a field name or a '
                                     'subclass of Node. Got: %s' % part)
            fields.append((index_nodes, is_unique))
        return fields


class DoesNotExist(Exception): pass


class BaseModel(type):
    inheritable = set(['constraints', 'database', 'indexes', 'primary_key',
                       'schema'])

    def __new__(cls, name, bases, attrs):
        if name == MODEL_BASE or bases[0].__name__ == MODEL_BASE:
            return super(BaseModel, cls).__new__(cls, name, bases, attrs)

        meta_options = {}
        meta = attrs.pop('Meta', None)
        if meta:
            for attr in dir(meta):
                if not attr.startswith('_'):
                    meta_options[attr] = getattr(meta, attr)

        pk = getattr(meta, 'primary_key', None)
        pk_name = parent_pk = None

        # Inherit any field descriptors by deep copying the underlying field
        # into the attrs of the new model, additionally see if the bases define
        # inheritable model options and swipe them.
        for b in bases:
            if not hasattr(b, '_meta'):
                continue

            base_meta = b._meta
            if parent_pk is None:
                parent_pk = deepcopy(base_meta.primary_key)
            all_inheritable = cls.inheritable | base_meta._additional_keys
            for k in base_meta.__dict__:
                if k in all_inheritable and k not in meta_options:
                    meta_options[k] = base_meta.__dict__[k]

            for (k, v) in b.__dict__.items():
                if (k not in attrs) and isinstance(v, FieldAccessor) and \
                   (not v.field.primary_key):
                    attrs[k] = deepcopy(v.field)

        sopts = meta_options.pop('schema_options', None) or {}
        Meta = meta_options.get('model_metadata_class', ModelMetadata)
        Schema = meta_options.get('schema_manager_class', SchemaManager)

        # Construct the new class.
        cls = super(BaseModel, cls).__new__(cls, name, bases, attrs)
        cls.__data__ = cls.__rel__ = None

        cls._meta = Meta(cls, **meta_options)
        cls._schema = Schema(cls, cls._meta.database, **sopts)

        fields = []
        for key, value in cls.__dict__.items():
            if isinstance(value, Field):
                if value.primary_key and pk:
                    raise ValueError('over-determined primary key %s.' % name)
                elif value.primary_key:
                    pk, pk_name = value, key
                else:
                    fields.append((key, value))

        if pk is None:
            pk, pk_name = ((parent_pk, parent_pk.name)
                           if parent_pk is not None else
                           (AutoField(), 'id'))

        if pk is not False:
            cls._meta.set_primary_key(pk_name, pk)

        for name, field in fields:
            cls._meta.add_field(name, field)

        # Create a repr and error class before finalizing.
        if hasattr(cls, '__unicode__'):
            setattr(cls, '__repr__', lambda self: '<%s: %r>' % (
                cls.__name__, self.__unicode__()))

        exc_name = '%sDoesNotExist' % cls.__name__
        exc_attrs = {'__module__': cls.__module__}
        exception_class = type(exc_name, (DoesNotExist,), exc_attrs)
        cls.DoesNotExist = exception_class

        # Call validation hook, allowing additional model validation.
        cls.validate_model()

        # TODO: Resolve any deferred relations waiting on this class.
        #DeferredRelation.resolve(cls)

        return cls

    def __iter__(self):
        return iter(self.select())


class Model(with_metaclass(BaseModel, Node)):
    def __init__(self, *args, **kwargs):
        self.__data__ = self._meta.get_default_dict()
        self._dirty = set(self.__data__)
        self.__rel__ = {}

        for k in kwargs:
            setattr(self, k, kwargs[k])

    @classmethod
    def validate_model(cls):
        pass

    @classmethod
    def alias(cls, alias=None):
        return Table(cls._meta.table_name, [
            field.column_name for field in cls._meta.sorted_fields],
            alias=alias, _model=cls)

    @classmethod
    def select(cls, *fields):
        if not fields:
            fields = cls._meta.sorted_fields
        return ModelSelect(cls, fields)

    @classmethod
    def update(cls, __data=None, **update):
        fdict = __data or {}
        for field in update:
            fdict[cls._meta.fields[f]] = update[f]
        return ModelUpdate(cls, fdict)

    @classmethod
    def insert(cls, __data=None, **insert):
        fdict = __data or {}
        for field in insert:
            if not isinstance(field, Field):
                field_obj = cls._meta.fields[field]
                fdict[field_obj] = insert[field]
            else:
                fdict[field] = insert[field]
        return ModelInsert(cls, fdict)

    @classmethod
    def insert_many(cls, rows, fields=None):
        return ModelInsert(cls, insert=rows, columns=fields)

    @classmethod
    def insert_from(cls, query, fields):
        return ModelInsert(cls, insert=query, columns=fields)

    @classmethod
    def delete(cls):
        return ModelDelete(cls)

    @classmethod
    def create(cls, **query):
        inst = cls(**query)
        inst.save(force_insert=True)
        inst._prepare_instance()
        return inst

    @classmethod
    def get(cls, *query):
        sq = cls.select()
        if query:
            sq = sq.where(*query)
        return sq.get()

    @classmethod
    def get_by_id(cls, pk):
        return cls.get(cls._meta.primary_key == pk)

    @classmethod
    def get_or_create(cls, **kwargs):
        defaults = kwargs.pop('defaults', {})
        query = cls.select()
        for field, value in kwargs.items():
            query = query.where(getattr(cls, field) == value)

        try:
            return query.get(), False
        except cls.DoesNotExist:
            try:
                if defaults:
                    kwargs.update(defaults)
                with cls._meta.database.atomic():
                    return cls.create(**kwargs), True
            except IntegrityError as exc:
                try:
                    return query.get(), False
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
                field = getattr(cls, field_name)
                if field.unique or field.primary_key:
                    query.append(field == value)
            return cls.get(*query), False

    @classmethod
    def as_entity(cls):
        if cls._meta.schema:
            return Entity(cls._meta.schema, cls._meta.db_table)
        return Entity(cls._meta.db_table)

    @property
    def _pk(self):
        return getattr(self, self._meta.primary_key.name)

    @_pk.setter
    def _pk(self, value):
        setattr(self, self._meta.primary_key.name, value)

    def _pk_expr(self):
        return self._meta.primary_key == self._pk

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
        for foreign_key in self._meta.refs:
            conditions = (
                foreign_key in self._dirty and
                foreign_key in field_dict and
                field_dict[foreign_key] is None and
                self.__rel__.get(foreign_key) is not None)
            if conditions:
                setattr(self, foreign_key, getattr(self, foreign_key))
                field_dict[foreign_key] = self._data[foreign_key]

    def save(self, force_insert=False, only=None):
        field_dict = self.__data__.copy()
        if self._meta.primary_key is not False:
            pk_field = self._meta.primary_key
            pk_value = self._pk
        else:
            pk_field = pk_value = None
        if only:
            field_dict = self._prune_fields(field_dict, only)
        elif self._meta.only_save_dirty and not force_insert:
            field_dict = self._prune_fields(field_dict, self.dirty_fields)
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
            self._pk = pk_value
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
            for rel_name, fk in klass._meta.backrefs.items():
                rel_model = fk.model_class
                if fk.rel_model is model_class:
                    node = (fk == self.__data__[fk.to_field.name])
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
        return hash((self.__class__, self._pk))

    def __eq__(self, other):
        return (
            other.__class__ == self.__class__ and
            self._pk is not None and
            other._pk == self._pk)

    def __ne__(self, other):
        return not self == other

    def __sql__(self, ctx):
        return ctx.sql(self.id)

    @classmethod
    def bind(cls, database, bind_refs=True, bind_backrefs=True):
        is_different = cls._meta.database is not database
        cls._meta.database = database
        if bind_refs or bind_backrefs:
            G = cls._meta.model_graph(refs=bind_refs, backrefs=bind_backrefs)
            for _, model, is_backref in G:
                model._meta.database = database
        return is_different

    @classmethod
    def create_schema(cls, safe=True):
        database = cls._meta.database
        cls._schema.create_all(database, safe)

    @classmethod
    def drop_schema(cls, database=None, safe=True):
        database = database or cls._meta.database
        cls._schema.drop_all(database, safe)


class _ModelQueryHelper(object):
    default_row_type = ROW.MODEL

    def _get_cursor_wrapper(self, cursor):
        row_type = self._row_type or self.default_row_type
        if row_type == ROW.MODEL:
            if len(self._from_list) == 1 and not self._joins:
                return ModelObjectCursorWrapper(cursor, self.model,
                                                self._columns)
            return ModelCursorWrapper(cursor, self.model, self._columns,
                                      self._from_list, self._joins)
        elif row_type == ROW.DICT:
            return ModelDictCursorWrapper(cursor, self.model, self._columns)
        elif row_type == ROW.TUPLE:
            return ModelTupleCursorWrapper(cursor, self.model, self._columns)
        elif row_type == ROW.NAMED_TUPLE:
            return ModelNamedTupleCursorWrapper(cursor, self.model,
                                                self._columns)
        elif row_type == ROW.CONSTRUCTOR:
            return ModelObjectCursorWrapper(cursor, self._constructor,
                                            self._columns)
        else:
            raise ValueError('Unrecognized row type: "%s".' % row_type)

    def execute(self, database=None):
        database = self.model._meta.database if database is None else database
        return super(_ModelQueryHelper, self).execute(database)


class ModelSelect(_ModelQueryHelper, Select):
    def __init__(self, model, fields_or_models):
        self.model = self._join_ctx = model
        self._joins = {}
        fields = []
        for fm in fields_or_models:
            if is_model(fm):
                fields.extend(fm._meta.sorted_fields)
            else:
                fields.append(fm)
        super(ModelSelect, self).__init__([model], fields)

    def switch(self, ctx=None):
        self._join_ctx = ctx
        return self

    @Node.copy
    def join(self, dest, join_type='INNER', on=None, src=None):
        src = self._join_ctx if src is None else src
        if is_model(dest):
            self._join_ctx = constructor = dest
            if on is None or isinstance(on, Field):
                fk_field, is_backref = self._generate_on_clause(src, dest, on)
                on = fk_field.expression()
                attr = fk_field.backref if is_backref else fk_field.name
            elif isinstance(on, Alias):
                attr = on._alias
            else:
                attr = dest._meta.name

        # TODO: support for dest being a table. Will require being able to
        # infer the correct foreign-key/primary-key ON expression to use by
        # iterating the source model's refs and backrefs and matching on the
        # table name.

        elif isinstance(dest, Source):
            on_is_alias = isinstance(on, Alias)
            attr = on._alias if on_is_alias else dest._alias
            constructor = dict
            if isinstance(dest, Table):
                attr = attr or dest._name
                if dest._model is not None:
                    constructor = dest._model
                    if not on_is_alias:
                        fk,_ = self._generate_on_clause(src, constructor, None)
                        attr = fk.name

        if attr:
            self._joins.setdefault(src, [])
            self._joins[src].append((dest, attr, constructor))

        return super(ModelSelect, self).join(dest, join_type, on)

    def _generate_on_clause(self, src, dest, to_field=None):
        meta = src._meta
        backref = fk_fields = False
        if dest in meta.model_refs:
            fk_fields = meta.model_refs[dest]
        elif dest in meta.model_backrefs:
            fk_fields = meta.model_backrefs[dest]
            backref = True

        if not fk_fields:
            raise ValueError('Unable to find foreign key between %s and %s. '
                             'Please specify an explicit join condition.' %
                             (src, dest))
        if to_field is not None:
            fk_fields = [f for f in fk_fields if (
                         (backref and f.rel_field is to_field) or
                         (not backref and f.to_field is to_field))]

        if len(fk_fields) > 1:
            raise ValueError('More than one foreign key between %s and %s. '
                             'Please specify which you are joining on.' %
                             (src, dest))
        else:
            fk_field = fk_fields[0]

        return fk_field, backref

    def __iter__(self):
        if not self._cursor_wrapper:
            self.execute()
        return iter(self._cursor_wrapper)


class _ModelWriteQueryHelper(_ModelQueryHelper):
    def __init__(self, model, *args, **kwargs):
        self.model = model
        super(_ModelWriteQueryHelper, self).__init__(model, *args, **kwargs)


class ModelUpdate(_ModelWriteQueryHelper, Update):
    pass


class ModelInsert(_ModelWriteQueryHelper, Insert):
    pass


class ModelDelete(_ModelWriteQueryHelper, Delete):
    pass


class BaseModelCursorWrapper(DictCursorWrapper):
    def __init__(self, cursor, model, columns):
        super(BaseModelCursorWrapper, self).__init__(cursor)
        self.model = model
        self.select = columns

    def _initialize_columns(self):
        combined = self.model._meta.combined
        description = self.cursor.description

        self.ncols = len(self.cursor.description)
        self.columns = []
        self.converters = converters = [None] * self.ncols
        self.fields = fields = [None] * self.ncols

        for idx, description_item in enumerate(description):
            column = description_item[0]
            dot_index = column.find('.')
            if dot_index != -1:
                column = column[dot_index + 1:]

            self.columns.append(column)

            node = self.select[idx]
            # Heuristics used to attempt to get the field associated with a
            # given SELECT column, so that we can accurately convert the value
            # returned by the database-cursor into a Python object.
            if isinstance(node, Field):
                converters[idx] = node.python_value
                fields[idx] = node
            elif column in combined:
                converters[idx] = combined[column].python_value
                fields[idx] = combined[column]
            elif (isinstance(node, Function) and node.arguments and
                  node._coerce):
                # Try to special-case functions calling fields.
                first = node.arguments[0]
                if isinstance(first, WrappedNode):
                    first = first.node  # Unwrap node object.

                if isinstance(first, Field):
                    self.converters[column] = first.python_value
                elif isinstance(first, Entity):
                    path = first.path[-1]
                    field = combined.get(path)
                    if field is not None:
                        converters[idx] = field.python_value

    initialize = _initialize_columns

    def process_row(self, row):
        raise NotImplementedError


class ModelDictCursorWrapper(BaseModelCursorWrapper):
    def process_row(self, row):
        result = {}
        columns, converters = self.columns, self.converters

        for i in range(self.ncols):
            if converters[i] is not None:
                result[columns[i]] = converters[i](row[i])
            else:
                result[columns[i]] = row[i]

        return result


class ModelTupleCursorWrapper(ModelDictCursorWrapper):
    constructor = tuple

    def process_row(self, row):
        columns, converters = self.columns, self.converters
        return self.constructor([
            (converters[i](row[i]) if converters[i] is not None else row[i])
            for i in range(self.ncols)])


class ModelNamedTupleCursorWrapper(ModelTupleCursorWrapper):
    def initialize(self):
        self._initialize_columns()
        self.constructor = namedtuple('Row', self.columns)


class ModelObjectCursorWrapper(ModelDictCursorWrapper):
    def __init__(self, cursor, model, select, constructor):
        self.constructor = constructor
        super(ModelObjectCursorWrapper, self).__init__(cursor, model, select)

    def process_row(self, row):
        return self.constructor(**self._process_row(row))


class ModelCursorWrapper(BaseModelCursorWrapper):
    def __init__(self, cursor, model, select, from_list, joins):
        super(ModelCursorWrapper, self).__init__(cursor, model, select)
        self.from_list = from_list
        self.joins = joins

    def initialize(self):
        self._initialize_columns()
        select, columns = self.select, self.columns

        self.key_to_constructor = {self.model: self.model}
        self.src_to_dest = []
        accum = deque(self.from_list)
        while accum:
            curr = accum.popleft()
            if isinstance(curr, Join):
                accum.append(curr.lhs)
                accum.append(curr.rhs)
                continue

            if curr not in self.joins:
                continue

            for key, attr, constructor in self.joins[curr]:
                if key not in self.key_to_constructor:
                    self.key_to_constructor[key] = constructor
                    self.src_to_dest.append((curr, attr, key,
                                             constructor is dict))
                    accum.append(key)

        self.column_keys = []
        for idx, node in enumerate(select):
            key = self.model
            if self.fields[idx] is not None:
                key = self.fields[idx].model
            else:
                if isinstance(node, WrappedNode):
                    node = node.node
                if isinstance(node, Column):
                    key = node.source

            self.column_keys.append(key)

    def process_row(self, row):
        objects = {}
        for key, constructor in self.key_to_constructor.iteritems():
            objects[key] = constructor()

        for idx, key in enumerate(self.column_keys):
            instance = objects[key]
            column = self.columns[idx]
            value = row[idx]
            if self.converters[idx]:
                value = self.converters[idx](value)

            if isinstance(instance, dict):
                instance[column] = value
            else:
                setattr(instance, column, value)

        # Need to do some analysis on the joins before this.
        for (src, attr, dest, is_dict) in self.src_to_dest:
            instance = objects[src]
            try:
                joined_instance = objects[dest]
            except KeyError:
                continue

            if is_dict:
                instance[attr] = joined_instance
            else:
                setattr(instance, attr, joined_instance)

        return objects[self.model]
