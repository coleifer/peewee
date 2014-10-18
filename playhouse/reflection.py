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
                 primary_key=False, max_length=None, db_column=None):
        self.name = name
        self.field_class = field_class
        self.raw_column_type = raw_column_type
        self.nullable = nullable
        self.primary_key = primary_key
        self.max_length = max_length
        self.db_column = db_column

    def __repr__(self):
        attrs = [
            'field_class',
            'raw_column_type',
            'nullable',
            'primary_key',
            'max_length',
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
        if self.field_class is CharField and self.max_length:
            params['max_length'] = self.max_length
        if self.field_class is ForeignKeyField or self.name != self.db_column:
            params['db_column'] = "'%s'" % self.db_column
        if self.primary_key and not self.field_class is PrimaryKeyField:
            params['primary_key'] = True

        # Handle ForeignKeyField-specific attributes.
        if self.field_class is ForeignKeyField:
            params['rel_model'] = self.rel_model
            if self.to_field:
                params['to_field'] = "'%s'" % self.to_field

        return params

    def is_primary_key(self):
        return self.field_class is PrimaryKeyField or self.primary_key

    def is_foreign_key(self):
        return self.field_class is ForeignKeyField

    def is_self_referential_fk(self):
        return (self.field_class is ForeignKeyField and
                self.rel_model == "'self'")

    def set_foreign_key(self, foreign_key, model_names, dest=None):
        self.foreign_key = foreign_key
        self.field_class = ForeignKeyField
        if foreign_key.dest_table == foreign_key.table:
            self.rel_model = "'self'"
        else:
            self.rel_model = model_names[foreign_key.dest_table]
        self.to_field = dest and dest.name or None

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


class ForeignKeyMapping(object):
    def __init__(self, table, column, dest_table, dest_column):
        self.table = table
        self.column = column
        self.dest_table = dest_table
        self.dest_column = dest_column

    def __repr__(self):
        return 'ForeignKeyMapping(%s.%s -> %s.%s)' % (
            self.table,
            self.column,
            self.dest_table,
            self.dest_column)


class Metadata(object):
    column_map = {}

    def __init__(self, database):
        self.database = database

    def execute(self, sql, *params):
        return self.database.execute_sql(sql, params)

    def set_search_path(self, *path):
        self.database.set_search_path(*path)

    def get_tables(self):
        """Returns a list of table names."""
        return self.database.get_tables()

    def get_columns(self, table):
        pass

    def get_foreign_keys(self, table, schema=None):
        pass


class PostgresqlMetadata(Metadata):
    # select oid, typname from pg_type;
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

    def get_columns(self, table):
        # Get basic metadata about columns.
        cursor = self.execute("""
            SELECT
                column_name, is_nullable, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name=%s""", table)
        name_to_info = {}
        for row in cursor.fetchall():
            name_to_info[row[0]] = {
                'db_column': row[0],
                'nullable': row[1] == 'YES',
                'raw_column_type': row[2],
                'max_length': row[3],
                'primary_key': False,
            }

        # Look up the actual column type for each column.
        cursor = self.execute('SELECT * FROM "%s" LIMIT 1' % table)

        # Store column metadata in dictionary keyed by column name.
        for column_description in cursor.description:
            field_class = self.column_map.get(
                column_description.type_code,
                UnknownField)
            column = column_description.name
            name_to_info[column]['field_class'] = field_class

        # Look up the primary keys.
        cursor = self.execute("""
            SELECT pg_attribute.attname
            FROM pg_index, pg_class, pg_attribute
            WHERE
              pg_class.oid = '%s'::regclass AND
              indrelid = pg_class.oid AND
              pg_attribute.attrelid = pg_class.oid AND
              pg_attribute.attnum = any(pg_index.indkey)
              AND indisprimary;""" % table)
        pk_names = [row[0] for row in cursor.fetchall()]
        for pk_name in pk_names:
            name_to_info[pk_name]['primary_key'] = True
            if name_to_info[pk_name]['field_class'] is IntegerField:
                name_to_info[pk_name]['field_class'] = PrimaryKeyField

        columns = {}
        for name, column_info in name_to_info.items():
            columns[name] = Column(
                name,
                field_class=column_info['field_class'],
                raw_column_type=column_info['raw_column_type'],
                nullable=column_info['nullable'],
                primary_key=column_info['primary_key'],
                max_length=column_info['max_length'],
                db_column=name)

        return columns

    def get_foreign_keys(self, table, schema=None):
        schema = schema or 'public'
        sql = """
            SELECT
                kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON (tc.constraint_name = kcu.constraint_name AND
                    tc.constraint_schema = kcu.constraint_schema)
            JOIN information_schema.constraint_column_usage AS ccu
                ON (ccu.constraint_name = tc.constraint_name AND
                    ccu.constraint_schema = tc.constraint_schema)
            WHERE
                tc.constraint_type = 'FOREIGN KEY' AND
                tc.table_name = %s AND
                tc.table_schema = %s"""
        cursor = self.execute(sql, table, schema)
        return [
            ForeignKeyMapping(table, column, dest_table, dest_column)
            for column, dest_table, dest_column in cursor]


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

    def get_columns(self, table):
        pk_name = self.get_primary_key(table)

        # Get basic metadata about columns.
        cursor = self.execute("""
            SELECT
                column_name, is_nullable, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name=%s AND table_schema=DATABASE()""", table)
        name_to_info = {}
        for row in cursor.fetchall():
            name_to_info[row[0]] = {
                'db_column': row[0],
                'nullable': row[1] == 'YES',
                'raw_column_type': row[2],
                'max_length': row[3],
                'primary_key': False,
            }

        # Look up the actual column type for each column.
        cursor = self.execute('SELECT * FROM `%s` LIMIT 1' % table)

        # Store column metadata in dictionary keyed by column name.
        for column_description in cursor.description:
            name, type_code = column_description[:2]
            field_class = self.column_map.get(type_code, UnknownField)

            if name == pk_name:
                name_to_info[name]['primary_key'] = True
                if field_class is IntegerField:
                    field_class = PrimaryKeyField

            name_to_info[name]['field_class'] = field_class

        columns = {}
        for name, column_info in name_to_info.items():
            columns[name] = Column(
                name,
                field_class=column_info['field_class'],
                raw_column_type=column_info['raw_column_type'],
                nullable=column_info['nullable'],
                primary_key=column_info['primary_key'],
                max_length=column_info['max_length'],
                db_column=name)

        return columns

    def get_primary_key(self, table):
        cursor = self.execute('SHOW INDEX FROM `%s`' % table)
        for row in cursor.fetchall():
            if row[2] == 'PRIMARY':
                return row[4]

    def get_foreign_keys(self, table, schema=None):
        framing = """
            SELECT column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_name = %s
                AND table_schema = DATABASE()
                AND referenced_table_name IS NOT NULL
                AND referenced_column_name IS NOT NULL
        """
        cursor = self.execute(framing, table)
        return [
            ForeignKeyMapping(table, column, dest_table, dest_column)
            for column, dest_table, dest_column in cursor]


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
        return field_class, raw_column_type

    def get_columns(self, table):
        columns = {}

        # Column ID, Name, Column Type, Not Null?, Default, Is Primary Key?
        cursor = self.execute('PRAGMA table_info("%s")' % table)

        for (_, name, column_type, not_null, _, is_pk) in cursor.fetchall():
            field_class, raw_column_type = self._map_col(column_type)

            if is_pk and field_class == IntegerField:
                field_class = PrimaryKeyField

            max_length = None
            if field_class is CharField:
                match = re.match('\w+\((\d+)\)', column_type)
                if match:
                    max_length, = match.groups()

            columns[name] = Column(
                name,
                field_class=field_class,
                raw_column_type=raw_column_type,
                nullable=not not_null,
                primary_key=is_pk,
                max_length=max_length,
                db_column=name)

        return columns

    def get_foreign_keys(self, table, schema=None):
        query = """
            SELECT sql
            FROM sqlite_master
            WHERE (tbl_name = ? AND type = ?)"""
        cursor = self.execute(query, table, 'table')
        table_definition = cursor.fetchone()[0].strip()

        try:
            columns = re.search(
                '\((.+)\)',
                table_definition,
                re.MULTILINE | re.DOTALL).groups()[0]
        except AttributeError:
            raise ValueError(
                'Unable to read table definition for "%s"' % table)

        # Replace any new-lines or other junk with whitespace.
        columns = re.sub('[\s\n\r]+', ' ', columns).strip()

        fks = []
        for column_def in columns.split(','):
            column_def = column_def.strip()
            match = re.search(self.re_foreign_key, column_def, re.I)
            if not match:
                continue

            column, dest_table, dest_column = [
                s.strip('"') for s in match.groups()]
            fks.append(ForeignKeyMapping(
                table=table,
                column=column,
                dest_table=dest_table,
                dest_column=dest_column))

        return fks


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

    def introspect(self):
        # Retrieve all the tables in the database.
        tables = self.metadata.get_tables()

        # Store a mapping of table name -> dictionary of columns.
        columns = {}

        # Store a mapping of table -> foreign keys.
        foreign_keys = {}

        # Store a mapping of table name -> model name.
        model_names = {}

        # Gather the columns for each table.
        for table in tables:
            columns[table] = self.metadata.get_columns(table)
            try:
                foreign_keys[table] = self.metadata.get_foreign_keys(
                    table, self.schema)
            except ValueError as exc:
                err(exc.message)
                foreign_keys[table] = []

            model_names[table] = self.make_model_name(table)

            for column_name, column in columns[table].items():
                column.name = self.make_column_name(column_name)

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
                    foreign_key,
                    model_names,
                    dest)

        return columns, foreign_keys, model_names

    def generate_models(self):
        columns, foreign_keys, model_names = self.introspect()
        models = {}

        class BaseModel(Model):
            class Meta:
                database = self.metadata.database

        def _create_model(table, models):
            for foreign_key in foreign_keys[table]:
                dest = foreign_key.dest_table

                if dest not in models and dest != table:
                    _create_model(dest, models)

            attrs = {}
            for db_column, column in columns[table].items():
                FieldClass = column.field_class
                if FieldClass is UnknownField:
                    FieldClass = BareField

                params = {
                    'db_column': db_column,
                    'null': column.nullable}
                if FieldClass is CharField and column.max_length:
                    params['max_length'] = int(column.max_length)
                if column.primary_key and not FieldClass is PrimaryKeyField:
                    params['primary_key'] = True
                if FieldClass is ForeignKeyField:
                    if column.is_self_referential_fk():
                        params['rel_model'] = 'self'
                    else:
                        dest_table = column.foreign_key.dest_table
                        params['rel_model'] = models[dest_table]
                    if column.to_field:
                        params['to_field'] = column.to_field

                    # Generate a unique related name.
                    params['related_name'] = '%s_%s_rel' % (table, db_column)

                attrs[column.name] = FieldClass(**params)

            models[table] = type(str(table), (BaseModel,), attrs)

        # Actually generate Model classes.
        for table, model in sorted(model_names.items()):
            if table not in models:
                _create_model(table, models)

        return models


def introspect(database, schema=None):
    introspector = Introspector.from_database(database, schema=schema)
    return introspector.introspect()
