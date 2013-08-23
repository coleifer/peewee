"""
Collection of postgres-specific extensions, currently including:

* Support for hstore, a key/value type storage
* Support for UUID field
"""
import uuid

from peewee import *
from peewee import dict_update
from peewee import Expression
from peewee import logger
from peewee import Node
from peewee import Param
from peewee import QueryCompiler
from peewee import SelectQuery

from psycopg2 import extensions
from psycopg2.extras import register_hstore


class ObjectSlice(Node):
    def __init__(self, node, parts):
        self.node = node
        self.parts = parts
        super(ObjectSlice, self).__init__()

    def clone_base(self):
        return ObjectSlice(self.node, list(self.parts))

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


class ArrayField(Field):
    def __init__(self, field_class=IntegerField, dimensions=1, *args,
                 **kwargs):
        kwargs['field_class'] = field_class
        kwargs['dimensions'] = dimensions
        self.__field = field_class(*args, **kwargs)
        self.db_field = self.__field.get_db_field()
        super(ArrayField, self).__init__(*args, **kwargs)

    def get_template(self):
        brackets = ('[]' * self.attributes['dimensions'])
        return self.__field.get_template() + brackets

    def field_attributes(self):
        return self.__field.field_attributes()

    def __getitem__(self, value):
        return ObjectSlice.create(self, value)


class DateTimeTZField(DateTimeField):
    db_field = 'datetime_tz'


class HStoreField(Field):
    db_field = 'hash'

    def __init__(self, *args, **kwargs):
        kwargs['index'] = True  # always use an Index
        super(HStoreField, self).__init__(*args, **kwargs)

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


class UUIDField(Field):
    db_field = 'uuid'

    def db_value(self, value):
        return str(value)

    def python_value(self, value):
        return uuid.UUID(value)


OP_HUPDATE = 'H@>'
OP_HCONTAINS_DICT = 'H?&'
OP_HCONTAINS_KEYS = 'H?'
OP_HCONTAINS_KEY = 'H?|'
OP_HCONTAINS_ANY_KEY = 'H||'


class PostgresqlExtCompiler(QueryCompiler):
    def parse_create_index(self, model_class, fields, unique=False):
        parts = super(PostgresqlExtCompiler, self).parse_create_index(
            model_class, fields, unique)
        # If this index is on an HStoreField, be sure to specify the
        # GIST index immediately before the column names.
        if any(map(lambda f: isinstance(f, HStoreField), fields)):
            parts.insert(-1, 'USING GIST')
        return parts

    def _parse(self, node, alias_map, conv):
        sql, params, unknown = super(PostgresqlExtCompiler, self)._parse(
            node, alias_map, conv)
        if unknown and isinstance(node, ObjectSlice):
            unknown = False
            sql, params = self.parse_node(node.node)
            # Postgresql uses 1-based indexes.
            parts = [str(part + 1) for part in node.parts]
            sql = '%s[%s]' % (sql, ':'.join(parts))
        return sql, params, unknown


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
        if use_named_cursor:
            cursor = self.get_cursor(name=str(uuid.uuid1()))
            require_commit = False
        else:
            cursor = self.get_cursor()
        try:
            res = cursor.execute(sql, params or ())
        except Exception as exc:
            logger.error('Error executing query %s (%s)' % (sql, params))
            return self.sql_error_handler(exc, sql, params, require_commit)
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
    'hash': 'hstore',
    'datetime_tz': 'timestamp with time zone',
    'uuid': 'uuid'})
PostgresqlExtDatabase.register_ops({
    OP_HCONTAINS_DICT: '@>',
    OP_HCONTAINS_KEYS: '?&',
    OP_HCONTAINS_KEY: '?',
    OP_HCONTAINS_ANY_KEY: '?|',
    OP_HUPDATE: '||',
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
