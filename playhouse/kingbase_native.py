import os
import ctypes
import importlib.util
import json
import re
from collections.abc import Mapping


def _preload_kingbase_client_libs():
    """
    Ensure Kingbase client shared libraries are loaded before importing the
    ksycopg2 C-extension, so we can run without system-wide ldconfig changes.
    """
    candidates = []
    # The driver is a separate dependency, not part of the Peewee checkout.
    driver_spec = importlib.util.find_spec('ksycopg2')
    if driver_spec and driver_spec.submodule_search_locations:
        for directory in driver_spec.submodule_search_locations:
            candidates.append(os.path.join(directory, 'libkci.so.5'))

    # Also respect explicit LD_LIBRARY_PATH if user set it.
    ld_library_path = os.environ.get('LD_LIBRARY_PATH') or ''
    for entry in [p for p in ld_library_path.split(':') if p]:
        candidates.append(os.path.join(entry, 'libkci.so.5'))

    # Attempt to preload first existing candidate.
    mode = getattr(ctypes, 'RTLD_GLOBAL', 0)
    last_err = None
    for path in candidates:
        if os.path.exists(path):
            try:
                ctypes.CDLL(path, mode=mode)
                return
            except OSError as exc:
                last_err = exc

    if last_err is not None:
        raise ImportError(
            'Failed to preload Kingbase client library libkci.so.5 from: %r '
            '(last error: %s)' % (candidates, last_err))


from peewee import Alias
from peewee import AsIs
from peewee import Cast
from peewee import Case
from peewee import CSQ_PARENTHESES_NEVER
from peewee import ColumnMetadata
from peewee import CompositeKey
from peewee import Context
from peewee import Database
from peewee import DatabaseError
from peewee import EnclosedNodeList
from peewee import Expression
from peewee import Field
from peewee import fn
from peewee import ForeignKeyField
from peewee import ForeignKeyMetadata
from peewee import Join
from peewee import JOIN
from peewee import Model
from peewee import ModelIndex
from peewee import MySQLDatabase
from peewee import MySQLJSONMethods
from peewee import NodeList
from peewee import OP
from peewee import PostgresqlDatabase
from peewee import PostgresqlJSONMethods
from peewee import Psycopg2Adapter
from peewee import SQL
from peewee import Value
from peewee import Insert
from peewee import IndexMetadata
from peewee import ImproperlyConfigured
from peewee import SchemaManager
from peewee import SelectBase
from peewee import ViewMetadata
from peewee import _truncate_constraint_name
from peewee import _BasePsycopgAdapter
from peewee import __exception_wrapper__
from peewee import ensure_tuple
from peewee import is_model
from peewee import sort_models


def _reflected_full_type(data_type, char_length=None, precision=None,
                         scale=None):
    """Keep reflected field length and precision information."""
    full_type = str(data_type)
    if '(' in full_type:
        return full_type
    base = full_type.lower()
    if base in ('char', 'character', 'varchar', 'varchar2',
                'character varying', 'nchar', 'nvarchar2') and char_length:
        return '%s(%s)' % (full_type, char_length)
    if base in ('decimal', 'numeric', 'number') and precision:
        if scale is not None:
            return '%s(%s,%s)' % (full_type, precision, scale)
        return '%s(%s)' % (full_type, precision)
    return full_type


def _catalog_column_details(database, table, schema):
    """Read physical type and identity flags absent from compatibility views."""
    cursor = database.execute_sql(
        'SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), '
        'a.attidentity FROM pg_catalog.pg_attribute a '
        'JOIN pg_catalog.pg_class t ON t.oid = a.attrelid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace '
        'WHERE t.relname = %s AND n.nspname = %s '
        'AND a.attnum > 0 AND NOT a.attisdropped', (table, schema))
    return {name: (full_type, bool(identity))
            for name, full_type, identity in cursor.fetchall()}


def _catalog_foreign_keys(database, table, schema):
    """Use one catalog constraint per key instead of duplicated ALL_* rows."""
    cursor = database.execute_sql(
        'SELECT a.attname, rt.relname, ra.attname, c.conname, '
        'c.confdeltype, c.confupdtype '
        'FROM pg_catalog.pg_constraint c '
        'JOIN pg_catalog.pg_class t ON t.oid = c.conrelid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace '
        'JOIN pg_catalog.pg_class rt ON rt.oid = c.confrelid '
        'JOIN generate_subscripts(c.conkey, 1) AS ord(i) ON TRUE '
        'JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid '
        'AND a.attnum = c.conkey[ord.i] '
        'JOIN pg_catalog.pg_attribute ra ON ra.attrelid = rt.oid '
        'AND ra.attnum = c.confkey[ord.i] '
        "WHERE c.contype = 'f' AND t.relname = %s AND n.nspname = %s "
        'ORDER BY c.conname, ord.i', (table, schema))
    actions = {'a': 'NO ACTION', 'r': 'RESTRICT', 'c': 'CASCADE',
               'n': 'SET NULL', 'd': 'SET DEFAULT'}
    return [ForeignKeyMetadata(column, dest_table, dest_column, table,
                               name, actions[delete], actions[update])
            for column, dest_table, dest_column, name, delete, update
            in cursor.fetchall()]


def _mysql_reflected_full_type(data_type, char_length, precision, scale):
    """Expose MySQL-compatible declarations despite PostgreSQL catalog types."""
    base = str(data_type).lower()
    if base in ('boolean', 'bool'):
        return 'tinyint(1)'
    if base in ('numeric', 'number'):
        base = 'decimal'
    return _reflected_full_type(base, char_length, precision, scale)


def _field_unique_index(index, model):
    """Identify Peewee's implicit, single-field UNIQUE index."""
    if not isinstance(index, ModelIndex) or not index._unique:
        return False
    if len(index._expressions) != 1:
        return False
    field = index._expressions[0]
    if not getattr(field, 'unique', False) or field.primary_key:
        return False
    if field.model is not model or field.index_type is not None:
        return False
    return index._name == ModelIndex(model, (field,), unique=True)._name


def _schema_index_exists(schema, name):
    meta = schema.model._meta
    name = _catalog_identifier(name)
    return any(index.name == name for index in schema.database.get_indexes(
        meta.table_name, meta.schema))


def _create_kingbase_indexes(schema, safe, skip_field_uniques=False):
    """Create indexes once; a UNIQUE constraint covers simple unique fields."""
    meta = schema.model._meta
    existing = ({index.name for index in schema.database.get_indexes(
        meta.table_name, meta.schema)} if safe else set())
    for index in schema.model._meta.fields_to_index():
        if skip_field_uniques and _field_unique_index(index, schema.model):
            continue
        name = getattr(index, '_name', None)
        catalog_name = _catalog_identifier(name) if name else None
        if safe and catalog_name in existing:
            continue
        try:
            schema.database.execute(schema._create_index(index, safe=safe))
        except DatabaseError:
            if safe and name and _schema_index_exists(schema, name):
                continue
            raise
        if catalog_name:
            existing.add(catalog_name)


def _schema_constraint_exists(schema, name, kind):
    meta = schema.model._meta
    cursor = schema.database.execute_sql(
        'SELECT 1 FROM pg_catalog.pg_constraint c '
        'JOIN pg_catalog.pg_class t ON t.oid = c.conrelid '
        'JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace '
        'WHERE LOWER(c.conname) = LOWER(%s) AND c.contype = %s '
        'AND t.relname = %s AND n.nspname = %s',
        (_catalog_identifier(name), kind, meta.table_name,
         meta.schema or 'public'))
    return cursor.fetchone() is not None


def _catalog_identifier(name):
    return str(name).encode('utf-8')[:63].decode('utf-8', 'ignore')


def _catalog_foreign_key_name(field):
    # Peewee limits generated constraint names to 64 characters, while the
    # server's PostgreSQL catalog stores at most 63 bytes of the identifier.
    name = _truncate_constraint_name(field.get_constraint_name())
    return _catalog_identifier(name)

class KingbasePsycopg2Adapter(Psycopg2Adapter):
    """Use Peewee's PG transaction behavior with KES driver value types."""

    txn_idle = 0
    txn_inerror = 3
    txn_unknown = 4
    cast_json_case = True

    def __init__(self):
        _BasePsycopgAdapter.__init__(self)
        # KES is an optional dependency; resolve its value adapters on use.

    @property
    def json_type(self):
        _preload_kingbase_client_libs()
        from ksycopg2.extras import Json
        return Json

    jsonb_type = json_type

    def get_binary_type(self):
        _preload_kingbase_client_libs()
        from ksycopg2 import Binary
        return Binary


# 2. 定义金仓原生数据库引擎
class KingbaseDatabase(PostgresqlDatabase):
    """
    人大金仓原生 Peewee 数据库引擎
    """

    def init(self, database, encoding=None, isolation_level=None, **kwargs):
        """
        Bypass PostgresqlDatabase.init()'s psycopg adapter selection.
        The synchronous Kingbase client is imported lazily so this module can
        still be imported in async-only environments.
        """
        self._encoding = encoding
        # Peewee's PostgreSQL helpers now delegate transaction and JSON
        # behavior to an adapter. Keep that API while routing connections
        # through ksycopg2 in _connect() below.
        self._adapter = KingbasePsycopg2Adapter()
        self._isolation_level = self._adapter.isolation_level_int(
            isolation_level)
        Database.init(self, database, **kwargs)

    def _connect(self):
        """
        【核心改造】重写底层连接方法，并将 ksycopg2 改为按需导入。
        """
        try:
            _preload_kingbase_client_libs()
            import ksycopg2
        except ImportError as exc:
            raise ImproperlyConfigured(
                'ksycopg2 is required for synchronous KingbaseDatabase connections '
                'but is not installed in this environment.'
            ) from exc

        # 注意：ksycopg2 的连接参数中，数据库名通常叫 dbname，而 Peewee 内部叫 database
        # 所以我们需要在这里做一个映射转换
        conn_kwargs = self.connect_params.copy()
        # Map Peewee "database" to driver "dbname".
        if 'dbname' not in conn_kwargs and self.database:
            conn_kwargs['dbname'] = self.database
        conn_kwargs.pop('database', None)

        # 真正发起底层连接
        conn = ksycopg2.connect(**conn_kwargs)
        if self._isolation_level is not None:
            try:
                conn.set_isolation_level(self._isolation_level)
            except Exception:
                pass
        try:
            conn.autocommit = True
        except Exception:
            pass
        return conn

    def _set_server_version(self, conn):
        """
        重写版本获取逻辑：某些早期版本的同步驱动可能不支持原生的
        server_version 属性。为了稳妥，我们在这里手动获取或设置默认值。
        """
        try:
            self.server_version = conn.server_version
        except AttributeError:
            self.server_version = 90000  # 默认设置为金仓 V9 的兼容数字版本

    def _initialize_connection(self, conn):
        # Best-effort type registration for consistent Python decoding.
        # Keep this non-fatal so older ksycopg2 builds still work.
        try:
            from ksycopg2.extras import register_default_json
            register_default_json(conn, loads=json.loads)
        except Exception:
            pass
        try:
            from ksycopg2.extras import register_default_jsonb
            register_default_jsonb(conn, loads=json.loads)
        except Exception:
            pass
        try:
            from ksycopg2.extras import register_uuid
            register_uuid(conn_or_curs=conn)
        except Exception:
            pass

    def begin(self, isolation_level=None):
        if isolation_level is None:
            isolation_level = self._isolation_level
        if isolation_level:
            txn_type = self._adapter.isolation_level_str(isolation_level)
            stmt = 'BEGIN TRANSACTION ISOLATION LEVEL %s' % txn_type
        else:
            stmt = 'BEGIN'
        with __exception_wrapper__:
            self.cursor().execute(stmt)

    def last_insert_id(self, cursor, query_type=None):
        # MERGE has no result set even when Peewee prepared implicit PK
        # returning for an ordinary INSERT. Peewee wraps returned INSERT
        # cursors, so inspect the underlying DB-API cursor's description.
        raw_cursor = getattr(cursor, 'cursor', cursor)
        if getattr(raw_cursor, 'description', None) is None:
            return None
        return super(KingbaseDatabase, self).last_insert_id(
            cursor, query_type)


class KingbaseMySQLCompiler(Context):
    """
    Kingbase MySQL 模式走 PG 协议：裸 ``CAST(x AS CHAR)`` 等价于 ``CHAR(1)``，
    而 Peewee 官方 MySQL 测试期望 ``CHAR`` 为可变长字符串。在此将无长度
    ``CHAR`` 重写为 ``CHAR(255)``，并保留 Peewee 原生别名语义。
    """

    _BARE_CHAR_CAST = 'CHAR(255)'

    def sql(self, obj):
        if isinstance(obj, Expression) and obj.op == OP.CONCAT:
            return (self.literal('CONCAT(').sql(obj.lhs)
                    .literal(', ').sql(obj.rhs).literal(')'))
        if isinstance(obj, Cast):
            return self._sql_cast(obj)
        if isinstance(obj, Join):
            return self._sql_join(obj)
        return super(KingbaseMySQLCompiler, self).sql(obj)

    def _sql_cast(self, cast_node):
        cast_type = cast_node._cast
        if isinstance(cast_type, str) and cast_type.upper() == 'CHAR':
            cast_type = self._BARE_CHAR_CAST
        return (self
                .literal('CAST(')
                .sql(cast_node.node)
                .literal(' AS %s)' % cast_type))

    def _sql_join(self, join_node):
        self.sql(join_node.lhs)
        self.literal(' %s ' % join_node.join_type)
        self.sql(join_node.rhs)
        if join_node._on is not None:
            self.literal(' ON ').sql(join_node._on)
        return self


class KingbaseMySQLCursorWrapper(object):
    def __init__(self, cursor, alias_map=None):
        self.cursor = cursor
        self.alias_map = alias_map or {}
        self._description = None

    @staticmethod
    def _clone_description_item(item, name):
        if not item:
            return item
        try:
            return tuple([name] + list(item[1:]))
        except Exception:
            return item

    @property
    def description(self):
        if self._description is None:
            description = getattr(self.cursor, 'description', None)
            if not description:
                return description
            patched = []
            for item in description:
                name = item[0]
                if name:
                    mapped = self.alias_map.get(str(name).lower())
                    if mapped:
                        item = self._clone_description_item(item, mapped)
                patched.append(item)
            self._description = tuple(patched)
        return self._description

    def __getattr__(self, attr):
        return getattr(self.cursor, attr)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size=None):
        return self.cursor.fetchmany(size)

    def __iter__(self):
        return iter(self.cursor)


class KingbaseMySQLSchemaManager(SchemaManager):
    """
    金仓 MySQL 模式 + ksycopg2 的 Schema 拦截器（延后 FK + UNIQUE CONSTRAINT）。

    问题：Peewee 默认在 CREATE TABLE 中内联 FOREIGN KEY；金仓经 ksycopg2 做
    PG 式约束校验时，对「引用非主键 UNIQUE 列」常报 InvalidForeignKey。
    且 Peewee 的 ``unique=True`` 通常只生成 UNIQUE INDEX，金仓 FK 要求
    UNIQUE CONSTRAINT。

    做法：
      1. ``_create_table`` 只建列与 PRIMARY KEY 等，不写内联 FK；
      2. ``create_indexes`` 先建索引；
      3. ``ensure_unique_constraints`` 为 unique 列补 UNIQUE CONSTRAINT；
      4. ``create_deferred_foreign_keys`` 用 ALTER TABLE 补 FK。
    """

    def _create_table(self, safe=True, **options):
        """与 SchemaManager._create_table 相同，但省略内联 FOREIGN KEY。"""
        is_temp = options.pop('temporary', False)
        ctx = self._create_context()
        ctx.literal('CREATE TEMPORARY TABLE ' if is_temp else 'CREATE TABLE ')
        if safe:
            ctx.literal('IF NOT EXISTS ')
        ctx.sql(self.model).literal(' ')

        columns = []
        constraints = []
        meta = self.model._meta
        if meta.composite_key:
            pk_columns = [meta.fields[field_name].column
                          for field_name in meta.primary_key.field_names]
            constraints.append(NodeList((SQL('PRIMARY KEY'),
                                         EnclosedNodeList(pk_columns))))

        for field in meta.sorted_fields:
            columns.append(field.ddl(ctx))
            # 内联 FK 交由 create_deferred_foreign_keys() 延后创建。

        if meta.constraints:
            constraints.extend(meta.constraints)

        constraints.extend(self._create_table_option_sql(options))
        ctx.sql(EnclosedNodeList(columns + constraints))

        if meta.table_settings is not None:
            table_settings = ensure_tuple(meta.table_settings)
            for setting in table_settings:
                if not isinstance(setting, str):
                    raise ValueError('table_settings must be strings')
                ctx.literal(' ').literal(setting)

        extra_opts = []
        if meta.strict_tables:
            extra_opts.append('STRICT')
        if meta.without_rowid:
            extra_opts.append('WITHOUT ROWID')
        if extra_opts:
            ctx.literal(' %s' % ', '.join(extra_opts))
        return ctx

    def _foreign_key_fields(self):
        return [
            field for field in self.model._meta.sorted_fields
            if isinstance(field, ForeignKeyField) and not field.deferred
        ]

    def ensure_unique_constraints(self, safe=True):
        """
        金仓 ksycopg2 路径下，Peewee 的 field.unique 仅生成 UNIQUE INDEX，
        外键引用非主键列时必须有 UNIQUE CONSTRAINT。在此显式补齐。
        """
        meta = self.model._meta
        table = meta.table_name
        for field in meta.sorted_fields:
            if not field.unique or field.primary_key:
                continue
            cname = ModelIndex(self.model, (field,), unique=True)._name
            legacy_name = _catalog_identifier(
                '%s_%s_key' % (table, field.column_name))
            if safe and (_schema_constraint_exists(self, cname, 'u') or
                         _schema_constraint_exists(self, legacy_name, 'u')):
                continue
            sql = (
                'ALTER TABLE `%s` ADD CONSTRAINT `%s` UNIQUE (`%s`)'
                % (table, cname, field.column_name))
            try:
                self.database.execute_sql(sql)
            except DatabaseError:
                if safe and _schema_constraint_exists(self, cname, 'u'):
                    continue
                raise

    def create_deferred_foreign_keys(self, safe=True):
        """对已存在的表执行 ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY。"""
        for field in self._foreign_key_fields():
            cname = _catalog_foreign_key_name(field)
            if safe and _schema_constraint_exists(self, cname, 'f'):
                continue
            try:
                self.create_foreign_key(field)
            except DatabaseError:
                if safe and _schema_constraint_exists(self, cname, 'f'):
                    continue
                raise

    def create_indexes(self, safe=True, skip_field_uniques=False):
        _create_kingbase_indexes(self, safe, skip_field_uniques)

    def create_all(self, safe=True, **table_options):
        self.create_sequences()
        self.create_table(safe, **table_options)
        self.create_indexes(safe=safe, skip_field_uniques=True)
        # A UNIQUE constraint creates its own index; avoid a duplicate index.
        self.ensure_unique_constraints(safe=safe)
        self.create_deferred_foreign_keys(safe=safe)


class KingbaseMySQLJSONMethods(MySQLJSONMethods):
    def set(self, field, keys, value):
        # V9R3C18's JSON_SET writes a nested missing key at the root when
        # its parent is absent. MySQL leaves the document unchanged.
        result = super(KingbaseMySQLJSONMethods, self).set(field, keys, value)
        if len(keys) < 2:
            return result
        parent_exists = fn.JSON_CONTAINS_PATH(field, 'one',
                                               self._path(keys[:-1]))
        return Case(None, ((parent_exists, result),), field)


class KingbaseOracleJSONMethods(PostgresqlJSONMethods):
    def update(self, field, value):
        # Oracle mode resolves JSONB || JSONB as varchar concatenation. For
        # JSON objects, apply the same shallow, last-key-wins merge with
        # jsonb_set(), which is available in this compatibility mode.
        if not isinstance(value, Mapping):
            return super(KingbaseOracleJSONMethods, self).update(field, value)
        result = field
        for key, item in value.items():
            result = self.set(result, (key,), item)
        return result


class KingbaseMySQLDatabase(MySQLDatabase):
    # The PostgreSQL wire cursor's lastrowid is an OID, while the MySQL-mode
    # LAST_INSERT_ID() does not report explicitly supplied primary keys.
    # Kingbase supports RETURNING for both explicit and generated keys.
    # Keep Peewee's MySQL return contract for bulk inserts and SQL generation.
    # Only simple INSERTs need a private RETURNING clause for reliable keys.
    returning_clause = False
    # The PostgreSQL wire driver returns VARBINARY as an encoded string,
    # whereas BYTEA comes back as a memoryview understood by BinaryUUIDField.
    field_types = dict(MySQLDatabase.field_types, UUIDB='BYTEA')
    json_methods = KingbaseMySQLJSONMethods
    # The server accepts OFFSET without LIMIT; Peewee's MySQL limit_max is
    # 2**64-1 and overflows the server's signed BIGINT parser.
    limit_max = None
    # In this version sql_mode accepts one mode token, so compile CONCAT in
    # the dialect and use the strict mode needed for NOT NULL enforcement.
    sql_mode = 'STRICT_ALL_TABLES'
    # 挂载定制的 DDL 引擎，解决外键约束报错
    # （Peewee 原生不读 schema_class；create_tables/bind 会实际使用它）
    schema_class = KingbaseMySQLSchemaManager
    # 挂载定制的语法树编译器，解决 CAST 等问题
    context_class = KingbaseMySQLCompiler

    @property
    def introspector_class(self):
        from playhouse.kingbase_reflection import KingbaseIntrospector
        return KingbaseIntrospector

    @property
    def schema_migrator_class(self):
        # Resolve on demand: kingbase_migrate imports playhouse.migrate.
        from playhouse.kingbase_migrate import KingbaseMySQLMigrator
        return KingbaseMySQLMigrator

    def init(self, database, sql_mode=None, **kwargs):
        # MySQLDatabase passes sql_mode as a driver argument. Keep it as a
        # session setting instead; ksycopg2 does not accept that argument.
        kwargs['sql_mode'] = self.sql_mode if sql_mode is None else sql_mode
        super(KingbaseMySQLDatabase, self).init(database, **kwargs)

    def _alias_map(self, query):
        alias_map = {}
        try:
            selected = list(getattr(query, '_returning', ()) or ())
        except Exception:
            selected = []
        for node in selected:
            alias = getattr(node, '_alias', None)
            if isinstance(alias, str) and alias:
                alias_map[alias.lower()] = alias
            name = getattr(node, 'name', None)
            if isinstance(name, str) and name:
                alias_map.setdefault(str(name).lower(), name)
        return alias_map

    def _wrap_cursor(self, cursor, query=None):
        alias_map = self._alias_map(query) if query is not None else {}
        return KingbaseMySQLCursorWrapper(cursor, alias_map=alias_map)

    def get_cursor_wrapper(self, cursor, query=None):
        return self._wrap_cursor(cursor, query=query)

    def execute_sql(self, sql, params=None):
        return super(KingbaseMySQLDatabase, self).execute_sql(sql, params)

    def execute(self, query, **context_options):
        ctx = self.get_sql_context(**context_options)
        sql, params = ctx.sql(query).query()
        if (isinstance(query, Insert) and
                query._query_type in (Insert.SIMPLE, Insert.MULTI) and
                query._returning is None and not query._as_rowcount and
                (query._on_conflict is None or
                 query._on_conflict._update or
                 query._on_conflict._preserve) and
                getattr(query.table, '_meta', None) is not None):
            pk = query.table._meta.primary_key
            if isinstance(pk, Field) and not isinstance(pk, CompositeKey):
                sql += ' RETURNING `%s`' % pk.column_name.replace('`', '``')
        return self.execute_sql(sql, params)

    def _install_schema(self, model):
        """将模型的 SchemaManager 替换为金仓延后 FK 版本。"""
        model._schema = self.schema_class(model, database=self)

    def bind(self, models, bind_refs=True, bind_backrefs=True):
        """绑定模型时替换 SchemaManager，保证单表 create_table 也走延后 FK。"""
        super(KingbaseMySQLDatabase, self).bind(
            models, bind_refs=bind_refs, bind_backrefs=bind_backrefs)
        for model in models:
            self._install_schema(model)

    def create_tables(self, models, **options):
        """批量建表：统一经 KingbaseMySQLSchemaManager（含 UNIQUE + 延后 FK）。

        注意：不永久替换 model._schema，以免官方用例断言内联 FK 的
        ``_create_table().query()`` 结果被改写。
        """
        for model in sort_models(models):
            self.schema_class(model, database=self).create_all(**options)

    @property
    def Model(self):
        """通过 db.Model 定义的模型默认使用延后 FK 的 Schema 管理器。"""
        if not hasattr(self, '_KingbaseMySQLModel'):
            class Meta:
                database = self
                schema_manager_class = KingbaseMySQLSchemaManager
            self._KingbaseMySQLModel = type(
                'BaseModel', (Model,), {'Meta': Meta})
        return self._KingbaseMySQLModel

    def _connect(self):
        """1. 过滤 DSN 参数，建立纯净底层连接"""
        try:
            _preload_kingbase_client_libs()
            import ksycopg2
        except ImportError as exc:
            raise ImproperlyConfigured(
                'ksycopg2 is required for synchronous KingbaseMySQLDatabase '
                'connections but is not installed in this environment.') from exc

        conn_kwargs = self.connect_params.copy()
        sql_mode = conn_kwargs.pop('sql_mode', None)
        # Peewee 库名在 self.database；ksycopg2 需要 dbname。
        if 'dbname' not in conn_kwargs and self.database:
            conn_kwargs['dbname'] = self.database
        conn_kwargs.pop('database', None)

        # 清理 ksycopg2 不认识的 MySQL 专属参数
        for key in ['charset', 'use_unicode',
                    'client_flag', 'compress', 'interactive']:
            conn_kwargs.pop(key, None)

        conn = ksycopg2.connect(**conn_kwargs)
        conn.autocommit = True
        # Peewee DateField/TimestampField 测试用 calendar.timegm() 按 UTC 解释
        # naive datetime；金仓 MySQL 模式默认 session 常为 UTC+8，UNIX_TIMESTAMP /
        # FROM_UNIXTIME 会与官方 MySQL 用例差 28800s。仅改连接级 time_zone，不动
        # 实例全局配置。
        try:
            with conn.cursor() as cursor:
                cursor.execute("SET time_zone = '+00:00'")
                # MySQL's default is REPEATABLE READ. Kingbase starts at
                # READ COMMITTED, which changes snapshots for ordinary
                # Peewee atomic() blocks and official transaction tests.
                cursor.execute(
                    'SET SESSION CHARACTERISTICS AS TRANSACTION '
                    'ISOLATION LEVEL REPEATABLE READ')
                if sql_mode:
                    sql_mode = str(sql_mode).upper()
                    if not re.fullmatch(
                            r'[A-Z][A-Z0-9_]*(?:,[A-Z][A-Z0-9_]*)*',
                            sql_mode):
                        raise ImproperlyConfigured(
                            'Kingbase MySQL sql_mode contains an invalid token.')
                    cursor.execute("SET sql_mode = '%s'" % sql_mode)
        except BaseException:
            conn.close()
            raise
        return conn

    def _set_server_version(self, conn):
        """2. 【版本伪造补丁】跳过 ksycopg2 的整数版本导致 .lower() 报错"""
        self.server_version = (8, 0, 0)

    def _normalize_schema_name(self, schema=None):
        # MySQL calls the current database a schema; the wire-protocol
        # catalog stores its objects in the PostgreSQL ``public`` namespace.
        if schema is None or str(schema).lower() in (
                'public', str(self.database).lower()):
            return 'public'
        return schema

    def get_tables(self, schema=None):
        schema = self._normalize_schema_name(schema)
        cursor = self.execute_sql(
            'SELECT table_name FROM information_schema.tables '
            'WHERE table_schema = %s AND table_type = %s '
            'ORDER BY table_name',
            (schema, 'BASE TABLE'))
        return [table for table, in cursor.fetchall()]

    def get_views(self, schema=None):
        schema = self._normalize_schema_name(schema)
        cursor = self.execute_sql(
            'SELECT v.table_name, v.view_definition '
            'FROM information_schema.views v '
            'JOIN pg_catalog.pg_views p ON p.schemaname = v.table_schema '
            'AND p.viewname = v.table_name '
            "WHERE v.table_schema = %s AND LOWER(p.viewowner) <> 'system' "
            'ORDER BY v.table_name',
            (schema,))
        return [ViewMetadata(name, sql) for name, sql in cursor.fetchall()]

    def get_indexes(self, table, schema=None):
        # The MySQL parent issues SHOW INDEX, which is not accepted by the
        # Kingbase server even in MySQL compatibility mode. Its metadata
        # contract also has no SQL definition, unlike PostgreSQL metadata.
        indexes = PostgresqlDatabase.get_indexes(
            self, table, self._normalize_schema_name(schema))
        def normalize_column(column):
            # MySQL metadata exposes column names, not SQL identifier syntax.
            # The PostgreSQL catalog quotes reserved names such as `position`.
            if column.startswith('`') and column.endswith('`'):
                return column[1:-1].replace('``', '`')
            return column
        return [IndexMetadata(index.name, None,
                              [normalize_column(c) for c in index.columns],
                              index.unique, index.table) for index in indexes]

    def get_primary_keys(self, table, schema=None):
        schema = self._normalize_schema_name(schema)
        cursor = self.execute_sql(
            'SELECT kc.column_name FROM information_schema.table_constraints tc '
            'JOIN information_schema.key_column_usage kc ON '
            'tc.constraint_name = kc.constraint_name AND '
            'tc.table_schema = kc.table_schema AND '
            'tc.table_name = kc.table_name '
            'WHERE tc.constraint_type = %s AND tc.table_schema = %s '
            'AND tc.table_name = %s ORDER BY kc.ordinal_position',
            ('PRIMARY KEY', schema, table))
        return [name for name, in cursor.fetchall()]

    def get_foreign_keys(self, table, schema=None):
        return _catalog_foreign_keys(
            self, table, self._normalize_schema_name(schema))

    def get_columns(self, table, schema=None):
        schema = self._normalize_schema_name(schema)
        query = (
            'SELECT column_name, data_type, is_nullable, column_default, '
            'character_maximum_length, numeric_precision, numeric_scale '
            'FROM information_schema.columns '
            'WHERE table_schema = %s AND table_name = %s '
            'ORDER BY ordinal_position')
        cursor = self.execute_sql(query, (schema, table))
        rows = cursor.fetchall()
        primary_keys = set(self.get_primary_keys(table, schema))
        catalog = _catalog_column_details(self, table, schema)
        columns = []
        for (name, data_type, null, default, char_length, precision,
             scale) in rows:
            _, identity = catalog.get(name, (None, False))
            columns.append(ColumnMetadata(
                name=name,
                data_type=data_type,
                null=(str(null).upper() == 'YES'),
                primary_key=name in primary_keys,
                table=table,
                default=default,
                full_type=_mysql_reflected_full_type(
                    data_type, char_length, precision, scale),
                identity=identity or bool(default and str(default).startswith(
                    ('nextval(', 'unique_rowid(')))))
        return columns

    def last_insert_id(self, cursor, query_type):
        """Read the key from a private RETURNING clause without extra SQL."""
        if cursor.description:
            row = cursor.fetchone()
            if row is not None:
                return row[0]
        return cursor.lastrowid

    def table_exists(self, table_name, schema=None):
        """
        4. 【优雅的元数据补丁】抛弃 MySQL 的 DATABASE()
        利用底层的 information_schema 跨维度查询表是否存在
        """
        if is_model(table_name):
            schema = table_name._meta.schema
            table_name = table_name._meta.table_name
        schema = self._normalize_schema_name(schema)
        query = """
            SELECT 1 FROM information_schema.tables
            WHERE table_name = %s
            AND table_schema = %s
        """
        cursor = self.execute_sql(query, (table_name, schema))
        return cursor.fetchone() is not None

    def get_binary_type(self):
        """
        官方 tests 在加载 BlobField 时会调用 database.get_binary_type()。
        MySQLDatabase 默认返回 PyMySQL 的 mysql.Binary；金仓走 ksycopg2 时需改用
        ksycopg2.extensions.Binary，否则在未安装 pymysql 时导入 tests 包即报错。
        """
        try:
            from ksycopg2.extensions import Binary
            return Binary
        except ImportError:
            return bytes


class KingbaseOracleCompiler(Context):
    """Oracle 兼容模式的 SQL 渲染入口。"""

    def sql(self, obj):
        if isinstance(obj, Insert) and getattr(obj, '_on_conflict', None) is not None:
            if self._is_replace_insert(obj):
                return self._sql_merge_insert(obj)
        return super(KingbaseOracleCompiler, self).sql(obj)

    @staticmethod
    def _is_replace_insert(query):
        on_conflict = getattr(query, '_on_conflict', None)
        return bool(on_conflict and (on_conflict._action or '').upper() == 'REPLACE')

    @staticmethod
    def _merge_alias_name(column):
        name = getattr(column, 'column_name', None) or getattr(column, 'name', None) or str(column)
        if '.' in name:
            name = name.rsplit('.', 1)[-1]
        return name.strip('"')

    def _merge_unique_targets(self, table):
        """Return model-declared keys that can identify an entire MERGE row.

        A partial or expression-based unique index does not establish that
        equality on the inserted columns identifies a row unconditionally.
        """
        meta = table._meta
        candidates = []
        seen = set()

        def add(fields):
            if not fields or not all(
                    isinstance(field, Field) and
                    meta.columns.get(field.column_name) is field
                    for field in fields):
                return
            names = tuple(field.column_name for field in fields)
            key = frozenset(names)
            if len(key) != len(names) or key in seen:
                return
            candidates.append(names)
            seen.add(key)

        add(meta.get_primary_keys())
        for index in meta.fields_to_index():
            if (isinstance(index, ModelIndex) and index._unique and
                    index._where is None):
                add(index._expressions)
        return candidates

    def _render_merge_source(self, rows, columns, defaults):
        row_sqls = []
        row_params = []
        for row in rows:
            select_parts = []
            for i, col in enumerate(columns):
                from_default = False
                if isinstance(row, Mapping):
                    for key in (col, getattr(col, 'name', None),
                                getattr(col, 'column_name', None)):
                        if key in row:
                            value = row[key]
                            break
                    else:
                        if col in defaults:
                            value = defaults[col]
                            from_default = True
                        elif getattr(col, 'null', False):
                            value = None
                        else:
                            raise ValueError('Missing value for %s.' % col.name)
                else:
                    if i < len(row):
                        value = row[i]
                    elif col in defaults:
                        value = defaults[col]
                        from_default = True
                    elif getattr(col, 'null', False):
                        value = None
                    else:
                        raise ValueError('Missing value for %s.' % col.name)
                if from_default and callable(value):
                    value = value()
                alias = self._merge_alias_name(col)
                value_ctx = self.as_new()
                converter = col.db_value if isinstance(col, Field) else None
                value_ctx.sql(Value(value, converter=converter, unpack=False))
                select_parts.append(''.join(value_ctx._sql) + ' AS "%s"' % alias)
                row_params.extend(value_ctx._values)
            row_sqls.append('SELECT ' + ', '.join(select_parts) + ' FROM DUAL')
        if len(row_sqls) == 1:
            return row_sqls[0], row_params
        return ' UNION ALL '.join(row_sqls), row_params

    def _sql_merge_insert(self, query):
        table = query.table
        rows = query._insert
        if isinstance(rows, Mapping):
            rows = [rows]
        elif not isinstance(rows, (list, tuple)):
            rows = [rows]

        defaults = query.get_default_data()
        columns = query._columns
        if not columns and rows and all(isinstance(row, Mapping) for row in rows):
            # get_default_columns() also contains fields absent from a sparse
            # replace(). Such fields must not become NULL-valued MERGE input or
            # count as inferable conflict targets.
            row_names = {self._merge_alias_name(key) for key in rows[0]}
            names = row_names | {self._merge_alias_name(key) for key in defaults}
            if any({self._merge_alias_name(key) for key in row} != row_names
                   for row in rows[1:]):
                raise ValueError('Oracle MERGE rows must use the same columns.')
            columns = [field for field in table._meta.sorted_fields
                       if self._merge_alias_name(field) in names]
        elif columns:
            columns = [getattr(table, col) if isinstance(col, str) else col
                       for col in columns]
            supplied = {self._merge_alias_name(col) for col in columns}
            columns.extend(field for field in defaults
                           if self._merge_alias_name(field) not in supplied)
        if not columns:
            columns = query.get_default_columns()
        if not columns:
            raise ValueError('Oracle MERGE rewrite requires explicit columns.')

        conflict = getattr(query, '_on_conflict', None)
        target_columns = None
        meta = table._meta
        candidates = self._merge_unique_targets(table)
        inserted_names = {self._merge_alias_name(col) for col in columns}
        if conflict is not None and getattr(conflict, '_conflict_target', None):
            target = []
            for col in conflict._conflict_target:
                if isinstance(col, str):
                    col = meta.combined.get(col)
                if (not isinstance(col, Field) or
                        meta.columns.get(col.column_name) is not col):
                    raise ValueError(
                        'Oracle MERGE conflict target must reference fields '
                        'of the target model.')
                target.append(col.column_name)
            if not all(name in inserted_names for name in target):
                raise ValueError(
                    'Oracle MERGE conflict target must be present in inserted columns.')
            if (len(set(target)) != len(target) or
                    frozenset(target) not in
                    {frozenset(candidate) for candidate in candidates}):
                raise ValueError(
                    'Oracle MERGE conflict target must match a model-declared '
                    'primary key or non-partial unique index.')
            target_columns = target

        if target_columns is None:
            matching = []
            for candidate in candidates:
                if all(name in inserted_names for name in candidate):
                    matching.append(candidate)

            if len(matching) > 1:
                raise ValueError(
                    'Oracle MERGE rewrite has multiple inferable conflict targets; '
                    'specify conflict_target explicitly.')
            if not matching:
                raise ValueError('Oracle MERGE rewrite requires an explicit or inferable conflict target.')
            target_columns = matching[0]

        source_sql, source_params = self._render_merge_source(
            rows, columns, defaults)
        self.literal('MERGE INTO "').literal(table._meta.table_name).literal('" t USING (').literal(source_sql).literal(') src ON (')
        self.literal(' AND '.join('t."%s" = src."%s"' % (name, name)
                                  for name in target_columns))
        self.literal(') ')
        self._values.extend(source_params)
        blocked = set(target_columns)
        updates = []
        for col in columns:
            alias = self._merge_alias_name(col)
            if alias in blocked:
                continue
            updates.append('t."%s" = src."%s"' % (col.column_name, alias))
        if updates:
            self.literal('WHEN MATCHED THEN UPDATE SET ')
            self.literal(', '.join(updates))
            self.literal(' ')
        self.literal('WHEN NOT MATCHED THEN INSERT (')
        self.literal(', '.join('"%s"' % self._merge_alias_name(col) for col in columns))
        self.literal(') VALUES (')
        self.literal(', '.join('src."%s"' % self._merge_alias_name(col) for col in columns))
        self.literal(')')
        return self


class KingbaseOracleSchemaManager(KingbaseMySQLSchemaManager):
    # Reuse the deferred-FK CREATE TABLE path. Inlining the FK and adding it
    # again below produced two physical constraints for the same column.
    def _foreign_key_fields(self):
        return [
            field for field in self.model._meta.sorted_fields
            if isinstance(field, ForeignKeyField) and not field.deferred
        ]

    def ensure_unique_constraints(self, safe=True):
        meta = self.model._meta
        table = meta.table_name
        for field in meta.sorted_fields:
            if not field.unique or field.primary_key:
                continue
            cname = ModelIndex(self.model, (field,), unique=True)._name
            legacy_name = _catalog_identifier(
                '%s_%s_key' % (table, field.column_name))
            if safe and (_schema_constraint_exists(self, cname, 'u') or
                         _schema_constraint_exists(self, legacy_name, 'u')):
                continue
            sql = 'ALTER TABLE "%s" ADD CONSTRAINT "%s" UNIQUE ("%s")' % (
                table, cname, field.column_name)
            try:
                self.database.execute_sql(sql)
            except DatabaseError:
                if safe and _schema_constraint_exists(self, cname, 'u'):
                    continue
                raise

    def create_deferred_foreign_keys(self, safe=True):
        for field in self._foreign_key_fields():
            cname = _catalog_foreign_key_name(field)
            if safe and _schema_constraint_exists(self, cname, 'f'):
                continue
            try:
                self.create_foreign_key(field)
            except DatabaseError:
                if safe and _schema_constraint_exists(self, cname, 'f'):
                    continue
                raise

    def create_indexes(self, safe=True, skip_field_uniques=False):
        _create_kingbase_indexes(self, safe, skip_field_uniques)

    def create_all(self, safe=True, **table_options):
        self.create_sequences()
        self.create_table(safe, **table_options)
        self.create_indexes(safe=safe, skip_field_uniques=True)
        self.ensure_unique_constraints(safe=safe)
        self.create_deferred_foreign_keys(safe=safe)


class _BufferedReplaceCursor:
    """Expose all per-row INSERT results as one Peewee-compatible cursor."""

    def __init__(self, rows, description, rowcount):
        self._rows = iter(rows)
        self.description = description
        self.rowcount = rowcount

    def fetchone(self):
        return next(self._rows, None)

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self._rows = iter(())


class KingbaseOracleDatabase(KingbaseDatabase):
    """
    KingbaseES Oracle-mode dialect over the PostgreSQL wire protocol.

    By default, preserve_empty_strings=True makes ``''`` distinct from NULL
    on each synchronous connection, matching Peewee TextField semantics.
    Set it to False when native Oracle empty-string behavior is required.
    """

    context_class = KingbaseOracleCompiler
    schema_class = KingbaseOracleSchemaManager
    json_methods = KingbaseOracleJSONMethods

    @property
    def introspector_class(self):
        from playhouse.kingbase_reflection import KingbaseIntrospector
        return KingbaseIntrospector

    @property
    def schema_migrator_class(self):
        from playhouse.kingbase_migrate import KingbaseOracleMigrator
        return KingbaseOracleMigrator

    def get_context_options(self):
        options = super(KingbaseOracleDatabase, self).get_context_options()
        options['pagination'] = self._render_oracle_pagination
        return options

    @staticmethod
    def _render_oracle_pagination(query, ctx):
        # Only SELECT and compound SELECT use Oracle row limiting. UPDATE and
        # DELETE retain Peewee's existing ordering and limit compilation.
        if not isinstance(query, SelectBase):
            return False
        if query._limit is None and query._offset is None:
            return True
        ctx.literal(' OFFSET ').sql(
            query._offset if query._offset is not None else 0).literal(' ROWS')
        if query._limit is not None:
            ctx.literal(' FETCH NEXT ').sql(query._limit).literal(' ROWS ONLY')
        return True

    def init(self, database, preserve_empty_strings=True, **kwargs):
        # Peewee TextField and user-defined fields can distinguish '' from
        # None. The Oracle-mode server defaults to treating '' as NULL; keep
        # that behavior available when native Oracle semantics are required.
        self.preserve_empty_strings = preserve_empty_strings
        super(KingbaseOracleDatabase, self).init(database, **kwargs)

    def _initialize_connection(self, conn):
        super(KingbaseOracleDatabase, self)._initialize_connection(conn)
        if self.preserve_empty_strings:
            cursor = conn.cursor()
            try:
                cursor.execute('SET ora_input_emptystr_isnull TO off')
            finally:
                cursor.close()

    def get_cursor_wrapper(self, cursor, query=None):
        # The Oracle wire cursor folds unquoted result labels to lower case.
        # Restore aliases explicitly selected by Peewee (e.g. .alias('L')).
        alias_map = KingbaseMySQLDatabase._alias_map(self, query)
        return KingbaseMySQLCursorWrapper(cursor, alias_map=alias_map)

    @staticmethod
    def _guard_nullable_inner_join(source):
        if not isinstance(source, Join):
            return source, False
        lhs, lhs_changed = KingbaseOracleDatabase._guard_nullable_inner_join(
            source.lhs)
        rhs, rhs_changed = KingbaseOracleDatabase._guard_nullable_inner_join(
            source.rhs)
        on = source._on
        guarded = False
        if (source.join_type == JOIN.INNER and isinstance(on, Expression) and
                on.op == OP.EQ):
            for operand in (on.lhs, on.rhs):
                if isinstance(operand, Field) and operand.null:
                    on = on & operand.is_null(False)
                    guarded = True
        if not (lhs_changed or rhs_changed or guarded):
            return source, False
        return Join(lhs, rhs, source.join_type, on, alias=source._alias), True

    def _implicit_replace_candidates(self, query):
        if (not isinstance(query, Insert) or
                not KingbaseOracleCompiler._is_replace_insert(query) or
                getattr(query._on_conflict, '_conflict_target', None) or
                not is_model(query.table)):
            return ()
        candidates = self.get_sql_context()._merge_unique_targets(query.table)
        if isinstance(query._insert, Mapping):
            supplied = {KingbaseOracleCompiler._merge_alias_name(key)
                        for key in query._insert}
        elif query._columns:
            supplied = {KingbaseOracleCompiler._merge_alias_name(key)
                        for key in query._columns}
        else:
            return ()
        supplied.update(KingbaseOracleCompiler._merge_alias_name(key)
                        for key in query.get_default_data())
        return tuple(candidate for candidate in candidates
                     if all(name in supplied for name in candidate))

    @staticmethod
    def _implicit_replace_rows(query):
        model = query.table
        source = query._insert
        rows = [source] if isinstance(source, Mapping) else list(source)
        fields = [model._meta.combined[name] if isinstance(name, str) else name
                  for name in (query._columns or ())]
        for source_row in rows:
            if isinstance(source_row, Mapping):
                values = {
                    model._meta.combined[key] if isinstance(key, str) else key: value
                    for key, value in source_row.items()}
            else:
                if len(source_row) != len(fields):
                    raise ValueError('Oracle REPLACE row length does not match fields.')
                values = dict(zip(fields, source_row))
            for field, default in query.get_default_data().items():
                if field not in values:
                    values[field] = default() if callable(default) else default
            yield values

    def _execute_implicit_replace(self, query, candidates):
        """Implement MySQL-style REPLACE across every declared unique key.

        A single MERGE target cannot reproduce REPLACE when different unique
        keys identify different existing rows. Delete all conflicting rows,
        then insert each source row in order, atomically for the whole batch.
        """
        model = query.table
        result_rows = []
        description = None
        affected = 0
        with self.atomic():
            for values in self._implicit_replace_rows(query):
                by_column = {field.column_name: value for field, value in values.items()}
                matches = []
                for candidate in candidates:
                    if any(by_column.get(name) is None for name in candidate):
                        continue
                    match = None
                    for name in candidate:
                        condition = model._meta.columns[name] == by_column[name]
                        match = condition if match is None else match & condition
                    matches.append(match)
                if matches:
                    predicate = matches[0]
                    for match in matches[1:]:
                        predicate |= match
                    affected += model.delete().where(predicate).execute()

                insert = model.insert(values)
                insert._returning = query._returning
                cursor = self.execute(insert)
                try:
                    description = cursor.description
                    if description is not None:
                        result_rows.extend(cursor.fetchall())
                finally:
                    cursor.close()
                affected += 1
        return _BufferedReplaceCursor(result_rows, description, affected)

    def execute(self, query, **context_options):
        candidates = self._implicit_replace_candidates(query)
        if len(candidates) > 1:
            return self._execute_implicit_replace(query, candidates)
        if isinstance(query, SelectBase) and getattr(query, '_from_list', None):
            sources = [self._guard_nullable_inner_join(source)
                       for source in query._from_list]
            if any(changed for _, changed in sources):
                # V9R2C16 can return NULL-key rows from an INNER JOIN.
                # Add the logically implied guard only to the executed clone;
                # callers' query and its SQL representation remain untouched.
                query = query.clone()
                query._from_list = [source for source, _ in sources]
        cursor = super(KingbaseOracleDatabase, self).execute(
            query, **context_options)
        return self.get_cursor_wrapper(cursor, query=query)

    def create_tables(self, models, **options):
        for model in sort_models(models):
            self.schema_class(model, database=self).create_all(**options)

    def _normalize_schema_name(self, schema=None):
        # Peewee models commonly use the underlying PostgreSQL namespace
        # "public". Oracle's ALL_* views expose the same objects under the
        # session user instead of an owner named PUBLIC.
        if schema is None or str(schema).lower() == 'public':
            return self.get_current_user()
        return schema

    def get_current_user(self):
        cursor = self.execute_sql('SELECT USER FROM DUAL')
        row = cursor.fetchone()
        return row[0] if row else None

    def _oracle_owner(self, schema=None):
        return str(self._normalize_schema_name(schema) or '').upper()

    @staticmethod
    def _oracle_catalog_table_name(table):
        # Oracle's ALL_* views fold lowercase identifiers to uppercase, but
        # retain the spelling of quoted mixed-case identifiers.
        table = str(table)
        return table.upper() if table == table.lower() else table

    @staticmethod
    def _oracle_metadata_name(name):
        name = str(name)
        return name.lower() if name == name.upper() else name

    def get_tables(self, schema=None):
        if schema is not None and str(schema).lower() != 'public':
            return super(KingbaseOracleDatabase, self).get_tables(schema)
        owner = self._oracle_owner(schema)
        cursor = self.execute_sql(
            'SELECT tablename FROM pg_catalog.pg_tables '
            'WHERE LOWER(tableowner) = LOWER(%s) AND schemaname = %s '
            'ORDER BY tablename',
            (owner, 'public'))
        return [table for table, in cursor.fetchall()]

    def get_views(self, schema=None):
        if schema is not None and str(schema).lower() != 'public':
            return super(KingbaseOracleDatabase, self).get_views(schema)
        owner = self._oracle_owner(schema)
        cursor = self.execute_sql(
            'SELECT viewname, definition FROM pg_catalog.pg_views '
            'WHERE LOWER(viewowner) = LOWER(%s) AND schemaname = %s '
            'ORDER BY viewname',
            (owner, 'public'))
        return [ViewMetadata(name, sql.strip(' \t;'))
                for name, sql in cursor.fetchall()]

    def get_primary_keys(self, table, schema=None):
        if schema is not None and str(schema).lower() != 'public':
            return super(KingbaseOracleDatabase, self).get_primary_keys(
                table, schema)
        owner = self._oracle_owner(schema)
        cursor = self.execute_sql(
            'SELECT cc.column_name FROM all_constraints c '
            'JOIN all_cons_columns cc ON LOWER(c.owner) = LOWER(cc.owner) '
            'AND LOWER(c.constraint_name) = LOWER(cc.constraint_name) '
            'AND LOWER(c.table_name) = LOWER(cc.table_name) '
            'WHERE c.owner = UPPER(%s) AND c.table_name = %s '
            "AND c.constraint_type = 'P' ORDER BY cc.position",
            (owner, self._oracle_catalog_table_name(table)))
        return [self._oracle_metadata_name(name)
                for name, in cursor.fetchall()]

    def get_foreign_keys(self, table, schema=None):
        catalog_schema = (schema if schema is not None and
                          str(schema).lower() != 'public' else 'public')
        return _catalog_foreign_keys(self, table, catalog_schema)

    def get_columns(self, table, schema=None):
        if schema is not None and str(schema).lower() != 'public':
            return super(KingbaseOracleDatabase, self).get_columns(
                table, schema)
        owner = self._oracle_owner(schema)
        query = (
            'SELECT column_name, data_type, nullable, data_default, '
            'char_length, data_precision, data_scale '
            'FROM all_tab_columns '
            'WHERE owner = UPPER(%s) AND table_name = %s '
            'ORDER BY column_id')
        cursor = self.execute_sql(
            query, (owner, self._oracle_catalog_table_name(table)))
        columns = []
        primary_keys = set(self.get_primary_keys(table, schema))
        catalog = _catalog_column_details(self, table, 'public')
        for (name, data_type, nullable, default, char_length, precision,
             scale) in cursor.fetchall():
            normalized_name = self._oracle_metadata_name(name)
            physical_type, identity = catalog.get(
                normalized_name, (None, False))
            full_type = (physical_type or _reflected_full_type(
                data_type, char_length, precision, scale))
            # format_type() includes Oracle's CHAR-length qualifier, which
            # Peewee's full_type contract does not expose.
            full_type = re.sub(r'(\d+) char\)', r'\1)', full_type)
            reflected_type = (str(data_type).lower() if
                              str(data_type).lower() == 'int4' else
                              physical_type.split('(', 1)[0]
                              if physical_type else data_type)
            columns.append(ColumnMetadata(
                name=normalized_name,
                data_type=reflected_type,
                null=(str(nullable).upper() == 'Y'),
                primary_key=normalized_name in primary_keys,
                table=table,
                default=default,
                full_type=full_type,
                identity=identity or bool(default and str(default).startswith(
                    ('nextval(', 'unique_rowid(')))))
        return columns

    def table_exists(self, table_name, schema=None):
        if is_model(table_name):
            schema = table_name._meta.schema
            table_name = table_name._meta.table_name
        if schema is not None and str(schema).lower() != 'public':
            return super(KingbaseOracleDatabase, self).table_exists(
                table_name, schema)
        owner = self._oracle_owner(schema)
        cursor = self.execute_sql(
            'SELECT 1 FROM all_tables WHERE owner = UPPER(%s) AND table_name = %s',
            (owner, self._oracle_catalog_table_name(table_name)))
        return cursor.fetchone() is not None


class KingbaseSQLServerCompiler(KingbaseOracleCompiler):
    def sql(self, obj):
        if isinstance(obj, Expression) and obj.op in (OP.REGEXP, OP.IREGEXP):
            # SQL Server mode's ~ operator ignores case even with a C
            # collation. regexp_match honors the explicit c/i flag.
            flag = 'c' if obj.op == OP.REGEXP else 'i'
            return self.sql(fn.regexp_match(obj.lhs, obj.rhs, flag).is_null(False))
        if isinstance(obj, Cast) and isinstance(obj._cast, str) and \
                obj._cast.lower() == 'text':
            return (self.literal('CAST(').sql(obj.node)
                    .literal(' AS VARCHAR(MAX))'))
        if isinstance(obj, Expression) and obj.op == OP.CONCAT:
            return (self.literal('CONCAT(').sql(obj.lhs)
                    .literal(', ').sql(obj.rhs).literal(')'))
        return super(KingbaseSQLServerCompiler, self).sql(obj)


class KingbaseSQLServerJSONMethods(KingbaseOracleJSONMethods):
    def _path_array(self, keys):
        # SQL Server mode accepts the PostgreSQL jsonb path functions, but
        # its parser rejects the ARRAY[...] and text[] syntax. The unknown
        # string literal is resolved by the function/operator as text[].
        parts = ['"%s"' % str(key).replace('\\', '\\\\').replace('"', '\\"')
                 for key in keys]
        return AsIs('{%s}' % ','.join(parts), False)

    def has_keys(self, field, keys, key_list):
        return Expression(self.extract(field, keys), '?&',
                          self._path_array(key_list))

    def has_any_keys(self, field, keys, key_list):
        return Expression(self.extract(field, keys), '?|',
                          self._path_array(key_list))


class KingbaseSQLServerDatabase(KingbaseDatabase):
    """KingbaseES SQL Server compatibility mode over the PostgreSQL wire.

    Keep Peewee's PostgreSQL expression and connection machinery where the
    server accepts it, while using the Kingbase schema path for deferred
    foreign keys and explicit unique constraints.
    """

    field_types = dict(PostgresqlDatabase.field_types,
                       AUTO='INTEGER IDENTITY(1,1)',
                       BIGAUTO='BIGINT IDENTITY(1,1)',
                       DATETIME='DATETIME2',
                       TEXT='VARCHAR(MAX)')
    context_class = KingbaseSQLServerCompiler
    # SQL Server mode must materialize limited UNION members as subqueries;
    # parenthesized members can apply their ORDER BY after the row limit.
    compound_select_parentheses = CSQ_PARENTHESES_NEVER
    operations = dict(PostgresqlDatabase.operations, ILIKE='LIKE')
    json_methods = KingbaseSQLServerJSONMethods
    schema_class = KingbaseOracleSchemaManager
    _implicit_replace_candidates = KingbaseOracleDatabase._implicit_replace_candidates
    _implicit_replace_rows = staticmethod(
        KingbaseOracleDatabase._implicit_replace_rows)
    _execute_implicit_replace = KingbaseOracleDatabase._execute_implicit_replace

    def get_context_options(self):
        options = super(KingbaseSQLServerDatabase, self).get_context_options()
        options['pagination'] = KingbaseOracleDatabase._render_oracle_pagination
        return options

    @property
    def introspector_class(self):
        from playhouse.kingbase_reflection import KingbaseIntrospector
        return KingbaseIntrospector

    @property
    def schema_migrator_class(self):
        from playhouse.kingbase_migrate import KingbaseSQLServerMigrator
        return KingbaseSQLServerMigrator

    def begin(self, isolation_level=None):
        if isolation_level is None:
            isolation_level = self._isolation_level
        statement = 'BEGIN TRANSACTION'
        if isolation_level:
            txn_type = self._adapter.isolation_level_str(isolation_level)
            statement += ' ISOLATION LEVEL %s' % txn_type
        with __exception_wrapper__:
            self.cursor().execute(statement)

    def execute_sql(self, sql, params=None):
        # The PG-wire driver adapts datetime as ::timestamp, which is the SQL
        # Server rowversion type. Quote each value before changing its
        # type annotation to datetime2.
        if params:
            import datetime
            from ksycopg2.extensions import AsIs, adapt
            converted = (
                AsIs(adapt(value).getquoted().decode().replace(
                    '::timestamp', '::datetime2'))
                if isinstance(value, datetime.datetime) else value
                for value in params)
            params = type(params)(converted)
        return super(KingbaseSQLServerDatabase, self).execute_sql(sql, params)

    def _initialize_connection(self, conn):
        super(KingbaseSQLServerDatabase, self)._initialize_connection(conn)
        # SQL Server compatibility types use sys.* OIDs. The PostgreSQL wire
        # driver otherwise returns their numeric and temporal values as text.
        import datetime
        import decimal
        import uuid
        from ksycopg2.extensions import new_type, register_type

        def parse_datetime(value, _):
            # datetime2 may carry seven fractional digits; Python stores six.
            return datetime.datetime.fromisoformat(
                re.sub(r'(\.\d{6})\d+', r'\1', value))

        def parse_time(value, _):
            return datetime.time.fromisoformat(
                re.sub(r'(\.\d{6})\d+', r'\1', value))

        readers = {
            'tinyint': lambda value, _: int(value),
            'smallint': lambda value, _: int(value),
            'int': lambda value, _: int(value),
            'bigint': lambda value, _: int(value),
            'bit': lambda value, _: value not in ('0', 'false', 'f'),
            'numeric': lambda value, _: decimal.Decimal(value),
            'money': lambda value, _: decimal.Decimal(value.replace(',', '')),
            'real': lambda value, _: float(format(float(value), '.7g')),
            'float': lambda value, _: float(value),
            'date': lambda value, _: datetime.date.fromisoformat(value),
            'time': parse_time,
            'datetime': parse_datetime,
            'datetime2': parse_datetime,
            'uniqueidentifier': lambda value, _: uuid.UUID(value),
        }
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT t.typname, t.oid FROM pg_catalog.pg_type t '
                'JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace '
                'WHERE n.nspname = %s', ('sys',))
            for name, oid in cursor.fetchall():
                reader = readers.get(name)
                if reader is not None:
                    register_type(new_type((oid,), 'KES_SQLSERVER_' + name,
                                           lambda value, cur, fn=reader:
                                           None if value is None else fn(value, cur)),
                                  conn)
            cursor.execute('SET arithabort ON')
        finally:
            cursor.close()

    @staticmethod
    def _schema(schema):
        return 'dbo' if schema is None or str(schema).lower() == 'public' else schema

    def _normalize_schema_name(self, schema=None):
        return self._schema(schema)

    def extract_date(self, date_part, date_field):
        if date_part.lower() == 'second':
            return (fn.DATEPART('second', date_field) +
                    fn.DATEPART('microsecond', date_field) / 1000000.0)
        return fn.DATEPART(date_part, date_field)

    def truncate_date(self, date_part, date_field):
        base = SQL("CAST('2000-01-01' AS datetime2)")
        return fn.DATEADD(date_part,
                          fn.DATEDIFF(date_part, base, date_field), base)

    def to_timestamp(self, date_field):
        base = SQL("CAST('1970-01-01' AS datetime2)")
        return fn.DATEDIFF_BIG('second', base, date_field)

    def from_timestamp(self, date_field):
        base = SQL("CAST('1970-01-01' AS datetime2)")
        return fn.DATEADD('second', date_field, base)

    def get_tables(self, schema=None):
        return super(KingbaseSQLServerDatabase, self).get_tables(self._schema(schema))

    def get_views(self, schema=None):
        return super(KingbaseSQLServerDatabase, self).get_views(self._schema(schema))

    def get_indexes(self, table, schema=None):
        return super(KingbaseSQLServerDatabase, self).get_indexes(
            table, self._schema(schema))

    def get_primary_keys(self, table, schema=None):
        return super(KingbaseSQLServerDatabase, self).get_primary_keys(
            table, self._schema(schema))

    def get_foreign_keys(self, table, schema=None):
        return super(KingbaseSQLServerDatabase, self).get_foreign_keys(
            table, self._schema(schema))

    def get_columns(self, table, schema=None):
        schema = self._schema(schema)
        cursor = self.execute_sql(
            'SELECT c.column_name, c.is_nullable, c.data_type, '
            'c.column_default, '
            'pg_catalog.format_type(a.atttypid, a.atttypmod), a.attidentity '
            'FROM information_schema.columns c '
            'JOIN pg_catalog.pg_namespace n ON n.nspname = c.table_schema '
            'JOIN pg_catalog.pg_class t ON t.relname = c.table_name '
            'AND t.relnamespace = n.oid '
            'JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid '
            'AND a.attname = c.column_name '
            'WHERE c.table_name = %s AND c.table_schema = %s '
            'AND NOT a.attisdropped ORDER BY c.ordinal_position',
            (table, schema))
        pks = set(self.get_primary_keys(table, schema))
        return [ColumnMetadata(name,
                               'text' if full_type == 'sys.text' else data_type,
                               nullable == 'YES', name in pks, table, default,
                               'text' if full_type == 'sys.text' else full_type,
                               bool(identity) or bool(default and
                                   str(default).startswith('nextval(')))
                for name, nullable, data_type, default, full_type, identity
                in cursor.fetchall()]

    def create_tables(self, models, **options):
        for model in sort_models(models):
            self.schema_class(model, database=self).create_all(**options)

    def get_cursor_wrapper(self, cursor, query=None):
        alias_map = KingbaseMySQLDatabase._alias_map(self, query)
        return KingbaseMySQLCursorWrapper(cursor, alias_map=alias_map)

    def execute(self, query, **context_options):
        candidates = self._implicit_replace_candidates(query)
        if candidates:
            return self._execute_implicit_replace(query, candidates)
        # SQL Server IDENTITY normally rejects an explicitly supplied key.
        # Peewee's insert_many and insert_from tests exercise this supported
        # model operation, so enable it only for that insert and connection.
        pk = (getattr(getattr(query.table, '_meta', None), 'primary_key', None)
              if isinstance(query, Insert) else None)
        columns = getattr(query, '_columns', None)
        if pk and columns:
            explicit_pk = any(getattr(column, 'column_name', column) ==
                              pk.column_name for column in columns)
        elif pk and isinstance(query._insert, Mapping):
            explicit_pk = any(getattr(column, 'column_name', column) ==
                              pk.column_name for column in query._insert)
        else:
            explicit_pk = False
        if explicit_pk and getattr(pk, 'auto_increment', False):
            table = '"%s"' % query.table._meta.table_name.replace('"', '""')
            self.execute_sql('SET IDENTITY_INSERT %s ON' % table)
            try:
                cursor = super(KingbaseSQLServerDatabase, self).execute(
                    query, **context_options)
            finally:
                self.execute_sql('SET IDENTITY_INSERT %s OFF' % table)
        else:
            cursor = super(KingbaseSQLServerDatabase, self).execute(
                query, **context_options)
        return self.get_cursor_wrapper(cursor, query=query)
