#!/usr/bin/env python

from optparse import OptionParser
import sys

from peewee import *
from peewee import print_
from playhouse.reflection import *

TEMPLATE = """from peewee import *

database = %s('%s', **%s)

class UnknownField(object):
    pass

class BaseModel(Model):
    class Meta:
        database = database
"""

DATABASE_ALIASES = {
    MySQLDatabase: ['mysql', 'mysqldb'],
    PostgresqlDatabase: ['postgres', 'postgresql'],
    SqliteDatabase: ['sqlite', 'sqlite3'],
}

DATABASE_MAP = dict((value, key)
                    for key in DATABASE_ALIASES
                    for value in DATABASE_ALIASES[key])

def make_introspector(database_type, database_name, **kwargs):
    if database_type not in DATABASE_MAP:
        err('Unrecognized database, must be one of: %s' %
            ', '.join(DATABASE_MAP.keys()))
        sys.exit(1)

    schema = kwargs.pop('schema', None)
    DatabaseClass = DATABASE_MAP[database_type]
    db = DatabaseClass(database_name, **kwargs)
    return Introspector.from_database(db, schema=schema)

def print_models(introspector, tables=None):
    database = introspector.introspect()

    print_(TEMPLATE % (
        introspector.get_database_class().__name__,
        introspector.get_database_name(),
        repr(introspector.get_database_kwargs())))

    def _print_table(table, seen, accum=None):
        accum = accum or []
        foreign_keys = database.foreign_keys[table]
        for foreign_key in foreign_keys:
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

        print_('class %s(BaseModel):' % database.model_names[table])
        columns = database.columns[table]
        for name, column in sorted(columns.items()):
            if name == 'id' and column.field_class in introspector.pk_classes:
                continue

            print_('    %s' % column.get_field())

        print_('')
        print_('    class Meta:')
        print_('        db_table = \'%s\'' % table)
        primary_keys = database.primary_keys[table]
        if len(primary_keys) > 1:
            pk_field_names = sorted([
                field.name for col, field in columns.items()
                if col in primary_keys])
            pk_list = ', '.join("'%s'" % pk for pk in pk_field_names)
            print_('        primary_key = CompositeKey(%s)' % pk_list)
        print_('')

        seen.add(table)

    seen = set()
    for table in sorted(database.model_names.keys()):
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
    print_models(introspector, tables)
