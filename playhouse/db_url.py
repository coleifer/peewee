try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

from peewee import *
from playhouse.pool import PooledMySQLDatabase
from playhouse.pool import PooledPostgresqlDatabase
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
}

def register_database(db_class, *names):
    global schemes
    for name in names:
        schemes[name] = db_class

def parseresult_to_dict(parsed):
    connect_kwargs = {'database': parsed.path[1:]}
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

    return connect_kwargs

def parse(url):
    parsed = urlparse(url)
    return parseresult_to_dict(parsed)

def connect(url, **connect_params):
    parsed = urlparse(url)
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
