from peewee import *
from peewee import QueryCompiler, Param, BinaryExpr, dict_update

from psycopg2 import extensions
from psycopg2.extras import register_hstore


class HStoreField(Field):
    db_field = 'hash'

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
        return BinaryExpr(self, OP_HUPDATE, data)

    def delete(self, *keys):
        return fn.delete(self, Param(list(keys)))

    def contains(self, value):
        if isinstance(value, dict):
            return Q(self, OP_HCONTAINS_DICT, Param(value))
        elif isinstance(value, (list, tuple)):
            return Q(self, OP_HCONTAINS_KEYS, Param(value))
        return Q(self, OP_HCONTAINS_KEY, value)


OP_HUPDATE = 120
OP_HCONTAINS_DICT = 121
OP_HCONTAINS_KEYS = 122
OP_HCONTAINS_KEY = 123


class PostgresqlExtCompiler(QueryCompiler):
    def parse_create_index(self, model_class, fields, unique=False):
        parts = super(PostgresqlExtDatabase, self).parse_create_index(
            model_class, fields, unique)
        if any(lambda f: isinstance(f, HStore), fields):
            parts.insert(-1, 'USING GIST')
        return parts


class PostgresqlExtDatabase(PostgresqlDatabase):
    compiler_class = PostgresqlExtCompiler
    expr_overrides = dict_update(PostgresqlDatabase.expr_overrides, {
        OP_HUPDATE: '||',
    })
    field_overrides = dict_update(PostgresqlDatabase.field_overrides, {
        'hash': 'hstore',
    })
    op_overrides = dict_update(PostgresqlDatabase.op_overrides, {
        OP_HCONTAINS_DICT: '@>',
        OP_HCONTAINS_KEYS: '?&',
        OP_HCONTAINS_KEY: '?',
    })

    def _connect(self, database, **kwargs):
        conn = super(PostgresqlExtDatabase, self)._connect(database, **kwargs)
        register_hstore(conn, globally=True)
        return conn
