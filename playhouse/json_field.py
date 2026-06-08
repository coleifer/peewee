import json

from peewee import *
from peewee import AsIs
from peewee import ColumnBase
from peewee import Expression
from peewee import FieldDatabaseHook
from peewee import Node
from peewee import OP
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

    def set(self, field, keys, value):
        raise NotImplementedError
    def remove(self, field, keys):
        raise NotImplementedError
    def update(self, field, value):
        raise NotImplementedError
    def length(self, field, keys):
        raise NotImplementedError

    # Containment / key predicates, used in WHERE clauses.
    def contains(self, field, keys, value):
        raise NotImplementedError
    def contained_by(self, field, keys, value):
        raise NotImplementedError
    def has_key(self, field, keys, key):
        raise NotImplementedError
    def has_keys(self, field, keys, key_list):
        raise NotImplementedError
    def has_any_keys(self, field, keys, key_list):
        raise NotImplementedError


def _is_container(v):
    return isinstance(v, (dict, list))


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

    def cast_for_case(self, value, dumps):
        # SQLite's CASE-WHEN tolerates a plain wrapped value.
        return None

    def _wrap_value(self, field, value):
        # Wrap a Python value so SQLite stores it as JSON-typed. Containers
        # and JSON null go through fn.json() so the result is JSON-typed
        # (otherwise SQLite stores them as TEXT). Scalars are passed as-is.
        if value is None:
            return fn.json(Value('null', converter=False))
        if _is_container(value):
            return fn.json(field._dumps(value))
        return value

    def set(self, field, keys, value):
        return fn.json_set(
            field,
            self._path(keys),
            self._wrap_value(field, value))

    def remove(self, field, keys):
        return fn.json_remove(field, self._path(keys))

    def length(self, field, keys):
        if keys:
            return fn.json_array_length(field, self._path(keys))
        return fn.json_array_length(field)

    def update(self, field, value):
        # RFC-7396 merge patch. Null values delete keys.
        return fn.json_patch(field, fn.json(field._dumps(value)))


class PostgresqlJSONMethods(BaseJSONMethods):
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

    def _jsonb_wrap(self, field, value):
        adapter = self.database._adapter
        jsonb_cls = adapter.jsonb_type
        if isinstance(value, (adapter.json_type, jsonb_cls)):
            return value
        return jsonb_cls(value, dumps=field._dumps)

    def _path_array(self, keys):
        # Build a text[] from keys for jsonb_set / #- operator.
        parts = [str(k) for k in keys]
        return Cast(AsIs(parts, False), 'text[]')

    def set(self, field, keys, value):
        # jsonb_set(field, '{path}'::text[], value::jsonb, create_missing=true)
        return fn.jsonb_set(
            field,
            self._path_array(keys),
            self._jsonb_wrap(field, value),
            True)

    def remove(self, field, keys):
        return Expression(field, '#-', self._path_array(keys))

    def length(self, field, keys):
        if keys:
            return fn.jsonb_array_length(self.extract(field, keys))
        return fn.jsonb_array_length(field)

    def update(self, field, value):
        # Postgres `||` is a SHALLOW concat.
        return Expression(field, '||', self._jsonb_wrap(field, value))

    def contains(self, field, keys, value):
        lhs = self.extract(field, keys)
        return Expression(lhs, '@>', self._jsonb_wrap(field, value))

    def contained_by(self, field, keys, value):
        lhs = self.extract(field, keys)
        return Expression(lhs, '<@', self._jsonb_wrap(field, value))

    def has_key(self, field, keys, key):
        lhs = self.extract(field, keys)
        return Expression(lhs, '?', Value(key, converter=False))

    def has_keys(self, field, keys, key_list):
        lhs = self.extract(field, keys)
        return Expression(lhs, '?&', AsIs(list(key_list), False))

    def has_any_keys(self, field, keys, key_list):
        lhs = self.extract(field, keys)
        return Expression(lhs, '?|', AsIs(list(key_list), False))


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

    def cast_for_case(self, value, dumps):
        # MySQL/MariaDB infer JSON-column type from the column, no cast needed.
        return None

    def _json_value(self, field, value):
        # Build a JSON-typed expression for use as the value argument to
        # JSON_SET / JSON_MERGE_PATCH / JSON_CONTAINS etc. The bare string
        # form (`Value(dumps(value))`) only works for scalars on MySQL —
        # containers need JSON_COMPACT(?) to be parsed as JSON. Python None
        # needs JSON_COMPACT('null') so we don't trip MySQL's "any-NULL-arg
        # wipes the result" rule on JSON_SET.
        if value is None:
            return fn.JSON_COMPACT(Value('null', converter=False))
        if _is_container(value):
            return fn.JSON_COMPACT(Value(field._dumps(value), converter=False))
        return Value(value, converter=False)

    def set(self, field, keys, value):
        return fn.JSON_SET(field, self._path(keys),
                           self._json_value(field, value))

    def remove(self, field, keys):
        return fn.JSON_REMOVE(field, self._path(keys))

    def length(self, field, keys):
        if keys:
            return fn.JSON_LENGTH(field, self._path(keys))
        return fn.JSON_LENGTH(field)

    def update(self, field, value):
        # RFC-7396 merge patch (MySQL 8.0.7+, MariaDB 10.2.25+). Null values
        # delete keys. Diverges from PG's shallow `||`.
        return fn.JSON_MERGE_PATCH(field, self._json_value(field, value))

    def contains(self, field, keys, value):
        # JSON_CONTAINS returns 0/1; wrap in `= 1` so it composes cleanly in
        # boolean contexts (NOT, AND, etc.).
        path_args = (self._path(keys),) if keys else ()
        call = fn.JSON_CONTAINS(field, self._json_value(field, value),
                                *path_args)
        return Expression(call, OP.EQ, 1)

    def contained_by(self, field, keys, value):
        # Args flipped: is `value` a superset of (sub-extract of) field?
        lhs = self.extract(field, keys) if keys else field
        call = fn.JSON_CONTAINS(self._json_value(field, value), lhs)
        return Expression(call, OP.EQ, 1)

    def has_key(self, field, keys, key):
        # JSON_CONTAINS_PATH(field, 'one', '$.key'). Reuse _path([key]) so the
        # key gets the same escaping as anywhere else.
        path = self._path(tuple(keys) + (key,))
        call = fn.JSON_CONTAINS_PATH(field, 'one', path)
        return Expression(call, OP.EQ, 1)

    def has_keys(self, field, keys, key_list):
        paths = [self._path(tuple(keys) + (k,)) for k in key_list]
        call = fn.JSON_CONTAINS_PATH(field, 'all', *paths)
        return Expression(call, OP.EQ, 1)

    def has_any_keys(self, field, keys, key_list):
        paths = [self._path(tuple(keys) + (k,)) for k in key_list]
        call = fn.JSON_CONTAINS_PATH(field, 'one', *paths)
        return Expression(call, OP.EQ, 1)


class JSONPath(ColumnBase):
    def __init__(self, field, keys=(), as_text=False):
        super(JSONPath, self).__init__()
        self._field = field
        self._keys = tuple(keys)
        self._as_text = as_text

    def clone(self):
        return type(self)(self._field, self._keys, self._as_text)

    def __getitem__(self, key):
        return type(self)(self._field, self._keys + (key,), self._as_text)

    def path(self, *keys):
        return type(self)(self._field, self._keys + keys, self._as_text)

    @Node.copy
    def as_text(self, as_text=True):
        self._as_text = as_text

    def _typed_cast(self, t):
        expr = self._field._helper.extract_text(self._field, self._keys)
        typ_name = self._field._helper.cast_type(t)
        return Cast(expr, typ_name)

    def as_int(self):
        return self._typed_cast('int')
    def as_float(self):
        return self._typed_cast('float')

    def __sql__(self, ctx):
        if self._as_text:
            expr = self._field._helper.extract_text(self._field, self._keys)
        else:
            expr = self._field._helper.extract(self._field, self._keys)
        return ctx.sql(expr)

    def _converter(self, value):
        if self._as_text or value is None:
            return value
        return self._field.python_value(value)

    def __eq__(self, rhs):
        return self._field._compare(self, OP.EQ, OP.IS, rhs, self._as_text)
    def __ne__(self, rhs):
        return self._field._compare(self, OP.NE, OP.IS_NOT, rhs, self._as_text)

    def is_null(self, is_null=True):
        # Default-mode IS NULL on a path needs to catch SQL NULL, missing key,
        # and stored JSON null — same three cases ``== None`` matches.
        is_op = OP.IS if is_null else OP.IS_NOT
        return self._field._compare(self, OP.EQ, is_op, None, self._as_text)

    __hash__ = object.__hash__

    def _in_helper(self, op, rhs):
        if self._as_text:
            return Expression(self, op, list(rhs))
        field = self._field
        rhs = [r if isinstance(r, Node) else field.db_value(r) for r in rhs]
        return Expression(self, op, rhs)
    def in_(self, rhs):
        return self._in_helper(OP.IN, rhs)
    def not_in(self, rhs):
        return self._in_helper(OP.NOT_IN, rhs)

    def _cmp(self, op, rhs):
        # Make RHS canonical for structural compare.
        if self._as_text or isinstance(rhs, Node):
            return Expression(self, op, rhs)
        return Expression(self, op, self._field.db_value(rhs))

    def __lt__(self, rhs): return self._cmp(OP.LT, rhs)
    def __le__(self, rhs): return self._cmp(OP.LTE, rhs)
    def __gt__(self, rhs): return self._cmp(OP.GT, rhs)
    def __ge__(self, rhs): return self._cmp(OP.GTE, rhs)
    def between(self, lo, hi):
        if not self._as_text:
            if not isinstance(lo, Node):
                lo = self._field.db_value(lo)
            if not isinstance(hi, Node):
                hi = self._field.db_value(hi)
        return super(JSONPath, self).between(lo, hi)

    def like(self, rhs):
        return ColumnBase.like(self.as_text(True), rhs)
    def ilike(self, rhs):
        return ColumnBase.ilike(self.as_text(True), rhs)
    def regexp(self, rhs):
        return ColumnBase.regexp(self.as_text(True), rhs)
    def iregexp(self, rhs):
        return ColumnBase.iregexp(self.as_text(True), rhs)
    def startswith(self, rhs):
        return ColumnBase.startswith(self.as_text(True), rhs)
    def endswith(self, rhs):
        return ColumnBase.endswith(self.as_text(True), rhs)

    def contains(self, rhs):
        return self._field._helper.contains(self._field, self._keys, rhs)

    def set(self, value):
        return self._field._helper.set(self._field, self._keys, value)

    def remove(self):
        return self._field._helper.remove(self._field, self._keys)

    def length(self):
        return self._field._helper.length(self._field, self._keys)

    def contained_by(self, value):
        return self._field._helper.contained_by(self._field, self._keys, value)

    def has_key(self, key):
        return self._field._helper.has_key(self._field, self._keys, key)

    def has_keys(self, key_list):
        return self._field._helper.has_keys(self._field, self._keys, key_list)

    def has_any_keys(self, key_list):
        return self._field._helper.has_any_keys(self._field, self._keys,
                                                key_list)


class JSONField(FieldDatabaseHook, Field):
    field_type = 'JSON'

    def __init__(self, dumps=None, loads=None, **kwargs):
        self._dumps = dumps or json.dumps
        self._loads = loads or json.loads
        self._helper = None
        self._wrap = None
        self._read = None
        super(JSONField, self).__init__(**kwargs)

    def _db_hook(self, database):
        if database is None:
            # Clear implementation-specific stuff.
            self._helper = self._wrap = self._read = None
            return
        if isinstance(database, SqliteDatabase):
            cls = SqliteJSONMethods
        elif isinstance(database, MySQLDatabase):
            cls = MySQLJSONMethods
        elif isinstance(database, PostgresqlDatabase):
            cls = PostgresqlJSONMethods
        else:
            raise NotImplementedError('%s is not supported.' % type(database))
        self._helper = cls(database)
        self._wrap = self._helper.make_value_wrapper(self._dumps)
        self._read = self._helper.make_value_reader(self._loads)
        self.field_type = self._helper.field_type

    def db_value(self, value):
        if value is None or isinstance(value, Node):
            return value
        return self._wrap(value) if self._wrap is not None else value

    def python_value(self, value):
        if value is None:
            return value
        return self._read(value) if self._read is not None else value

    def to_value(self, value, case=False):
        # bulk_update() needs a cast.
        if value is None or isinstance(value, Node):
            return value
        if case and self._helper is not None:
            cast = self._helper.cast_for_case(value, self._dumps)
            if cast is not None:
                return cast
        return self.db_value(value)

    def __getitem__(self, key):
        return JSONPath(self, (key,))

    def path(self, *keys):
        return JSONPath(self, keys)

    def _compare(self, lhs, eq_op, is_op, rhs, as_text):
        # Helper for making sure we handle NULLs properly.
        if rhs is None:
            # When operating on a json path, use text extraction so IS NULL
            # catches SQL NULL, missing key, and when the stored value is the
            # JSON 'null'.
            if isinstance(lhs, JSONPath) and not lhs._as_text and \
               self._helper is not None:
                expr = self._helper.extract_text(self, lhs._keys)
                return Expression(expr, is_op, None)
            return Expression(lhs, is_op, None)
        if as_text or isinstance(rhs, Node):
            return Expression(lhs, eq_op, rhs)
        return Expression(lhs, eq_op, self.db_value(rhs))

    def __eq__(self, rhs):
        return self._compare(self, OP.EQ, OP.IS, rhs, False)
    def __ne__(self, rhs):
        return self._compare(self, OP.NE, OP.IS_NOT, rhs, False)
    __hash__ = Field.__hash__

    def length(self):
        return self._helper.length(self, ())

    def update(self, value):
        # RFC-7396 deep merge on SQLite/MySQL/MariaDB; shallow `||` concat on
        # PostgreSQL. Same call, different semantics — see the docs.
        return self._helper.update(self, value)

    def contains(self, value):
        return self._helper.contains(self, (), value)

    def contained_by(self, value):
        return self._helper.contained_by(self, (), value)

    def has_key(self, key):
        return self._helper.has_key(self, (), key)

    def has_keys(self, key_list):
        return self._helper.has_keys(self, (), key_list)

    def has_any_keys(self, key_list):
        return self._helper.has_any_keys(self, (), key_list)
