"""Generate Peewee models for a Kingbase compatibility-mode database.

Run ``python -m playhouse.kingbase_pwiz --mode mysql --database mydb``.
Connection credentials are read from the environment and are never included
in the generated Python module.
"""

import argparse
import contextlib
import io
import os

from peewee import UUIDField
from pwiz import print_models

from playhouse.kingbase_native import KingbaseMySQLDatabase
from playhouse.kingbase_native import KingbaseOracleDatabase
from playhouse.kingbase_reflection import KingbaseIntrospector


def render_models(database, tables=None, schema=None, include_views=False,
                  field_overrides=None):
    """Return importable model source with environment-based connection data."""
    if isinstance(database, KingbaseMySQLDatabase):
        database_class = KingbaseMySQLDatabase
        database_key = 'KINGBASE_DB'
        port_key = 'KINGBASE_MYSQL_PORT'
    elif isinstance(database, KingbaseOracleDatabase):
        database_class = KingbaseOracleDatabase
        database_key = 'KINGBASE_ORACLE_DB'
        port_key = 'KINGBASE_ORACLE_PORT'
    else:
        raise ValueError('Expected a Kingbase MySQL or Oracle database')

    introspector = KingbaseIntrospector.from_database(
        database, schema=schema, field_overrides=field_overrides)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print_models(introspector, tables=tables, include_views=include_views)
    lines = buffer.getvalue().splitlines()
    connection = (
        'database = %s(os.environ[%r], host=os.environ[%r], '
        'port=int(os.environ[%r]), user=os.environ[%r], '
        'password=os.environ[%r])' % (
            database_class.__name__, database_key, 'KINGBASE_HOST', port_key,
            'KINGBASE_USER', 'KINGBASE_PASSWORD'))
    for index, line in enumerate(lines):
        if line.startswith('database = '):
            lines[index] = connection
            break
    else:
        raise RuntimeError('pwiz did not generate a database declaration')
    lines.insert(1, 'import os')
    lines.insert(2, 'from playhouse.kingbase_native import %s' %
                 database_class.__name__)
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('mysql', 'oracle'), required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--schema')
    parser.add_argument('--tables', help='Comma-separated physical table names')
    parser.add_argument('--include-views', action='store_true')
    parser.add_argument('--uuid-column', action='append', default=[],
                        metavar='TABLE.COLUMN',
                        help='Explicitly map a character column to UUIDField')
    args = parser.parse_args(argv)

    port_key = ('KINGBASE_MYSQL_PORT' if args.mode == 'mysql'
                else 'KINGBASE_ORACLE_PORT')
    database_class = (KingbaseMySQLDatabase if args.mode == 'mysql'
                      else KingbaseOracleDatabase)
    required = ('KINGBASE_HOST', port_key, 'KINGBASE_USER', 'KINGBASE_PASSWORD')
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        parser.error('Missing environment variable(s): %s' %
                     ', '.join(missing))
    overrides = {}
    for item in args.uuid_column:
        if '.' not in item:
            parser.error('--uuid-column must be TABLE.COLUMN')
        table, column = item.rsplit('.', 1)
        overrides[table, column] = UUIDField

    database = database_class(
        args.database,
        host=os.environ['KINGBASE_HOST'],
        port=int(os.environ[port_key]),
        user=os.environ['KINGBASE_USER'],
        password=os.environ['KINGBASE_PASSWORD'])
    try:
        database.connect()
        actual = str(database.execute_sql(
            'SHOW database_mode').fetchone()[0]).lower()
        if actual != args.mode:
            parser.error('Connected instance is %s mode, expected %s' %
                         (actual, args.mode))
        print(render_models(
            database,
            tables=args.tables.split(',') if args.tables else None,
            schema=args.schema,
            include_views=args.include_views,
            field_overrides=overrides), end='')
    finally:
        if not database.is_closed():
            database.close()


if __name__ == '__main__':
    main()
