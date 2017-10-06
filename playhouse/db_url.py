try:
    from urlparse import urlparse, parse_qsl
except ImportError:
    from urllib.parse import urlparse, parse_qsl

from peewee import *
from playhouse.pool import PooledMySQLDatabase
from playhouse.pool import PooledPostgresqlDatabase
from playhouse.pool import PooledSqliteDatabase
from playhouse.pool import PooledSqliteExtDatabase
from playhouse.sqlite_ext import SqliteExtDatabase


schemes = {
    'mysql': MySQLDatabase,
    'mysql+pool': PooledMySQLDatabase,
    'postgres': PostgresqlDatabase,
    'postgresql': PostgresqlDatabase,
    'postgres+pool': PooledPostgresqlDatabase,
    'postgresql+pool': PooledPostgresqlDatabase,
    'sqlite': SqliteDatabase,
    'sqliteext': SqliteExtDatabase,
    'sqlite+pool': PooledSqliteDatabase,
    'sqliteext+pool': PooledSqliteExtDatabase,
}

scheme_resolvers = {
}

def register_database(db_class, *names):
    global schemes
    for name in names:
        schemes[name] = db_class

def register_resolver(url_resolver, *names):
    global scheme_resolvers
    for name in names:
        scheme_resolvers[name] = url_resolver

def resolve(parsed):
    # could be made recursive with some safe-guards.
    if parsed.scheme in scheme_resolvers:
        parsed = scheme_resolvers[parsed.scheme](parsed)
    return parsed

def parseresult_to_dict(parsed):

    # urlparse in python 2.6 is broken so query will be empty and instead
    # appended to path complete with '?'
    path_parts = parsed.path[1:].split('?')
    try:
        query = path_parts[1]
    except IndexError:
        query = parsed.query

    connect_kwargs = {'database': path_parts[0]}
    if parsed.username:
        connect_kwargs['user'] = parsed.username
    if parsed.password:
        connect_kwargs['password'] = parsed.password
    if parsed.hostname:
        connect_kwargs['host'] = parsed.hostname
    if parsed.port:
        connect_kwargs['port'] = parsed.port

    # Adjust parameters for MySQL.
    if parsed.scheme == 'mysql' and 'password' in connect_kwargs:
        connect_kwargs['passwd'] = connect_kwargs.pop('password')
    elif 'sqlite' in parsed.scheme and not connect_kwargs['database']:
        connect_kwargs['database'] = ':memory:'

    # Get additional connection args from the query string
    qs_args = parse_qsl(query, keep_blank_values=True)
    for key, value in qs_args:
        if value.lower() == 'false':
            value = False
        elif value.lower() == 'true':
            value = True
        elif value.isdigit():
            value = int(value)
        elif '.' in value and all(p.isdigit() for p in value.split('.', 1)):
            try:
                value = float(value)
            except ValueError:
                pass
        elif value.lower() in ('null', 'none'):
            value = None

        connect_kwargs[key] = value

    return connect_kwargs

def parse(url):
    parsed = resolve(urlparse(url))
    return parseresult_to_dict(parsed)

def connect(url, **connect_params):
    parsed = resolve(urlparse(url))
    connect_kwargs = parseresult_to_dict(parsed)
    connect_kwargs.update(connect_params)
    database_class = schemes.get(parsed.scheme)

    if database_class is None:
        if database_class in schemes:
            raise RuntimeError('Attempted to use "%s" but a required library '
                               'could not be imported.' % parsed.scheme)
        else:
            raise RuntimeError('Unrecognized or unsupported scheme: "%s".' %
                               parsed.scheme)

    return database_class(**connect_kwargs)

# Conditionally register additional databases.
try:
    from playhouse.pool import PooledPostgresqlExtDatabase
except ImportError:
    pass
else:
    register_database(
        PooledPostgresqlExtDatabase,
        'postgresext+pool',
        'postgresqlext+pool')

try:
    from playhouse.apsw_ext import APSWDatabase
except ImportError:
    pass
else:
    register_database(APSWDatabase, 'apsw')

try:
    from playhouse.berkeleydb import BerkeleyDatabase
except ImportError:
    pass
else:
    register_database(BerkeleyDatabase, 'berkeleydb')

try:
    from playhouse.postgres_ext import PostgresqlExtDatabase
except ImportError:
    pass
else:
    register_database(PostgresqlExtDatabase, 'postgresext', 'postgresqlext')

try:
    from playhouse.rds_ext import parse_from_rds
except ImportError:
    pass
else:
    register_resolver(parse_from_rds, 'rds', 'rdsro')
