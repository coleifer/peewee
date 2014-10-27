try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase
try:
    from playhouse.apsw_ext import APSWDatabase
except ImportError:
    APSWDatabase = None
try:
    from playhouse.berkeleydb import BerkeleyDatabase
except ImportError:
    BerkeleyDatabase = None
try:
    from playhouse.postgres_ext import PostgresqlExtDatabase
except ImportError:
    PostgresqlExtDatabase = None


schemes = {
    'apsw': APSWDatabase,
    'berkeleydb': BerkeleyDatabase,
    'mysql': MySQLDatabase,
    'postgres': PostgresqlDatabase,
    'postgresql': PostgresqlDatabase,
    'postgresext': PostgresqlExtDatabase,
    'postgresqlext': PostgresqlExtDatabase,
    'sqlite': SqliteDatabase,
    'sqliteext': SqliteExtDatabase,
}

def connect(url):
    parsed = urlparse(url)
    database_class = schemes.get(parsed.scheme)
    if database_class is None:
        if database_class in schemes:
            raise RuntimeError('Attempted to use "%s" but a required library '
                               'could not be imported.' % parsed.scheme)
        else:
            raise RuntimeError('Unrecognized or unsupported scheme: "%s".' %
                               parsed.scheme)

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
    if database_class is MySQLDatabase and 'password' in connect_kwargs:
        connect_kwargs['passwd'] = connect_kwargs.pop('password')

    return database_class(**connect_kwargs)
