import json

from peewee import *
from peewee import __sqlite_version__


class BaseJSONMethods(object):
    field_type = 'JSON'

    def __init__(self, database):
        self.database = database

    def make_value_wrapper(self, dumps):
        def wrapper(value):
            return dumps(value) if value is not None else value
        return wrapper

    def make_value_reader(self, loads):
        def reader(value):
            if isinstance(value, str):
                try:
                    return loads(value)
                except (TypeError, ValueError):
                    pass
            return value
        return reader

    @staticmethod
    def _path(keys):
        parts = ['$']
        for k in keys:
            if isinstance(k, int):
                parts.append('[#%d]' % k if k < 0 else '[%d]' % k)
            else:
                k = str(k).replace('\\', '\\\\').replace('"', '\\"')
                parts.append('."%s"' % k)
        return Value(''.join(parts), converter=False)

    def extract(self, field, keys):
        raise NotImplementedError

    def extract_text(self, field, keys):
        raise NotImplementedError

    def cast_type(self, t):
        raise NotImplementedError

    def cast_for_case(self, value, dumps):
        # Postgres needs to wrap CAST(... AS JSONB) so untyped CASE expressions
        # can assign in to json fields.
        raise NotImplementedError


class SqliteJSONMethods(BaseJSONMethods):
    field_type = 'TEXT'  # Sqlite's affinity rules treat JSON as NUMERIC.

    def __init__(self, database):
        super(SqliteJSONMethods, self).__init__(database)
        if __sqlite_version__ < (3, 38, 0):
            raise NotSupportedError('JSONField requires Sqlite >= 3.38')

    def make_value_wrapper(self, dumps):
        def wrapper(value):
            return fn.json(dumps(value))
        return wrapper

    def extract(self, field, keys):
        return Expression(field, '->', self._path(keys)) if keys else field

    def extract_text(self, field, keys):
        return Expression(field, '->>', self._path(keys)) if keys else field

    def cast_type(self, t):
        return {'int': 'INTEGER', 'float': 'REAL'}[t]

class PostgresJSONMethods(BaseJSONMethods):
    field_type = 'JSONB'

    def make_value_wrapper(self, dumps):
        db = self.database
        adapter = db._adapter
        json_types = (adapter.json_type, adapter.jsonb_type)
        jsonb_cls = adapter.jsonb_type
        def wrapper(value):
            if isinstance(value, json_types):
                return value
            return jsonb_cls(value, dumps=dumps)
        return wrapper

    def make_value_reader(self, loads):
        # psycopg2 and psycopg3 intercepts these coming from the DB, so we
        # can't use any user-provided loads() impl.
        return lambda v: v

    @staticmethod
    def _key(k):
        return Value(k, converter=False)

    def extract(self, field, keys):
        if not keys:
            return field
        node = field
        for k in keys:
            node = Expression(node, '->', self._key(k))
        return node

    def extract_text(self, field, keys):
        if not keys:
            return field
        node = field
        for k in keys[:-1]:
            node = Expression(node, '->', self._key(k))
        return Expression(node, '->>', self._key(keys[-1]))

    def cast_type(self, t):
        return {'int': 'INTEGER', 'float': 'DOUBLE PRECISION'}[t]

    def cast_for_case(self, value, dumps):
        return Cast(Value(dumps(value)), 'JSONB')


class MySQLJSONMethods(BaseJSONMethods):
    field_type = 'JSON'

    def make_value_wrapper(self, dumps):
        # MySQL and MariaDB accept json-encoded str.
        def wrapper(value):
            return Value(dumps(value), converter=False)
        return wrapper

    def extract(self, field, keys):
        if not keys:
            return field
        # json_compact() is needed to normalize on MariaDB.
        return fn.json_compact(fn.json_extract(field, self._path(keys)))

    def extract_text(self, field, keys):
        if not keys:
            return field
        return fn.json_unquote(fn.json_extract(field, self._path(keys)))

    def cast_type(self, t):
        return {'int': 'SIGNED', 'float': 'DOUBLE'}[t]
