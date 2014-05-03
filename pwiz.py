#!/usr/bin/env python

from optparse import OptionParser
import re
import sys

from peewee import *
from peewee import print_

try:
    from MySQLdb.constants import FIELD_TYPE
except ImportError:
    try:
        from pymysql.constants import FIELD_TYPE
    except ImportError:
        FIELD_TYPE = None


RESERVED_WORDS = set([
    'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif',
    'else', 'except', 'exec', 'finally', 'for', 'from', 'global', 'if', 'import',
    'in', 'is', 'lambda', 'not', 'or', 'pass', 'print', 'raise', 'return', 'try',
    'while', 'with', 'yield',
])

TEMPLATE = """from peewee import *

database = %s('%s', **%s)

class UnknownField(object):
    pass

class BaseModel(Model):
    class Meta:
        database = database
"""

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

        return params

    def is_primary_key(self):
        return self.field_class is PrimaryKeyField or self.primary_key

    def set_foreign_key(self, foreign_key, model_names):
        self.field_class = ForeignKeyField
        if foreign_key.dest_table == foreign_key.table:
            self.rel_model = "'self'"
        else:
            self.rel_model = model_names[foreign_key.dest_table]
        self.to_field = foreign_key.dest_column

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
    database_class = None

    def __init__(self, database, **kwargs):
        self._conn = self.connect(database, **kwargs)
        self.database = database
        self.database_kwargs = kwargs

    def execute(self, sql, *params):
        return self._conn.execute_sql(sql, params)

    def set_search_path(self, *path):
        self._conn.set_search_path(*path)

    def connect(self, database, **kwargs):
        return self.database_class(database, **kwargs)

    def get_tables(self):
        """Returns a list of table names."""
        return self._conn.get_tables()

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
    database_class = PostgresqlDatabase

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
    database_class = MySQLDatabase

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
    database_class = SqliteDatabase

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
            columns = re.search('\((.+)\)', table_definition).groups()[0]
        except AttributeError:
            print_('Unable to read table definition for "%s"' % table)
            return []

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


DATABASE_ALIASES = {
    SqliteMetadata: ['sqlite', 'sqlite3'],
    MySQLMetadata: ['mysql', 'mysqldb'],
    PostgresqlMetadata: ['postgres', 'postgresql'],
}
DATABASE_MAP = dict((value, key)
                    for key in DATABASE_ALIASES
                    for value in DATABASE_ALIASES[key])


def make_introspector(database_type, database, **kwargs):
    if database_type not in DATABASE_MAP:
        err('Unrecognized database, must be one of: %s' %
            ', '.join(DATABASE_MAP.keys()))
        sys.exit(1)

    schema = kwargs.pop('schema', None)
    metadata = DATABASE_MAP[database_type](database, **kwargs)

    if schema:
        metadata.set_search_path(*schema.split(','))

    return Introspector(metadata, schema=schema)


class Introspector(object):
    pk_classes = [PrimaryKeyField, IntegerField]

    def __init__(self, metadata, schema=None):
        self.metadata = metadata
        self.schema = schema

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
            foreign_keys[table] = self.metadata.get_foreign_keys(
                table, self.schema)
            model_names[table] = self.make_model_name(table)

        # On the second pass convert all foreign keys.
        for table in tables:
            for foreign_key in foreign_keys[table]:
                src = columns[foreign_key.table][foreign_key.column]
                src.set_foreign_key(foreign_key, model_names)

            for column_name, column in columns[table].items():
                column.name = self.make_column_name(column_name)

        return columns, foreign_keys, model_names

    def print_models(self, tables=None):
        columns, foreign_keys, model_names = self.introspect()
        print_(TEMPLATE % (
            self.metadata.database_class.__name__,
            self.metadata.database,
            repr(self.metadata.database_kwargs)))

        def _print_table(table, seen, accum=None):
            accum = accum or []
            for foreign_key in foreign_keys[table]:
                dest = foreign_key.dest_table

                # In the event the destination table has already been pushed
                # for printing, then we have a reference cycle.
                if dest in accum and table not in accum:
                    print_('# Possible reference cycle: %s' % foreign_key)

                # If this is not a self-referential foreign key, and we have
                # not already processed the destination table, do so now.
                if dest not in seen and dest not in accum:
                    seen.add(dest)
                    if dest != table:
                        _print_table(dest, seen, accum + [table])

            print_('class %s(BaseModel):' % model_names[table])
            for name, column in sorted(columns[table].items()):
                if name == 'id' and column.field_class in self.pk_classes:
                    continue

                print_('    %s' % column.get_field())

            print_('')
            print_('    class Meta:')
            print_('        db_table = \'%s\'' % table)
            print_('')

            seen.add(table)

        seen = set()
        for table in sorted(model_names.keys()):
            if table not in seen:
                if not tables or table in tables:
                    _print_table(table, seen)


def err(msg):
    sys.stderr.write('\033[91m%s\033[0m\n' % msg)
    sys.stderr.flush()


if __name__ == '__main__':
    parser = OptionParser(usage='usage: %prog [options] database_name')
    ao = parser.add_option
    ao('-H', '--host', dest='host')
    ao('-p', '--port', dest='port', type='int')
    ao('-u', '--user', dest='user')
    ao('-P', '--password', dest='password')
    ao('-e', '--engine', dest='engine', default='postgresql')
    ao('-s', '--schema', dest='schema')
    ao('-t', '--tables', dest='tables')

    options, args = parser.parse_args()
    ops = ('host', 'port', 'user', 'password', 'schema')
    connect = dict((o, getattr(options, o)) for o in ops if getattr(options, o))

    if len(args) < 1:
        err('Missing required parameter "database"')
        parser.print_help()
        sys.exit(1)

    database = args[-1]

    tables = None
    if options.tables:
        tables = [x for x in options.tables.split(',') if x]

    introspector = make_introspector(options.engine, database, **connect)
    introspector.print_models(tables)
