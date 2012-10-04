from peewee import *

from psycopg2 import extensions
from psycopg2.extras import register_hstore


class HStore(Field):
    db_field = 'hash'

    def keys(self):
        return fn.akeys(self)

    def values(self):
        return fn.avals(self)

    def items(self):
        return fn.hstore_to_matrix(self)

    def slice(self, *args):
        return fn.slice(self, *args)

    def exists(self, key):
        return fn.exist(self, key)

    def defined(self, key):
        return fn.defined(self, key)

    def update(self, **data):
        return BinaryExpr('update', OP_HUPDATE, data)

    def delete(self, key):
        return fn.delete(self, key)

    def contains(self, value):
        if isinstance(value, dict):
            return BinaryExpr(self, OP_HCONTAINS_DICT, value)
        elif isinstance(value, (list, tuple)):
            return BinaryExpr(self, OP_HCONTAINS_KEYS, value)
        return BinaryExpr(self, OP_HCONTAINS_KEY, value)


OP_HUPDATE = 20
OP_HCONTAINS_DICT = 21
OP_HCONTAINS_KEYS = 22
OP_HCONTAINS_KEY = 23

_expr_overrides = dict(PostgresqlDatabase.expr_overrides)
_expr_overrides.update(
    OP_HUPDATE='||',
    OP_HCONTAINS_DICT='@>',
    OP_HCONTAINS_KEYS='?&',
    OP_HCONTAINS_KEY='?',
)
_field_overrides = dict(PostgresqlDatabase.field_overrides)
_field_overrides.update({'hash': 'hstore'})

class PostgresqlExtDatabase(PostgresqlDatabase):
    expr_overrides = _expr_overrides
    field_overrides = _field_overrides

    def _connect(self, database, **kwargs):
        conn = super(PostgresqlExtDatabase, self)._connect(database, **kwargs)
        register_hstore(conn, globally=True)
        return conn

    #def create_index(self, model_class, field_name, unique=False):
    #    field_obj = model_class._meta.fields[field_name]
    #    if isinstance(field_obj, (HStoreField, LTreeField)):
    #        framing = 'CREATE INDEX %(index)s ON %(table)s USING GIST (%(field)s);'
    #    else:
    #        framing = None
    #    self.execute(self.create_index_query(model_class, field_name, unique, framing))
