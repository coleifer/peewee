try:
    from collections import OrderedDict
except ImportError:
    OrderedDict = dict
from collections import namedtuple
import re

from peewee import *
try:
    from MySQLdb.constants import FIELD_TYPE
except ImportError:
    try:
        from pymysql.constants import FIELD_TYPE
    except ImportError:
        FIELD_TYPE = None
try:
    from playhouse import postgres_ext
except ImportError:
    postgres_ext = None

RESERVED_WORDS = set([
    'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif',
    'else', 'except', 'exec', 'finally', 'for', 'from', 'global', 'if',
    'import', 'in', 'is', 'lambda', 'not', 'or', 'pass', 'print', 'raise',
    'return', 'try', 'while', 'with', 'yield',
])


class UnknownField(object):
    pass


class Column(object):
    """
    Store metadata about a database column.
    """
    primary_key_types = (IntegerField, PrimaryKeyField)

    def __init__(self, name, field_class, raw_column_type, nullable,
                 primary_key=False, db_column=None, index=False, unique=False):
        self.name = name
        self.field_class = field_class
        self.raw_column_type = raw_column_type
        self.nullable = nullable
        self.primary_key = primary_key
        self.db_column = db_column
        self.index = index
        self.unique = unique

        # Foreign key metadata.
        self.rel_model = None
        self.related_name = None
        self.to_field = None

    def __repr__(self):
        attrs = [
            'field_class',
            'raw_column_type',
            'nullable',
            'primary_key',
            'db_column']
        keyword_args = ', '.join(
            '%s=%s' % (attr, getattr(self, attr))
            for attr in attrs)
        return 'Column(%s, %s)' % (self.name, keyword_args)

    def get_field_parameters(self):
        params = {}

        # Set up default attributes.
        if self.nullable:
            params['null'] = True
        if self.field_class is ForeignKeyField or self.name != self.db_column:
            params['db_column'] = "'%s'" % self.db_column
        if self.primary_key and self.field_class is not PrimaryKeyField:
            params['primary_key'] = True

        # Handle ForeignKeyField-specific attributes.
        if self.is_foreign_key():
            params['rel_model'] = self.rel_model
            if self.to_field:
                params['to_field'] = "'%s'" % self.to_field
            if self.related_name:
                params['related_name'] = "'%s'" % self.related_name

        # Handle indexes on column.
        if not self.is_primary_key():
            if self.unique:
                params['unique'] = 'True'
            elif self.index and not self.is_foreign_key():
                params['index'] = 'True'

        return params

    def is_primary_key(self):
        return self.field_class is PrimaryKeyField or self.primary_key

    def is_foreign_key(self):
        return self.field_class is ForeignKeyField

    def is_self_referential_fk(self):
        return (self.field_class is ForeignKeyField and
                self.rel_model == "'self'")

    def set_foreign_key(self, foreign_key, model_names, dest=None,
                        related_name=None):
        self.foreign_key = foreign_key
        self.field_class = ForeignKeyField
        if foreign_key.dest_table == foreign_key.table:
            self.rel_model = "'self'"
        else:
            self.rel_model = model_names[foreign_key.dest_table]
        self.to_field = dest and dest.name or None
        self.related_name = related_name or None

    def get_field(self):
        # Generate the field definition for this column.
        field_params = self.get_field_parameters()
        param_str = ', '.join('%s=%s' % (k, v)
                              for k, v in sorted(field_params.items()))
        field = '%s = %s(%s)' % (
            self.name,
            self.field_class.__name__,
            param_str)

        if self.field_class is UnknownField:
            field = '%s  # %s' % (field, self.raw_column_type)

        return field


class Metadata(object):
    column_map = {}

    def __init__(self, database):
        self.database = database

    def execute(self, sql, *params):
        return self.database.execute_sql(sql, params)

    def get_columns(self, table, schema=None):
        metadata = OrderedDict(
            (metadata.name, metadata)
            for metadata in self.database.get_columns(table, schema))

        # Look up the actual column type for each column.
        column_types = self.get_column_types(table, schema)

        # Look up the primary keys.
        pk_names = self.get_primary_keys(table, schema)
        if len(pk_names) == 1:
            pk = pk_names[0]
            if column_types[pk] is IntegerField:
                column_types[pk] = PrimaryKeyField

        columns = OrderedDict()
        for name, column_data in metadata.items():
            columns[name] = Column(
                name,
                field_class=column_types[name],
                raw_column_type=column_data.data_type,
                nullable=column_data.null,
                primary_key=column_data.primary_key,
                db_column=name)

        return columns

    def get_column_types(self, table, schema=None):
        raise NotImplementedError

    def get_foreign_keys(self, table, schema=None):
        return self.database.get_foreign_keys(table, schema)

    def get_primary_keys(self, table, schema=None):
        return self.database.get_primary_keys(table, schema)

    def get_indexes(self, table, schema=None):
        return self.database.get_indexes(table, schema)


class PostgresqlMetadata(Metadata):
    column_map = {
        16: BooleanField,
        17: BlobField,
        20: BigIntegerField,
        21: IntegerField,
        23: IntegerField,
        25: TextField,
        700: FloatField,
        701: FloatField,
        1042: CharField, # blank-padded CHAR
        1043: CharField,
        1082: DateField,
        1114: DateTimeField,
        1184: DateTimeField,
        1083: TimeField,
        1266: TimeField,
        1700: DecimalField,
        2950: TextField, # UUID
    }

    def __init__(self, database):
        super(PostgresqlMetadata, self).__init__(database)

        if postgres_ext is not None:
            # Attempt to add types like HStore and JSON.
            cursor = self.execute('select oid, typname from pg_type;')
            results = cursor.fetchall()

            for oid, typname in results:
                if 'json' in typname:
                    self.column_map[oid] = postgres_ext.JSONField
                elif 'hstore' in typname:
                    self.column_map[oid] = postgres_ext.HStoreField
                elif 'tsvector' in typname:
                    self.column_map[oid] = postgres_ext.TSVectorField

    def get_column_types(self, table, schema):
        column_types = {}

        # Look up the actual column type for each column.
        identifier = '"%s"."%s"' % (schema, table)
        cursor = self.execute('SELECT * FROM %s LIMIT 1' % identifier)

        # Store column metadata in dictionary keyed by column name.
        for column_description in cursor.description:
            column_types[column_description.name] = self.column_map.get(
                column_description.type_code,
                UnknownField)

        return column_types

    def get_columns(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_columns(table, schema)

    def get_foreign_keys(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_foreign_keys(table, schema)

    def get_primary_keys(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_primary_keys(table, schema)

    def get_indexes(self, table, schema=None):
        schema = schema or 'public'
        return super(PostgresqlMetadata, self).get_indexes(table, schema)


class MySQLMetadata(Metadata):
    if FIELD_TYPE is None:
        column_map = {}
    else:
        column_map = {
            FIELD_TYPE.BLOB: TextField,
            FIELD_TYPE.CHAR: CharField,
            FIELD_TYPE.DATE: DateField,
            FIELD_TYPE.DATETIME: DateTimeField,
            FIELD_TYPE.DECIMAL: DecimalField,
            FIELD_TYPE.DOUBLE: FloatField,
            FIELD_TYPE.FLOAT: FloatField,
            FIELD_TYPE.INT24: IntegerField,
            FIELD_TYPE.LONG_BLOB: TextField,
            FIELD_TYPE.LONG: IntegerField,
            FIELD_TYPE.LONGLONG: BigIntegerField,
            FIELD_TYPE.MEDIUM_BLOB: TextField,
            FIELD_TYPE.NEWDECIMAL: DecimalField,
            FIELD_TYPE.SHORT: IntegerField,
            FIELD_TYPE.STRING: CharField,
            FIELD_TYPE.TIMESTAMP: DateTimeField,
            FIELD_TYPE.TIME: TimeField,
            FIELD_TYPE.TINY_BLOB: TextField,
            FIELD_TYPE.TINY: IntegerField,
            FIELD_TYPE.VAR_STRING: CharField,
        }

    def __init__(self, database, **kwargs):
        if 'password' in kwargs:
            kwargs['passwd'] = kwargs.pop('password')
        super(MySQLMetadata, self).__init__(database, **kwargs)

    def get_column_types(self, table, schema=None):
        column_types = {}

        # Look up the actual column type for each column.
        cursor = self.execute('SELECT * FROM `%s` LIMIT 1' % table)

        # Store column metadata in dictionary keyed by column name.
        for column_description in cursor.description:
            name, type_code = column_description[:2]
            column_types[name] = self.column_map.get(type_code, UnknownField)

        return column_types


class SqliteMetadata(Metadata):
    column_map = {
        'bigint': BigIntegerField,
        'blob': BlobField,
        'bool': BooleanField,
        'boolean': BooleanField,
        'char': CharField,
        'date': DateField,
        'datetime': DateTimeField,
        'decimal': DecimalField,
        'integer': IntegerField,
        'integer unsigned': IntegerField,
        'int': IntegerField,
        'long': BigIntegerField,
        'real': FloatField,
        'smallinteger': IntegerField,
        'smallint': IntegerField,
        'smallint unsigned': IntegerField,
        'text': TextField,
        'time': TimeField,
    }

    begin = '(?:["\[\(]+)?'
    end = '(?:["\]\)]+)?'
    re_foreign_key = (
        '(?:FOREIGN KEY\s*)?'
        '{begin}(.+?){end}\s+(?:.+\s+)?'
        'references\s+{begin}(.+?){end}'
        '\s*\(["|\[]?(.+?)["|\]]?\)').format(begin=begin, end=end)
    re_varchar = r'^\s*(?:var)?char\s*\(\s*(\d+)\s*\)\s*$'

    def _map_col(self, column_type):
        raw_column_type = column_type.lower()
        if raw_column_type in self.column_map:
            field_class = self.column_map[raw_column_type]
        elif re.search(self.re_varchar, raw_column_type):
            field_class = CharField
        else:
            column_type = re.sub('\(.+\)', '', raw_column_type)
            field_class = self.column_map.get(column_type, UnknownField)
        return field_class

    def get_column_types(self, table, schema=None):
        column_types = {}
        columns = self.database.get_columns(table)

        for column in columns:
            column_types[column.name] = self._map_col(column.data_type)

        return column_types


_DatabaseMetadata = namedtuple('_DatabaseMetadata', (
    'columns',
    'primary_keys',
    'foreign_keys',
    'model_names',
    'indexes'))


class DatabaseMetadata(_DatabaseMetadata):
    def multi_column_indexes(self, table):
        accum = []
        for index in self.indexes[table]:
            if len(index.columns) > 1:
                field_names = [self.columns[table][column].name
                               for column in index.columns]
                accum.append((field_names, index.unique))
        return accum

    def column_indexes(self, table):
        accum = {}
        for index in self.indexes[table]:
            if len(index.columns) == 1:
                accum[index.columns[0]] = index.unique
        return accum


class Introspector(object):
    pk_classes = [PrimaryKeyField, IntegerField]

    def __init__(self, metadata, schema=None):
        self.metadata = metadata
        self.schema = schema

    def __repr__(self):
        return '<Introspector: %s>' % self.metadata.database

    @classmethod
    def from_database(cls, database, schema=None):
        if isinstance(database, PostgresqlDatabase):
            metadata = PostgresqlMetadata(database)
        elif isinstance(database, MySQLDatabase):
            metadata = MySQLMetadata(database)
        else:
            metadata = SqliteMetadata(database)
        return cls(metadata, schema=schema)

    def get_database_class(self):
        return type(self.metadata.database)

    def get_database_name(self):
        return self.metadata.database.database

    def get_database_kwargs(self):
        return self.metadata.database.connect_kwargs

    def make_model_name(self, table):
        model = re.sub('[^\w]+', '', table)
        return ''.join(sub.title() for sub in model.split('_'))

    def make_column_name(self, column):
        column = re.sub('_id$', '', column.lower()) or column.lower()
        if column in RESERVED_WORDS:
            column += '_'
        return column

    def introspect(self, table_names=None):
        # Retrieve all the tables in the database.
        if self.schema:
            tables = self.metadata.database.get_tables(schema=self.schema)
        else:
            tables = self.metadata.database.get_tables()

        if table_names is not None:
            tables = [table for table in tables if table in table_names]

        # Store a mapping of table name -> dictionary of columns.
        columns = {}

        # Store a mapping of table name -> set of primary key columns.
        primary_keys = {}

        # Store a mapping of table -> foreign keys.
        foreign_keys = {}

        # Store a mapping of table name -> model name.
        model_names = {}

        # Store a mapping of table name -> indexes.
        indexes = {}

        # Gather the columns for each table.
        for table in tables:
            table_indexes = self.metadata.get_indexes(table, self.schema)
            table_columns = self.metadata.get_columns(table, self.schema)
            try:
                foreign_keys[table] = self.metadata.get_foreign_keys(
                    table, self.schema)
            except ValueError as exc:
                err(exc.message)
                foreign_keys[table] = []

            model_names[table] = self.make_model_name(table)

            lower_col_names = set(column_name.lower()
                                  for column_name in table_columns)

            for col_name, column in table_columns.items():
                new_name = self.make_column_name(col_name)

                # If we have two columns, "parent" and "parent_id", ensure
                # that when we don't introduce naming conflicts.
                lower_name = col_name.lower()
                if lower_name.endswith('_id') and new_name in lower_col_names:
                    new_name = col_name.lower()

                column.name = new_name

            for index in table_indexes:
                if len(index.columns) == 1:
                    column = index.columns[0]
                    if column in table_columns:
                        table_columns[column].unique = index.unique
                        table_columns[column].index = True

            primary_keys[table] = self.metadata.get_primary_keys(
                table, self.schema)
            columns[table] = table_columns
            indexes[table] = table_indexes

        # Gather all instances where we might have a `related_name` conflict,
        # either due to multiple FKs on a table pointing to the same table,
        # or a related_name that would conflict with an existing field.
        related_names = {}
        sort_fn = lambda foreign_key: foreign_key.column
        for table in tables:
            models_referenced = set()
            for foreign_key in sorted(foreign_keys[table], key=sort_fn):
                try:
                    column = columns[table][foreign_key.column]
                except KeyError:
                    continue

                dest_table = foreign_key.dest_table
                if dest_table in models_referenced:
                    related_names[column] = '%s_%s_set' % (
                        dest_table,
                        column.name)
                else:
                    models_referenced.add(dest_table)

        # On the second pass convert all foreign keys.
        for table in tables:
            for foreign_key in foreign_keys[table]:
                src = columns[foreign_key.table][foreign_key.column]
                try:
                    dest = columns[foreign_key.dest_table][
                        foreign_key.dest_column]
                except KeyError:
                    dest = None

                src.set_foreign_key(
                    foreign_key=foreign_key,
                    model_names=model_names,
                    dest=dest,
                    related_name=related_names.get(src))

        return DatabaseMetadata(
            columns,
            primary_keys,
            foreign_keys,
            model_names,
            indexes)

    def generate_models(self, skip_invalid=False, table_names=None):
        database = self.introspect(table_names=table_names)
        models = {}

        class BaseModel(Model):
            class Meta:
                database = self.metadata.database

        def _create_model(table, models):
            for foreign_key in database.foreign_keys[table]:
                dest = foreign_key.dest_table

                if dest not in models and dest != table:
                    _create_model(dest, models)

            primary_keys = []
            columns = database.columns[table]
            for db_column, column in columns.items():
                if column.primary_key:
                    primary_keys.append(column.name)

            multi_column_indexes = database.multi_column_indexes(table)
            column_indexes = database.column_indexes(table)

            class Meta:
                indexes = multi_column_indexes

            # Fix models with multi-column primary keys.
            if len(primary_keys) == 0:
                primary_keys = columns.keys()
            if len(primary_keys) > 1:
                Meta.primary_key = CompositeKey([
                    field.name for col, field in columns.items()
                    if col in primary_keys])

            attrs = {'Meta': Meta}
            for db_column, column in columns.items():
                FieldClass = column.field_class
                if FieldClass is UnknownField:
                    FieldClass = BareField

                params = {
                    'db_column': db_column,
                    'null': column.nullable}
                if column.primary_key and FieldClass is not PrimaryKeyField:
                    params['primary_key'] = True
                if column.is_foreign_key():
                    if column.is_self_referential_fk():
                        params['rel_model'] = 'self'
                    else:
                        dest_table = column.foreign_key.dest_table
                        params['rel_model'] = models[dest_table]
                    if column.to_field:
                        params['to_field'] = column.to_field

                    # Generate a unique related name.
                    params['related_name'] = '%s_%s_rel' % (table, db_column)
                if db_column in column_indexes and not column.is_primary_key():
                    if column_indexes[db_column]:
                        params['unique'] = True
                    elif not column.is_foreign_key():
                        params['index'] = True

                attrs[column.name] = FieldClass(**params)

            try:
                models[table] = type(str(table), (BaseModel,), attrs)
            except ValueError:
                if not skip_invalid:
                    raise

        # Actually generate Model classes.
        for table, model in sorted(database.model_names.items()):
            if table not in models:
                _create_model(table, models)

        return models


def introspect(database, schema=None):
    introspector = Introspector.from_database(database, schema=schema)
    return introspector.introspect()
