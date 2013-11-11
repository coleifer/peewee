#!/usr/bin/env python
"""
            .----.
           ===(_)==   THIS WONT HURT A BIT...
          // 6  6 \\  /
          (    7   )
           \ '--' /
            \_ ._/
           __)  (__
        /"`/`\`V/`\`\
       /   \  `Y _/_ \
      / [DR]\_ |/ / /\
      |     ( \/ / / /
       \  \  \      /
        \  `-/`  _.`
         `=. `=./
            `"`
"""
from collections import namedtuple
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


class UnknownFieldType(object):
    pass

RESERVED_WORDS = set([
    'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif',
    'else', 'except', 'exec', 'finally', 'for', 'from', 'global', 'if', 'import',
    'in', 'is', 'lambda', 'not', 'or', 'pass', 'print', 'raise', 'return', 'try',
    'while', 'with', 'yield',
])

class ColumnInfo(object):
    __slots__ = ['field_class', 'nullable', 'is_pk']

    def __init__(self, field_class, nullable, is_pk=False):
        self.field_class = field_class
        self.nullable = nullable
        self.is_pk = is_pk

ForeignKeyMapping = namedtuple('ForeignKeyMapping', ('column', 'table', 'pk'))

class Introspector(object):
    conn = None
    peewee_mapping = {}

    def get_conn_class(self):
        raise NotImplementedError

    def get_columns(self, table):
        """
        Get the names, field type and attributes for the columns in the
        given table.

        Arguments:
            table str: the name of the table to introspect

        Returns:
            A dictionary keyed by the column name, mapped to a ColumnInfo
            object.
        """
        raise NotImplementedError

    def get_foreign_keys(self, table):
        """
        Get the foreign keys from the given table to other tables/columns.

        Arguments:
            table str: the name of the table to introspect

        Returns:
            A list of `ForeignKeyMapping`s
        """
        raise NotImplementedError

    def get_tables(self):
        """Returns a list of table names."""
        return self.conn.get_tables()

    def connect(self, database, **connect):
        """
        Open a connection to the given database, passing along any keyword
        arguments.
        """
        conn_class = self.get_conn_class()
        self.conn = conn_class(database, **connect)
        try:
            self.conn.connect()
        except:
            err('error connecting to %s' % database)
            raise


class PostgresqlIntrospector(Introspector):
    mapping = {
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

    def get_conn_class(self):
        return PostgresqlDatabase

    def get_columns(self, table):
        curs = self.conn.execute_sql("""
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_name=%s""", (table,))
        null_map = dict(curs.fetchall())
        curs = self.conn.execute_sql('select * from "%s" limit 1' % table)
        accum = {}
        for column in curs.description:
            field_class = self.mapping.get(column.type_code, UnknownFieldType)
            is_null = null_map[column.name] == 'YES'
            accum[column.name] = ColumnInfo(field_class, is_null)

        curs = self.conn.execute_sql("""
            SELECT pg_attribute.attname
            FROM pg_index, pg_class, pg_attribute
            WHERE
              pg_class.oid = '%s'::regclass AND
              indrelid = pg_class.oid AND
              pg_attribute.attrelid = pg_class.oid AND
              pg_attribute.attnum = any(pg_index.indkey)
              AND indisprimary;""" % table)
        pks = [x[0] for x in curs.fetchall()]
        for pk in pks:
            accum[pk].field_class = PrimaryKeyField

        return accum

    def get_foreign_keys(self, table, schema='public'):
        framing = '''
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
                tc.table_schema = %s
        '''
        fks = []
        for row in self.conn.execute_sql(framing, (table,schema)):
            fks.append(ForeignKeyMapping(*row))
        return fks


class MySQLIntrospector(Introspector):
    if FIELD_TYPE is None:
        mapping = {}
    else:
        mapping = {
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

    def get_conn_class(self):
        return MySQLDatabase

    def get_columns(self, table):
        curs = self.conn.execute_sql('select * from `%s` limit 1' % table)
        accum = {}
        for column in curs.description:
            field_class = self.mapping.get(column[1], UnknownFieldType)
            accum[column[0]] = ColumnInfo(field_class, column[6])
        return accum

    def get_foreign_keys(self, table):
        framing = '''
            SELECT column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_name = %s
                AND table_schema = DATABASE()
                AND referenced_table_name IS NOT NULL
                AND referenced_column_name IS NOT NULL
        '''
        cursor = self.conn.execute_sql(framing, (table,))
        return [ForeignKeyMapping(*row) for row in cursor]


class SqliteIntrospector(Introspector):
    mapping = {
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
        'real': FloatField,
        'smallinteger': IntegerField,
        'smallint': IntegerField,
        'smallint unsigned': IntegerField,
        'text': TextField,
        'time': TimeField,
    }
    re_foreign_key = '["\[]?(.+?)["\]]?\s+.+\s+references ["\[]?(.+?)["\]]? \(["|\[]?(.+?)["|\]]?\)'
    re_varchar = r'^\s*(?:var)?char\s*\(\s*(\d+)\s*\)\s*$'

    def get_conn_class(self):
        return SqliteDatabase

    def map_col(self, column_type):
        column_type = column_type.lower()
        if column_type in self.mapping:
            return self.mapping[column_type]
        elif re.search(self.re_varchar, column_type):
            return CharField
        else:
            column_type = re.sub('\(.+\)', '', column_type)
            return self.mapping.get(column_type, UnknownFieldType)

    def get_columns(self, table):
        curs = self.conn.execute_sql('pragma table_info("%s")' % table)
        accum = {}
        # cid, name, type, notnull, dflt_value, pk
        for (_, name, column_type, not_null, _, is_pk) in curs.fetchall():
            if is_pk:
                field_class = PrimaryKeyField
            else:
                field_class = self.map_col(column_type)
            accum[name] = ColumnInfo(field_class, not not_null)
        return accum

    def get_foreign_keys(self, table):
        curs = self.conn.execute_sql("SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = ?", [table, "table"])
        table_def = curs.fetchone()[0].strip()

        try:
            columns = re.search('\((.+)\)', table_def).groups()[0]
        except AttributeError:
            err('Unable to read table definition for "%s"' % table)
            return []

        fks = []
        for column_def in columns.split(','):
            column_def = column_def.strip()
            match = re.search(self.re_foreign_key, column_def, re.I)
            if not match:
                continue

            fk_column, rel_table, rel_pk = [s.strip('"') for s in match.groups()]
            fks.append(ForeignKeyMapping(fk_column, rel_table, rel_pk))
        return fks


TEMPLATE = '''from peewee import *

database = %s('%s', **%s)

class UnknownFieldType(object):
    pass

class BaseModel(Model):
    class Meta:
        database = database
'''

ENGINE_MAPPING = {
    'postgresql': PostgresqlIntrospector,
    'postgres': PostgresqlIntrospector,
    'sqlite': SqliteIntrospector,
    'mysql': MySQLIntrospector,
}

def get_introspector(engine, database, **connect):
    if engine not in ENGINE_MAPPING:
        err('Unsupported engine: "%s"' % engine)
        sys.exit(1)

    introspector = ENGINE_MAPPING[engine]()
    schema = connect.pop('schema', None)
    introspector.connect(database, **connect)

    if schema:
        introspector.conn.set_search_path(*schema.split(','))
    return introspector

def introspect(db, schema=None):
    tables = db.get_tables()

    table_columns = {}
    table_to_model = {}
    table_fks = {}

    # first pass, just raw column names and peewee type
    for table in tables:
        table_columns[table] = db.get_columns(table)
        table_to_model[table] = tn(table)
        if schema:
            table_fks[table] = db.get_foreign_keys(table, schema)
        else:
            table_fks[table] = db.get_foreign_keys(table)

    # second pass, convert foreign keys, assign primary keys, and mark
    # explicit column names where they don't match the "pythonic" ones
    column_metadata = {}
    for table in tables:
        column_metadata[table] = {}
        for column, rel_table, rel_pk in table_fks[table]:
            is_pk = table_columns[table][column].field_class is PrimaryKeyField
            table_columns[table][column].field_class = ForeignKeyField
            table_columns[rel_table][rel_pk].field_class = PrimaryKeyField
            if rel_table == table:
                ttm = "'self'"
            else:
                ttm = table_to_model[rel_table]
            column_metadata[table][column] = {'rel_model': ttm}
            if is_pk:
                column_metadata[table][column]['primary_key'] = True

        for col_name, column_info in table_columns[table].items():
            column_metadata[table].setdefault(col_name, {})
            if column_info.field_class is ForeignKeyField:
                column_metadata[table][col_name]['db_column'] = "'%s'" % col_name
            elif col_name != cn(col_name):
                column_metadata[table][col_name]['db_column'] = "'%s'" % col_name
            if column_info.nullable:
                column_metadata[table][col_name]['null'] = "True"

    return table_columns, table_to_model, table_fks, column_metadata

def print_models(engine, database, tables, **connect):
    schema = connect.get('schema')
    db = get_introspector(engine, database, **connect)

    models, table_to_model, table_fks, col_meta = introspect(db, schema)

    # write generated code to standard out
    print_(TEMPLATE % (db.get_conn_class().__name__, database, repr(connect)))
    pk_classes = (IntegerField, PrimaryKeyField)

    # print the models
    def print_model(model, seen, accum=None):
        accum = accum or []

        for _, rel_table, _ in table_fks[model]:
            if rel_table in accum and model not in accum:
                print_('# POSSIBLE REFERENCE CYCLE: %s' % table_to_model[rel_table])

            if rel_table not in seen and rel_table not in accum:
                seen.add(rel_table)
                if rel_table != model:
                    print_model(rel_table, seen, accum + [model])

        ttm = table_to_model[model]
        print_('class %s(BaseModel):' % ttm)
        cols = models[model]
        for column, column_info in ds(cols):
            if column == 'id' and column_info.field_class in pk_classes:
                continue

            field_params = ', '.join([
                '%s=%s' % (k, v) for k, v in col_meta[model][column].items()
            ])
            colname = cn(column)
            if colname in RESERVED_WORDS:
                print_('    # FIXME: "%s" is a reserved word' % colname)
                colname = '#' + colname
            print_('    %s = %s(%s)' % (
                colname, column_info.field_class.__name__, field_params))
        print_('')

        print_('    class Meta:')
        print_('        db_table = \'%s\'' % model)
        print_('')
        seen.add(model)

    seen = set()
    for model, cols in ds(models):
        if model not in seen:
            if not tables or model in tables:
                print_model(model, seen)

# misc
tn = lambda t: re.sub('[^\w]+', '', t.title())
cn = lambda c: re.sub('_id$', '', c.lower())
ds = lambda d: sorted(d.items(), key=lambda t:t[0])

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
        print_('error: missing required parameter "database"')
        parser.print_help()
        sys.exit(1)

    database = args[-1]

    if options.engine == 'mysql' and 'password' in connect:
        connect['passwd'] = connect.pop('password', None)

    if options.tables:
        tables = [x for x in options.tables.split(',') if x]
    else:
        tables = []
    print_models(options.engine, database, tables, **connect)
