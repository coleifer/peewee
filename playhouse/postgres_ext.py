"""
Collection of postgres-specific extensions, currently including:

* Support for hstore, a key/value type storage
"""
import uuid

from peewee import *
from peewee import Expression
from peewee import logger
from peewee import Node
from peewee import Param
from peewee import QueryCompiler
from peewee import SelectQuery
from peewee import UUIDField  # For backwards-compatibility.

from psycopg2 import extensions
from psycopg2.extensions import adapt
from psycopg2.extensions import AsIs
from psycopg2.extensions import register_adapter
from psycopg2.extras import register_hstore
try:
    from psycopg2.extras import Json
except:
    Json = None


class _LookupNode(Node):
    def __init__(self, node, parts):
        self.node = node
        self.parts = parts
        super(_LookupNode, self).__init__()

    def clone_base(self):
        return type(self)(self.node, list(self.parts))

class JsonLookup(_LookupNode):
    _node_type = 'json_lookup'

    def __getitem__(self, value):
        return JsonLookup(self.node, self.parts + [value])

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
        '[]'* arr.field.dimensions))
register_adapter(_Array, adapt_array)


class IndexedField(Field):
    def __init__(self, index_type='GiST', *args, **kwargs):
        kwargs.setdefault('index', True)  # By default, use an index.
        super(IndexedField, self).__init__(*args, **kwargs)
        self.index_type = index_type


class ArrayField(IndexedField):
    def __init__(self, field_class=IntegerField, dimensions=1,
                 index_type='GIN', *args, **kwargs):
        self.__field = field_class(*args, **kwargs)
        self.dimensions = dimensions
        self.db_field = self.__field.get_db_field()
        super(ArrayField, self).__init__(
            index_type=index_type, *args, **kwargs)

    def __ddl_column__(self, column_type):
        sql = self.__field.__ddl_column__(column_type)
        sql.value += '[]' * self.dimensions
        return sql

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)

    def contains(self, *items):
        return Expression(self, OP_ACONTAINS, _Array(self, list(items)))

    def contains_any(self, *items):
        return Expression(self, OP_ACONTAINS_ANY, _Array(self, list(items)))


class DateTimeTZField(DateTimeField):
    db_field = 'datetime_tz'


class HStoreField(IndexedField):
    db_field = 'hash'

    def __init__(self, *args, **kwargs):
        super(HStoreField, self).__init__(*args, **kwargs)

    def __getitem__(self, key):
        return Expression(self, OP_HKEY, Param(key))

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
        return Expression(self, OP_HUPDATE, data)

    def delete(self, *keys):
        return fn.delete(self, Param(list(keys)))

    def contains(self, value):
        if isinstance(value, dict):
            return Expression(self, OP_HCONTAINS_DICT, Param(value))
        elif isinstance(value, (list, tuple)):
            return Expression(self, OP_HCONTAINS_KEYS, Param(value))
        return Expression(self, OP_HCONTAINS_KEY, value)

    def contains_any(self, *keys):
        return Expression(self, OP_HCONTAINS_ANY_KEY, Param(value))


class JSONField(Field):
    db_field = 'json'

    def __init__(self, *args, **kwargs):
        if Json is None:
            raise Exception('Your version of psycopg2 does not support JSON.')
        super(JSONField, self).__init__(*args, **kwargs)

    def db_value(self, value):
        return Json(value)

    def __getitem__(self, value):
        return JsonLookup(self, [value])


OP_HKEY = 'key'
OP_HUPDATE = 'H@>'
OP_HCONTAINS_DICT = 'H?&'
OP_HCONTAINS_KEYS = 'H?'
OP_HCONTAINS_KEY = 'H?|'
OP_HCONTAINS_ANY_KEY = 'H||'
OP_ACONTAINS = 'A@>'
OP_ACONTAINS_ANY = 'A||'


class PostgresqlExtCompiler(QueryCompiler):
    def _create_index(self, model_class, fields, unique=False):
        clause = super(PostgresqlExtCompiler, self)._create_index(
            model_class, fields, unique)
        # Allow fields to specify a type of index.  HStore and Array fields
        # may want to use GiST indexes, for example.
        index_type = None
        for field in fields:
            if isinstance(field, IndexedField):
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
        # The last lookup should be converted to text.
        head, tail = lookups[:-1], lookups[-1]
        sql = '->>'.join(('->'.join(head), tail))
        return sql, params

    def get_parse_map(self):
        parse_map = super(PostgresqlExtCompiler, self).get_parse_map()
        parse_map.update(
            object_slice=self._parse_object_slice,
            json_lookup=self._parse_json_lookup)
        return parse_map


class PostgresqlExtDatabase(PostgresqlDatabase):
    compiler_class = PostgresqlExtCompiler

    def __init__(self, *args, **kwargs):
        self.server_side_cursors = kwargs.pop('server_side_cursors', False)
        super(PostgresqlExtDatabase, self).__init__(*args, **kwargs)

    def get_cursor(self, name=None):
        return self.get_conn().cursor(name=name)

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
                res = cursor.execute(sql, params or ())
            except Exception as exc:
                logger.exception('%s %s', sql, params)
                if self.sql_error_handler(exc, sql, params, require_commit):
                    raise
            else:
                if require_commit and self.get_autocommit():
                    self.commit()
        return cursor

    def _connect(self, database, **kwargs):
        conn = super(PostgresqlExtDatabase, self)._connect(database, **kwargs)
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
})
PostgresqlExtDatabase.register_ops({
    OP_HCONTAINS_DICT: '@>',
    OP_HCONTAINS_KEYS: '?&',
    OP_HCONTAINS_KEY: '?',
    OP_HCONTAINS_ANY_KEY: '?|',
    OP_HKEY: '->',
    OP_HUPDATE: '||',
    OP_ACONTAINS: '@>',
    OP_ACONTAINS_ANY: '&&',
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
