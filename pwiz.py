#!/usr/bin/env python
#            .----.
#           ===(_)==   THIS WONT HURT A BIT...
#          // 6  6 \\  /
#          (    7   )
#           \ '--' /
#            \_ ._/
#           __)  (__
#        /"`/`\`V/`\`\
#       /   \  `Y _/_ \
#      / [DR]\_ |/ / /\
#      |     ( \/ / / /
#       \  \  \      /
#        \  `-/`  _.`
#         `=. `=./
#            `"`
from optparse import OptionParser
import re
import sys

try:
    from MySQLdb.constants import FIELD_TYPE
    MYSQL_MAP = {
        FIELD_TYPE.BLOB: 'TextField',
        FIELD_TYPE.CHAR: 'CharField',
        FIELD_TYPE.DECIMAL: 'DecimalField',
        FIELD_TYPE.NEWDECIMAL: 'DecimalField',
        FIELD_TYPE.DATE: 'DateField',
        FIELD_TYPE.DATETIME: 'DateTimeField',
        FIELD_TYPE.DOUBLE: 'FloatField',
        FIELD_TYPE.FLOAT: 'FloatField',
        FIELD_TYPE.INT24: 'IntegerField',
        FIELD_TYPE.LONG: 'IntegerField',
        FIELD_TYPE.LONGLONG: 'BigIntegerField',
        FIELD_TYPE.SHORT: 'IntegerField',
        FIELD_TYPE.STRING: 'CharField',
        FIELD_TYPE.TIME: 'TimeField',
        FIELD_TYPE.TIMESTAMP: 'DateTimeField',
        FIELD_TYPE.TINY: 'IntegerField',
        FIELD_TYPE.TINY_BLOB: 'TextField',
        FIELD_TYPE.MEDIUM_BLOB: 'TextField',
        FIELD_TYPE.LONG_BLOB: 'TextField',
        FIELD_TYPE.VAR_STRING: 'CharField',
    }
except ImportError:
    MYSQL_MAP = {}

from peewee import *


class DB(object):
    conn = None

    def get_conn_class(self):
        raise NotImplementedError

    def get_columns(self, table):
        """
        get_columns('some_table')

        {
            'name': 'CharField',
            'age': 'IntegerField',
        }
        """
        raise NotImplementedError

    def get_foreign_keys(self, table):
        """
        get_foreign_keys('some_table')

        [
            # column,   rel table,  rel pk
            ('blog_id', 'blog',     'id'),
            ('user_id', 'users',    'id'),
        ]
        """
        raise NotImplementedError

    def get_tables(self):
        return self.conn.get_tables()

    def connect(self, database, **connect):
        conn_class = self.get_conn_class()
        self.conn = conn_class(database, **connect)
        try:
            self.conn.connect()
        except:
            err('error connecting to %s' % database)
            raise


class PgDB(DB):
    # thanks, django
    reverse_mapping = {
        16: 'BooleanField',
        20: 'IntegerField',
        21: 'IntegerField',
        23: 'IntegerField',
        25: 'TextField',
        700: 'FloatField',
        701: 'FloatField',
        1042: 'CharField', # blank-padded CHAR
        1043: 'CharField',
        1082: 'DateField',
        1114: 'DateTimeField',
        1184: 'DateTimeField',
        1083: 'TimeField',
        1266: 'TimeField',
        1700: 'DecimalField',
        2950: 'TextField', # UUID
    }

    def get_conn_class(self):
        return PostgresqlDatabase

    def get_columns(self, table):
        curs = self.conn.execute_sql('select * from %s limit 1' % table)
        return dict((c.name, self.reverse_mapping.get(c.type_code, 'UnknownFieldType')) for c in curs.description)

    def get_foreign_keys(self, table):
        framing = '''
            SELECT
                kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE
                tc.constraint_type = 'FOREIGN KEY' AND
                tc.table_name = %s
        '''
        fks = []
        for row in self.conn.execute_sql(framing, (table,)):
            fks.append(row)
        return fks


class MySQLDB(DB):
    # thanks, django
    reverse_mapping = MYSQL_MAP

    def get_conn_class(self):
        return MySQLDatabase

    def get_columns(self, table):
        curs = self.conn.execute_sql('select * from %s limit 1' % table)
        return dict((r[0], self.reverse_mapping.get(r[1], 'UnknownFieldType')) for r in curs.description)

    def get_foreign_keys(self, table):
        framing = '''
            SELECT column_name, referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_name = %s
                AND table_schema = DATABASE()
                AND referenced_table_name IS NOT NULL
                AND referenced_column_name IS NOT NULL
        '''
        return [row for row in self.conn.execute_sql(framing, (table,))]


class SqDB(DB):
    # thanks, django
    reverse_mapping = {
        'bool': 'BooleanField',
        'boolean': 'BooleanField',
        'smallint': 'IntegerField',
        'smallint unsigned': 'IntegerField',
        'smallinteger': 'IntegerField',
        'int': 'IntegerField',
        'integer': 'IntegerField',
        'bigint': 'BigIntegerField',
        'integer unsigned': 'IntegerField',
        'decimal': 'DecimalField',
        'real': 'FloatField',
        'text': 'TextField',
        'char': 'CharField',
        'date': 'DateField',
        'datetime': 'DateTimeField',
        'time': 'TimeField',
    }

    def get_conn_class(self):
        return SqliteDatabase

    def map_col(self, col):
        col = col.lower()
        if col in self.reverse_mapping:
            return self.reverse_mapping[col]
        elif re.search(r'^\s*(?:var)?char\s*\(\s*(\d+)\s*\)\s*$', col):
            return 'CharField'
        else:
            return 'UnknownFieldType'

    def get_columns(self, table):
        curs = self.conn.execute_sql('pragma table_info(%s)' % table)
        col_dict = {}
        for (_, name, col, not_null, _, is_pk) in curs.fetchall():
            # cid, name, type, notnull, dflt_value, pk
            if is_pk:
                col_type = 'PrimaryKeyField'
            else:
                col_type = self.map_col(col)
            col_dict[name] = col_type
        return col_dict

    def get_foreign_keys(self, table):
        fks = []

        curs = self.conn.execute_sql("SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = ?", [table, "table"])
        table_def = curs.fetchone()[0].strip()

        try:
            columns = re.search('\((.+)\)', table_def).groups()[0]
        except AttributeError:
            err('Unable to read table definition for "%s"' % table)
            sys.exit(1)

        for col_def in columns.split(','):
            col_def = col_def.strip()
            m = re.search('"?(.+?)"?\s+.+\s+references (.*) \(["|]?(.*)["|]?\)', col_def, re.I)
            if not m:
                continue

            fk_column, rel_table, rel_pk = [s.strip('"') for s in m.groups()]
            fks.append((fk_column, rel_table, rel_pk))

        return fks


frame = '''from peewee import *

database = %s('%s', **%s)

class UnknownFieldType(object):
    pass

class BaseModel(Model):
    class Meta:
        database = database
'''

engine_mapping = {
    'postgresql': PgDB,
    'sqlite': SqDB,
    'mysql': MySQLDB,
}

def get_db(engine):
    if engine not in engine_mapping:
        err('Unsupported engine: "%s"' % engine)
        sys.exit(1)

    db_class = engine_mapping[engine]
    return db_class()

def introspect(engine, database, **connect):
    db = get_db(engine)
    schema = connect.pop('schema', None)
    db.connect(database, **connect)

    if schema:
        db.conn.set_search_path(*schema.split(','))

    tables = db.get_tables()

    models = {}
    table_to_model = {}
    table_fks = {}

    # first pass, just raw column names and peewee type
    for table in tables:
        models[table] = db.get_columns(table)
        table_to_model[table] = tn(table)
        table_fks[table] = db.get_foreign_keys(table)

    # second pass, convert foreign keys, assign primary keys, and mark
    # explicit column names where they don't match the "pythonic" ones
    col_meta = {}
    for table in tables:
        col_meta[table] = {}
        for column, rel_table, rel_pk in table_fks[table]:
            models[table][column] = 'ForeignKeyField'
            models[rel_table][rel_pk] = 'PrimaryKeyField'
            col_meta[table][column] = {'rel_model': table_to_model[rel_table]}

        for column in models[table]:
            col_meta[table].setdefault(column, {})
            if column != cn(column):
                col_meta[table][column]['db_column'] = "'%s'" % column

    # write generated code to standard out
    print frame % (db.get_conn_class().__name__, database, repr(connect))

    # print the models
    def print_model(model, seen):
        for _, rel_table, _ in table_fks[model]:
            if rel_table not in seen:
                seen.add(rel_table)
                print_model(rel_table, seen)

        ttm = table_to_model[model]
        print 'class %s(BaseModel):' % ttm
        cols = models[model]
        for column, field_class in ds(cols):
            if column == 'id' and field_class in ('IntegerField', 'PrimaryKeyField'):
                continue

            field_params = ', '.join([
                '%s=%s' % (k, v) for k, v in col_meta[model][column].items()
            ])
            print '    %s = %s(%s)' % (cn(column), field_class, field_params)
        print

        print '    class Meta:'
        print '        db_table = \'%s\'' % model
        print
        seen.add(model)

    seen = set()
    for model, cols in ds(models):
        if model not in seen:
            print_model(model, seen)

# misc
tn = lambda t: t.title().replace('_', '')
cn = lambda c: re.sub('_id$', '', c.lower())
ds = lambda d: sorted(d.items(), key=lambda t:t[0])

def err(msg):
    print '\033[91m%s\033[0m' % msg


if __name__ == '__main__':
    parser = OptionParser(usage='usage: %prog [options] database_name')
    ao = parser.add_option
    ao('-H', '--host', dest='host')
    ao('-p', '--port', dest='port', type='int')
    ao('-u', '--user', dest='user')
    ao('-P', '--password', dest='password')
    ao('-e', '--engine', dest='engine', default='postgresql')
    ao('-s', '--schema', dest='schema')

    options, args = parser.parse_args()
    ops = ('host', 'port', 'user', 'password', 'schema')
    connect = dict((o, getattr(options, o)) for o in ops if getattr(options, o))

    if len(args) < 1:
        print 'error: missing required parameter "database"'
        parser.print_help()
        sys.exit(1)

    database = args[-1]
    
    if options.engine == 'mysql' and 'password' in connect:
        connect['passwd'] = connect.pop('password', None)

    introspect(options.engine, database, **connect)
