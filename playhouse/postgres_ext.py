"""
Collection of postgres-specific extensions, currently including:

* Support for hstore, a key/value type storage
"""
import logging
import uuid

from peewee import *
from peewee import __exception_wrapper__

try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass

from psycopg2.extras import register_hstore
try:
    from psycopg2.extras import Json
except:
    Json = None


logger = logging.getLogger('peewee')


HCONTAINS_DICT = '@>'
HCONTAINS_KEYS = '?&'
HCONTAINS_KEY = '?'
HCONTAINS_ANY_KEY = '?|'
HKEY = '->'
HUPDATE = '||'
ACONTAINS = '@>'
ACONTAINS_ANY = '&&'
TS_MATCH = '@@'
JSONB_CONTAINS = '@>'
JSONB_CONTAINED_BY = '<@'
JSONB_CONTAINS_ANY_KEY = '?|'
JSONB_CONTAINS_ALL_KEYS = '?&'
JSONB_EXISTS = '?'
CAST = '::'


class _LookupNode(ColumnBase):
    def __init__(self, node, parts):
        self.node = node
        self.parts = parts
        super(_LookupNode, self).__init__()

    def clone(self):
        return type(self)(self.node, list(self.parts))

    def cast(self, as_type):
        return Expression(NodeList(self, parens=True), CAST, SQL(as_type))


class _JsonLookupBase(_LookupNode):
    def __init__(self, node, parts, as_json=False):
        super(_JsonLookupBase, self).__init__(node, parts)
        self._as_json = as_json

    def clone(self):
        return type(self)(self.node, list(self.parts), self._as_json)

    @Node.copy
    def as_json(self, as_json=True):
        self._as_json = as_json

    def contains(self, other):
        clone = self.as_json(True)
        if isinstance(other, (list, dict)):
            return Expression(clone, JSONB_CONTAINS, Json(other))
        return Expression(clone, JSONB_EXISTS, other)

    def contains_any(self, *keys):
        return Expression(
            self.as_json(True),
            JSONB_CONTAINS_ANY_KEY,
            Value(list(keys), unpack=False))

    def contains_all(self, *keys):
        return Expression(
            self.as_json(True),
            JSONB_CONTAINS_ALL_KEYS,
            Value(list(keys), unpack=False))


class JsonLookup(_JsonLookupBase):
    def __getitem__(self, value):
        return JsonLookup(self.node, self.parts + [value], self._as_json)

    def __sql__(self, ctx):
        ctx.sql(self.node)
        for part in self.node.parts[:-1]:
            ctx.literal('->').sql(part)
        if self.node.parts:
            (ctx
             .literal('->' if self.node._as_json else '->>')
             .sql(parts[-1]))

        return ctx


class JsonPath(_JsonLookupBase):
    def __sql__(self, ctx):
        return (ctx
                .sql(self.node)
                .literal('#>' if self.node._as_json else '#>>')
                .sql(Value('{%s}' % ','.join(map(str, self.node.parts)))))


class ObjectSlice(_LookupNode):
    @classmethod
    def create(cls, node, value):
        if isinstance(value, slice):
            parts = [value.start or 0, value.stop or 0]
        elif isinstance(value, int):
            parts = [value]
        else:
            parts = map(int, value.split(':'))
        return cls(node, parts)

    def __sql__(self, ctx):
        return (ctx
                .sql(self.node)
                .literal('[%s]' % ':'.join(str(p + 1) for p in self.parts)))

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)


class IndexedFieldMixin(object):
    default_index_type = 'GiST'

    def __init__(self, index_type=None, *args, **kwargs):
        kwargs.setdefault('index', True)  # By default, use an index.
        super(IndexedFieldMixin, self).__init__(*args, **kwargs)
        if self.index:
            self.index_type = index_type or self.default_index_type
        else:
            self.index_type = None


class ArrayField(IndexedFieldMixin, Field):
    default_index_type = 'GIN'
    passthrough = True

    def __init__(self, field_class=IntegerField, dimensions=1, *args,
                 **kwargs):
        self.__field = field_class(*args, **kwargs)
        self.dimensions = dimensions
        self.field_type = self.__field.field_type
        super(ArrayField, self).__init__(*args, **kwargs)

    def ddl_datatype(self, ctx):
        data_type = self.__field.ddl_datatype(ctx)
        return NodeList((data_type, SQL('[]' * self.dimensions)), glue='')

    def db_value(self, value):
        if value is not None:
            return list(value) if not isinstance(value, Node) else value

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)

    def contains(self, *items):
        return Expression(self, ACONTAINS, ArrayValue(self, items))

    def contains_any(self, *items):
        return Expression(self, ACONTAINS_ANY, ArrayValue(self, items))


class ArrayValue(Node):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def __sql__(self, ctx):
        return (ctx
                .sql(Value(self.value, unpack=False))
                .literal('::')
                .sql(self.field.ddl_datatype(ctx)))


class DateTimeTZField(DateTimeField):
    field_type = 'TIMESTAMPTZ'


class HStoreField(IndexedFieldMixin, Field):
    field_type = 'HSTORE'

    def __getitem__(self, key):
        return Expression(self, HKEY, Value(key))

    def keys(self):
        return fn.akeys(self)

    def values(self):
        return fn.avals(self)

    def items(self):
        return fn.hstore_to_matrix(self)

    def slice(self, *args):
        return fn.slice(self, Value(list(args), unpack=False))

    def exists(self, key):
        return fn.exist(self, key)

    def defined(self, key):
        return fn.defined(self, key)

    def update(self, **data):
        return Expression(self, HUPDATE, data)

    def delete(self, *keys):
        return fn.delete(self, Value(list(keys), unpack=False))

    def contains(self, value):
        if isinstance(value, dict):
            rhs = Value(value, unpack=False)
            return Expression(self, HCONTAINS_DICT, rhs)
        elif isinstance(value, (list, tuple)):
            rhs = Value(value, unpack=False)
            return Expression(self, HCONTAINS_KEYS, rhs)
        return Expression(self, HCONTAINS_KEY, value)

    def contains_any(self, *keys):
        return Expression(self, HCONTAINS_ANY_KEY, Value(list(keys),
                                                         unpack=False))


class JSONField(Field):
    field_type = 'JSON'

    def __init__(self, dumps=None, *args, **kwargs):
        if Json is None:
            raise Exception('Your version of psycopg2 does not support JSON.')
        self.dumps = dumps
        super(JSONField, self).__init__(*args, **kwargs)

    def db_value(self, value):
        if value is None:
            return value
        if not isinstance(value, Json):
            return Json(value, dumps=self.dumps)
        return value

    def __getitem__(self, value):
        return JsonLookup(self, [value])

    def path(self, *keys):
        return JsonPath(self, keys)


class BinaryJSONField(IndexedFieldMixin, JSONField):
    field_type = 'JSONB'
    default_index_type = 'GIN'

    def contains(self, other):
        if isinstance(other, (list, dict)):
            return Expression(self, JSONB_CONTAINS, Json(other))
        return Expression(self, JSONB_EXISTS, Value(other, unpack=False))

    def contained_by(self, other):
        return Expression(self, JSONB_CONTAINED_BY, Json(other))

    def contains_any(self, *items):
        return Expression(
            self,
            JSONB_CONTAINS_ANY_KEY,
            Value(list(items), unpack=False))

    def contains_all(self, *items):
        return Expression(
            self,
            JSONB_CONTAINS_ALL_KEYS,
            Value(list(items), unpack=False))


class TSVectorField(IndexedFieldMixin, TextField):
    field_type = 'TSVECTOR'
    default_index_type = 'GIN'

    def match(self, query, language=None):
        params = (language, query) if language is not None else (query,)
        return Expression(self, TS_MATCH, fn.to_tsquery(*params))


def Match(field, query, language=None):
    params = (language, query) if language is not None else (query,)
    return Expression(
        fn.to_tsvector(field),
        TS_MATCH,
        fn.to_tsquery(*params))


class PostgresqlExtDatabase(PostgresqlDatabase):
    def __init__(self, *args, **kwargs):
        self.server_side_cursors = kwargs.pop('server_side_cursors', False)
        self.register_hstore = kwargs.pop('register_hstore', True)
        super(PostgresqlExtDatabase, self).__init__(*args, **kwargs)

    def cursor(self, name=None):
        if name:
            return self.connection().cursor(name=name)
        return self.connection().cursor()

    def execute_sql(self, sql, params=None, commit=True, named_cursor=False):
        logger.debug((sql, params))
        use_named_cursor = (named_cursor or (
                            self.server_side_cursors and
                            sql.lower().startswith('select')))
        with __exception_wrapper__:
            if use_named_cursor:
                cursor = self.cursor(name=str(uuid.uuid1()))
                require_commit = False
            else:
                cursor = self.cursor()
                try:
                    cursor.execute(sql, params or ())
                except Exception:
                    if self.autorollback and not self.in_transaction():
                        self.rollback()
                    raise
                else:
                    if commit and not self.in_transaction() and \
                       (self.commit_select or not sql.startswith('SELECT')):
                        self.commit()
        return cursor

    def _connect(self):
        conn = super(PostgresqlExtDatabase, self)._connect()
        if self.register_hstore:
            register_hstore(conn, globally=True)
        return conn


class ServerSideSelectQuery(SelectQuery):
    @classmethod
    def clone_from_query(cls, query):
        clone = ServerSideSelectQuery(query.model_class)
        return query._clone_attributes(clone)

    def _execute(self):
        sql, params = self.sql()
        return self.database.execute_sql(
            sql, params, require_commit=False, named_cursor=True)


#PostgresqlExtDatabase.register_fields({
#    'datetime_tz': 'timestamp with time zone',
#    'hash': 'hstore',
#    'json': 'json',
#    'jsonb': 'jsonb',
#    'tsvector': 'tsvector',
#})
#PostgresqlExtDatabase.register_ops({
#    OP.HCONTAINS_DICT: '@>',
#    OP.HCONTAINS_KEYS: '?&',
#    OP.HCONTAINS_KEY: '?',
#    OP.HCONTAINS_ANY_KEY: '?|',
#    OP.HKEY: '->',
#    OP.HUPDATE: '||',
#    OP.ACONTAINS: '@>',
#    OP.ACONTAINS_ANY: '&&',
#    OP.TS_MATCH: '@@',
#    OP.JSONB_CONTAINS: '@>',
#    OP.JSONB_CONTAINED_BY: '<@',
#    OP.JSONB_CONTAINS_ANY_KEY: '?|',
#    OP.JSONB_CONTAINS_ALL_KEYS: '?&',
#    OP.JSONB_EXISTS: '?',
#    OP.CAST: '::',
#})

def ServerSide(select_query):
    # Flag query for execution using server-side cursors.
    clone = ServerSideSelectQuery.clone_from_query(select_query)
    with clone.database.transaction():
        # Execute the query.
        query_result = clone.execute()

        # Patch QueryResultWrapper onto original query.
        select_query._qr = query_result

        # Expose generator for iterating over query.
        for obj in query_result.iterator():
            yield obj


def LateralJoin(lhs, rhs, join_type='LEFT', condition=True):
    return Clause(
        lhs,
        SQL('%s JOIN LATERAL' % join_type),
        rhs,
        SQL('ON %s', condition))
