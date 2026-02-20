import json
import logging
import uuid

from peewee import *
from peewee import ColumnBase
from peewee import Expression
from peewee import FieldDatabaseHook
from peewee import Node
from peewee import NodeList
from peewee import Psycopg2Adapter
from peewee import Psycopg3Adapter
from peewee import __exception_wrapper__

try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass

try:
    from psycopg2.extras import register_hstore
except ImportError:
    def register_hstore(*args): pass

try:
    from psycopg.types import TypeInfo
    from psycopg.types.hstore import register_hstore as register_hstore_pg3
except ImportError:
    def register_hstore_pg3(*args): pass


logger = logging.getLogger('peewee')


HCONTAINS_DICT = '@>'
HCONTAINS_KEYS = '?&'
HCONTAINS_KEY = '?'
HCONTAINS_ANY_KEY = '?|'
HKEY = '->'
HUPDATE = '||'
ACONTAINS = '@>'
ACONTAINED_BY = '<@'
ACONTAINS_ANY = '&&'
TS_MATCH = '@@'
JSONB_CONTAINS = '@>'
JSONB_CONTAINED_BY = '<@'
JSONB_CONTAINS_KEY = '?'
JSONB_CONTAINS_ANY_KEY = '?|'
JSONB_CONTAINS_ALL_KEYS = '?&'
JSONB_EXISTS = '?'
JSONB_REMOVE = '-'
JSONB_PATH = '#>'


class Json(Node):
    # Fallback JSON handler.
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def __sql__(self, ctx):
        return ctx.value(self.value, json.dumps)


class _LookupNode(ColumnBase):
    def __init__(self, node, parts):
        self.node = node
        self.parts = parts
        super(_LookupNode, self).__init__()

    def clone(self):
        return type(self)(self.node, list(self.parts))

    def __hash__(self):
        return hash((self.__class__.__name__, id(self)))


class ObjectSlice(_LookupNode):
    @classmethod
    def create(cls, node, value):
        if isinstance(value, slice):
            parts = [value.start or 0, value.stop or 0]
        elif isinstance(value, int):
            parts = [value]
        elif isinstance(value, Node):
            parts = value
        else:
            # Assumes colon-separated integer indexes.
            parts = [int(i) for i in value.split(':')]
        return cls(node, parts)

    def __sql__(self, ctx):
        ctx.sql(self.node)
        if isinstance(self.parts, Node):
            ctx.literal('[').sql(self.parts).literal(']')
        else:
            ctx.literal('[%s]' % ':'.join(str(p + 1) for p in self.parts))
        return ctx

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)


class IndexedFieldMixin(object):
    default_index_type = 'GIN'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('index', True)  # By default, use an index.
        super(IndexedFieldMixin, self).__init__(*args, **kwargs)


class ArrayField(IndexedFieldMixin, Field):
    passthrough = True

    def __init__(self, field_class=IntegerField, field_kwargs=None,
                 dimensions=1, convert_values=False, *args, **kwargs):
        self.__field = field_class(**(field_kwargs or {}))
        self.dimensions = dimensions
        self.convert_values = convert_values
        self.field_type = self.__field.field_type
        super(ArrayField, self).__init__(*args, **kwargs)

    def bind(self, model, name, set_attribute=True):
        ret = super(ArrayField, self).bind(model, name, set_attribute)
        self.__field.bind(model, '__array_%s' % name, False)
        return ret

    def ddl_datatype(self, ctx):
        data_type = self.__field.ddl_datatype(ctx)
        return NodeList((data_type, SQL('[]' * self.dimensions)), glue='')

    def db_value(self, value):
        if value is None or isinstance(value, Node):
            return value
        elif self.convert_values:
            return self._process(self.__field.db_value, value, self.dimensions)
        else:
            return value if isinstance(value, list) else list(value)

    def python_value(self, value):
        if self.convert_values and value is not None:
            conv = self.__field.python_value
            if isinstance(value, list):
                return self._process(conv, value, self.dimensions)
            else:
                return conv(value)
        else:
            return value

    def _process(self, conv, value, dimensions):
        dimensions -= 1
        if dimensions == 0:
            return [conv(v) for v in value]
        else:
            return [self._process(conv, v, dimensions) for v in value]

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)

    def _e(op):
        def inner(self, rhs):
            return Expression(self, op, ArrayValue(self, rhs))
        return inner
    __eq__ = _e(OP.EQ)
    __ne__ = _e(OP.NE)
    __gt__ = _e(OP.GT)
    __ge__ = _e(OP.GTE)
    __lt__ = _e(OP.LT)
    __le__ = _e(OP.LTE)
    __hash__ = Field.__hash__

    def contains(self, *items):
        return Expression(self, ACONTAINS, ArrayValue(self, items))

    def contains_any(self, *items):
        return Expression(self, ACONTAINS_ANY, ArrayValue(self, items))

    def contained_by(self, *items):
        return Expression(self, ACONTAINED_BY, ArrayValue(self, items))


class ArrayValue(Node):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def __sql__(self, ctx):
        return (ctx
                .sql(AsIs(self.value))
                .literal('::')
                .sql(self.field.ddl_datatype(ctx)))


class DateTimeTZField(DateTimeField):
    field_type = 'TIMESTAMPTZ'


class HStoreField(IndexedFieldMixin, Field):
    field_type = 'HSTORE'
    __hash__ = Field.__hash__

    def __getitem__(self, key):
        return Expression(self, HKEY, Value(key))

    def keys(self):
        return fn.akeys(self)

    def values(self):
        return fn.avals(self)

    def items(self):
        return fn.hstore_to_matrix(self)

    def slice(self, *args):
        return fn.slice(self, AsIs(list(args)))

    def exists(self, key):
        return fn.exist(self, key)

    def defined(self, key):
        return fn.defined(self, key)

    def update(self, **data):
        return Expression(self, HUPDATE, data)

    def delete(self, *keys):
        value = Cast(AsIs(list(keys)), 'text[]')
        return fn.delete(self, value)

    def contains(self, value):
        if isinstance(value, dict):
            rhs = AsIs(value)
            return Expression(self, HCONTAINS_DICT, rhs)
        elif isinstance(value, (list, tuple)):
            rhs = AsIs(value)
            return Expression(self, HCONTAINS_KEYS, rhs)
        return Expression(self, HCONTAINS_KEY, value)

    def contains_any(self, *keys):
        return Expression(self, HCONTAINS_ANY_KEY, AsIs(list(keys)))


class _JsonLookupBase(_LookupNode):
    def __init__(self, node, parts, as_json=False):
        super(_JsonLookupBase, self).__init__(node, parts)
        self._as_json = as_json

    def clone(self):
        return type(self)(self.node, list(self.parts), self._as_json)

    @Node.copy
    def as_json(self, as_json=True):
        self._as_json = as_json

    def concat(self, rhs):
        if not isinstance(rhs, Node):
            rhs = self.node.json_type(rhs)
        return Expression(self.as_json(True), OP.CONCAT, rhs)

    def contains(self, other):
        if not isinstance(other, Node):
            other = self.node.json_type(other)
        return Expression(self.as_json(True), JSONB_CONTAINS, other)

    def contained_by(self, other):
        if not isinstance(other, Node):
            other = self.node.json_type(other)
        return Expression(self.as_json(True), JSONB_CONTAINED_BY, other)

    def contains_any(self, *keys):
        return Expression(
            self.as_json(True),
            JSONB_CONTAINS_ANY_KEY,
            AsIs(list(keys), False))

    def contains_all(self, *keys):
        return Expression(
            self.as_json(True),
            JSONB_CONTAINS_ALL_KEYS,
            AsIs(list(keys), False))

    def has_key(self, key):
        return Expression(self.as_json(True), JSONB_CONTAINS_KEY, key)

    def path(self, *keys):
        return JsonPath(self.as_json(True), keys)


class JsonLookup(_JsonLookupBase):
    def __getitem__(self, value):
        return JsonLookup(self.node, self.parts + [value], self._as_json)

    def __sql__(self, ctx):
        ctx.sql(self.node)
        for part in self.parts[:-1]:
            ctx.literal('->').sql(part)
        if self.parts:
            (ctx
             .literal('->' if self._as_json else '->>')
             .sql(self.parts[-1]))

        return ctx


class JsonPath(_JsonLookupBase):
    def __sql__(self, ctx):
        return (ctx
                .sql(self.node)
                .literal('#>' if self._as_json else '#>>')
                .sql(Value('{%s}' % ','.join(map(str, self.parts)))))


class JSONField(FieldDatabaseHook, Field):
    field_type = 'JSON'
    _json_datatype = 'json'

    def _db_hook(self, database):
        if database is None or not hasattr(database, '_adapter'):
            self.json_type = Json
            self.cast_json_case = True
        else:
            self.json_type = database._adapter.json_type
            self.cast_json_case = database._adapter.cast_json_case

    def db_value(self, value):
        if value is None or isinstance(value, (Node, self.json_type)):
            return value
        return self.json_type(value)

    def to_value(self, value, case=False):
        # CASE WHEN id = 123 THEN x.json_data fails because the expression is
        # untyped, so we need an explicit cast with psycopg2.
        if case and self.cast_json_case:
            return Cast(self.json_type(value), self._json_datatype)
        return self.json_type(value)

    def __getitem__(self, value):
        return JsonLookup(self, [value])

    def path(self, *keys):
        return JsonPath(self, keys)

    def concat(self, value):
        if not isinstance(value, Node):
            value = self.json_type(value)
        return super(JSONField, self).concat(value)


class BinaryJSONField(IndexedFieldMixin, JSONField):
    field_type = 'JSONB'
    _json_datatype = 'jsonb'
    __hash__ = Field.__hash__

    def _db_hook(self, database):
        if database is None or not hasattr(database, '_adapter'):
            self.json_type = Json
            self.cast_json_case = True
        else:
            self.json_type = database._adapter.jsonb_type
            self.cast_json_case = database._adapter.cast_json_case

    def contains(self, other):
        if not isinstance(other, Node):
            other = self.json_type(other)
        return Expression(self, JSONB_CONTAINS, other)

    def contained_by(self, other):
        if not isinstance(other, Node):
            other = self.json_type(other)
        return Expression(self, JSONB_CONTAINED_BY, other)

    def contains_any(self, *items):
        return Expression(
            self,
            JSONB_CONTAINS_ANY_KEY,
            AsIs(list(items), False))

    def contains_all(self, *items):
        return Expression(
            self,
            JSONB_CONTAINS_ALL_KEYS,
            AsIs(list(items), False))

    def has_key(self, key):
        return Expression(self, JSONB_CONTAINS_KEY, Value(key, False))

    def remove(self, *items):
        value = Cast(AsIs(list(items), False), 'text[]')
        return Expression(self, JSONB_REMOVE, value)


class TSVectorField(IndexedFieldMixin, TextField):
    field_type = 'TSVECTOR'
    __hash__ = Field.__hash__

    def match(self, query, language=None, plain=False):
        params = (language, query) if language is not None else (query,)
        func = fn.plainto_tsquery if plain else fn.to_tsquery
        return Expression(self, TS_MATCH, func(*params))


def Match(field, query, language=None):
    params = (language, query) if language is not None else (query,)
    field_params = (language, field) if language is not None else (field,)
    return Expression(
        fn.to_tsvector(*field_params),
        TS_MATCH,
        fn.to_tsquery(*params))


class IntervalField(Field):
    field_type = 'INTERVAL'


class FetchManyCursor(object):
    __slots__ = ('cursor', 'array_size', 'exhausted', 'iterable')

    def __init__(self, cursor, array_size=None):
        self.cursor = cursor
        self.array_size = array_size or cursor.itersize
        self.exhausted = False
        self.iterable = self.row_gen()

    def __del__(self):
        if self.cursor and not self.cursor.closed:
            try:
                self.cursor.close()
            except Exception:
                pass

    @property
    def description(self):
        return self.cursor.description

    def close(self):
        self.cursor.close()

    def row_gen(self):
        try:
            while True:
                rows = self.cursor.fetchmany(self.array_size)
                if not rows:
                    return
                for row in rows:
                    yield row
        finally:
            self.close()

    def fetchone(self):
        if self.exhausted:
            return
        try:
            return next(self.iterable)
        except StopIteration:
            self.exhausted = True


class ServerSideQuery(Node):
    def __init__(self, query, array_size=None):
        self.query = query
        self.array_size = array_size
        self._cursor_wrapper = None

    def __sql__(self, ctx):
        return self.query.__sql__(ctx)

    def __iter__(self):
        if self._cursor_wrapper is None:
            self._execute(self.query._database)
        return iter(self._cursor_wrapper.iterator())

    def close(self):
        if self._cursor_wrapper is not None:
            self._cursor_wrapper.cursor.close()
            self._cursor_wrapper = None
            return True
        return False

    def iterator(self):
        if self._cursor_wrapper is None:
            self._execute(self.query._database)
        return self._cursor_wrapper.iterator()

    def _execute(self, database):
        if self._cursor_wrapper is None:
            cursor = database.execute(self.query, named_cursor=True,
                                      array_size=self.array_size)
            self._cursor_wrapper = self.query._get_cursor_wrapper(cursor)
        return self._cursor_wrapper


def ServerSide(query, array_size=None):
    server_side_query = ServerSideQuery(query, array_size=array_size)
    for row in server_side_query:
        yield row


class _empty_object(object):
    __slots__ = ()
    def __nonzero__(self):
        return False
    __bool__ = __nonzero__


class Psycopg2ExtAdapter(Psycopg2Adapter):
    def register_hstore(self, conn):
        register_hstore(conn)

    def server_side_cursor(self, conn):
        # psycopg2 does not allow us to use these in autocommit, even if we ARE
        # inside a transaction - so specify withhold (not desirable!).
        return conn.cursor(name=str(uuid.uuid1()), withhold=True)


class Psycopg3ExtAdapter(Psycopg3Adapter):
    def register_hstore(self, conn):
        info = TypeInfo.fetch(conn, 'hstore')
        register_hstore_pg3(info, conn)

    def server_side_cursor(self, conn):
        return conn.cursor(name=str(uuid.uuid1()))


class PostgresqlExtDatabase(PostgresqlDatabase):
    psycopg2_adapter = Psycopg2ExtAdapter
    psycopg3_adapter = Psycopg3ExtAdapter

    def __init__(self, *args, **kwargs):
        self._register_hstore = kwargs.pop('register_hstore', False)
        self._server_side_cursors = kwargs.pop('server_side_cursors', False)
        super(PostgresqlExtDatabase, self).__init__(*args, **kwargs)

    def _connect(self):
        conn = super(PostgresqlExtDatabase, self)._connect()
        if self._register_hstore:
            self._adapter.register_hstore(conn)
        return conn

    def cursor(self, named_cursor=None):
        if self.is_closed():
            if self.autoconnect:
                self.connect()
            else:
                raise InterfaceError('Error, database connection not opened.')
        if named_cursor:
            return self._adapter.server_side_cursor(self._state.conn)
        return self._state.conn.cursor()

    def execute(self, query, named_cursor=False, array_size=None,
                **context_options):
        ctx = self.get_sql_context(**context_options)
        sql, params = ctx.sql(query).query()
        named_cursor = named_cursor or (self._server_side_cursors and
                                        sql[:6].lower() == 'select')
        cursor = self.execute_sql(sql, params, named_cursor=named_cursor)
        if named_cursor:
            cursor = FetchManyCursor(cursor, array_size)
        return cursor

    def execute_sql(self, sql, params=None, named_cursor=None):
        logger.debug((sql, params))
        with __exception_wrapper__:
            cursor = self.cursor(named_cursor=named_cursor)
            cursor.execute(sql, params or ())
        return cursor


class Psycopg3Database(PostgresqlExtDatabase):
    def __init__(self, *args, **kwargs):
        kwargs['prefer_psycopg3'] = True
        super(Psycopg3Database, self).__init__(*args, **kwargs)
