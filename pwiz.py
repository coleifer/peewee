from optparse import OptionParser
from psycopg2 import OperationalError
import re
import sys

from peewee import *

# thanks, django
reverse_mapping = {
    16: 'BooleanField',
    20: 'IntegerField',
    21: 'IntegerField',
    23: 'IntegerField',
    25: 'TextField',
    700: 'FloatField',
    701: 'FloatField',
    1043: 'CharField',
    1114: 'DateTimeField',
    1184: 'DateTimeField',
    1700: 'DecimalField',
}

def get_conn(database, **connect):
    db = PostgresqlDatabase(database, **connect)
    try:
        db.connect()
    except OperationalError:
        err('error connecting to %s' % database)
        raise
    return db

def get_columns(conn, table):
    curs = conn.execute('select * from %s limit 1' % table)
    return dict((c.name, reverse_mapping.get(c.type_code, 'UnknownFieldType')) for c in curs.description)

def get_foreign_keys(conn, table):
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
    for row in conn.execute(framing, (table,)):
        fks.append(row)
    return fks

frame = '''from peewee import *

database = PostgresqlDatabase('%s', **%s)

class UnknownFieldType(object):
    pass

class BaseModel(Model):
    class Meta:
        database = database
'''

def introspect(database, **connect):
    conn = get_conn(database, **connect)
    tables = conn.get_tables()

    models = {}
    table_to_model = {}
    table_fks = {}

    # first pass, just raw column names and peewee type
    for table in tables:
        models[table] = get_columns(conn, table)
        table_to_model[table] = tn(table)
        table_fks[table] = get_foreign_keys(conn, table)

    # second pass, convert foreign keys, assign primary keys, and mark
    # explicit column names where they don't match the "pythonic" ones
    col_meta = {}
    for table in tables:
        col_meta[table] = {}
        for column, rel_table, rel_pk in table_fks[table]:
            models[table][column] = 'ForeignKeyField'
            models[rel_table][rel_pk] = 'PrimaryKeyField'
            col_meta[table][column] = {'to': table_to_model[rel_table]}

        for column in models[table]:
            col_meta[table].setdefault(column, {})
            if column != cn(column):
                col_meta[table][column]['db_column'] = "'%s'" % column

    # write generated code to standard out
    print frame % (database, repr(connect))

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

    options, args = parser.parse_args()
    ops = ('host', 'port', 'user', 'password')
    connect = dict((o, getattr(options, o)) for o in ops if getattr(options, o))

    if len(args) < 1:
        print 'error: missing required parameter "database"'
        parser.print_help()
        sys.exit(1)

    database = args[-1]

    introspect(database, **connect)
