"""
Collection of postgres-specific extensions, currently including:

* Support for hstore, a key/value type storage
* Support for UUID field
"""
import uuid

from peewee import *
from peewee import dict_update
from peewee import Expr
from peewee import Param
from peewee import QueryCompiler

from psycopg2 import extensions
from psycopg2.extras import register_hstore


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
        return Expr(self, OP_HUPDATE, data)

    def delete(self, *keys):
        return fn.delete(self, Param(list(keys)))

    def contains(self, value):
        if isinstance(value, dict):
            return Expr(self, OP_HCONTAINS_DICT, Param(value))
        elif isinstance(value, (list, tuple)):
            return Expr(self, OP_HCONTAINS_KEYS, Param(value))
        return Expr(self, OP_HCONTAINS_KEY, value)

    def contains_any(self, *keys):
        return Expr(self, OP_HCONTAINS_ANY_KEY, Param(value))


class DateTimeTZField(DateTimeField):
    db_field = 'datetime_tz'


class UUIDField(Field):
    db_field = 'uuid'

    def db_value(self, value):
        return str(value)

    def python_value(self, value):
        return uuid.UUID(value)


OP_HUPDATE = 120
OP_HCONTAINS_DICT = 121
OP_HCONTAINS_KEYS = 122
OP_HCONTAINS_KEY = 123
OP_HCONTAINS_ANY_KEY = 124


class PostgresqlExtCompiler(QueryCompiler):
    def parse_create_index(self, model_class, fields, unique=False):
        parts = super(PostgresqlExtCompiler, self).parse_create_index(
            model_class, fields, unique)
        # If this index is on an HStoreField, be sure to specify the
        # GIST index immediately before the column names.
        if any(map(lambda f: isinstance(f, HStoreField), fields)):
            parts.insert(-1, 'USING GIST')
        return parts


class PostgresqlExtDatabase(PostgresqlDatabase):
    compiler_class = PostgresqlExtCompiler

    def _connect(self, database, **kwargs):
        conn = super(PostgresqlExtDatabase, self)._connect(database, **kwargs)
        register_hstore(conn, globally=True)
        return conn

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
