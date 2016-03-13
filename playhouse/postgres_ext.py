"""
Collection of postgres-specific extensions, currently including:

* Support for hstore, a key/value type storage
"""
import uuid

from peewee import *
from peewee import Expression
from peewee import logger
from peewee import Node
from peewee import OP
from peewee import Param
from peewee import Passthrough
from peewee import returns_clone
from peewee import QueryCompiler
from peewee import SelectQuery
from peewee import UUIDField  # For backwards-compatibility.

try:
    from psycopg2cffi import compat
    compat.register()
except ImportError:
    pass

from psycopg2.extensions import adapt
from psycopg2.extensions import AsIs
from psycopg2.extensions import register_adapter
from psycopg2.extras import register_hstore
try:
    from psycopg2.extras import Json
except:
    Json = None

@Node.extend(clone=False)
def cast(self, as_type):
    return Expression(self, OP.CAST, SQL(as_type))

class _LookupNode(Node):
    def __init__(self, node, parts):
        self.node = node
        self.parts = parts
        super(_LookupNode, self).__init__()

    def clone_base(self):
        return type(self)(self.node, list(self.parts))

    def cast(self, as_type):
        return Expression(Clause(self, parens=True), OP.CAST, SQL(as_type))

class _JsonLookupBase(_LookupNode):
    def __init__(self, node, parts, as_json=False):
        super(_JsonLookupBase, self).__init__(node, parts)
        self._as_json = as_json

    def clone_base(self):
        return type(self)(self.node, list(self.parts), self._as_json)

    @returns_clone
    def as_json(self, as_json=True):
        self._as_json = as_json

    def contains(self, other):
        clone = self.as_json(True)
        if isinstance(other, (list, dict)):
            return Expression(clone, OP.JSONB_CONTAINS, Json(other))
        return Expression(clone, OP.JSONB_EXISTS, other)

    def contains_any(self, *keys):
        return Expression(
            self.as_json(True),
            OP.JSONB_CONTAINS_ANY_KEY,
            Passthrough(list(keys)))

    def contains_all(self, *keys):
        return Expression(
            self.as_json(True),
            OP.JSONB_CONTAINS_ALL_KEYS,
            Passthrough(list(keys)))

class JsonLookup(_JsonLookupBase):
    _node_type = 'json_lookup'

    def __getitem__(self, value):
        return JsonLookup(self.node, self.parts + [value], self._as_json)

class JsonPath(_JsonLookupBase):
    _node_type = 'json_path'

class ObjectSlice(_LookupNode):
    _node_type = 'object_slice'

    @classmethod
    def create(cls, node, value):
        if isinstance(value, slice):
            parts = [value.start or 0, value.stop or 0]
        elif isinstance(value, int):
            parts = [value]
        else:
            parts = map(int, value.split(':'))
        return cls(node, parts)

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)

class _Array(Node):
    def __init__(self, field, items):
        self.field = field
        self.items = items
        super(_Array, self).__init__()

def adapt_array(arr):
    conn = arr.field.model_class._meta.database.get_conn()
    items = adapt(arr.items)
    items.prepare(conn)
    return AsIs('%s::%s%s' % (
        items,
        arr.field.get_column_type(),
        '[]' * arr.field.dimensions))
register_adapter(_Array, adapt_array)


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

    def __init__(self, field_class=IntegerField, dimensions=1, *args,
                 **kwargs):
        self.__field = field_class(*args, **kwargs)
        self.dimensions = dimensions
        self.db_field = self.__field.get_db_field()
        super(ArrayField, self).__init__(*args, **kwargs)

    def __ddl_column__(self, column_type):
        sql = self.__field.__ddl_column__(column_type)
        sql.value += '[]' * self.dimensions
        return sql

    def db_value(self, value):
        if value is not None and not isinstance(value, (list, _Array)):
            return list(value)
        return value

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)

    def contains(self, *items):
        return Expression(self, OP.ACONTAINS, _Array(self, list(items)))

    def contains_any(self, *items):
        return Expression(self, OP.ACONTAINS_ANY, _Array(self, list(items)))


class DateTimeTZField(DateTimeField):
    db_field = 'datetime_tz'


class HStoreField(IndexedFieldMixin, Field):
    db_field = 'hash'

    def __getitem__(self, key):
        return Expression(self, OP.HKEY, Param(key))

    def keys(self):
        return fn.akeys(self)

    def values(self):
        return fn.avals(self)

    def items(self):
        return fn.hstore_to_matrix(self)

    def slice(self, *args):
        return fn.slice(self, Param(list(args)))

    def exists(self, key):
        return fn.exist(self, key)

    def defined(self, key):
        return fn.defined(self, key)

    def update(self, **data):
        return Expression(self, OP.HUPDATE, data)

    def delete(self, *keys):
        return fn.delete(self, Param(list(keys)))

    def contains(self, value):
        if isinstance(value, dict):
            return Expression(self, OP.HCONTAINS_DICT, Param(value))
        elif isinstance(value, (list, tuple)):
            return Expression(self, OP.HCONTAINS_KEYS, Param(value))
        return Expression(self, OP.HCONTAINS_KEY, value)

    def contains_any(self, *keys):
        return Expression(self, OP.HCONTAINS_ANY_KEY, Param(list(keys)))


class JSONField(Field):
    db_field = 'json'

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
    db_field = 'jsonb'
    default_index_type = 'GIN'

    def contains(self, other):
        if isinstance(other, (list, dict)):
            return Expression(self, OP.JSONB_CONTAINS, Json(other))
        return Expression(self, OP.JSONB_EXISTS, Passthrough(other))

    def contained_by(self, other):
        return Expression(self, OP.JSONB_CONTAINED_BY, Json(other))

    def contains_any(self, *items):
        return Expression(
            self,
            OP.JSONB_CONTAINS_ANY_KEY,
            Passthrough(list(items)))

    def contains_all(self, *items):
        return Expression(
            self,
            OP.JSONB_CONTAINS_ALL_KEYS,
            Passthrough(list(items)))


class TSVectorField(IndexedFieldMixin, TextField):
    db_field = 'tsvector'
    default_index_type = 'GIN'

    def match(self, query):
        return Expression(self, OP.TS_MATCH, fn.to_tsquery(query))


def Match(field, query):
    return Expression(fn.to_tsvector(field), OP.TS_MATCH, fn.to_tsquery(query))


OP.update(
    HKEY='key',
    HUPDATE='H@>',
    HCONTAINS_DICT='H?&',
    HCONTAINS_KEYS='H?',
    HCONTAINS_KEY='H?|',
    HCONTAINS_ANY_KEY='H||',
    ACONTAINS='A@>',
    ACONTAINS_ANY='A||',
    TS_MATCH='T@@',
    JSONB_CONTAINS='JB@>',
    JSONB_CONTAINED_BY='JB<@',
    JSONB_CONTAINS_ANY_KEY='JB?|',
    JSONB_CONTAINS_ALL_KEYS='JB?&',
    JSONB_EXISTS='JB?',
    CAST='::',
)


class PostgresqlExtCompiler(QueryCompiler):
    def _create_index(self, model_class, fields, unique=False):
        clause = super(PostgresqlExtCompiler, self)._create_index(
            model_class, fields, unique)
        # Allow fields to specify a type of index.  HStore and Array fields
        # may want to use GiST indexes, for example.
        index_type = None
        for field in fields:
            if isinstance(field, IndexedFieldMixin):
                index_type = field.index_type
        if index_type:
            clause.nodes.insert(-1, SQL('USING %s' % index_type))
        return clause

    def _parse_object_slice(self, node, alias_map, conv):
        sql, params = self.parse_node(node.node, alias_map, conv)
        # Postgresql uses 1-based indexes.
        parts = [str(part + 1) for part in node.parts]
        sql = '%s[%s]' % (sql, ':'.join(parts))
        return sql, params

    def _parse_json_lookup(self, node, alias_map, conv):
        sql, params = self.parse_node(node.node, alias_map, conv)
        lookups = [sql]
        for part in node.parts:
            part_sql, part_params = self.parse_node(
                part, alias_map, conv)
            lookups.append(part_sql)
            params.extend(part_params)

        if node._as_json:
            sql = '->'.join(lookups)
        else:
            # The last lookup should be converted to text.
            head, tail = lookups[:-1], lookups[-1]
            sql = '->>'.join(('->'.join(head), tail))

        return sql, params

    def _parse_json_path(self, node, alias_map, conv):
        sql, params = self.parse_node(node.node, alias_map, conv)
        if node._as_json:
            operand = '#>'
        else:
            operand = '#>>'
        params.append('{%s}' % ','.join(map(str, node.parts)))
        return operand.join((sql, self.interpolation)), params

    def get_parse_map(self):
        parse_map = super(PostgresqlExtCompiler, self).get_parse_map()
        parse_map.update(
            object_slice=self._parse_object_slice,
            json_lookup=self._parse_json_lookup,
            json_path=self._parse_json_path)
        return parse_map


class PostgresqlExtDatabase(PostgresqlDatabase):
    compiler_class = PostgresqlExtCompiler

    def __init__(self, *args, **kwargs):
        self.server_side_cursors = kwargs.pop('server_side_cursors', False)
        self.register_hstore = kwargs.pop('register_hstore', True)
        super(PostgresqlExtDatabase, self).__init__(*args, **kwargs)

    def get_cursor(self, name=None):
        if name:
            return self.get_conn().cursor(name=name)
        return self.get_conn().cursor()

    def execute_sql(self, sql, params=None, require_commit=True,
                    named_cursor=False):
        logger.debug((sql, params))
        use_named_cursor = (named_cursor or (
                            self.server_side_cursors and
                            sql.lower().startswith('select')))
        with self.exception_wrapper():
            if use_named_cursor:
                cursor = self.get_cursor(name=str(uuid.uuid1()))
                require_commit = False
            else:
                cursor = self.get_cursor()
            try:
                cursor.execute(sql, params or ())
            except Exception as exc:
                if self.get_autocommit() and self.autorollback:
                    self.rollback()
                raise
            else:
                if require_commit and self.get_autocommit():
                    self.commit()
        return cursor

    def _connect(self, database, **kwargs):
        conn = super(PostgresqlExtDatabase, self)._connect(database, **kwargs)
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


PostgresqlExtDatabase.register_fields({
    'datetime_tz': 'timestamp with time zone',
    'hash': 'hstore',
    'json': 'json',
    'jsonb': 'jsonb',
    'tsvector': 'tsvector',
})
PostgresqlExtDatabase.register_ops({
    OP.HCONTAINS_DICT: '@>',
    OP.HCONTAINS_KEYS: '?&',
    OP.HCONTAINS_KEY: '?',
    OP.HCONTAINS_ANY_KEY: '?|',
    OP.HKEY: '->',
    OP.HUPDATE: '||',
    OP.ACONTAINS: '@>',
    OP.ACONTAINS_ANY: '&&',
    OP.TS_MATCH: '@@',
    OP.JSONB_CONTAINS: '@>',
    OP.JSONB_CONTAINED_BY: '<@',
    OP.JSONB_CONTAINS_ANY_KEY: '?|',
    OP.JSONB_CONTAINS_ALL_KEYS: '?&',
    OP.JSONB_EXISTS: '?',
    OP.CAST: '::',
})

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
