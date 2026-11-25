"""KingbaseES reflection without changing Peewee's Playhouse implementation."""

import re
import warnings
from collections.abc import Mapping
from inspect import isclass

from peewee import *
from playhouse import postgres_ext
from playhouse.kingbase_native import KingbaseMySQLDatabase
from playhouse.kingbase_native import KingbaseOracleDatabase
from playhouse.kingbase_native import KingbaseSQLServerDatabase
from playhouse.reflection import Introspector
from playhouse.reflection import Metadata
from playhouse.reflection import PostgresqlMetadata
from playhouse.reflection import UnknownField


class _KingbaseArrayMetadata(object):
    def _resolve_array_types(self, table, schema, column_types, extra_params,
                             array_columns):
        if not array_columns or postgres_ext is None:
            return

        # Both compatibility modes expose array element types and declared
        # dimensions through the PostgreSQL catalog.
        catalog_schema = schema or 'public'
        cursor = self.execute(
            'SELECT a.attname, e.typname, a.attndims '
            'FROM pg_catalog.pg_attribute a '
            'JOIN pg_catalog.pg_class c ON c.oid = a.attrelid '
            'JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace '
            'JOIN pg_catalog.pg_type t ON t.oid = a.atttypid '
            'LEFT JOIN pg_catalog.pg_type e ON e.oid = t.typelem '
            'WHERE n.nspname = %s AND c.relname = %s '
            'AND a.attnum > 0 AND NOT a.attisdropped',
            catalog_schema, table)
        for name, element_type, dimensions in cursor.fetchall():
            if name not in array_columns:
                continue
            element_type = str(element_type).lower() if element_type else None
            field_class = KingbaseMySQLMetadata.column_map.get(
                element_type, UnknownField)
            if element_type == 'json':
                field_class = postgres_ext.JSONField
            elif element_type == 'jsonb':
                field_class = postgres_ext.BinaryJSONField
            if field_class is UnknownField:
                continue
            column_types[name] = postgres_ext.ArrayField
            extra_params[name] = {
                'field_class': field_class,
                'dimensions': dimensions if dimensions and dimensions > 0 else 1}
            if hasattr(self, '_require_import'):
                self._require_import(
                    'from playhouse.postgres_ext import ArrayField')
                if element_type == 'json':
                    self._require_import(
                        'from playhouse.postgres_ext import JSONField')
                elif element_type == 'jsonb':
                    self._require_import(
                        'from playhouse.postgres_ext import BinaryJSONField')
            else:
                self.requires_extension = True


class KingbaseMySQLMetadata(_KingbaseArrayMetadata, Metadata):
    """Map Kingbase catalog types, not MySQL DB-API cursor type codes.

    Kingbase uses the PostgreSQL wire protocol in MySQL compatibility mode,
    so ksycopg2's cursor.description does not contain MySQL FIELD_TYPE values.
    """
    extension_import = ''
    column_map = {
        'bigint': BigIntegerField,
        'bigserial': BigIntegerField,
        'blob': BlobField,
        'bool': BooleanField,
        'boolean': BooleanField,
        'bpchar': CharField,
        'bytea': BlobField,
        'char': CharField,
        'character': CharField,
        'character varying': CharField,
        'date': DateField,
        'datetime': DateTimeField,
        'decimal': DecimalField,
        'double': DoubleField,
        'double precision': DoubleField,
        'float': FloatField,
        'float4': FloatField,
        'float8': DoubleField,
        'int': IntegerField,
        'int2': SmallIntegerField,
        'int4': IntegerField,
        'int8': BigIntegerField,
        'integer': IntegerField,
        'number': DecimalField,
        'numeric': DecimalField,
        'real': FloatField,
        'serial': IntegerField,
        'smallint': SmallIntegerField,
        'text': TextField,
        'time': TimeField,
        'time with time zone': TimeField,
        'time without time zone': TimeField,
        'timetz': TimeField,
        'timestamp': DateTimeField,
        'timestamp with time zone': DateTimeField,
        'timestamp without time zone': DateTimeField,
        'timestamptz': DateTimeField,
        'tinyint': IntegerField,
        'uuid': UUIDField,
        'varchar': CharField,
        'varchar2': CharField,
    }

    def get_column_types(self, table, schema=None):
        columns = self.database.get_columns(table, schema)
        column_types = {}
        extra_params = {}
        array_columns = set()
        for column in columns:
            data_type = str(column.data_type).strip().lower()
            data_type = re.sub(r'\s*\([^)]*\)', '', data_type)
            if data_type == 'json':
                from playhouse.mysql_ext import JSONField
                column_types[column.name] = JSONField
                self._require_import('from playhouse.mysql_ext import JSONField')
            elif data_type == 'jsonb' and postgres_ext is not None:
                column_types[column.name] = postgres_ext.BinaryJSONField
                self._require_import(
                    'from playhouse.postgres_ext import BinaryJSONField')
            elif data_type == 'array' or data_type.endswith('[]'):
                column_types[column.name] = UnknownField
                array_columns.add(column.name)
            else:
                column_types[column.name] = self.column_map.get(
                    data_type, UnknownField)

        if array_columns:
            self._resolve_array_types(
                table, self.database._normalize_schema_name(schema),
                column_types, extra_params, array_columns)
        return column_types, extra_params

    def _require_import(self, statement):
        self.requires_extension = True
        imports = self.extension_import.splitlines()
        if statement not in imports:
            imports.append(statement)
            self.extension_import = '\n'.join(imports)


class KingbaseSQLServerMetadata(KingbaseMySQLMetadata):
    column_map = dict(KingbaseMySQLMetadata.column_map,
                      bit=BooleanField,
                      datetime2=DateTimeField,
                      float=DoubleField,
                      nchar=CharField,
                      nvarchar=CharField,
                      uniqueidentifier=UUIDField)

    def get_column_types(self, table, schema=None):
        column_types, extras = super().get_column_types(table, schema)
        for column in self.database.get_columns(table, schema):
            if str(column.full_type).lower() == 'varchar(max)':
                column_types[column.name] = TextField
        return column_types, extras


class KingbaseOracleMetadata(_KingbaseArrayMetadata, PostgresqlMetadata):
    """Retain PostgreSQL type coverage and resolve Kingbase-specific OIDs."""

    def get_column_types(self, table, schema):
        column_types, extra_params = super(
            KingbaseOracleMetadata, self).get_column_types(table, schema)
        array_columns = set()
        for column in self.database.get_columns(table, schema):
            data_type = str(column.data_type).strip().lower()
            data_type = re.sub(r'\s*\([^)]*\)', '', data_type)
            if (data_type == 'array' or data_type.endswith('[]') or
                    (postgres_ext is not None and
                     column_types.get(column.name) is postgres_ext.ArrayField)):
                array_columns.add(column.name)
            if column_types.get(column.name, UnknownField) is UnknownField:
                column_types[column.name] = KingbaseMySQLMetadata.column_map.get(
                    data_type, UnknownField)
        self._resolve_array_types(
            table, schema, column_types, extra_params, array_columns)
        return column_types, extra_params


class KingbaseIntrospector(Introspector):
    """Select the Kingbase catalog mapper and apply explicit field intent."""

    def __init__(self, metadata, schema=None, field_overrides=None):
        super().__init__(metadata, schema=schema)
        self.field_overrides = {}
        if field_overrides is not None:
            if not isinstance(field_overrides, Mapping):
                raise TypeError(
                    'field_overrides must map (table, column) to a Field class')
            for key, field_class in field_overrides.items():
                if (not isinstance(key, tuple) or len(key) != 2 or
                        not all(isinstance(part, str) for part in key)):
                    raise ValueError(
                        'field_overrides keys must be (table, column) pairs')
                if (not isclass(field_class) or
                        not issubclass(field_class, Field) or
                        issubclass(field_class, ForeignKeyField)):
                    raise TypeError(
                        'field_overrides values must be non-relation Field classes')
                self.field_overrides[key] = field_class

    @classmethod
    def from_database(cls, database, schema=None, field_overrides=None):
        if isinstance(database, Proxy):
            if database.obj is None:
                raise ValueError('Cannot introspect an uninitialized Proxy.')
            database = database.obj
        if isinstance(database, KingbaseMySQLDatabase):
            metadata = KingbaseMySQLMetadata(database)
        elif isinstance(database, KingbaseOracleDatabase):
            metadata = KingbaseOracleMetadata(database)
        elif isinstance(database, KingbaseSQLServerDatabase):
            metadata = KingbaseSQLServerMetadata(database)
            schema = database._schema(schema)
        else:
            raise ValueError('Introspection not supported for %r' % database)
        return cls(metadata, schema=schema, field_overrides=field_overrides)

    def introspect(self, table_names=None, literal_column_names=False,
                   include_views=False, snake_case=True):
        database = super().introspect(
            table_names=table_names,
            literal_column_names=literal_column_names,
            include_views=include_views,
            snake_case=snake_case)
        for (table, column), field_class in self.field_overrides.items():
            if table_names is not None and table not in table_names:
                continue
            if table not in database.columns:
                raise ValueError('Unknown reflected table %s' % table)
            if column not in database.columns[table]:
                raise ValueError('Unknown reflected column %s.%s' %
                                 (table, column))
            reflected = database.columns[table][column]
            if reflected.is_foreign_key():
                raise ValueError('Cannot override foreign-key column %s.%s' %
                                 (table, column))
            reflected.field_class = field_class
            # The old type's constructor parameters (for example a VARCHAR
            # length) must not be passed to an explicit UUIDField override.
            reflected.extra_parameters = None
        return database

    def generate_models(self, skip_invalid=False, table_names=None,
                        literal_column_names=False, bare_fields=False,
                        include_views=False):
        # The upstream model builder does not pass Column.extra_parameters to
        # Field constructors. Keep the Kingbase-specific copy here so array
        # element type and declared dimensions survive model generation.
        database = self.introspect(table_names, literal_column_names,
                                   include_views)
        models = {}

        class BaseModel(Model):
            class Meta:
                database = self.metadata.database
                schema = self.schema

        pending = set()

        def _create_model(table, models):
            pending.add(table)
            for foreign_key in database.foreign_keys[table]:
                dest = foreign_key.dest_table

                if dest not in models and dest != table:
                    if dest in pending:
                        warnings.warn('Possible reference cycle found between '
                                      '%s and %s' % (table, dest))
                    else:
                        _create_model(dest, models)

            columns = database.columns[table]
            primary_keys = [columns[name].name
                            for name in database.primary_keys[table]]

            multi_column_indexes = database.multi_column_indexes(table)
            column_indexes = database.column_indexes(table)

            class Meta:
                indexes = multi_column_indexes
                table_name = table

            # Fix models with multi-column primary keys.
            composite_key = False
            if not primary_keys:
                Meta.primary_key = False
            elif len(primary_keys) > 1:
                Meta.primary_key = CompositeKey(*primary_keys)
                composite_key = True

            attrs = {'Meta': Meta}
            for column_name, column in columns.items():
                FieldClass = column.field_class
                if FieldClass is not ForeignKeyField and bare_fields:
                    FieldClass = BareField
                elif FieldClass is UnknownField:
                    FieldClass = BareField

                params = {
                    'column_name': column_name,
                    'null': column.nullable}
                if (column.extra_parameters and
                        FieldClass not in (BareField, ForeignKeyField,
                                           DeferredForeignKey)):
                    params.update(column.extra_parameters)
                if column.primary_key and composite_key:
                    if FieldClass is AutoField:
                        FieldClass = IntegerField
                    params['primary_key'] = False
                elif column.primary_key and FieldClass is not AutoField:
                    params['primary_key'] = True
                if column.is_foreign_key():
                    if column.is_self_referential_fk():
                        params['model'] = 'self'
                    else:
                        dest_table = column.foreign_key.dest_table
                        if dest_table in models:
                            params['model'] = models[dest_table]
                        else:
                            FieldClass = DeferredForeignKey
                            params['rel_model_name'] = dest_table
                    if column.to_field:
                        params['field'] = column.to_field

                    # Generate a unique related name.
                    params['backref'] = '%s_%s_rel' % (table, column_name)

                    for attr in ('on_delete', 'on_update'):
                        value = getattr(column.foreign_key, attr, None)
                        if value and value not in ('NO ACTION', 'RESTRICT'):
                            params[attr] = value

                if column.default is not None:
                    constraint = SQL('DEFAULT %s' % column.default)
                    params['constraints'] = [constraint]

                if not column.is_primary_key():
                    if column_name in column_indexes:
                        if column_indexes[column_name]:
                            params['unique'] = True
                        elif not column.is_foreign_key():
                            params['index'] = True
                    else:
                        params['index'] = False

                attrs[column.name] = FieldClass(**params)

            try:
                models[table] = type(str(table), (BaseModel,), attrs)
            except ValueError:
                if not skip_invalid:
                    raise
            finally:
                if table in pending:
                    pending.remove(table)

        # Actually generate Model classes.
        for table, model in sorted(database.model_names.items()):
            if table not in models:
                _create_model(table, models)

        return models


def introspect(database, schema=None, field_overrides=None):
    return KingbaseIntrospector.from_database(
        database, schema=schema, field_overrides=field_overrides).introspect()


def generate_models(database, schema=None, **options):
    field_overrides = options.pop('field_overrides', None)
    return KingbaseIntrospector.from_database(
        database, schema=schema, field_overrides=field_overrides
    ).generate_models(**options)


__all__ = ['KingbaseIntrospector', 'generate_models', 'introspect']
