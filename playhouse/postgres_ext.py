from peewee import *
from peewee import QueryCompiler, Param, BinaryExpr

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


OP_HUPDATE = 20
OP_HCONTAINS_DICT = 21
OP_HCONTAINS_KEYS = 22
OP_HCONTAINS_KEY = 23

_expr_overrides = dict(PostgresqlDatabase.expr_overrides)
_expr_overrides.update({
    OP_HUPDATE: '||',
})
_field_overrides = dict(PostgresqlDatabase.field_overrides)
_field_overrides.update({'hash': 'hstore'})
_op_overrides = dict(PostgresqlDatabase.op_overrides)
_op_overrides.update({
    OP_HCONTAINS_DICT: '@>',
    OP_HCONTAINS_KEYS: '?&',
    OP_HCONTAINS_KEY: '?',
})

class PostgresqlExtCompiler(QueryCompiler):
    def parse_create_index(self, model_class, fields, unique=False):
        parts = super(PostgresqlExtDatabase, self).parse_create_index(
            model_class, fields, unique)
        if any(lambda f: isinstance(f, HStore), fields):
            parts.insert(-1, 'USING GIST')
        return parts


class PostgresqlExtDatabase(PostgresqlDatabase):
    compiler_class = PostgresqlExtCompiler
    expr_overrides = _expr_overrides
    field_overrides = _field_overrides
    op_overrides = _op_overrides

    def _connect(self, database, **kwargs):
        conn = super(PostgresqlExtDatabase, self)._connect(database, **kwargs)
        register_hstore(conn, globally=True)
        return conn
